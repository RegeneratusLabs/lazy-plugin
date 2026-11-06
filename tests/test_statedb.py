"""state.db mining: the fallback path must work, and the field must group by real event time."""

import datetime
import importlib.util
import sqlite3
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(f"pc_{name}_{id(object())}", ROOT / filename)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def statedb(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.setenv("LAZY_PLUGIN_SKILLS_DIR", str(tmp_path / "skills"))
    db = tmp_path / "state.db"
    conn = sqlite3.connect(db)
    conn.execute("""CREATE TABLE messages (id INTEGER PRIMARY KEY, session_id TEXT, role TEXT,
                    content TEXT, tool_name TEXT, timestamp REAL)""")
    # Noon, not "an hour ago": at 00:30 local an hour ago is yesterday, and this test would fail
    # once a day for reasons that have nothing to do with the code under test.
    midday = datetime.datetime.now().replace(hour=12, minute=0, second=0, microsecond=0)
    today = midday.timestamp()
    yesterday = (midday - datetime.timedelta(days=1)).timestamp()
    rows = [
        ("s1", "tool", '{"output": "bash: magick: command not found"}', "terminal", today),
        ("s1", "tool", "ModuleNotFoundError: No module named 'weasyprint'", "terminal", today - 60),
        ("s2", "tool", "ModuleNotFoundError: No module named 'weasyprint'", "terminal", yesterday),
        ("s2", "tool", '{"error": "path required"}', "patch", today - 900),
        ("s3", "tool", '{"output": "No module named \'tools\'"}', "terminal", today - 800),
        ("s3", "assistant", "hello", None, today),
    ]
    conn.executemany("INSERT INTO messages (session_id, role, content, tool_name, timestamp) "
                     "VALUES (?,?,?,?,?)", rows)
    conn.commit()
    conn.close()
    return _load("statedb", "statedb.py")


def test_state_db_is_detected(statedb):
    assert statedb.available() is True


def test_mine_records_only_real_gaps(statedb):
    out = statedb.mine(days=3650)
    assert out["available"] is True
    assert out["tool_messages"] == 5
    assert out["events_recorded"] == 3  # magick + weasyprint ×2; not "path required", not "tools"
    core = statedb._load("core", "core.py")
    sigs = {g["signature"] for g in core.gaps()["top"]}
    assert sigs == {"cmd:magick", "pkg:weasyprint"}


def test_field_groups_by_real_event_day(statedb):
    statedb.mine(days=3650)
    core = statedb._load("core", "core.py")
    f = core.field(days=30)
    assert f["total"] == 3
    assert f["active_days"] >= 2
    assert f["max"] >= 2
    today = datetime.date.today().isoformat()
    assert any(c["date"] == today and c["count"] >= 1 for c in f["cells"])
    assert len(f["cells"]) == 30


def test_missing_db_is_reported_not_raised(statedb, tmp_path):
    (tmp_path / "state.db").unlink()
    out = statedb.mine(days=30)
    assert out["available"] is False
    assert out["events_recorded"] == 0


def test_prune_does_not_eat_mined_history(statedb):
    statedb.mine(days=3650)
    core = statedb._load("core", "core.py")
    with core._db() as conn:
        conn.execute("UPDATE gaps SET ts = ?", (datetime.datetime.now().timestamp() - 200 * 86400,))
    core.prune_gaps()
    assert core.gaps()["total"] == 2
