"""``hermes pluginscout ...`` — same report, no model in the loop."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def _core():
    p = Path(__file__).parent / "core.py"
    spec = importlib.util.spec_from_file_location("pluginscout_core", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


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
    print(f"\n{h['matched_skills']} of {h['total_skills']} skills overlap a catalog plugin "
          f"({h['skill_lines']} lines) · {h['gaps']} recorded gaps")
    print(f"catalog: {c['entries']} entries, {c['source']}, {c['age_hours']}h old\n")
    rows = report["matches"] if getattr(args, "all", False) else report["matches"][:20]
    if rows:
        for m in rows:
            flag = " agent" if m["agent_created"] else ""
            tail = " [installed]" if m.get("installed") else ""
            print(f"  {m['skill'][:34]:34} -> {m['plugin'][:28]:28} {','.join(m['ids'][:2])}{flag}{tail}")
        print()
    for g in report["gaps"].get("top", [])[:10]:
        print(f"  gap {g['kind']:<18} {g['signature'][:40]:40} ×{g['seen']}")
    return 0


if __name__ == "__main__":  # works regardless of plugin isolation mode
    import argparse

    parser = argparse.ArgumentParser(prog="pluginscout", description="Capability-gap instrument")
    setup(parser)
    raise SystemExit(run(parser.parse_args()))
