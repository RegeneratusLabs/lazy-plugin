"""Which installed plugins could actually be submitted to the catalog, and what is missing.

Every check here is mechanical. There is no ranking, no model call, and no attempt to guess what a
plugin "should" be — the catalog's admission rules are a checklist, and this runs it against the
plugins on this machine. A plugin is `ready` only when every hard rule passes.

Rules this maps to (plugin-catalog/README.md):
  1. human-merged PR            -> we can prepare, never push
  2. exact SHA pin              -> reported as a submission step; the repo must exist first
  3. no self-updating code      -> scan for fetch-and-replace-own-files
  5. owner submission           -> repo declared and public
  6. capabilities match reality -> declared provides_* vs what registration reports
  7. install scanner at admission -> `hermes plugins validate`, the same gate CI runs
"""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
from pathlib import Path
from typing import Optional

_HERE = Path(__file__).resolve().parent


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(f"pluginscout_{name}", _HERE / filename)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


_CORE = _load("core", "core.py")

CATALOG_REPO = "https://github.com/NousResearch/hermes-agent"
CATALOG_DIR_IN_REPO = "plugin-catalog"
LICENSE_FILES = ("LICENSE", "LICENSE.md", "LICENSE.txt", "COPYING", "COPYING.md")
REPO_FIELDS = ("repository", "repo", "homepage", "url")

# Rule 3: fetching and replacing its own files. Deliberately narrow — a false positive here is
# reported as a review item, never as a hard blocker.
SELF_UPDATE = re.compile(
    r"(check_for_updates?|self[_-]?update|auto[_-]?update|download_update)", re.I)
# Actual calls, not the words appearing in a comment or a regex literal (which is how this scanner
# first flagged its own source and its own test fixture).
NETWORK_CALL = re.compile(r"\b(urlopen|urlretrieve|requests\.(?:get|post)|httpx\.(?:get|post))\s*\(", re.I)
OWN_FILE_WRITE = re.compile(r"(__file__|PLUGIN_ROOT)[^\n]{0,80}(write_text|write_bytes|open\()[^\n]{0,20}['\"]w", re.I)

CAPABILITY_KEYS = ("provides_tools", "provides_hooks", "provides_middleware",
                   "provides_web_providers", "provides_channels")


def _manifest(path: Path) -> Optional[dict]:
    for candidate in (path / "plugin.yaml", path / "plugin.json"):
        if not candidate.exists():
            continue
        text = candidate.read_text(encoding="utf-8", errors="replace")
        if candidate.suffix == ".json":
            try:
                return json.loads(text)
            except ValueError:
                return None
        try:
            import yaml  # type: ignore
            loaded = yaml.safe_load(text)
            return loaded if isinstance(loaded, dict) else None
        except Exception:
            # yaml is a core dependency of Hermes itself, but a manifest still has to be readable
            # without it: flat scalars, plus `key:` followed by `- item` lines.
            out, pending = {}, None
            for line in text.splitlines():
                item = re.match(r"^\s+-\s*(.+)$", line)
                if item and pending:
                    out[pending].append(item.group(1).strip().strip("'\""))
                    continue
                key = re.match(r"^([a-z_]+):\s*(.*)$", line)
                if not key:
                    pending = None
                    continue
                name, value = key.group(1), key.group(2).strip()
                if value:
                    out[name] = value.strip("'\"")
                    pending = None
                else:
                    out[name] = []
                    pending = name
            return out or None
    return None


def _declared_capabilities(manifest: dict) -> dict:
    caps = {}
    for key in CAPABILITY_KEYS:
        value = manifest.get(key)
        if isinstance(value, list) and value:
            caps[key] = [str(v) for v in value]
    return caps


def _license(path: Path, manifest: dict) -> Optional[str]:
    for name in LICENSE_FILES:
        if (path / name).is_file():
            return name
    declared = manifest.get("license")
    return f"declared: {declared}" if isinstance(declared, str) and declared.strip() else None


def _repo_url(manifest: dict) -> Optional[str]:
    for field in REPO_FIELDS:
        value = manifest.get(field)
        if isinstance(value, str) and value.startswith("http"):
            return value
        if isinstance(value, dict):
            for sub in value.values():
                if isinstance(sub, str) and sub.startswith("http"):
                    return sub
    return None


def _python_files(path: Path) -> list:
    """Shipped code only: rule 3 is about what the plugin runs, not what its tests contain."""
    return [p for p in path.rglob("*.py")
            if "__pycache__" not in p.parts and "tests" not in p.parts
            and not p.name.startswith("test_")][:40]


