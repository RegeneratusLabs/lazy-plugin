"""``hermes pluginscout ...`` — same report, no model in the loop."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def _load(name: str, filename: str):
    p = Path(__file__).parent / filename
    spec = importlib.util.spec_from_file_location(f"pluginscout_{name}", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def _core():
    return _load("core", "core.py")


def slash(raw_args: str = "") -> str:
    """``/scout [report|gaps|refresh|explain <target>]`` — returns text for the transcript."""
    core = _core()
    parts = (raw_args or "").split()
    cmd = parts[0].lower() if parts else "report"

    if cmd == "refresh":
        payload = core.load_catalog(force=True)
        index, _ = core.gate_index(payload["entries"])
        return (f"catalog: {len(payload['entries'])} entries, {len(index)} identifiers, "
                f"source={payload.get('source')}")

    if cmd == "gaps":
        data = core.gaps(limit=10)
        if not data["total"]:
            return "no capability gaps recorded yet — they appear as tool calls fail"
        return "\n".join([f"{data['total']} gap rows"] +
                        [f"  {g['seen']:>3}× {g['kind']:<18} {g['signature']}" for g in data["top"]])

    if cmd == "explain" and len(parts) > 1:
        target = parts[1]
        report = core.build_report("full")
        for m in report["matches"]:
            if m["skill"].lower() == target.lower():
                return (f"{m['skill']} -> {m['plugin']}\n  evidence: {', '.join(m['ids'])}\n"
                        f"  install:  {m['install']}")
        return f"no match named {target!r}"

    return core.summary_text(core.build_report("summary"))


def setup(subparser) -> None:
    sub = subparser.add_subparsers(dest="pluginscout_cmd")
    rep = sub.add_parser("report", help="Skills that overlap a catalog plugin, plus recorded gaps")
    rep.add_argument("--json", action="store_true", help="Print the full report as JSON")
    rep.add_argument("--min-match", type=int, default=1, help="Minimum matched identifiers (default 1)")
    rep.add_argument("--all", action="store_true", help="Show every match, not just the top 20")
    gaps = sub.add_parser("gaps", help="Recorded capability gaps")
    gaps.add_argument("--limit", type=int, default=20)
    sub.add_parser("refresh", help="Re-fetch the catalog and rebuild the index")
    bf = sub.add_parser("backfill", help="Mine past session transcripts for gaps")
    bf.add_argument("--days", type=int, default=365)
    bf.add_argument("--max-sessions", type=int, default=200)
    bf.add_argument("--source", default="auto", choices=["auto", "statedb", "jsonl"])
    fd = sub.add_parser("field", help="Per-day gap counts (the heatmap data)")
    fd.add_argument("--days", type=int, default=140)
    fd.add_argument("--json", action="store_true")
    rc = sub.add_parser("recommend", help="LLM pass: where a plugin would have replaced manual work")
    rc.add_argument("--days", type=int, default=7)
    rc.add_argument("--force", action="store_true")
    exp = sub.add_parser("explain", help="Show the evidence behind one match or gap")
    exp.add_argument("target")


def run(args) -> int:
    core = _core()
    cmd = getattr(args, "pluginscout_cmd", None) or "report"

    if cmd == "refresh":
        payload = core.load_catalog(force=True)
        index, _ = core.gate_index(payload["entries"])
        print(f"catalog: {len(payload['entries'])} entries, {len(index)} identifiers, "
              f"source={payload.get('source')}, generated={payload.get('generated_at')}")
        return 0

    if cmd == "gaps":
        data = core.gaps(limit=getattr(args, "limit", 20) or 20)
        if not data["total"]:
            print("no capability gaps recorded yet — they appear as tool calls fail")
            return 0
        print(f"{data['total']} gap rows\n")
        for g in data["top"]:
            print(f"  {g['seen']:>3}×  {g['kind']:<18} {g['signature']:<38} {g['age_hours']}h ago")
        return 0

    if cmd == "backfill":
        out: dict = {}
        source = getattr(args, "source", "auto") or "auto"
        days = getattr(args, "days", 365) or 365
        sessions = getattr(args, "max_sessions", 200) or 200
        if source in ("auto", "statedb"):
            out["statedb"] = _load("statedb", "statedb.py").mine(days=days)
            if out["statedb"].get("available") and source == "auto":
                print(json.dumps(out, indent=2))
                return 0
        if source in ("auto", "jsonl"):
            out["jsonl"] = _load("history", "history.py").backfill(days=days, max_sessions=sessions)
        print(json.dumps(out, indent=2))
        return 0

    if cmd == "field":
        data = core.field(days=getattr(args, "days", 140) or 140)
        if getattr(args, "json", False):
            print(json.dumps(data))
            return 0
        print(f"{data['total']} gap events across {data['active_days']} active days "
              f"{data['start']} → {data['end']} (max {data['max']}/day)")
        week = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        # 20 weeks, one row per weekday, column per week
        cells = data["cells"]
        cols = [cells[i:i + 7] for i in range(0, len(cells), 7)]
        peak = max(1, data["max"])
        shade = " .:-=+*#%@"
        for wd in range(7):
            row = "".join(shade[min(9, int((col[wd]["count"] / peak) * 9))] if wd < len(col) else " "
                          for col in cols)
            print(f"  {week[wd]} |{row}|")
        return 0

    if cmd == "recommend":
        tools = _load("tools", "tools.py")
        print(tools.handle_recommend({"days": getattr(args, "days", 7),
                                      "force": getattr(args, "force", False)}))
        return 0

    if cmd == "explain":
        target = args.target
        report = core.build_report("full")
        for m in report["matches"]:
            if m["skill"].lower() == target.lower():
                print(f"{m['skill']} -> {m['plugin']}")
                print(f"  evidence: {', '.join(m['ids'])}")
                print(f"  needs:    {', '.join(m['needs_env']) or 'nothing'}")
                print(f"  install:  {m['install']}")
                return 0
        for g in report["gaps"].get("top", []):
            if g["signature"].lower() == target.lower():
                print(f"gap {g['signature']} ({g['kind']}) seen {g['seen']}× — {g['snippet']}")
                return 0
        print(f"no match or gap named {target!r}")
        return 1

    report = core.build_report("full" if getattr(args, "json", False) or getattr(args, "all", False)
                              else "summary", getattr(args, "min_match", 1) or 1)
    if getattr(args, "json", False):
        print(json.dumps(report, indent=2))
        return 0

    h = report["headline"]
    c = report["catalog"]
    gi = report["gaps"]
    print(f"\n{h['gaps']} capability gaps from real tool calls "
          f"({gi.get('events', h['gaps'])} occurrences across {report['skills']['total']} skills' "
          f"worth of history; {gi.get('backfilled', 0)} mined from transcripts)")
    print(f"catalog: {c['entries']} entries, {c['source']}, {c['age_hours']}h old\n")

    answers = {a["signature"] for a in report.get("gap_answers", [])}
    for a in report.get("gap_answers", [])[:10]:
        print(f"  gap {a['signature'][:30]:30} ×{a['seen']:<3} -> {a['plugin'][:22]:22} {a['install']}")
    for g in report["gaps"].get("top", [])[:15]:
        if g["signature"] in answers:
            continue
        print(f"  gap {g['signature'][:30]:30} ×{g['seen']:<3} {g['kind']:<16} {g['source']}")

    print(f"\n{h['matched_skills']} of {h['total_skills']} skills also overlap a catalog plugin "
          f"({h['skill_lines']} lines, {h.get('recommendable', 0)} not installed)\n")
    rows = report["matches"] if getattr(args, "all", False) else report["matches"][:20]
    for m in rows:
        flag = " agent" if m["agent_created"] else ""
        tail = " [installed]" if m.get("installed") else ""
        print(f"  {m['skill'][:34]:34} -> {m['plugin'][:28]:28} {','.join(m['ids'][:2])}{flag}{tail}")
    return 0


if __name__ == "__main__":  # works regardless of plugin isolation mode
    import argparse

    parser = argparse.ArgumentParser(prog="pluginscout", description="Capability-gap instrument")
    setup(parser)
    raise SystemExit(run(parser.parse_args()))
