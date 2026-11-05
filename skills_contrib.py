"""Button two: which of the agent's own skills are worth publishing, and what would publishing take?

Screening is deterministic on purpose. A skill is a good community contribution when it is a
procedure (not a memory of Josh's box), when it names no private path/host/account, and when the
catalog does not already answer it. Every verdict cites the exact strings that decided it, so the
user can disagree with line numbers rather than vibes.

`package()` then stages a scrubbed bundle: SKILL.md with personal strings replaced, a README that
credits the author, and CONTRIBUTION.json recording what was redacted.
"""

from __future__ import annotations

import datetime
import importlib.util
import json
import re
from pathlib import Path
from typing import Optional

_HERE = Path(__file__).resolve().parent


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(f"pluginscout_{name}", _HERE / filename)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


_CORE = _load("core", "core.py")

DEFAULT_DAYS = 60
MAX_CANDIDATES = 12
PACKAGE_OUTBOX = "outbox"

# (kind, pattern, placeholder). Weight = how much a hit argues for keeping it private.
PERSONAL = [
    ("path", re.compile(r"/home/[a-z0-9_]+|~/\.hermes/profiles|/Users/[A-Za-z0-9_]+", re.I), "<path>"),
    ("host", re.compile(r"\b(100\.\d{1,3}\.\d{1,3}\.\d{1,3}|optiplex|victus|homelab)\b", re.I), "<host>"),
    ("identity", re.compile(r"\b(josh|joshua|thomson|becca|乔森)\b", re.I), "<name>"),
    ("org", re.compile(r"\b(nutri-?tech|RegeneratusLabs|NTS)\b"), "<org>"),
    ("account", re.compile(r"[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}|\bchat_id\s*[=:]\s*\d{6,}", re.I),
     "<account>"),
    ("secret", re.compile(r"\b(sk-[A-Za-z0-9]{16,}|ghp_[A-Za-z0-9]{20,}|xoxb-[A-Za-z0-9-]{10,})"), "<secret>"),
    ("port", re.compile(r"\b(9119|9120|9130|8447|8449)\b"), "<port>"),
]

WEIGHT = {"secret": 5, "account": 3, "path": 2, "org": 2, "host": 2, "identity": 1, "port": 1}

# A skill that needs the turn loop, a schedule or a UI is a plugin contribution, not a skill one.
PLUGIN_SHAPE = re.compile(
    r"(register_tool|register_hook|register_skill|ctx\.llm|plugin\.yaml|desktop/plugin\.js|"
    r"on_session_end|post_tool_call|register_auxiliary_task)", re.I)

STEPS = re.compile(r"^\s*(?:\d+\.|[-*])\s+\S", re.M)


def _usage() -> dict:
    try:
        return _CORE.load_usage() or {}
    except Exception:
        return {}


def _created(entry: dict) -> Optional[datetime.date]:
    for key in ("created_at", "first_seen_at"):
        raw = (entry or {}).get(key)
        if not raw:
            continue
        try:
            return datetime.datetime.fromisoformat(str(raw).replace("Z", "+00:00")).date()
        except ValueError:
            continue
    return None


def markers(body: str) -> list:
    """Every personal string, with its line number. The evidence, not a score."""
    found = []
    for lineno, line in enumerate(body.splitlines(), 1):
        for kind, pattern, placeholder in PERSONAL:
            for match in pattern.finditer(line):
                found.append({"kind": kind, "text": match.group(0)[:80], "line": lineno,
                              "placeholder": placeholder})
    return found


def verdict(skill: dict, hits: list, catalog_ids: set) -> tuple[str, list]:
    """(verdict, reasons). Deterministic; reasons name what decided it."""
    name = skill.get("name") or ""
    body = skill.get("body") or ""
    reasons = []

    if name.lower() in catalog_ids or name.lower().replace(" ", "-") in catalog_ids:
        return "already_covered", [f"a catalog plugin already ships as '{name}'"]

    weight = sum(WEIGHT.get(h["kind"], 1) for h in hits)
    steps = len(STEPS.findall(body))
    if not skill.get("description"):
        reasons.append("no description in frontmatter — a reader cannot tell when to use it")
    if steps < 3:
        reasons.append(f"only {steps} step-like lines — thin for a published procedure")
    if hits:
        kinds = sorted({h["kind"] for h in hits})
        reasons.append(f"{len(hits)} personal reference(s) across {len(kinds)} kind(s): "
                       + ", ".join(f"{k}×{sum(1 for h in hits if h['kind'] == k)}" for k in kinds))

    if weight >= 8 or len({h['kind'] for h in hits}) >= 4:
        return "private", reasons
    if hits:
        return "scrub", reasons
    if steps < 3 or not skill.get("description"):
        return "thin", reasons
    return "publish", reasons or ["no personal references, real steps, clear description"]


def home_for(skill: dict) -> str:
    return "plugin" if PLUGIN_SHAPE.search(skill.get("body") or "") else "skill"