def self_update_risk(path: Path) -> list:
    """Files that look like they fetch and replace their own code (rule 3)."""
    hits = []
    for file in _python_files(path):
        try:
            text = file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if NETWORK_CALL.search(text) and (OWN_FILE_WRITE.search(text) or SELF_UPDATE.search(text)):
            hits.append(file.name)
    return hits[:5]


def validate(path: Path, timeout: int = 120) -> dict:
    try:
        proc = subprocess.run(["hermes", "plugins", "validate", str(path)],
                              capture_output=True, text=True, timeout=timeout)
        text = (proc.stdout + proc.stderr).strip()
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        failures = [ln for ln in lines if ln.startswith("✗")]
        return {"ok": proc.returncode == 0, "failures": failures, "tail": lines[-4:]}
    except Exception as exc:
        return {"ok": False, "failures": [f"validator not run: {type(exc).__name__}"], "tail": []}


def registered_counts(name: str) -> Optional[dict]:
    """What the plugin actually registers, per `hermes plugins doctor`."""
    try:
        proc = subprocess.run(["hermes", "plugins", "doctor", name],
                              capture_output=True, text=True, timeout=120)
        m = re.search(r"registrations:\s*(\d+)\s*tool\(s\),\s*(\d+)\s*hook\(s\)",
                      proc.stdout + proc.stderr)
        if m:
            return {"tools": int(m.group(1)), "hooks": int(m.group(2))}
    except Exception:
        pass
    return None


def check_plugin(name: str, path: Path, catalog: dict, deep: bool = True) -> dict:
    manifest = _manifest(path) or {}
    declared = _declared_capabilities(manifest)
    entry = catalog.get(name)
    checks, blockers, review = [], [], []

    def add(key: str, ok: bool, detail: str, blocking: bool = True, record: bool = True):
        """blocking=False + record=False means a status line: shown, but never an action item."""
        checks.append({"check": key, "ok": ok, "detail": detail})
        if not ok and record:
            (blockers if blocking else review).append(f"{key}: {detail}")

    add("catalog", entry is None,
        "not in the catalog" if entry is None else f"already listed (tier: {entry.get('tier')})",
        blocking=False, record=False)
    add("manifest", bool(manifest.get("name")),
        "plugin.yaml present" if manifest.get("name") else "no readable plugin.yaml")
    add("version", bool(str(manifest.get("version") or "").strip()),
        str(manifest.get("version") or "version missing"))
    add("description", bool(str(manifest.get("description") or "").strip()),
        "description present" if manifest.get("description") else "description missing")

    licence = _license(path, manifest)
    add("license", bool(licence), licence or "no LICENSE file and none declared")

    repo = _repo_url(manifest)
    add("repository", bool(repo), repo or "no repository URL in the manifest (rule 5 needs one)")

    caps_present = bool(declared)
    add("capabilities declared", caps_present,
        ", ".join(f"{k}={len(v)}" for k, v in declared.items()) if caps_present
        else "no provides_* keys — reviewers cannot see what it registers")

    result = {"name": name, "path": str(path), "in_catalog": entry is not None,
              "tier": (entry or {}).get("tier"), "repo_declared": repo, "license": licence,
              "declared": declared, "checks": checks, "blockers": blockers, "review": review,
              "manifest": {k: manifest.get(k) for k in ("name", "version", "author", "description")
                           if manifest.get(k)}}

    risky = self_update_risk(path)
    if risky:
        review.append(f"self-updater check: review {', '.join(risky)} (rule 3)")
        result["self_update_files"] = risky

    if deep:
        val = validate(path)
        add("validate", val["ok"], "`hermes plugins validate` passed" if val["ok"]
            else (val["failures"][0] if val["failures"] else "validation failed"))
        result["validation"] = val
        counts = registered_counts(name)
        if counts is not None:
            result["registered"] = counts
            declared_tools = len(declared.get("provides_tools") or [])
            if declared_tools and counts["tools"] != declared_tools:
                review.append(f"capability mismatch: declares {declared_tools} tool(s), "
                              f"registers {counts['tools']} (rule 6)")
            declared_hooks = len(declared.get("provides_hooks") or [])
            if declared_hooks and counts["hooks"] != declared_hooks:
                review.append(f"capability mismatch: declares {declared_hooks} hook(s), "
                              f"registers {counts['hooks']} (rule 6)")

    result["ready"] = not blockers
    return result


def _installed_names() -> set:
    try:
        raw = json.loads((_CORE.hermes_home() / "plugins" / ".install-metadata.json").read_text())
        return set(raw) if isinstance(raw, dict) else set()
    except Exception:
        return set()


