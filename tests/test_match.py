"""The matcher's whole value is precision. These tests exist to keep it from drifting back
into prose-token matching, which matched 199/199 real skills and meant nothing."""


def test_extracts_concrete_command(core):
    ids = core.skill_identifiers("```bash\nbrightdata scrape https://example.com --json\n```")
    assert "brightdata" in ids["commands"]


def test_prose_words_are_not_identifiers(core):
    ids = core.skill_identifiers("We have access to announcements, briefs and changes.")
    assert ids["commands"] == set()
    assert ids["hosts"] == set()


def test_extracts_env_var_and_host(core):
    ids = core.skill_identifiers(
        "Set BRIGHTDATA_API_KEY then GET https://api.brightdata.com/datasets")
    assert "BRIGHTDATA_API_KEY" in ids["env"]
    assert "brightdata" in ids["hosts"]


def test_identifier_skill_matches(core):
    index, _ = core.gate_index(core.load_catalog()["entries"])
    skill = {"body": "```bash\nbrightdata scrape https://example.com --json\n```"}
    hits = core.match_skill(skill, index)
    assert [h["plugin"] for h in hits] == ["brightdata"]
    assert hits[0]["ids"] == ["commands:brightdata"]


def test_command_naming_entry_matches(core):
    index, _ = core.gate_index(core.load_catalog()["entries"])
    skill = {"body": "```bash\noffice-desk render report.docx --style clean\n```"}
    assert [h["plugin"] for h in core.match_skill(skill, index)] == ["office-desk"]


def test_prose_about_cron_does_not_match_cron_plugin(core):
    """The regression that killed the lexical design: 40 mentions of a word is not evidence."""
    index, _ = core.gate_index(core.load_catalog()["entries"])
    body = "cron " * 40
    assert core.match_skill({"body": body}, index) == []


def test_skill_name_alone_does_not_match(core):
    """A skill called ethics-filter does not prove the ethics-filter plugin covers it."""
    index, _ = core.gate_index(core.load_catalog()["entries"])
    skill = {"name": "ethics-filter", "description": "Score a decision for ethical soundness",
             "body": "Ask who bears the cost and whether the user consented."}
    assert core.match_skill(skill, index) == []


def test_blocklisted_binaries_never_match(core):
    index, _ = core.gate_index(core.load_catalog()["entries"])
    assert core.match_skill({"body": "```bash\npython3 script.py --flag\n```"}, index) == []
