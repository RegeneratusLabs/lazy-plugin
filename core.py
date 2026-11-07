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
GAP_RETENTION_DAYS = 30
GAP_MAX_ROWS = 5000

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
BLOCKED = set("""python python3 node npm npx pip pip3 uv cargo go git curl wget bash sh zsh
find grep sed awk jq tar zip unzip ssh scp rsync docker podman make cmake ffmpeg ffprobe ls cd cat
echo printf chmod chown mkdir rm cp mv touch head tail sort uniq wc xargs tee kill ps top df du
open code vim nano brew apt apt-get dnf yum pacman systemctl service launchctl pandoc sqlite3 psql
mysql openssl gpg hermes sudo env export source test true false sleep date which file stat ln
basename mktemp realpath osascript powershell cmd pwsh yarn pnpm bun deno php ruby perl java
gradle mvn dotnet swift xcodebuild adb fastboot tmux screen watch nohup timeout ip ifconfig
nmap nc socat dig nslookup ping traceroute crontab at journalctl dmesg lsof
skills skill token cost data health context self session provider business terminal length mock
diff drag debug free image images video audio music sound text read write event events feed mode
plan user users audit cron auth node nodes kernel series rooms alert alerts owners owner workers
worker repl ingest adapter submit billing companion wake diagnose optimize rates rate holdings
purchase posture broker graphics ascii github gitlab git google microsoft amazon aws azure
cloudflare openai anthropic claude gpt news best tool tools suite platform engine runner helper
utils utility generic common core base main app apps web net api service services system systems
files document docs playlist playlists library content source sources search query index store
cache queue task tasks jobs work flow flows step steps guide setup install update produce output
""".split())

HOST_NOISE = {
    "www", "api", "app", "docs", "cdn", "static", "help", "support", "auth", "login", "portal",
    "admin", "dashboard", "raw", "objects", "user-images", "github", "gitlab", "google", "amazon",
}


def _clean_key(key: str) -> Optional[str]:
    k = (key or "").strip().lower()
    if len(k) < 5 or k in BLOCKED or k.isdigit():
        return None
    if not re.fullmatch(r"[a-z0-9][a-z0-9._+-]*", k):
        return None
    return k


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
_STOP = set("""a an the and or of for to in on with from by as at is are be it its this that these those
you your we our they them their i me my can will would should could may might must do does did done
plugin plugins hermes agent agents tool tools build builds builder make makes made get gets got fetch
fetches return returns returned result results data api call calls called use uses used using into
over under more most less least new old one two three first last next best top also just only very
search searches find finds finding look looks list lists show shows give gives given take takes
from about across between during before after while when where which who whom what how why all any
each every some such than then there here not no yes""".split())


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

_PKG_PATTERNS = (
    r"pip3?\s+install\s+(?:-U\s+)?(?:-e\s+)?([A-Za-z0-9_.\-]+)",
    r"npm\s+i(?:nstall)?\s+(?:-g\s+)?([@A-Za-z0-9_./\-]+)",
    r"brew\s+install\s+([A-Za-z0-9_./\-]+)",
    r"(?:apt|apt-get|dnf)\s+install\s+(?:-y\s+)?([A-Za-z0-9_.\-]+)",
    r"uv\s+(?:pip\s+)?(?:add|install|tool\s+install)\s+([A-Za-z0-9_.\-]+)",
    r"cargo\s+install\s+([A-Za-z0-9_.\-]+)",
)


# ---------------------------------------------------------------- gap ledger


# ---------------------------------------------------------------- report

