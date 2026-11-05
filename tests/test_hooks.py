def test_command_not_found_is_recorded(hooks):
    hooks.on_post_tool_call(tool_name="terminal", args={"command": "magick convert a.png b.jpg"},
                            result="bash: magick: command not found", session_id="s1")
    hooks.flush()
    data = hooks.core.gaps()
    assert data["total"] == 1
    assert data["top"][0]["kind"] == "cmd_not_found"
    assert data["top"][0]["signature"] == "cmd:magick"


def test_tool_error_is_recorded(hooks):
    hooks.on_post_tool_call(tool_name="web_extract", args={},
                            result='{"error": "blocked by WAF"}', session_id="s1")
    hooks.flush()
    gap = hooks.core.gaps()["top"][0]
    assert gap["kind"] == "tool_error"
    assert gap["signature"] == "tool:web_extract"


def test_repeated_shellout_queues_on_third_call(hooks):
    for _ in range(2):
        hooks.on_post_tool_call(tool_name="terminal", args={"command": "exiftool -a img.jpg"},
                                result="ok", session_id="s9")
    hooks.flush()
    assert hooks.core.gaps()["total"] == 0
    hooks.on_post_tool_call(tool_name="terminal", args={"command": "exiftool -a img.jpg"},
                            result="ok", session_id="s9")
    hooks.flush()
    gap = hooks.core.gaps()["top"][0]
    assert gap["kind"] == "repeated_shellout"
    assert gap["signature"] == "shellout:exiftool -a img.jpg"


def test_skill_created_is_recorded(hooks):
    hooks.on_skill_lifecycle(action="created", skill_name="scrape-with-curl", session_id="s1")
    hooks.flush()
    gap = hooks.core.gaps()["top"][0]
    assert gap["kind"] == "skill_created"
    assert gap["signature"] == "skill:scrape-with-curl"


def test_other_lifecycle_actions_are_ignored(hooks):
    hooks.on_skill_lifecycle(action="patched", skill_name="x", session_id="s1")
    hooks.flush()
    assert hooks.core.gaps()["total"] == 0


def test_hooks_never_raise_on_garbage(hooks):
    hooks.on_post_tool_call(tool_name=None, args=None, result=None)
    hooks.on_post_tool_call(tool_name="x", args="not-a-dict", result=object())
    hooks.on_skill_lifecycle(action=None, skill_name=None)
    hooks.on_session_end()
    hooks.flush()
