"""Does anything in this bundle look like a live credential?

Publish is the boundary. A plugin built for one person's own Hermes is their business — a key in a
local file harms nobody but them, and blocking the build would be nannying. A repo push is public and
effectively permanent, so that is where this runs, and there it stops the push rather than warning.

Shapes, not opinions, and no model: the point is that the same bundle always gets the same answer.

Why this exists at all: `hermes plugins validate` has a guard, but it knows `ghp_` and `AKIA` and calls
`sk-`, `sk-ant-` and `xoxb-` *safe* (measured). Most API keys in this pipeline are `sk-` shaped, so the
host guard's blind side is precisely where the real risk sits.
"""
from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Iterable, List

# Values that are obviously placeholders rather than credentials. Checked against the whole match.
PLACEHOLDER = re.compile(
    r"(?i)(your[-_ ]?(key|token|secret)|example|sample|dummy|placeholder|changeme|replace[-_ ]?me"
    r"|redacted|<[^>]*>|\$\{[^}]*\}|x{6,}|\*{3,}|\.{3,}|env\.get|os\.environ|getenv)"
)

# Bare env var names: "PETBARN_API_KEY" is a name, not a value.
ENV_NAME = re.compile(r"^[A-Z][A-Z0-9_]{3,}$")

PATTERNS: List[tuple[str, re.Pattern, str]] = [
    ("anthropic key", re.compile(r"sk-ant-[A-Za-z0-9_-]{16,}"), "sk-ant-…"),
    ("openai-style key", re.compile(r"sk-[A-Za-z0-9_-]{16,}"), "sk-…"),
    ("github token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}"), "ghp_…"),
    ("aws access key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"), "AKIA…"),
    ("slack token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}"), "xoxb-…"),
    ("google api key", re.compile(r"\bAIza[0-9A-Za-z_-]{30,}"), "AIza…"),
    ("json web token", re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{4,}"), "eyJ…"),
    ("private key block", re.compile(r"-----BEGIN [A-Z ]{0,20}PRIVATE KEY-----"), "PEM block"),
    ("connection string", re.compile(r"\b(?:postgres|postgresql|mysql|mariadb|mongodb(?:\+srv)?|redis|amqp)://[^\s:@/]{1,64}:[^\s@/]{3,64}@"), "scheme://user:…@"),
    ("bearer header", re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._-]{20,}"), "Bearer …"),
]

# name = "long opaque value" — the shape a model writes when it hardcodes a key.
ASSIGNMENT = re.compile(
    r"""(?ix)
    \b(api[_-]?key|apikey|secret|token|password|passwd|access[_-]?key|client[_-]?secret)\b
    \s*[:=]\s*
    (["'])(?P<value>[^"'\n]{16,200})\2
    """
)

TEXT_SUFFIXES = {".py", ".js", ".mjs", ".ts", ".json", ".yaml", ".yml", ".md", ".txt", ".toml",
                 ".cfg", ".ini", ".sh", ".env", ".html", ".css"}
SKIP_DIRS = {".git", "__pycache__", ".venv", "node_modules", ".pytest_cache", ".mypy_cache"}


def _shannon(text: str) -> float:
    if not text:
        return 0.0
    counts = {}
    for ch in text:
        counts[ch] = counts.get(ch, 0) + 1
    return -sum((n / len(text)) * math.log2(n / len(text)) for n in counts.values())


def _worth_reading(value: str) -> bool:
    """Reject the things that look like keys but cannot be: names, placeholders, prose."""
    if PLACEHOLDER.search(value) or ENV_NAME.match(value):
        return False
    if len(set(value)) < 8:                     # "aaaaaaaaaaaaaaa1" is nobody's key
        return False
    has_digit = any(ch.isdigit() for ch in value)
    has_alpha = any(ch.isalpha() for ch in value)
    if not (has_digit and has_alpha):
        return False
    return _shannon(value) >= 3.0               # measured: real keys ~3.6+, prose ~4.2 but no digits


def scan_text(text: str, where: str) -> List[dict]:
    findings: List[dict] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        if "noqa: secrets" in line or "pragma: allowlist secret" in line:
            continue
        for kind, pattern, shape in PATTERNS:
            match = pattern.search(line)
            if not match:
                continue
            if PLACEHOLDER.search(match.group(0)):
                continue
            findings.append({"where": where, "line": lineno, "kind": kind, "shape": shape})
            break
        else:
            match = ASSIGNMENT.search(line)
            if match and _worth_reading(match.group("value")):
                findings.append({"where": where, "line": lineno, "kind": "hardcoded credential",
                                 "shape": f"{match.group(1)} = …"})
    return findings


def scan_bundle(bundle: Path) -> dict:
    """Every text file that would be pushed. Stops at the first finding per line, not per file."""
    bundle = Path(bundle)
    findings: List[dict] = []
    scanned = 0
    if not bundle.is_dir():
        return {"ok": False, "findings": [], "files_scanned": 0, "error": f"no bundle at {bundle}"}
    for path in sorted(bundle.rglob("*")):
        if not path.is_file():
            continue
        if set(path.relative_to(bundle).parts) & SKIP_DIRS:
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES and path.name not in (".env", "Dockerfile"):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        scanned += 1
        findings.extend(scan_text(text, str(path.relative_to(bundle))))
    return {"ok": not findings, "findings": findings, "files_scanned": scanned}


def describe(findings: Iterable[dict]) -> str:
    """One plain sentence a person can act on: what, where, and what to do instead."""
    items = list(findings)
    if not items:
        return "nothing key-shaped in the bundle"
    first = items[0]
    rest = f" (+{len(items) - 1} more)" if len(items) > 1 else ""
    return (f"{first['kind']} at {first['where']}:{first['line']} — {first['shape']}{rest}. "
            "A public repo is permanent: read it from env (os.environ.get) and declare it in "
            "requires_env instead.")


def redact(text: str) -> str:
    """For echoes and logs. Never used for storage — the bundle is the source of truth."""
    for _, pattern, _shape in PATTERNS:
        text = pattern.sub("[redacted]", text)
    return ASSIGNMENT.sub(lambda m: f"{m.group(1)} = \"[redacted]\"", text)
