"""lazy-plugin core — catalog, skills, identifiers, matching, gap ledger, report.

Deliberately dependency-free (stdlib only) and transport-agnostic: both the agent half
(``__init__.py``) and the dashboard half (``dashboard/plugin_api.py``) load this same module.
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

CATALOG_URL = "https://nousresearch.github.io/hermes-agent/docs/api/plugin-catalog.json"
CATALOG_TTL_HOURS = 24
FETCH_TIMEOUT = 5.0
# ---------------------------------------------------------------- paths


def hermes_home() -> Path:
    return Path(os.environ.get("HERMES_HOME") or (Path.home() / ".hermes")).expanduser()


def state_dir() -> Path:
    d = hermes_home() / "lazy-plugin"
    d.mkdir(parents=True, exist_ok=True)
    return d


def skills_dir() -> Path:
    override = os.environ.get("LAZY_PLUGIN_SKILLS_DIR")
    return Path(override).expanduser() if override else hermes_home() / "skills"


# ---------------------------------------------------------------- catalog

#: Tokens that are never identity evidence: shells, common binaries, generic English.
def _parse_entries(payload: Any) -> List[dict]:
    if isinstance(payload, dict):
        entries = payload.get("entries")
        if isinstance(entries, list):
            return [e for e in entries if isinstance(e, dict) and e.get("name")]
    if isinstance(payload, list):
        return [e for e in payload if isinstance(e, dict) and e.get("name")]
    return []


def _fetch_remote() -> Optional[dict]:
    try:
        with urllib.request.urlopen(CATALOG_URL, timeout=FETCH_TIMEOUT) as resp:  # noqa: S310
            raw = json.loads(resp.read().decode("utf-8", "replace"))
    except Exception:
        return None
    entries = _parse_entries(raw)
    if not entries:
        return None
    return {"entries": entries, "generated_at": raw.get("generated_at") if isinstance(raw, dict) else None,
            "source": "remote"}


def _fetch_local_yaml() -> Optional[dict]:
    """Optional fallback: a checked-out catalog directory (env override only, never assumed)."""
    d = os.environ.get("LAZY_PLUGIN_CATALOG_DIR")
    if not d:
        return None
    root = Path(d).expanduser()
    if not root.is_dir():
        return None
    try:
        import yaml  # noqa: F401  (available in the Hermes runtime)
    except Exception:
        return None
    entries = []
    for f in sorted(root.glob("*.yaml")):
        try:
            doc = yaml.safe_load(f.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            continue
        if isinstance(doc, dict) and doc.get("name"):
            doc.setdefault("name", f.stem)
            entries.append(doc)
    if not entries:
        return None
    return {"entries": entries, "generated_at": None, "source": "local"}


def load_catalog(force: bool = False) -> dict:
    """Remote → cache → local YAML. Never raises; returns ``source`` describing what happened."""
    cache_path = state_dir() / "catalog-cache.json"
    cached: Optional[dict] = None
    try:
        cached = json.loads(cache_path.read_text(encoding="utf-8"))
    except Exception:
        cached = None

    age_h = None
    if cached and cached.get("fetched_at"):
        age_h = (time.time() - float(cached["fetched_at"])) / 3600.0
        if not force and age_h < CATALOG_TTL_HOURS:
            payload = dict(cached.get("payload") or {})
            payload["source"] = "cache"
            payload["age_hours"] = round(age_h, 2)
            return payload

    fresh = _fetch_remote() or _fetch_local_yaml()
    if fresh:
        payload = {"entries": fresh["entries"], "generated_at": fresh.get("generated_at"),
                   "source": fresh["source"]}
        try:
            cache_path.write_text(json.dumps({"fetched_at": time.time(), "payload": payload}),
                                  encoding="utf-8")
        except Exception:
            pass
        payload["age_hours"] = 0.0
        return payload

    if cached:
        payload = dict(cached.get("payload") or {})
        payload["source"] = "cache(stale)"
        payload["age_hours"] = round(age_h or 0.0, 2)
        return payload
    return {"entries": [], "generated_at": None, "source": "unavailable", "age_hours": None,
            "error": "catalog unavailable: no cache and the fetch failed"}


# Words that carry no identity. Short connectors, plus the vocabulary every plugin description uses,
# so "search" and "report" cannot make two unrelated plugins look like one.
# ---------------------------------------------------------------- skills

_FRONTMATTER = re.compile(r"^---\n(.*?)\n---", re.S)


def _frontmatter(text: str) -> Dict[str, str]:
    m = _FRONTMATTER.search(text)
    out: Dict[str, str] = {}
    if not m:
        return out
    for line in m.group(1).splitlines():
        if ":" in line and not line.startswith((" ", "\t", "#")):
            k, v = line.split(":", 1)
            out[k.strip().lower()] = v.strip().strip("\"'")
    return out


def _body(text: str) -> str:
    m = _FRONTMATTER.search(text)
    return text[m.end():] if m else text


def installed_plugins() -> set:
    """Plugin ids installed for this home (an installed plugin is not a recommendation)."""
    root = hermes_home() / "plugins"
    out = set()
    try:
        for p in root.iterdir():
            if p.is_dir() and not p.name.startswith((".", "_")):
                out.add(p.name.lower())
    except OSError:
        pass
    return out


def load_usage() -> Dict[str, dict]:
    try:
        raw = json.loads((skills_dir() / ".usage.json").read_text(encoding="utf-8"))
    except Exception:
        return {}
    return {k: v for k, v in raw.items() if isinstance(v, dict)} if isinstance(raw, dict) else {}


def scan_skills(root: Optional[Path] = None) -> List[dict]:
    base = Path(root) if root else skills_dir()
    usage = load_usage()
    out: List[dict] = []
    if not base.exists():
        return out
    for md in sorted(base.rglob("SKILL.md")):
        parts = set(md.parts)
        if parts & {".archive", "bundled", "hub", "__pycache__", ".git", "node_modules"}:
            continue
        try:
            text = md.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        fm = _frontmatter(text)
        name = fm.get("name") or md.parent.name
        rec = usage.get(name) or {}
        out.append({
            "name": name,
            "path": str(md),
            "category": md.parent.parent.name if md.parent.parent != base else "",
            "description": fm.get("description", ""),
            "tags": fm.get("tags", ""),
            "body": _body(text),
            "lines": text.count("\n") + 1,
            "agent_created": bool(rec.get("created_by") == "agent"),
            "state": rec.get("state") or "active",
            "use_count": int(rec.get("use_count") or 0),
        })
    return out


# ---------------------------------------------------------------- identifiers

# ---------------------------------------------------------------- gap ledger


# ---------------------------------------------------------------- report

