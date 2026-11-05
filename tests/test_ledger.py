import time


def test_same_signature_upserts_and_counts(core):
    for _ in range(3):
        core.record_gap("cmd_not_found", "cmd:magick", tool="terminal", session_id="s1")
    data = core.gaps()
    assert data["total"] == 1
    assert data["top"][0]["seen"] == 3
    assert data["top"][0]["signature"] == "cmd:magick"


def test_same_gap_in_two_sessions_aggregates(core):
    """The feed is one row per thing you lacked, not one row per session."""
    core.record_gap("cmd_not_found", "cmd:magick", session_id="s1")
    core.record_gap("cmd_not_found", "cmd:magick", session_id="s2")
    data = core.gaps()
    assert data["total"] == 1
    assert data["top"][0]["seen"] == 2
    assert data["top"][0]["sessions"] == 2


def test_empty_signature_is_ignored(core):
    assert core.record_gap("tool_error", "   ") is False
    assert core.gaps()["total"] == 0


def test_prune_drops_old_rows(core):
    core.record_gap("tool_error", "tool:old", session_id="s1")
    with core._db() as conn:
        conn.execute("UPDATE gaps SET ts = ?", (time.time() - 40 * 86400,))
    core.prune_gaps()
    assert core.gaps()["total"] == 0


def test_top_is_ordered_by_frequency(core):
    core.record_gap("tool_error", "tool:a", session_id="s1")
    for _ in range(4):
        core.record_gap("tool_error", "tool:b", session_id="s1")
    assert core.gaps()["top"][0]["signature"] == "tool:b"
