"""Requests the page hands to the agent: written down, picked up once, not replayed forever."""

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture()
def queue():
    spec = importlib.util.spec_from_file_location("queue_mod", ROOT / "queue.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_enqueue_then_pending(queue, tmp_path):
    request = queue.enqueue(tmp_path, "watch gpu prices under six hundred")
    rows = queue.pending(tmp_path)
    assert [row["id"] for row in rows] == [request["id"]]
    assert rows[0]["idea"].startswith("watch gpu")


def test_finish_removes_it(queue, tmp_path):
    request = queue.enqueue(tmp_path, "watch gpu prices")
    assert queue.finish(tmp_path, request["id"]) is True
    assert queue.pending(tmp_path) == []
    assert queue.finish(tmp_path, request["id"]) is False


def test_stale_requests_are_dropped_not_replayed(queue, tmp_path):
    request = queue.enqueue(tmp_path, "watch gpu prices")
    path = next((tmp_path / "lazy-plugin" / "requests").glob("*.json"))
    import json
    import time

    body = json.loads(path.read_text())
    body["created"] = time.time() - 48 * 3600
    path.write_text(json.dumps(body))
    assert queue.pending(tmp_path) == []
    assert not path.exists()


def test_prompt_names_the_tool_and_forbids_empty_builds(queue, tmp_path):
    request = queue.enqueue(tmp_path, "find me lazy cat videos", "skill", "chinese-marketplace-sourcing")
    prompt = queue.as_prompt(queue.pending(tmp_path))
    assert "lazyplugin_create" in prompt
    assert request["id"] in prompt
    assert "ask the user one question" in prompt
