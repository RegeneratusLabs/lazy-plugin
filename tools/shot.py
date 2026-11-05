"""Render a faithful standalone copy of the Scout page from the real report payload, then screenshot."""
import html
import importlib.util
import json
import subprocess
from pathlib import Path

ROOT = Path("/home/josh/projects/lazy-plugin")


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(f"shot_{name}", ROOT / filename)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


core = _load("core", "core.py")
report = core.build_report("full")
field = report["field"]
gaps = report["gaps"]["top"]
sources = report["sources"]
Path("/tmp/scout_report.json").write_text(json.dumps(report, indent=1))

# ---- field grid: 7 rows (Mon..Sun) x N week columns
cells = field["cells"]
pad = cells[0]["weekday"]
padded = [None] * pad + cells
cols = [padded[i:i + 7] for i in range(0, len(padded), 7)]
peak = max(1, field["max"])


def level(c):
    if not c:
        return 0
    r = c / peak
    return 4 if r > 0.75 else 3 if r > 0.45 else 2 if r > 0.18 else 1


MIX = {0: None, 1: 30, 2: 52, 3: 74, 4: 100}

col_html = []
for col in cols:
    cell_html = []
    for wd in range(7):
        cell = col[wd] if wd < len(col) else None
        if not cell:
            cell_html.append('<div class="gapcell empty"></div>')
            continue
        lv = level(cell["count"])
        style = (f' style="background:color-mix(in srgb, var(--accent) {MIX[lv]}%, var(--bg3));"'
                 if lv else "")
        cls = "gapcell" + ("" if lv else " zero")
        cell_html.append(f'<div class="{cls}"{style} title="{cell["date"]} — {cell["count"]} gaps"></div>')
    col_html.append('<div class="gcol">' + "".join(cell_html) + "</div>")
grid_html = "".join(col_html)

wd_html = "".join(
    f'<div class="wd">{["Mon","Tue","Wed","Thu","Fri","Sat","Sun"][i] if i % 2 == 0 else ""}</div>'
    for i in range(7))

_panel_html = Path("/home/josh/.hermes/cache/scratch/panel.html")
_panel_css = Path("/home/josh/.hermes/cache/scratch/panel.css")
_contrib_html = Path("/home/josh/.hermes/cache/scratch/contrib_panel.html")
_contrib_css = Path("/home/josh/.hermes/cache/scratch/contrib_panel.css")
panel = _panel_html.read_text() if _panel_html.exists() else ""
panel_css = _panel_css.read_text() if _panel_css.exists() else ""
contrib_panel = _contrib_html.read_text() if _contrib_html.exists() else ""
_contrib_json = Path("/home/josh/.hermes/cache/scratch/contrib-sample.json")
contrib_counts = json.loads(_contrib_json.read_text()).get("counts", {}) if _contrib_json.exists() else {}
contrib_css = _contrib_css.read_text() if _contrib_css.exists() else ""

gap_rows = "\n".join(
    f'''<div class="grow">
      <span class="rank">{i+1}</span>
      <span class="count">{g["seen"]}×</span>
      <span class="sig">{html.escape(g["signature"])}</span>
      <span class="sess">{g.get("sessions") or 1} sess</span>
      <span class="badge">{ {"statedb":"state.db","backfill":"transcripts","live":"live"}.get(g["source"], g["source"]) }</span>
    </div>''' for i, g in enumerate(gaps[:10]))

