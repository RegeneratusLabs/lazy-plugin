"""One classifier, two data sources.

`command not found` and `No module named` are capability gaps. Everything else that looks like an
error — the model's own malformed calls, its own guessed paths, HTTP 404s from servers it started,
imports of its own repo layout — is noise, and noise in this feed reads as a broken plugin.

Measured on a real profile: ~80,000 tool results contain 490 error-shaped matches, of which ~353
are real after this filter. The filter is the product.
"""

from __future__ import annotations

import re

PATTERNS = (
    ("pkg_missing", re.compile(r"No module named '?([A-Za-z0-9_][A-Za-z0-9_.]*)")),
    ("pkg_missing", re.compile(r"ModuleNotFoundError:\s*(?:No module named )?'?([A-Za-z0-9_][A-Za-z0-9_.]*)")),
    ("cmd_missing", re.compile(r"(?:bash|sh|zsh|dash):\s*(?:line \d+:\s*)?([^\s:]+):\s*command not found", re.I)),
    ("cmd_missing", re.compile(r"Command '([^']+)' not found", re.I)),
    ("cmd_missing", re.compile(r"exec: \"?([^\s\"]+)\"?: executable file not found", re.I)),
    ("cmd_missing", re.compile(r"'([^']+)' is not recognized as an internal or external command", re.I)),
)

NOISE = re.compile(
    r"(old_string|path required|question text is required|memory at \d|"
    r"requires either prompt|invalid argument|missing required|"
    r"detail\\?\"?:\\?\"?not found|404 not found|File not found:|Path not found:|"
    r"Task not found|Skill '[^']*' not found|Job with ID)", re.I)

NOT_A_DEPENDENCY = {
    "tools", "tool", "core", "config", "configs", "utils", "util", "main", "app", "apps", "agent",
    "agents", "cli", "server", "router", "routers", "tests", "test", "src", "lib", "libs",
    "scripts", "script", "models", "model", "schemas", "schema", "plugins", "plugin", "skills",
    "skill", "memory", "prompts", "prompt", "hermes", "hermes_core", "hermes_agent", "gateway",
    "hooks", "handlers", "api", "web", "dashboard", "cron", "session", "sessions", "voice", "tts",
    "stt", "asr", "llm", "chat", "ui", "db", "database", "helpers", "common", "shared", "build",
    "dist", "setup", "conftest", "typing", "types", "abc", "os", "sys", "json", "re", "time",
    "datetime", "pathlib", "subprocess", "logging", "asyncio", "tempfile", "shutil", "argparse",
    "collections", "itertools", "functools", "math", "random", "hashlib", "base64", "csv", "io",
    "uuid", "threading", "sqlite3", "urllib", "http", "socket", "ssl", "email", "html", "xml",
}


def classify(text: str):
    """``("cmd_not_found", "cmd:name" | "pkg:name")`` for a real gap, else None."""
    if not text or NOISE.search(text):
        return None
    for kind, pattern in PATTERNS:
        m = pattern.search(text)
        if not m:
            continue
        token = (m.group(1) or "").strip().strip("\"'`")
        if not token:
            continue
        if kind == "pkg_missing":
            token = token.split(".")[0]
            if token.strip().lower() in NOT_A_DEPENDENCY:
                return None
            prefix = "pkg"
        else:
            token = token.rsplit("/", 1)[-1].strip().lower()
            prefix = "cmd"
        if len(token) < 3:
            continue
        return ("cmd_not_found", f"{prefix}:{token}")
    return None


def content_of(record: dict) -> str:
    """Flatten a tool message/record to the text we classify."""
    import json

    raw = record.get("content")
    text = raw if isinstance(raw, str) else json.dumps(raw or "")
    stripped = text.strip()
    if stripped.startswith("{"):
        try:
            obj = json.loads(stripped)
        except Exception:
            return text
        if isinstance(obj, dict):
            return " ".join(str(obj.get(k) or "") for k in ("output", "error", "message", "detail"))
    return text
