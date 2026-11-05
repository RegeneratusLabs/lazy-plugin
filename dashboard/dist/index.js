/* Lazy Plugin — dashboard tab. Plain IIFE, no build step. */
(function () {
  "use strict";

  var SDK = window.__HERMES_PLUGIN_SDK__ || {};
  var React = SDK.React;
  if (!React) return;
  var h = React.createElement;
  var useState = React.useState;
  var useEffect = React.useEffect;

  var API = "/api/plugins/lazy-plugin";

  function Metric(props) {
    return h("div", { className: "flex flex-col gap-1" },
      h("div", { className: "text-2xl font-semibold tabular-nums" }, props.value),
      h("div", { className: "text-xs text-muted-foreground" }, props.label));
  }

  function Meter(props) {
    var pct = props.total ? Math.round((props.matched / props.total) * 100) : 0;
    return h("div", { className: "w-full" },
      h("div", { className: "text-sm" },
        props.matched + " of " + props.total + " skills overlap a catalog plugin"),
      h("div", {
        className: "mt-2 h-2 w-full overflow-hidden rounded-full",
        style: { background: "var(--border)" }
      }, h("div", {
        style: {
          width: Math.max(2, pct) + "%",
          height: "100%",
          background: "var(--accent)",
          transition: "width 240ms ease"
        }
      })),
      h("div", { className: "mt-1 text-xs text-muted-foreground" },
        props.lines + " lines of skill · " + props.gaps + " recorded gaps"));
  }

  function Ledger(props) {
    if (!props.rows.length) {
      return h("p", { className: "text-sm text-muted-foreground" },
        "No overlaps found. That is the common result — most skills are workflow knowledge, " +
        "not tool wrappers. The gap feed below is the part that fills in over time.");
    }
    return h("table", { className: "w-full border-collapse text-sm" },
      h("thead", null, h("tr", { className: "text-left text-xs text-muted-foreground" },
        h("th", { className: "border-b py-2 pr-3 font-medium", style: { borderColor: "var(--border)" } }, "Skill"),
        h("th", { className: "border-b py-2 pr-3 font-medium", style: { borderColor: "var(--border)" } }, "Plugin"),
        h("th", { className: "border-b py-2 pr-3 font-medium", style: { borderColor: "var(--border)" } }, "Evidence"),
        h("th", { className: "border-b py-2 pr-3 font-medium", style: { borderColor: "var(--border)" } }, "Install"))),
      h("tbody", null, props.rows.map(function (m) {
        return h("tr", { key: m.skill, className: "align-top" },
          h("td", { className: "border-b py-2 pr-3", style: { borderColor: "var(--border)" } },
            m.skill,
            m.agent_created ? h("span", {
              className: "ml-2 rounded px-1 text-[10px] uppercase text-muted-foreground",
              style: { border: "1px solid var(--border)" }
            }, "agent") : null),
          h("td", { className: "border-b py-2 pr-3 font-medium", style: { borderColor: "var(--border)" } },
            m.plugin, m.tier ? h("span", { className: "ml-2 text-[10px] text-muted-foreground" }, m.tier) : null),
          h("td", { className: "border-b py-2 pr-3 font-mono text-xs text-muted-foreground", style: { borderColor: "var(--border)" } },
            (m.ids || []).slice(0, 2).join(", ")),
          h("td", { className: "border-b py-2 pr-3", style: { borderColor: "var(--border)" } },
            h("code", { className: "text-xs" }, "hermes plugins install " + m.plugin)));
      })));
  }

  function GapFeed(props) {
    if (!props.gaps.total) {
      return h("p", { className: "text-sm text-muted-foreground" },
        "Nothing recorded yet. Gaps appear when a tool call fails — a missing binary, a tool error, " +
        "the same shell-out three times, or a skill the agent writes to cope.");
    }
    return h("div", { className: "flex flex-col gap-1 text-sm" },
      props.gaps.top.map(function (g, i) {
        return h("div", { key: i, className: "flex items-baseline gap-3" },
          h("span", { className: "w-10 shrink-0 text-right font-mono text-xs text-muted-foreground" }, g.seen + "\u00d7"),
          h("span", { className: "w-40 shrink-0 text-xs text-muted-foreground" }, g.kind),
          h("span", { className: "font-mono text-xs" }, g.signature));
      }));
  }

  function LazyPluginTab() {
    var r = useState(null), data = r[0], setData = r[1];
    var e = useState(""), err = e[0], setErr = e[1];
    var l = useState(false), loading = l[0], setLoading = l[1];

    function load() {
      setLoading(true);
      fetch(API + "/report?format=json", { credentials: "same-origin" })
        .then(function (res) { if (!res.ok) throw new Error("HTTP " + res.status); return res.json(); })
        .then(function (d) { setData(d); setErr(""); })
        .catch(function (x) { setErr(String(x)); })
        .then(function () { setLoading(false); });
    }

    useEffect(load, []);

    function refresh() {
      setLoading(true);
      fetch(API + "/refresh", { method: "POST", credentials: "same-origin" })
        .then(load)
        .catch(function (x) { setErr(String(x)); setLoading(false); });
    }

    if (err) {
      return h("div", { className: "p-4 text-sm" },
        h("p", { className: "font-medium" }, "Lazy Plugin could not read the report"),
        h("p", { className: "mt-1 text-muted-foreground" }, err),
        h("button", { className: "mt-3 rounded px-3 py-1 text-sm", style: { border: "1px solid var(--border)" }, onClick: load }, "Retry"));
    }
    if (!data) return h("div", { className: "p-4 text-sm text-muted-foreground" }, "Reading the ledger…");

    var hl = data.headline, cat = data.catalog;
    return h("div", { className: "flex flex-col gap-6 p-4" },
      h(Meter, { matched: hl.matched_skills, total: hl.total_skills, lines: hl.skill_lines, gaps: hl.gaps }),
      h("div", { className: "flex gap-8" },
        h(Metric, { value: data.skills.total, label: "skills scanned" }),
        h(Metric, { value: cat.entries, label: "catalog entries" }),
        h(Metric, { value: hl.gaps, label: "recorded gaps" })),
      h("section", null,
        h("h2", { className: "mb-2 text-sm font-semibold" }, "Capability gaps"),
        h(GapFeed, { gaps: data.gaps || { total: 0, top: [] } })),
      h("section", null,
        h("h2", { className: "mb-2 text-sm font-semibold" }, "Skill → plugin"),
        h(Ledger, { rows: data.matches || [] })),
      h("footer", { className: "flex items-center justify-between border-t pt-3 text-xs text-muted-foreground", style: { borderColor: "var(--border)" } },
        h("span", null, cat.entries + " entries · " + (cat.generated_at || "unknown") + " · " + (cat.source || "?")),
        h("button", { className: "rounded px-2 py-1", style: { border: "1px solid var(--border)" }, disabled: loading, onClick: refresh },
          loading ? "Refreshing…" : "Refresh catalog")));
  }

  window.__HERMES_PLUGINS__.register("lazy-plugin", LazyPluginTab);
})();
