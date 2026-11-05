def test_report_headline_counts(core):
    report = core.build_report("full")
    assert report["skills"]["total"] == 5
    assert report["headline"]["total_skills"] == 5
    assert report["headline"]["matched_skills"] == 2
    assert {m["skill"] for m in report["matches"]} == {"scraping", "office"}


def test_report_carries_usage_and_install(core):
    report = core.build_report("full")
    by_skill = {m["skill"]: m for m in report["matches"]}
    assert by_skill["scraping"]["agent_created"] is True
    assert by_skill["scraping"]["install"] == "hermes plugins install brightdata"
    bd = next(m for m in report["matches"] if m["plugin"] == "brightdata")
    assert "BRIGHTDATA_API_KEY" in bd["needs_env"]


def test_summary_is_short_and_names_the_number(core):
    text = core.summary_text()
    assert "2 of 5 skills overlap a catalog plugin" in text
    assert len(text) < 1200


def test_catalog_served_from_cache_on_second_call(core):
    core.load_catalog(force=True)
    again = core.load_catalog()
    assert again["source"] == "cache"
    assert len(again["entries"]) == 4


def test_catalog_unavailable_degrades_without_raising(core, tmp_path):
    core.CATALOG_URL = (tmp_path / "missing.json").as_uri()
    payload = core.load_catalog(force=True)
    assert payload["source"] in ("unavailable", "cache(stale)")
    assert isinstance(payload["entries"], list)


def test_installed_plugin_is_not_a_recommendation(core, tmp_path):
    (tmp_path / "plugins" / "brightdata").mkdir(parents=True)
    report = core.build_report("full")
    bd = next(m for m in report["matches"] if m["plugin"] == "brightdata")
    assert bd["installed"] is True
    assert bd["install"] == "already installed"
    assert report["headline"]["recommendable"] == 1  # office-desk only