def prepare(name: str, deep: bool = True) -> dict:
    """Write the catalog entry the PR expects, plus the steps that are still owed."""
    row = next((r for r in audit(deep=deep).get("plugins", []) if r["name"] == name), None)
    if row is None:
        return {"ok": False, "error": f"no installed plugin named {name!r}"}
    if row["in_catalog"]:
        return {"ok": False, "error": f"{name} is already in the catalog (tier: {row['tier']}); "
                                      "a SHA bump is a new PR against the existing entry"}
    outdir = _CORE.state_dir() / "outbox" / name
    (outdir / CATALOG_DIR_IN_REPO).mkdir(parents=True, exist_ok=True)
    manifest = row["manifest"]
    entry = {
        "name": name,
        "repo": row["repo_declared"] or "https://github.com/<you>/<repo>",
        "sha": "<full 40-character commit sha>",
        "version": str(manifest.get("version") or "0.1.0"),
        "title": name.replace("-", " ").replace("_", " ").title(),
        "description": str(manifest.get("description") or "")[:400],
        "maintainer": "<your-github-handle>",
        "tier": "community",
        "category": "tools",
        "docs_url": (row["repo_declared"] or "https://github.com/<you>/<repo>") + "#readme",
        "capabilities": {
            "provides_tools": row["declared"].get("provides_tools", []),
            "provides_hooks": row["declared"].get("provides_hooks", []),
            "provides_middleware": row["declared"].get("provides_middleware", []),
            "requires_env": [],
        },
        "requires_hermes": ">=0.21.6",
    }
    entry_path = outdir / CATALOG_DIR_IN_REPO / f"{name}.yaml"
    entry_path.write_text(json.dumps(entry, indent=2) + "\n", encoding="utf-8")

    blockers = "\n".join(f"- [ ] {b}" for b in row["blockers"]) or "- none"
    review = "\n".join(f"- [ ] {r}" for r in row["review"]) or "- none"
    (outdir / "SUBMISSION.md").write_text(
        f"""# Submitting `{name}`

## Still owed

{blockers}

## Reviewer questions before merge

{review}

## Steps

```bash
# the repo must be public and yours (rule 5)
cd /path/to/{name}
git rev-parse HEAD    # -> paste the full sha into {CATALOG_DIR_IN_REPO}/{name}.yaml
hermes plugins validate /path/to/{name} --install-deps
```

1. Make the repo public, add a LICENSE, declare the repository in `plugin.yaml`.
2. Pin the exact 40-character SHA in `{CATALOG_DIR_IN_REPO}/{name}.yaml`.
3. Fork {CATALOG_REPO}, add that file under `{CATALOG_DIR_IN_REPO}/`, open the PR.
4. Rule 3: no self-updating code. Rule 6: declared capabilities must match what it registers.

Generated from the manifest on this machine. Rules:
{CATALOG_REPO}/blob/main/plugin-catalog/README.md
""", encoding="utf-8")

    return {"ok": True, "name": name, "dir": str(outdir),
            "files": [f"{CATALOG_DIR_IN_REPO}/{name}.yaml", "SUBMISSION.md"],
            "blockers": row["blockers"], "review": row["review"], "ready": row["ready"],
            "validation": row.get("validation")}


def audit(deep: bool = True, plugins_dir: Optional[Path] = None) -> dict:
    """Every installed plugin against the admission rules. Never raises."""
    try:
        root = Path(plugins_dir or (_CORE.hermes_home() / "plugins"))
        try:
            catalog = {str(e.get("name")): e for e in _CORE.load_catalog()["entries"]}
        except Exception:
            catalog = {}
        rows = []
        for child in sorted(root.iterdir()):
            if not child.is_dir() or child.name.startswith("."):
                continue
            looks_like_plugin = (
                (child / "plugin.yaml").exists() or (child / "plugin.json").exists()
                or any(child.glob("*.py")) or any(child.glob("*.js"))
                or child.name in _installed_names())
            if not looks_like_plugin:
                continue
            rows.append(check_plugin(child.name, child, catalog, deep=deep))
        rows.sort(key=lambda r: (r["in_catalog"], not r["ready"], len(r["blockers"]), r["name"]))
        return {"ok": True, "total": len(rows),
                "ready": [r["name"] for r in rows if r["ready"] and not r["in_catalog"]],
                "listed": [r["name"] for r in rows if r["in_catalog"]],
                "blocked": [r["name"] for r in rows if not r["ready"]],
                "catalog_entries": len(catalog), "plugins": rows}
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
