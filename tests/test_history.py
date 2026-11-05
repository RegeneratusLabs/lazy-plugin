"""Backfill must find missing binaries/packages and must ignore the model's own bad calls.
The noise filter is the whole test surface: 391 raw error-shaped events collapse to a handful
of real gaps, and getting that wrong makes the feed worthless."""

import importlib.util
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
FIXTURE_SESSION = Path(__file__).resolve().parent / "fixtures" / "sessions" / "20260101_120000_fixture.jsonl"


@pytest.fixture()
def history(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    (tmp_path / "sessions").mkdir(parents=True, exist_ok=True)
    shutil.copy(FIXTURE_SESSION, tmp_path / "sessions" / FIXTURE_SESSION.name)
    spec = importlib.util.spec_from_file_location(f"pc_hist_{id(tmp_path)}", ROOT / "history.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_missing_binary(history):
    assert history.classify('{"output": "bash: weasyprint: command not found"}') == \
        ("cmd_not_found", "cmd:weasyprint")


def test_missing_module(history):
    assert history.classify("ModuleNotFoundError: No module named 'ddgs'") == \
        ("cmd_not_found", "pkg:ddgs")


def test_dotted_module_takes_top_level(history):
    assert history.classify("ModuleNotFoundError: No module named 'youtube_transcript_api.main'") == \
        ("cmd_not_found", "pkg:youtube_transcript_api")


def test_command_not_found_from_other_shell(history):
    assert history.classify("bash: line 3: magick: command not found")[1] == "cmd:magick"


def test_model_errors_are_not_gaps(history):
    for noise in (
        '{"success": false, "error": "Could not find a match for old_string in the file"}',
        '{"error": "path required"}',
        '{"success": false, "error": "Replacement would put memory at 2,780/2,200 chars."}',
        '{"detail": "Not Found"}',
        "File not found: /home/hermes/x.py",
        "{\"success\": false, \"error\": \"Skill 'foo' not found.\"}",
    ):
        assert history.classify(noise) is None, noise


def test_backfill_records_only_real_gaps(history):
    result = history.backfill(days=3650)
    assert result["events_recorded"] == 2  # weasyprint + ddgs
    sigs = {g["signature"] for g in history.CORE.gaps()["top"]}
    assert sigs == {"cmd:weasyprint", "pkg:ddgs"}


def test_backfill_is_idempotent(history):
    history.backfill(days=3650)
    before = history.CORE.gaps()["total"]
    history.backfill(days=3650)
    assert history.CORE.gaps()["total"] == before
    assert history.CORE.gaps()["backfilled"] == 2


def test_backfilled_rows_survive_prune(history):
    history.backfill(days=3650)
    history.CORE.prune_gaps()
    assert history.CORE.gaps()["total"] == 2
