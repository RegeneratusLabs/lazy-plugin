"""The questionnaire path: deterministic, offline, and it must always produce a valid spec."""

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture()
def creator(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    spec = importlib.util.spec_from_file_location(f"cr_{id(tmp_path)}", ROOT / "creator.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.validate_plugin = lambda path, timeout=180: {"ok": True, "failures": [], "tail": ["passed"]}
    return mod


BASE = {"purpose": "Watch GPU prices and tell me when one drops under 600 dollars",
        "action": "fetch a URL", "target": "https://example.com/deals.json",
        "returns": "the cheapest listing with its price and link",
        "trigger": "when I ask", "secret": "", "category": "tools"}


def test_answers_produce_a_spec_that_validates(creator):
    out = creator.spec_from_answers(BASE)
    assert out["ok"] is True
    spec = out["spec"]
    assert spec["name"] == "watch-gpu-prices-and-tell"
    assert spec["tools"][0]["kind"] == "http"
    assert "cheapest listing" in spec["tools"][0]["description"]
    assert spec["hooks"] == []
    assert out["meta"]["lane"] == "questionnaire"


def test_kind_follows_the_answer(creator):
    assert creator.spec_from_answers({**BASE, "action": "run a command"})["spec"]["tools"][0]["kind"] == "command"
    assert creator.spec_from_answers({**BASE, "action": "read or write a file"})["spec"]["tools"][0]["kind"] == "file"
    assert creator.spec_from_answers({**BASE, "action": "just scaffold it"})["spec"]["tools"][0]["kind"] == "stub"


def test_secret_and_trigger_are_carried(creator):
    spec = creator.spec_from_answers({
        **BASE, "secret": "my api key", "trigger": "after every session"})["spec"]
    assert spec["tools"][0]["requires_env"] == ["MY_API_KEY"]
    assert spec["hooks"] == ["on_session_end"]


def test_a_too_short_purpose_is_refused(creator):
    out = creator.spec_from_answers({**BASE, "purpose": "prices"})
    assert out["ok"] is False and out["stage"] == "input"


def test_answers_never_need_a_model(creator, tmp_path):
    """The whole point: this path works on a profile that cannot read a provider key."""
    out = creator.spec_from_answers(BASE)
    written = creator.create(out["spec"], outbox=tmp_path / "created")
    assert written["ok"] is True
    assert (tmp_path / "created" / out["spec"]["name"] / "plugin.yaml").exists()
