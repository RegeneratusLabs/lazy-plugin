"""The catalog check: does something already do this job?

The rule this file protects: prose is never evidence on its own. The catalog is 1,063 wordy
descriptions, so any matcher that scores shared words will confidently match everything — that is
exactly how the gap finder died. A match has to be anchored in a tool name or a rare name token.
"""

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

# A 60-entry catalog, because the identity rule is statistical: "watch" has to appear in enough
# entries to be vocabulary rather than identity, or the fixture tests nothing.
def _filler(count: int = 56):
    entries = []
    for index in range(count):
        entries.append({
            "name": f"sample-watch-{index}" if index % 2 else f"sample-check-{index}",
            "repo": f"https://github.com/x/sample-{index}",
            "description": "Watch listings, check prices, report changes and answer with the best "
                           "result for a price threshold.",
            "capabilities": {"provides_tools": [f"check_{index}", f"watch_{index}"]},
        })
    return entries


CATALOG = {
    "entries": [
        {"name": "hermes-plugin-gen", "repo": "https://github.com/x/hermes-plugin-gen",
         "description": "Generate, scaffold, and extend Hermes Agent plugins from simple descriptions.",
         "capabilities": {"provides_tools": ["plugin_scaffold", "plugin_add_tool", "plugin_add_skill"]}},
        {"name": "model-drift-watch", "repo": "https://github.com/x/model-drift-watch",
         "description": "Watch a model's answers drift over time and report price and quality changes.",
         "capabilities": {"provides_tools": ["check_drift"]}},
        {"name": "kanban", "repo": "https://github.com/x/kanban",
         "description": "A board for tasks with cards, columns and a dispatcher.",
         "capabilities": {"provides_tools": ["board_add_card", "board_move_card"]}},
        {"name": "tenor-gifs", "repo": "https://github.com/x/tenor-gifs",
         "description": "Find GIFs on Tenor and return shortlists.",
         "capabilities": {"provides_tools": ["search_gifs"]}},
    ] + _filler(),
    "source": "test",
    "age_hours": 0,
}


@pytest.fixture()
def core(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    spec = importlib.util.spec_from_file_location(f"core_similar_{id(tmp_path)}", ROOT / "core.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.load_catalog = lambda force=False: CATALOG
    return mod


def test_a_shared_tool_name_is_the_strongest_evidence(core):
    out = core.similar_plugins(name="plugin-scaffolder",
                               description="Generate a Hermes plugin from a sentence.",
                               tools=["plugin_scaffold"])
    assert out["verdict"] in ("similar", "duplicate")
    assert out["matches"][0]["name"] == "hermes-plugin-gen"
    assert "same tool name" in out["matches"][0]["why"][0]


def test_prose_alone_never_reaches_similar(core):
    """An unrelated plugin that merely shares common words must not be reported as similar."""
    out = core.similar_plugins(name="catnip-price-watch",
                               description="Watch pet retailers for price drops and report the cheapest.",
                               tools=["check_prices"])
    assert out["verdict"] in ("nothing", "possible")
    assert out["verdict"] != "similar"


def test_an_unrelated_plugin_gets_nothing(core):
    out = core.similar_plugins(name="venue-liveness",
                               description="Confirm a venue website still responds before recommending it.",
                               tools=["check_venue_live"])
    assert out["verdict"] == "nothing" and out["matches"] == []


def test_a_shared_rare_name_token_is_evidence(core):
    out = core.similar_plugins(name="tenor-cat-gifs", description="Cat GIFs, shortlisted.",
                               tools=["cat_gif_finder"])
    assert out["verdict"] in ("similar", "duplicate")
    assert out["matches"][0]["name"] == "tenor-gifs"
    assert any("name shares" in line for line in out["matches"][0]["why"])


def test_the_checked_count_is_reported(core):
    out = core.similar_plugins(name="anything-here", description="nothing in common at all",
                               tools=["nothing_like_it"])
    assert out["checked"] == len(CATALOG["entries"])
    assert out["verdict"] == "nothing"
