"""The publish gate: a credential in a bundle stops the push, and nothing else does.

The rule this file defends: a plugin built for one person's own Hermes is their business. A repo push
is public and permanent, so that is the only place we refuse.
"""

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def load(name):
    spec = importlib.util.spec_from_file_location(name + "_secrettest", ROOT / f"{name}.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


SECRETS = load("secretscan")
PUBLISH = load("publish")


KEY_SHAPES = [
    'KEY = "sk-proj-AbCdEf1234567890AbCdEf1234567890"',
    'KEY = "sk-ant-api03-AbCdEf1234567890AbCdEf"',
    'KEY = "sk-deadbeef1234567890abcdef12345678"',
    'TOKEN = "ghp_aBcDeFgHiJkLmNoPqRsTuVwXyZ0123456789"',
    'AWS = "AKIAIOSFODNN7EXAMPLE"'.replace("EXAMPLE", "EXAMPL3"),
    'SLACK = "xoxb-1234567890-1234567890123-AbCdEfGhIj"',
    'GOOGLE = "AIzaSyA1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7"',
    'DSN = "postgres://josh:hunter2pass@db.internal/app"',
]


@pytest.mark.parametrize("line", KEY_SHAPES)
def test_credential_shapes_are_caught(line):
    assert SECRETS.scan_text(line, "tools.py"), f"missed: {line}"


@pytest.mark.parametrize("line", [
    'found = os.environ.get("PETBARN_API_KEY")',
    'api_key = "your-key-here"',
    'token = "${TOKEN}"',
    'key = getenv("OPENCODE_KEY")',
    'name = "PETBARN_API_KEY"',
    'description = "Search the catalogue for catnip and return the cheapest delivered option"',
])
def test_benign_lines_are_not_flagged(line):
    assert SECRETS.scan_text(line, "tools.py") == [], f"false positive: {line}"


def test_env_read_is_the_documented_fix():
    """The message must tell them what to do, not just that they failed."""
    findings = SECRETS.scan_text('KEY = "sk-proj-AbCdEf1234567890AbCdEf1234567890"', "tools.py")
    message = SECRETS.describe(findings)
    assert "tools.py:1" in message
    assert "os.environ.get" in message


def test_redact_leaves_no_key_behind():
    text = 'KEY = "sk-proj-AbCdEf1234567890AbCdEf1234567890"'
    assert "sk-proj" not in SECRETS.redact(text)
    assert SECRETS.redact(SECRETS.redact(text)) == SECRETS.redact(text)


def _bundle(tmp_path: Path, tools_src: str) -> Path:
    bundle = tmp_path / "leaky"
    bundle.mkdir()
    (bundle / "plugin.yaml").write_text("name: leaky\nversion: 0.1.0\ndescription: test\n")
    (bundle / "__init__.py").write_text("def register(ctx):\n    pass\n")
    (bundle / "tools.py").write_text(tools_src)
    return bundle


class Recorder:
    """Any command, remembered. If publish refuses first, this stays empty."""

    def __init__(self):
        self.calls = []

    def __call__(self, cmd, cwd=None, timeout=300):
        self.calls.append(" ".join(cmd))
        return "abc1234\n"


def test_publish_refuses_before_touching_any_remote(tmp_path):
    bundle = _bundle(tmp_path, 'KEY = "sk-proj-AbCdEf1234567890AbCdEf1234567890"\n')
    run = Recorder()
    out = PUBLISH.publish(bundle, "leaky", "someone", {"version": "0.1.0"}, run)
    assert out["ok"] is False
    assert out["stage"] == "secrets"
    assert "tools.py:1" in out["error"]
    assert run.calls == [], f"a remote was touched before the gate: {run.calls}"
    assert not (bundle / "plugin-catalog").exists()


def test_clean_bundle_passes_the_gate(tmp_path):
    bundle = _bundle(tmp_path, 'KEY_NAME = "SOME_API_KEY"\nimport os\n'
                               'def go():\n    return os.environ.get(KEY_NAME)\n')
    run = Recorder()
    out = PUBLISH.publish(bundle, "leaky", "someone", {"version": "0.1.0"}, run)
    assert out["stage"] != "secrets", out.get("error")
    steps = {s["step"]: s for s in out["steps"]}
    assert steps["secrets"]["ok"] is True
    assert run.calls, "a clean bundle should proceed to validate/commit"


def test_scan_reads_the_whole_tree_not_just_the_top(tmp_path):
    bundle = _bundle(tmp_path, "x = 1\n")
    nested = bundle / "lib"
    nested.mkdir()
    (nested / "client.py").write_text('K = "sk-proj-AbCdEf1234567890AbCdEf1234567890"\n')
    found = SECRETS.scan_bundle(bundle)["findings"]
    assert any(f["where"] == "lib/client.py" for f in found)