DOC = f"""<!doctype html><meta charset="utf-8"><title>Scout</title>
<style>
  :root {{
    --bg: #17181c; --bg2: #1e1f25; --bg3: #2a2c33;
    --fg: #e8e9ed; --fg2: #a9adb8; --fg3: #7b8090; --fg4: #5d6272;
    --stroke: #2f323b; --accent: #6ea8fe;
  }}
  * {{ box-sizing: border-box; }}
  body {{ margin:0; background:var(--bg); color:var(--fg);
    font-family: ui-sans-serif, -apple-system, "Segoe UI", Roboto, sans-serif; font-size:14px; }}
  .app {{ display:flex; min-height:100vh; }}
  .side {{ width:196px; background:var(--bg2); border-right:1px solid var(--stroke); padding:14px 10px; }}
  .side .brand {{ font-size:12px; letter-spacing:.08em; text-transform:uppercase; color:var(--fg4); padding:0 8px 12px; }}
  .side .item {{ display:flex; gap:8px; align-items:center; padding:6px 8px; border-radius:6px; color:var(--fg2); font-size:13px; }}
  .side .item.on {{ background:var(--bg3); color:var(--fg); }}
  .dot {{ width:6px; height:6px; border-radius:2px; background:var(--fg4); }}
  .side .item.on .dot {{ background:var(--accent); }}
  .main {{ flex:1; padding:22px 26px; }}
  h1 {{ font-size:13px; font-weight:600; margin:0; }}
  .sub {{ font-size:11px; color:var(--fg4); }}
  .head {{ display:flex; justify-content:space-between; align-items:baseline; margin-bottom:14px; }}
  .field {{ display:flex; gap:10px; align-items:flex-start; }}
  .wd {{ width:26px; height:13px; line-height:13px; font-size:9px; color:var(--fg4); }}
  .grid {{ display:flex; gap:3px; }}
  .gcol {{ display:flex; flex-direction:column; gap:3px; }}
  .gcol .gapcell {{ width:13px; height:13px; border-radius:3px; }}
  .gcol .zero {{ background: color-mix(in srgb, var(--fg4) 22%, transparent); }}
  .gcol .empty {{ background: transparent; }}
  .stats {{ display:grid; grid-template-columns:repeat(3,1fr); gap:18px;
            border:1px solid var(--stroke); border-radius:8px; padding:14px 16px; margin:20px 0 22px; }}
  .stat .label {{ font-size:10.5px; color:var(--fg4); }}
  .stat .value {{ font-size:19px; font-weight:600; margin-top:4px; line-height:1; }}
  .stat .hint {{ font-size:10.5px; color:var(--fg4); margin-top:6px; }}
  .section {{ font-size:13px; font-weight:600; margin-bottom:8px; }}
  .grow {{ display:flex; align-items:baseline; gap:12px; padding:7px 0; border-bottom:1px solid var(--stroke); }}
  .rank {{ width:20px; text-align:right; font-size:10.5px; color:var(--fg4); }}
  .count {{ width:38px; text-align:right; font-size:11.5px; color:var(--fg2); }}
  .sig {{ flex:1; font-family: ui-monospace, "SF Mono", Menlo, monospace; font-size:12px; }}
  .sess {{ font-size:10.5px; color:var(--fg4); }}
  .badge {{ font-size:9px; text-transform:uppercase; letter-spacing:.06em; color:var(--fg3);
            border:1px solid var(--stroke); border-radius:4px; padding:1px 5px; }}
  .foot {{ margin-top:18px; display:flex; justify-content:space-between; font-size:10.5px; color:var(--fg4); }}
  .status {{ border-top:1px solid var(--stroke); padding:5px 12px; display:flex; justify-content:flex-end; gap:14px;
             font-size:11px; color:var(--fg3); background:var(--bg2); position:fixed; bottom:0; left:0; right:0; }}
  .status b {{ color:var(--fg2); font-weight:500; }}
{panel_css}
{contrib_css}
</style>
<div class="app">
  <div class="side">
    <div class="brand">Hermes</div>
    <div class="item"><span class="dot"></span>Chat</div>
    <div class="item"><span class="dot"></span>Sessions</div>
    <div class="item"><span class="dot"></span>Skills</div>
    <div class="item on"><span class="dot"></span>Scout</div>
    <div class="item"><span class="dot"></span>Cron</div>
  </div>
  <div class="main">
    {panel}
    {contrib_panel}
    <div class="foot">
      <span>model writes the spec · templates write the code · the validator decides</span>
      <span>generated plugins are never installed</span>
    </div>
  </div>
</div>
<div class="status"><span><b>{contrib_counts.get('publish', 0)} to share</b></span><span>plugin host: default</span></div>
"""
Path("/home/josh/projects/lazy-plugin/assets/preview.html").write_text(DOC)

out = "/home/josh/projects/lazy-plugin/assets/preview.png"
subprocess.run(["chromium", "--headless", "--no-sandbox", "--disable-gpu", "--hide-scrollbars",
                "--force-device-scale-factor=2", "--window-size=1120,980",
                f"--screenshot={out}", "file:///home/josh/projects/lazy-plugin/assets/preview.html"],
               check=False, capture_output=True, timeout=120)
print("png:", out, Path(out).stat().st_size if Path(out).exists() else "MISSING")
print("field:", field["total"], "events /", field["active_days"], "active days / peak", field["max"])
