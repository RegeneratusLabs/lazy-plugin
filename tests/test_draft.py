"""The model writes the spec; a bad spec must never reach the filesystem."""

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

SPEC_TEXT = """{"name": "gpu-price-watch", "title": "GPU Price Watch",
 "description": "Watch GPU listing pages for prices under a threshold and report matches.",
 "category": "tools", "hooks": ["on_session_end"],
 "tools": [{"name": "check_prices", "description": "Fetch the listing page and filter.",
            "kind": "http", "params": {"max_price": "price ceiling"},
             "target": "https://api.example.com/prices", "behaviour": "GET the prices endpoint"}]}"""


class Result:
    def __init__(self, text, parsed=None, model="deepseek-flash", tokens=800):
        self.text = text
        self.parsed = parsed
        self.model = model
        self.usage = type("U", (), {"total_tokens": tokens})()


class StructuredLlm:
    def complete_structured(self, **kwargs):
        return Result(SPEC_TEXT, parsed=None)

    def complete(self, **kwargs):
        raise AssertionError("structured lane should have been used")


class ChatOnlyLlm:
    def complete_structured(self, **kwargs):
        raise RuntimeError("400 this feature is not yet supported")

    def complete(self, **kwargs):
        return Result("Here you go:\n```json\n" + SPEC_TEXT + "\n```")


class GarbageLlm:
    def complete_structured(self, **kwargs):
        raise RuntimeError("nope")

    def complete(self, **kwargs):
        return Result("I'm afraid I can't do that.")


class BadSpecLlm:
    def complete_structured(self, **kwargs):
        return Result('{"name": "Bad Name!", "description": "x", "tools": []}')


@pytest.fixture()
def creator(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    spec = importlib.util.spec_from_file_location(f"cr_{id(tmp_path)}", ROOT / "creator.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.validate_plugin = lambda path, timeout=180: {"ok": True, "failures": [], "tail": ["passed"]}
    return mod


def test_structured_lane_yields_a_valid_spec(creator):
    out = creator.draft_spec("watch gpu prices under a threshold", StructuredLlm())
    assert out["ok"] is True and out["stage"] == "drafted"
    assert out["spec"]["tools"][0]["kind"] == "http"
    assert out["meta"]["lane"] == "structured"


def test_chat_fallback_handles_a_code_fence(creator):
    out = creator.draft_spec("watch gpu prices", ChatOnlyLlm())
    assert out["ok"] is True
    assert out["meta"]["lane"] == "chat"
    assert "structured_error" in out["meta"]


def test_model_returning_prose_is_reported_not_written(creator):
    out = creator.draft_spec("watch gpu prices", GarbageLlm())
    assert out["ok"] is False and out["stage"] == "parse"
    assert creator.create(out.get("spec") or {})["ok"] is False


def test_invalid_spec_from_the_model_is_refused_before_writing(creator, tmp_path):
    out = creator.draft_spec("watch gpu prices", BadSpecLlm())
    assert out["ok"] is False and out["stage"] == "spec"
    assert any("name" in p or "description" in p for p in out["problems"])
    assert not (tmp_path / "created").exists()


def test_short_idea_never_calls_the_model(creator):
    class Exploding:
        def complete_structured(self, **kwargs):
            raise AssertionError("should not be called")

    out = creator.draft_spec("hi", Exploding())
    assert out["ok"] is False and out["stage"] == "input"


def test_no_model_is_stated_plainly(creator):
    out = creator.draft_spec("watch gpu prices under a threshold", None)
    assert out["ok"] is False and out["stage"] == "llm"


def test_context_is_passed_through(creator):
    seen = {}

    class Capture:
        def complete_structured(self, **kwargs):
            seen["payload"] = kwargs["input"][0]["text"]
            return Result(SPEC_TEXT)

    creator.draft_spec("turn this skill into a plugin", Capture(), context="SKILL.md says: do X then Y")
    assert "SKILL.md says" in seen["payload"]
