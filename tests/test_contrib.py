"""Button two: screening is deterministic, packaging is scrubbed, private stays private."""

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _load(name, filename, tmp_path):
    spec = importlib.util.spec_from_file_location(f"pc_{name}_{id(tmp_path)}", ROOT / filename)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def contrib(monkeypatch, tmp_path):
    skills = tmp_path / "skills"
    (skills / "general").mkdir(parents=True)
    (skills / "personalised").mkdir(parents=True)
    (skills / "pluginy").mkdir(parents=True)
    (skills / "ethics-filter").mkdir(parents=True)

    def write(path, desc, body):
        (skills / path / "SKILL.md").write_text(
            f"---\nname: {path}\ndescription: {desc}\n---\n\n{body}", encoding="utf-8")

    write("general", "Use when an HTML page needs a colour-blindness check.",
          "## Steps\n1. Render the page headless.\n2. Convert to grayscale.\n"
          "3. Compare contrast ratios.\n4. Report the failures.\n")
    write("personalised", "Use when the homelab box needs a reboot.",
          "## Steps\n1. ssh josh@optiplex\n2. run the script in /home/josh/homelab\n"
          "3. check port 9119\n4. tell josh it worked\n5. email josht@nutri-tech.com.au\n"
          "6. ssh becca@100.86.176.62\n")
    write("pluginy", "Use when the dashboard needs a hook.",
          "## Steps\n1. register_tool in plugin.yaml\n2. ctx.register_hook('post_tool_call')\n"
          "3. ship desktop/plugin.js\n")
    write("ethics-filter", "Use when judging a decision.",
          "1. read\n2. weigh\n3. decide\n")

    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.setenv("LAZY_PLUGIN_SKILLS_DIR", str(skills))
    mod = _load("contrib", "skills_contrib.py", tmp_path)
    mod._CORE.CATALOG_URL = (FIXTURES / "catalog.json").as_uri()
    # every fixture skill counts as agent-written; usage.json is what marks that
    (tmp_path / "skills" / ".usage.json").write_text(json.dumps({
        "general": {"created_at": "2026-11-01T00:00:00+00:00"},
        "personalised": {"created_at": "2026-11-01T00:00:00+00:00"},
        "pluginy": {"created_at": "2026-11-01T00:00:00+00:00"},
        "ethics-filter": {"created_at": "2026-11-01T00:00:00+00:00"},
    }), encoding="utf-8")
    monkeypatch.setattr(mod._CORE, "scan_skills", lambda root=None: [
        {**_stub(skills / p), "agent_created": True} for p in
        ("general", "personalised", "pluginy", "ethics-filter")
    ])
    return mod


def _stub(path: Path) -> dict:
    text = (path / "SKILL.md").read_text()
    desc = ""
    for line in text.splitlines():
        if line.startswith("description:"):
            desc = line.split(":", 1)[1].strip()
    body = text.split("---", 2)[-1]
    return {"name": path.name, "path": str(path / "SKILL.md"), "description": desc,
            "body": body, "lines": len(body.splitlines()), "use_count": 1, "category": ""}


def test_clean_procedure_is_publishable(contrib):
    out = contrib.run(days=365)
    by = {c["name"]: c for c in out["candidates"]}
    assert by["general"]["verdict"] == "publish"
    assert by["general"]["contribute_as"] == "skill"


def test_personal_environment_is_private_and_lists_evidence(contrib):
    by = {c["name"]: c for c in contrib.run(days=365)["candidates"]}
    personal = by["personalised"]
    assert personal["verdict"] == "private"
    kinds = {m["kind"] for m in personal["markers"]}
    assert {"path", "host", "identity", "account"} <= kinds
    assert any("optiplex" in m["text"] or "100.86" in m["text"] for m in personal["markers"])


def test_plugin_shaped_skill_is_flagged_as_a_plugin(contrib):
    by = {c["name"]: c for c in contrib.run(days=365)["candidates"]}
    assert by["pluginy"]["contribute_as"] == "plugin"


def test_catalog_collision_is_already_covered(contrib):
    by = {c["name"]: c for c in contrib.run(days=365)["candidates"]}
    assert by["ethics-filter"]["verdict"] == "already_covered"


def test_package_scrubs_paths_and_credits_the_author(contrib, tmp_path):
    contrib.run(days=365)
    # 'personalised' is private and must refuse; use a scrubbable one instead
    out = contrib.package("general", days=365)
    assert out["ok"] is True
    bundle = Path(out["dir"])
    text = (bundle / "SKILL.md").read_text()
    assert "Render the page headless" in text
    readme = (bundle / "README.md").read_text()
    assert "Josh Thomson" in readme and "MIT" in readme
    meta = json.loads((bundle / "CONTRIBUTION.json").read_text())
    assert meta["verdict"] == "publish"


def test_package_refuses_a_private_skill(contrib):
    out = contrib.package("personalised", days=365)
    assert out["ok"] is False
    assert "private" in out["error"]
    assert out["reasons"]


def test_scrub_replaces_identity_and_hosts(contrib):
    text, count = contrib._scrub("ssh josh@optiplex then check 9119 in /home/josh/homelab")
    assert count >= 3
    assert "josh" not in text.lower()
    assert "optiplex" not in text.lower()
    assert "/home/josh" not in text


def test_markers_report_line_numbers(contrib):
    hits = contrib.markers("ok\nssh josh@optiplex\nfine")
    assert hits and hits[0]["line"] == 2


def test_submit_writes_a_portable_package_and_catalog_entry(contrib):
    out = contrib.submit("general", days=365)
    assert out["ok"] is True
    bundle = Path(out["dir"])
    assert (bundle / "plugin.json").exists()
    assert (bundle / "skills" / bundle.name / "SKILL.md").exists()
    entry = bundle / "plugin-catalog" / f"{bundle.name}.yaml"
    assert entry.exists()
    body = entry.read_text()
    assert '"sha"' in body and "<full 40-character commit sha>" in body
    assert '"capabilities"' in body
    assert "SUBMISSION.md" in out["files"]
    assert len(out["steps"]) == 5
    submission = (bundle / "SUBMISSION.md").read_text()
    assert "NousResearch/hermes-agent" in submission
    assert "hermes plugins validate" in submission


def test_submit_refuses_a_private_skill(contrib):
    out = contrib.submit("personalised", days=365)
    assert out["ok"] is False
    assert "private" in out["error"]


def test_missing_skill_name_fails_cleanly(contrib):
    out = contrib.package("does-not-exist", days=365)
    assert out["ok"] is False and "no agent-written skill" in out["error"]
