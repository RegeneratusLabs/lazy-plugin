"""Install and share, on a generated plugin. Nothing here needs a model or the network."""

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture()
def api(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    spec = importlib.util.spec_from_file_location(f"api_{id(tmp_path)}", ROOT / "dashboard" / "plugin_api.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    bundle = tmp_path / "lazy-plugin" / "created" / "gpu-price-watch"
    bundle.mkdir(parents=True)
    (bundle / "plugin.yaml").write_text(
        "name: gpu-price-watch\nversion: 1.2.0\ndescription: Watch GPU prices.\n"
        "provides_tools:\n  - check_prices\n", encoding="utf-8")
    # A package that actually runs: the install gate smoke-tests before it links anything.
    (bundle / "__init__.py").write_text(
        "def handle_check_prices(params, config):\n"
        "    return {'ok': True, 'count': 0, 'items': []}\n"
        "\n"
        "def register(ctx):\n"
        "    ctx.register_tool(name='check_prices', toolset='gpu',\n"
        "                      schema={'name': 'check_prices'},\n"
        "                      handler=handle_check_prices, description='x')\n",
        encoding="utf-8")

    cs = importlib.util.spec_from_file_location(f"creator_{id(tmp_path)}", ROOT / "creator.py")
    creator = importlib.util.module_from_spec(cs)
    cs.loader.exec_module(creator)
    creator.validate_plugin = lambda path, timeout=180: {"ok": True, "failures": [],
                                                         "tail": ["Validation passed."]}
    mod._creator_mod = lambda: creator
    return mod


def test_install_links_the_generated_plugin(api, tmp_path):
    out = api._install_created("gpu-price-watch")
    assert out["ok"] is True
    link = tmp_path / "plugins" / "gpu-price-watch"
    assert link.is_symlink()
    assert link.resolve() == (tmp_path / "lazy-plugin" / "created" / "gpu-price-watch").resolve()
    assert "enable" in out["next"]


def test_install_refuses_to_clobber_an_existing_plugin(api):
    api._install_created("gpu-price-watch")
    again = api._install_created("gpu-price-watch")
    assert again["ok"] is False and "already exists" in again["error"]


def test_install_refuses_a_package_that_does_not_validate(api, monkeypatch):
    creator = api._creator_mod()
    monkeypatch.setattr(creator, "validate_plugin",
                        lambda path, timeout=180: {"ok": False, "failures": ["\u2717 boom"], "tail": []})
    out = api._install_created("gpu-price-watch")
    assert out["ok"] is False and "does not validate" in out["error"]


def test_install_refuses_a_plugin_that_does_not_run(api, tmp_path):
    bundle = tmp_path / "lazy-plugin" / "created" / "gpu-price-watch" / "__init__.py"
    bundle.write_text(
        "def handle_check_prices(params, config):\n"
        "    raise NotImplementedError('This tool is a scaffold')\n"
        "\n"
        "def register(ctx):\n"
        "    ctx.register_tool(name='check_prices', toolset='gpu',\n"
        "                      schema={'name': 'check_prices'},\n"
        "                      handler=handle_check_prices, description='x')\n",
        encoding="utf-8")
    out = api._install_created("gpu-price-watch")
    assert out["ok"] is False and "does not run" in out["error"]


def test_install_rejects_an_unknown_name(api):
    assert api._install_created("nope")["ok"] is False


def test_job_status_rejects_an_unknown_id(api):
    """The publish job door is /jobs/<id>; an id nobody started is gone, not a 500."""
    import asyncio
    assert asyncio.run(api.job_status("nope"))["stage"] == "gone"


