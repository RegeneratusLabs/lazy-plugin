"""Publishing follows the catalog's own pathway, so every step is assertable without the network."""

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


PUBLISH = load("publish")


@pytest.fixture()
def publish():
    return PUBLISH


class Recorder:
    """Answers the commands publish() actually issues, and remembers them."""

    def __init__(self, validate_ok=True, repo_missing=True, pr_url="https://github.com/x/y/pull/7"):
        self.calls = []
        self.validate_ok = validate_ok
        self.repo_missing = repo_missing
        self.pr_url = pr_url

    def __call__(self, cmd, cwd=None, timeout=300):
        self.calls.append(" ".join(cmd))
        joined = " ".join(cmd)
        if "plugins" in joined and "validate" in joined:
            if self.validate_ok:
                return "✓ security scan — safe\nValidation passed."
            raise PUBLISH.PublishError("✗ security scan — dangerous: curl_pipe_sh")
        if "api user" in joined:
            return "josh@example.com" if ".email" in joined else "RegeneratusLabs"
        if "rev-parse HEAD" in joined:
            return "a" * 40
        if "repo view" in joined and "hermes-agent" in joined:
            raise PUBLISH.PublishError("no fork yet")
        if "repo create" in joined:
            self.repo_missing = False
            return ""
        if "repo view" in joined and self.repo_missing:
            raise PUBLISH.PublishError("Could not resolve to a Repository")
        if "repo view" in joined:
            return "https://github.com/RegeneratusLabs/x"
        if "rev-parse --abbrev-ref" in joined:
            return "main"
        if "pr create" in joined:
            return self.pr_url
        return ""

    def has(self, needle):
        return any(needle in call for call in self.calls)


@pytest.fixture()
def bundle(tmp_path):
    root = tmp_path / "gpu-price-watch"
    root.mkdir()
    (root / "plugin.yaml").write_text(
        'name: gpu-price-watch\nversion: 0.3.0\ndescription: >-\n  Watch GPU prices for a '
        'drop under the ceiling and report matches.\nprovides_tools:\n  - check_prices\n'
        '  - last_run\n', encoding="utf-8")
    (root / "__init__.py").write_text("def register(ctx):\n    pass\n", encoding="utf-8")
    (root / "README.md").write_text("# gpu-price-watch\n", encoding="utf-8")
    return root


def test_a_package_that_fails_validation_is_never_published(publish, bundle):
    run = Recorder(validate_ok=False)
    out = publish.publish(bundle, "gpu-price-watch", "RegeneratusLabs",
                          {"version": "0.3.0", "provides_tools": ["check_prices"]}, run=run)
    assert out["ok"] is False and out["stage"] == "validate"
    assert not run.has("repo create")
    assert not (bundle / "plugin-catalog").exists()


def test_publish_pins_a_real_commit_and_writes_the_entry(publish, bundle):
    run = Recorder()
    out = publish.publish(bundle, "gpu-price-watch", "RegeneratusLabs",
                          load("creator").read_manifest(bundle), run=run)

    assert out["ok"] is True and out["stage"] == "pinned"
    assert out["sha"] == "a" * 40
    entry = Path(out["entry"])
    assert entry.exists()
    text = entry.read_text()
    assert "name: gpu-price-watch" in text
    assert "repo: https://github.com/RegeneratusLabs/gpu-price-watch" in text
    assert f"sha: {'a' * 40}" in text
    assert 'version: "0.3.0"' in text
    assert "    - check_prices" in text
    assert "      - last_run" not in text
    assert "  provides_hooks: []" in text
    assert run.has("gh repo create RegeneratusLabs/gpu-price-watch --public")
    assert out["install_command"] == "hermes plugins install gpu-price-watch"
    assert [step["step"] for step in out["steps"]] == ["secrets", "validate", "commit", "repo", "catalog entry"]


def test_existing_repo_is_pushed_to_instead_of_recreated(publish, bundle):
    run = Recorder(repo_missing=False)
    out = publish.publish(bundle, "gpu-price-watch", "RegeneratusLabs",
                          load("creator").read_manifest(bundle), run=run)
    assert out["ok"] is True
    assert not run.has("repo create")
    assert run.has("git push -q -u origin main")


def test_opening_the_pr_forks_hermes_and_adds_one_file(publish, bundle, tmp_path):
    run = Recorder()
    out = publish.publish(bundle, "gpu-price-watch", "RegeneratusLabs",
                          load("creator").read_manifest(bundle), run=run, open_pull_request=True)
    assert out["stage"] == "submitted"
    assert run.has("gh repo fork NousResearch/hermes-agent")
    assert run.has("sparse-checkout set plugin-catalog")
    assert run.has("gh pr create --repo NousResearch/hermes-agent")
    assert out["pr"] == "https://github.com/x/y/pull/7"


def test_install_local_links_and_refuses_to_clobber(publish, tmp_path):
    bundle = tmp_path / "created" / "gpu-price-watch"
    bundle.mkdir(parents=True)
    (bundle / "plugin.yaml").write_text("name: gpu-price-watch\n", encoding="utf-8")
    plugins = tmp_path / "plugins"
    ok = publish.install_local(bundle, "gpu-price-watch", plugins,
                              lambda path: {"ok": True, "tail": ["Validation passed."]})
    assert ok["ok"] is True and (plugins / "gpu-price-watch").is_symlink()
    again = publish.install_local(bundle, "gpu-price-watch", plugins,
                                 lambda path: {"ok": True, "tail": []})
    assert again["ok"] is False and "already exists" in again["error"]


def test_install_local_refuses_an_unvalidated_package(publish, tmp_path):
    bundle = tmp_path / "b"
    bundle.mkdir()
    out = publish.install_local(bundle, "x", tmp_path / "plugins",
                                lambda path: {"ok": False, "failures": ["✗ boom"]})
    assert out["ok"] is False and "does not validate" in out["error"]
    assert not (tmp_path / "plugins" / "x").exists()


def test_catalog_entry_validates_against_the_real_catalog_checker(publish, bundle):
    """The entry the user gets must pass the same structural validator CI runs."""
    checker = Path.home() / ".hermes" / "hermes-agent" / "scripts" / "validate_plugin_catalog.py"
    if not checker.exists():
        pytest.skip("hermes-agent checkout not available")
    import shutil
    import subprocess
    import sys

    out = publish.publish(bundle, "gpu-price-watch", "RegeneratusLabs",
                          load("creator").read_manifest(bundle), run=Recorder())
    # the checker needs ruamel.yaml; the system python has it, a bare test venv may not
    interpreter = shutil.which("python3") or sys.executable
    done = subprocess.run([interpreter, str(checker), out["entry"], "--json"],
                          capture_output=True, text=True, timeout=120)
    if "ruamel.yaml is required" in (done.stderr or ""):
        pytest.skip("ruamel.yaml not installed for this interpreter")
    assert done.returncode == 0, done.stdout + done.stderr