def candidates(days: int = DEFAULT_DAYS, limit: int = MAX_CANDIDATES) -> dict:
    """Agent-written (or recently added) skills, screened. Newest first, worst verdicts kept."""
    days = max(1, min(3650, int(days)))
    cutoff = datetime.date.today() - datetime.timedelta(days=days)
    usage = _usage()
    try:
        catalog_ids, _meta = _CORE.gate_index(_CORE.load_catalog()["entries"])
    except Exception:
        catalog_ids = set()

    rows, skipped_old, skipped_human = [], 0, 0
    for skill in _CORE.scan_skills():
        entry = usage.get(skill.get("name") or "", {}) or {}
        created = _created(entry)
        agent = bool(skill.get("agent_created"))
        if not agent:
            skipped_human += 1
            continue
        if created and created < cutoff:
            skipped_old += 1
            continue
        hits = markers(skill.get("body") or "")
        state, reasons = verdict(skill, hits, catalog_ids)
        rows.append({
            "name": skill.get("name"),
            "path": skill.get("path"),
            "description": skill.get("description") or "",
            "lines": skill.get("lines") or 0,
            "created": created.isoformat() if created else None,
            "use_count": skill.get("use_count") or 0,
            "verdict": state,
            "reasons": reasons,
            "markers": hits[:12],
            "marker_count": len(hits),
            "contribute_as": home_for(skill),
        })

    order = {"publish": 0, "scrub": 1, "thin": 2, "already_covered": 3, "private": 4}
    rows.sort(key=lambda r: (order.get(r["verdict"], 9), r["created"] or "", -(r["use_count"] or 0)))
    counts = {}
    for row in rows:
        counts[row["verdict"]] = counts.get(row["verdict"], 0) + 1
    return {
        "days": days,
        "total_agent_skills": len(rows),
        "counts": counts,
        "skipped": {"human_written": skipped_human, "older_than_window": skipped_old},
        "candidates": rows[:max(1, min(50, limit))],
    }


def _scrub(text: str) -> tuple[str, int]:
    replaced = 0
    for _kind, pattern, placeholder in PERSONAL:
        text, n = pattern.subn(placeholder, text)
        replaced += n
    return text, replaced


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-") or "skill"


def package(name: str, days: int = DEFAULT_DAYS) -> dict:
    """Stage a submission bundle for one skill. Writes only inside the plugin's own outbox."""
    rows = candidates(days=days, limit=50)["candidates"]
    row = next((r for r in rows if r["name"] == name), None)
    if row is None:
        return {"ok": False, "error": f"no agent-written skill named {name!r} in the last {days} days"}
    if row["verdict"] == "private":
        return {"ok": False, "error": "verdict is private: too much of your environment is baked in "
                                      "to publish safely. Rewrite it as a general procedure first.",
                "reasons": row["reasons"]}

    source = Path(row["path"])
    body = source.read_text(encoding="utf-8", errors="replace")
    scrubbed, count = _scrub(body)
    outdir = _CORE.state_dir() / PACKAGE_OUTBOX / slugify(name)
    outdir.mkdir(parents=True, exist_ok=True)

    (outdir / "SKILL.md").write_text(scrubbed, encoding="utf-8")
    created = row["created"] or datetime.date.today().isoformat()
    readme = f"""# {row['name']}

{row['description'] or 'A Hermes skill.'}

## Use when

{row['description'] or 'See SKILL.md for the trigger conditions.'}

## Install

```bash
mkdir -p ~/.hermes/skills/community
cp -r {slugify(name)} ~/.hermes/skills/community/
```

Hermes picks it up on the next session. No dependencies beyond what SKILL.md lists.

## Provenance

Written by Josh Thomson's Hermes agent ({created}) while working on a real task, then
generalised for sharing. MIT — keep the attribution if you fork it.

{count} environment-specific reference(s) were replaced with placeholders
(`<path>`, `<host>`, `<name>`, `<port>`) during packaging; see CONTRIBUTION.json.
"""
    (outdir / "README.md").write_text(readme, encoding="utf-8")
    (outdir / "CONTRIBUTION.json").write_text(json.dumps({
        "name": row["name"], "contribute_as": row["contribute_as"], "source": str(source),
        "verdict": row["verdict"], "reasons": row["reasons"],
        "redactions": row["markers"], "redaction_count": count,
        "packaged_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "author": "Josh Thomson", "license": "MIT",
    }, indent=1), encoding="utf-8")

    return {"ok": True, "name": row["name"], "dir": str(outdir),
            "files": ["SKILL.md", "README.md", "CONTRIBUTION.json"],
            "redactions": count, "contribute_as": row["contribute_as"]}


def run(days: int = DEFAULT_DAYS, limit: int = MAX_CANDIDATES) -> dict:
    """Everything the panel needs. Never raises."""
    try:
        data = candidates(days=days, limit=limit)
        data["ok"] = True
        data["outbox"] = str(_CORE.state_dir() / PACKAGE_OUTBOX)
        return data
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
