"""lazy-plugin core — catalog, skills, identifiers, matching, gap ledger, report.

Deliberately dependency-free (stdlib only) and transport-agnostic: both the agent half
(``__init__.py``) and the dashboard half (``dashboard/plugin_api.py``) load this same module.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import time
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

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


def gate_index(entries: Iterable[dict]) -> Tuple[Dict[str, set], Dict[str, dict]]:
    """``identifier -> {plugin names}`` from entry name, provides_tools and repo basename only."""
    index: Dict[str, set] = defaultdict(set)
    meta: Dict[str, dict] = {}
    for e in entries:
        name = e.get("name") or ""
        meta[name] = e
        caps = e.get("capabilities") or {}
        candidates = [name]
        candidates += list(caps.get("provides_tools") or [])
        m = re.search(r"github\.com/[^/]+/([^/#?]+)", e.get("repo") or "")
        if m:
            candidates.append(m.group(1))
        for raw in candidates:
            key = _clean_key(str(raw))
            if key:
                index[key].add(name)
                index.setdefault(key.replace("_", "-"), set()).add(name)
    return dict(index), meta


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


def skill_identifiers(body: str) -> Dict[str, set]:
    """Concrete identifiers a skill drives — never prose words."""
    cmds: set = set()
    pkgs: set = set()
    hosts: set = set()
    envs: set = set()

    for block in re.findall(r"```[a-zA-Z0-9_-]*\n(.*?)```", body, re.S):
        for raw in block.splitlines():
            line = raw.strip().lstrip("$> ").strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            head = parts[0].strip("`'\"()[]{}|;&<>,").lower()
            if not re.fullmatch(r"[a-z][a-z0-9_.+-]{2,}", head):
                continue
            if head in BLOCKED or len(parts) < 2:
                continue
            if any(c in head for c in "-._+") or len(head) >= 6:
                key = _clean_key(head)
                if key:
                    cmds.add(key)

    for rx in _PKG_PATTERNS:
        for m in re.finditer(rx, body):
            pkg = m.group(1).split("/")[0].split("@")[0].strip(".-_").lower()
            key = _clean_key(pkg)
            if key:
                pkgs.add(key)

    for m in re.finditer(r"https?://([a-z0-9.-]+\.[a-z]{2,})", body, re.I):
        for label in m.group(1).lower().split(".")[:-1]:
            if label in HOST_NOISE:
                continue
            key = _clean_key(label)
            if key:
                hosts.add(key)

    for m in re.finditer(r"\b([A-Z][A-Z0-9]*(?:_[A-Z0-9]+){1,5})\b", body):
        name = m.group(1)
        if 8 <= len(name) <= 48 and name.endswith(("_API_KEY", "_TOKEN", "_SECRET", "_KEY", "_ID")):
            envs.add(name)

    return {"commands": cmds, "packages": pkgs, "hosts": hosts, "env": envs}


def match_skill(skill: dict, index: Dict[str, set]) -> List[dict]:
    ids = skill_identifiers(skill.get("body") or "")
    hits: Dict[str, set] = defaultdict(set)
    for kind, values in ids.items():
        for value in values:
            for plugin in index.get(value, ()):  # exact identifier identity only
                hits[plugin].add(f"{kind}:{value}")
    out = [{"plugin": p, "ids": sorted(v), "count": len(v)} for p, v in hits.items()]
    out.sort(key=lambda h: (-h["count"], h["plugin"]))
    return out


# ---------------------------------------------------------------- gap ledger


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(state_dir() / "ledger.db", timeout=10)
    conn.execute("""CREATE TABLE IF NOT EXISTS gaps (
        id TEXT PRIMARY KEY, kind TEXT NOT NULL, signature TEXT NOT NULL,
        tool TEXT, snippet TEXT, session_id TEXT, ts REAL NOT NULL, seen INTEGER DEFAULT 1,
        source TEXT DEFAULT 'live')""")
    try:  # migrate a ledger written before `source` existed
        cols = {r[1] for r in conn.execute("PRAGMA table_info(gaps)")}
        if "source" not in cols:
            conn.execute("ALTER TABLE gaps ADD COLUMN source TEXT DEFAULT 'live'")
    except Exception:
        pass
    conn.execute("CREATE INDEX IF NOT EXISTS gaps_sig ON gaps(signature)")
    return conn


def record_gap(kind: str, signature: str, *, tool: str = "", snippet: str = "",
               session_id: str = "", source: str = "live", ts: Optional[float] = None) -> bool:
    import hashlib

    signature = (signature or "").strip()[:120]
    if not signature:
        return False
    gid = hashlib.sha1(f"{kind}|{signature}|{session_id}".encode("utf-8")).hexdigest()[:16]
    when = float(ts) if ts else time.time()
    with _db() as conn:
        conn.execute(
            """INSERT INTO gaps (id, kind, signature, tool, snippet, session_id, ts, seen, source)
               VALUES (?,?,?,?,?,?,?,1,?)
               ON CONFLICT(id) DO UPDATE SET seen = seen + 1, ts = MAX(ts, excluded.ts)""",
            (gid, kind, signature, tool[:80], snippet[:120], session_id[:64], when, source))
    return True


def gaps(limit: int = 20) -> dict:
    """Aggregated by signature across sessions: one row per thing you reached for and lacked."""
    try:
        with _db() as conn:
            rows = conn.execute(
                """SELECT kind, signature, MAX(tool), MAX(snippet), SUM(seen), MAX(ts),
                          MAX(source), COUNT(*) AS sessions
                   FROM gaps GROUP BY signature
                   ORDER BY SUM(seen) DESC, MAX(ts) DESC LIMIT ?""", (max(1, limit),)).fetchall()
            total = conn.execute("SELECT COUNT(DISTINCT signature) FROM gaps").fetchone()[0]
            backfilled = conn.execute(
                "SELECT COUNT(DISTINCT signature) FROM gaps WHERE source = 'backfill'"
            ).fetchone()[0]
            events = conn.execute("SELECT SUM(seen) FROM gaps").fetchone()[0] or 0
    except Exception as exc:  # pragma: no cover - defensive
        return {"total": 0, "top": [], "error": str(exc)}
    now = time.time()
    return {"total": total, "events": events, "backfilled": backfilled, "top": [
        {"kind": r[0], "signature": r[1], "tool": r[2], "snippet": r[3], "seen": r[4],
         "age_hours": round((now - r[5]) / 3600.0, 1), "source": r[6] or "live",
         "sessions": r[7]} for r in rows]}


def prune_gaps() -> None:
    """Live rows age out; mined history is not recent noise and only loses to the row cap."""
    try:
        with _db() as conn:
            cutoff = time.time() - GAP_RETENTION_DAYS * 86400
            conn.execute("DELETE FROM gaps WHERE ts < ? AND source = 'live'", (cutoff,))
            conn.execute(
                "DELETE FROM gaps WHERE id NOT IN "
                "(SELECT id FROM gaps ORDER BY ts DESC LIMIT ?)", (GAP_MAX_ROWS,))
    except Exception:
        pass


def record_gaps_bulk(rows) -> int:
    """Same upsert as record_gap, one connection. 428 events took 56s one-at-a-time; this is <1s."""
    import hashlib

    prepared = []
    for kind, signature, tool, snippet, session_id, ts, source in rows:
        sig = (signature or "").strip()[:120]
        if not sig:
            continue
        gid = hashlib.sha1(f"{kind}|{sig}|{(session_id or '')}".encode("utf-8")).hexdigest()[:16]
        prepared.append((gid, kind, sig, (tool or "")[:80], (snippet or "")[:120],
                         (session_id or "")[:64], float(ts) if ts else time.time(), source))
    if not prepared:
        return 0
    with _db() as conn:
        conn.executemany(
            """INSERT INTO gaps (id, kind, signature, tool, snippet, session_id, ts, seen, source)
               VALUES (?,?,?,?,?,?,?,1,?)
               ON CONFLICT(id) DO UPDATE SET seen = seen + 1, ts = MAX(ts, excluded.ts)""",
            prepared)
    return len(prepared)


def clear_mined() -> int:
    """Mined history is one dataset: re-mining from either source replaces it, never stacks."""
    try:
        with _db() as conn:
            n = conn.execute("SELECT COUNT(*) FROM gaps WHERE source IN ('backfill','statedb')").fetchone()[0]
            conn.execute("DELETE FROM gaps WHERE source IN ('backfill','statedb')")
            return int(n or 0)
    except Exception:
        return 0


def field(days: int = 140, rows_by_weekday: bool = True) -> dict:
    """Per-day gap counts for the heatmap: real event times, zero-filled, newest day last."""
    import datetime as _dt

    days = max(7, min(730, days))
    today = _dt.date.today()
    start = today - _dt.timedelta(days=days - 1)
    try:
        with _db() as conn:
            rows = conn.execute(
                "SELECT ts, seen FROM gaps WHERE ts >= ?", (time.mktime(start.timetuple()),)).fetchall()
    except Exception:
        rows = []

    counts: Dict[str, int] = defaultdict(int)
    for ts, seen in rows:
        try:
            day = _dt.datetime.fromtimestamp(float(ts)).date()
        except Exception:
            continue
        if day < start:
            continue
        counts[day.isoformat()] += int(seen or 1)

    cells = []
    for i in range(days):
        day = start + _dt.timedelta(days=i)
        cells.append({"date": day.isoformat(), "count": counts.get(day.isoformat(), 0),
                      "weekday": day.weekday()})
    return {"start": start.isoformat(), "end": today.isoformat(), "days": days,
            "cells": cells,
            "active_days": sum(1 for c in cells if c["count"]),
            "total": sum(c["count"] for c in cells),
            "max": max((c["count"] for c in cells), default=0)}


def sources() -> dict:
    """Where the recorded gaps came from, so the UI can label mined history as mined."""
    out: Dict[str, int] = {}
    try:
        with _db() as conn:
            for source, n in conn.execute(
                    "SELECT COALESCE(source,'live'), COUNT(DISTINCT signature) FROM gaps GROUP BY 1"):
                out[source or "live"] = n
    except Exception:
        pass
    return out


# ---------------------------------------------------------------- report


def build_report(format: str = "summary", min_match: int = 1) -> dict:
    catalog = load_catalog()
    index, meta = gate_index(catalog["entries"])
    skills = scan_skills()
    installed = installed_plugins()

    matches = []
    for s in skills:
        hits = match_skill(s, index)
        hits = [h for h in hits if h["count"] >= min_match]
        if not hits:
            continue
        best = hits[0]
        entry = meta.get(best["plugin"]) or {}
        caps = entry.get("capabilities") or {}
        is_installed = best["plugin"].lower() in installed
        matches.append({
            "skill": s["name"],
            "plugin": best["plugin"],
            "tier": entry.get("tier") or "",
            "category": entry.get("category") or "",
            "ids": best["ids"][:6],
            "runners_up": [h["plugin"] for h in hits[1:3]],
            "lines": s["lines"],
            "agent_created": s["agent_created"],
            "use_count": s["use_count"],
            "state": s["state"],
            "needs_env": [x.get("name") if isinstance(x, dict) else x
                          for x in (caps.get("requires_env") or [])],
            "installed": is_installed,
            "install": "already installed" if is_installed else f"hermes plugins install {best['plugin']}",
        })
    matches.sort(key=lambda m: (-m["lines"], m["skill"]))

    gap_data = gaps(limit=20)

    # A gap becomes actionable when the identifier the agent lacked names a catalog plugin or tool.
    answers = []
    for g in gap_data.get("top", []):
        ident = g["signature"].split(":", 1)[-1]
        candidates = sorted(index.get(ident, ())) or sorted(index.get(ident.replace("_", "-"), ()))
        if not candidates:
            continue
        fresh = [p for p in candidates if p.lower() not in installed]
        plugin = fresh[0] if fresh else candidates[0]
        is_installed = plugin.lower() in installed
        answers.append({**g, "plugin": plugin, "installed": is_installed,
                        "install": "already installed" if is_installed
                                   else f"hermes plugins install {plugin}"})

    headline = {
        "matched_skills": len(matches),
        "total_skills": len(skills),
        "skill_lines": sum(m["lines"] for m in matches),
        "recommendable": sum(1 for m in matches if not m["installed"]),
        "gaps": gap_data.get("total", 0),
        "gap_answers": len(answers),
    }
    report = {
        "headline": headline,
        "catalog": {"entries": len(catalog["entries"]), "generated_at": catalog.get("generated_at"),
                    "source": catalog.get("source"), "age_hours": catalog.get("age_hours")},
        "skills": {"total": len(skills), "dir": str(skills_dir())},
        "matches": matches,
        "gap_answers": answers,
        "gaps": gap_data,
        "field": field(140),
        "sources": sources(),
    }
    if format == "summary":
        report["matches"] = matches[:5]
        report["gap_answers"] = answers[:5]
    return report


def summary_text(report: Optional[dict] = None) -> str:
    r = report or build_report("summary")
    h = r["headline"]
    gaps_info = r["gaps"]
    lines = [
        f"{h['gaps']} capability gaps recorded from real tool calls "
        f"({gaps_info.get('events', h['gaps'])} occurrences, "
        f"{gaps_info.get('backfilled', 0)} found by mining session history)",
    ]
    for a in r.get("gap_answers", [])[:3]:
        lines.append(f"  gap {a['signature']} ×{a['seen']} -> {a['plugin']} · {a['install']}")
    for g in (gaps_info.get("top") or [])[:5]:
        if g["signature"] not in {a["signature"] for a in r.get("gap_answers", [])}:
            lines.append(f"  gap {g['signature']} ×{g['seen']} ({g['source']})")
    lines.append(
        f"{h['matched_skills']} of {h['total_skills']} skills also overlap a catalog plugin "
        f"({h['skill_lines']} lines, {h.get('recommendable', 0)} not installed; "
        f"{r['catalog']['entries']} catalog entries, catalog {r['catalog']['source']})")
    for m in r["matches"][:5]:
        lines.append(f"  {m['skill']} -> {m['plugin']} ({', '.join(m['ids'][:3])}) · {m['install']}")
    return "\n".join(lines)
