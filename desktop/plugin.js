import {
  PALETTE_AREA,
  ROUTES_AREA,
  SIDEBAR_NAV_AREA,
  STATUSBAR_AREAS,
  host
} from '@hermes/plugin-sdk'
import { useEffect, useState } from 'react'
import { jsx, jsxs } from 'react/jsx-runtime'

const ID = 'pluginscout'
const ROUTE = '/pluginscout'
const WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

// ---------- data

function parseMaybe(value) {
  if (typeof value === 'string') {
    try { return JSON.parse(value) } catch { return null }
  }
  return value || null
}

// ctx.rest hits this plugin's own backend namespace (/api/plugins/pluginscout). The fetch is a
// fallback for a host where the scoped client is not wired or takes a different shape.
function makeApi(ctx) {
  async function rest(path, init) {
    if (ctx && typeof ctx.rest === 'function') {
      try {
        const out = await ctx.rest(path, init)
        const parsed = parseMaybe(out)
        if (parsed !== null && parsed !== undefined) return parsed
      } catch (err) {
        // fall through to fetch
      }
    }
    const res = await fetch(`/api/plugins/pluginscout${path}`, {
      credentials: 'same-origin',
      ...(init || {}),
      headers: { 'Content-Type': 'application/json', ...((init && init.headers) || {}) }
    })
    if (res.status === 404) {
      // The backend mounts plugin routes in-process at startup, so a running process keeps the
      // router it imported. A 404 on a route that exists on disk means the backend predates it.
      throw new Error(
        `${path} is not in the running backend — restart the Hermes gateway/dashboard ` +
        'to load the current plugin code (the gap report keeps working until then)'
      )
    }
    if (!res.ok) throw new Error(`${path} HTTP ${res.status}`)
    return res.json()
  }

  return {
    report: () => rest('/report?format=json'),
    recommend: (days, force) =>
      rest('/recommend', { method: 'POST', body: JSON.stringify({ days, force: !!force }) }),
    cached: days => rest(`/recommend?days=${days}`),
    contributions: days => rest(`/contributions?days=${days}`),
    packageSkill: (name, days) =>
      rest('/contributions/package', { method: 'POST', body: JSON.stringify({ name, days }) })
  }
}

// ---------- visual primitives

function level(count, max) {
  if (!count) return 0
  const ratio = count / Math.max(1, max)
  if (ratio > 0.75) return 4
  if (ratio > 0.45) return 3
  if (ratio > 0.18) return 2
  return 1
}

function cellColor(step) {
  if (!step) return 'color-mix(in srgb, var(--ui-text-quaternary) 22%, transparent)'
  const mix = [0, 30, 52, 74, 100][step]
  return `color-mix(in srgb, var(--ui-accent) ${mix}%, var(--ui-bg-tertiary))`
}

function Field({ cells, max }) {
  if (!cells || !cells.length) return jsx('div', { className: 'text-sm text-(--ui-text-tertiary)', children: 'No days to show.' })
  const pad = cells[0].weekday
  const padded = Array.from({ length: pad }, () => null).concat(cells)
  const cols = []
  for (let i = 0; i < padded.length; i += 7) cols.push(padded.slice(i, i + 7))
  return jsxs('div', {
    className: 'flex gap-1',
    children: [
      jsx('div', {
        className: 'mr-1 flex flex-col justify-between py-0.5 text-[0.62rem] text-(--ui-text-quaternary)',
        children: WEEKDAYS.map((d, i) => jsx('div', {
          key: d,
          style: { height: '13px', lineHeight: '13px' },
          children: i % 2 === 0 ? d : ''
        }, d))
      }),
      jsx('div', {
        className: 'flex gap-1',
        children: cols.map((col, ci) => jsx('div', {
          key: ci,
          className: 'flex flex-col gap-1',
          children: col.map((cell, ri) => jsx('div', {
            key: `${ci}-${ri}`,
            title: cell ? `${cell.date} — ${cell.count} gap${cell.count === 1 ? '' : 's'}` : '',
            style: {
              width: '13px',
              height: '13px',
              borderRadius: '3px',
              background: cell ? cellColor(level(cell.count, max)) : 'transparent'
            }
          }, `${ci}-${ri}`))
        }, ci))
      })
    ]
  })
}

function Stat({ label, value, hint }) {
  return jsxs('div', {
    className: 'min-w-0',
    children: [
      jsx('div', { className: 'truncate text-[0.68rem] text-(--ui-text-tertiary)', children: label }),
      jsx('div', { className: 'mt-1 truncate text-[1.2rem] font-medium leading-none text-foreground', children: value }),
      jsx('div', { className: 'mt-1.5 truncate text-[0.68rem] text-(--ui-text-quaternary)', children: hint || '' })
    ]
  })
}

function SourceBadge({ source }) {
  const label = source === 'statedb' ? 'state.db' : source === 'backfill' ? 'transcripts' : 'live'
  return jsx('span', {
    className: 'rounded px-1 text-[0.6rem] uppercase tracking-wide text-(--ui-text-tertiary)',
    style: { border: '1px solid var(--ui-stroke-tertiary)' },
    children: label
  })
}

function GapRow({ gap, rank }) {
  return jsxs('div', {
    className: 'flex items-baseline gap-3 border-b py-1.5',
    style: { borderColor: 'var(--ui-stroke-tertiary)' },
    children: [
      jsx('span', { className: 'w-5 shrink-0 text-right text-[0.68rem] text-(--ui-text-quaternary)', children: rank }),
      jsx('span', { className: 'w-10 shrink-0 text-right font-mono text-[0.72rem] text-(--ui-text-secondary)', children: `${gap.seen}×` }),
      jsx('span', { className: 'min-w-0 flex-1 truncate font-mono text-[0.74rem] text-foreground', children: gap.signature }),
      jsx('span', { className: 'shrink-0 text-[0.66rem] text-(--ui-text-quaternary)', children: `${gap.sessions || 1} sess` }),
      jsx(SourceBadge, { source: gap.source })
    ]
  })
}

// ---------- recommend panel (button one)

const RANGES = [
  { days: 7, label: '7 days' },
  { days: 14, label: '14 days' },
  { days: 30, label: '30 days' }
]

function Evidence({ item }) {
  return jsxs('div', {
    className: 'mt-1 border-l pl-2',
    style: { borderColor: 'var(--ui-stroke-tertiary)' },
    children: [
      jsx('div', { className: 'font-mono text-[0.68rem] text-(--ui-text-tertiary)', children: `“${item.quote}”` }),
      jsx('div', { className: 'text-[0.62rem] text-(--ui-text-quaternary)', children: `${item.date} · ${item.session_id}` })
    ]
  })
}

function RecCard({ rec }) {
  const fix = rec.fix || {}
  const fixLine =
    fix.kind === 'install'
      ? `hermes plugins install ${fix.plugin}`
      : fix.kind === 'installed'
        ? `${fix.plugin} is already installed`
        : fix.kind === 'related'
          ? fix.note
          : 'no catalog plugin covers this — candidate for a contribution'
  return jsxs('div', {
    className: 'rounded border p-3',
    style: { borderColor: 'var(--ui-stroke-tertiary)' },
    children: [
      jsxs('div', {
        className: 'flex items-baseline justify-between gap-3',
        children: [
          jsx('div', { className: 'text-[0.82rem] font-medium text-foreground', children: rec.title }),
          jsx('div', {
            className: 'shrink-0 text-[0.62rem] uppercase tracking-wide text-(--ui-text-quaternary)',
            children: rec.evidence_strength === 'recurring'
              ? `${rec.occurrences} sessions`
              : 'single session'
          })
        ]
      }),
      jsx('div', { className: 'mt-1 text-[0.74rem] text-(--ui-text-secondary)', children: rec.job }),
      rec.why_plugin
        ? jsx('div', { className: 'mt-1 text-[0.70rem] text-(--ui-text-tertiary)', children: rec.why_plugin })
        : null,
      jsx('div', { className: 'mt-2', children: (rec.evidence || []).map((e, i) => jsx(Evidence, { item: e }, i)) }),
      jsx('div', {
        className: 'mt-2 font-mono text-[0.68rem]',
        style: { color: fix.kind === 'install' ? 'var(--ui-accent)' : 'var(--ui-text-tertiary)' },
        children: fixLine
      })
    ]
  })
}

function RecommendPanel() {
  const [days, setDays] = useState(7)
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    let live = true
    RecommendPanel.__api
      .cached(days)
      .then(payload => { if (live && payload && payload.cached) setResult(payload) })
      .catch(() => {})
    return () => { live = false }
  }, [days])

  function run(force) {
    setBusy(true)
    setError('')
    RecommendPanel.__api
      .recommend(days, force)
      .then(payload => { setResult(payload); if (payload && payload.ok === false) setError(payload.error || 'no result') })
      .catch(err => setError(String(err && err.message ? err.message : err)))
      .finally(() => setBusy(false))
  }

  const recs = (result && result.recommendations) || []
  const dropped = (result && result.dropped) || []

  return jsxs('div', {
    className: 'rounded border p-3',
    style: { borderColor: 'var(--ui-stroke-secondary)' },
    children: [
      jsxs('div', {
        className: 'flex flex-wrap items-center justify-between gap-3',
        children: [
          jsxs('div', {
            children: [
              jsx('div', { className: 'text-sm font-medium text-foreground', children: 'Where a plugin would have saved you work' }),
              jsx('div', {
                className: 'mt-0.5 text-[0.68rem] text-(--ui-text-quaternary)',
                children: 'reads your real sessions · every claim carries a quote from the log · nothing is installed'
              })
            ]
          }),
          jsxs('div', {
            className: 'flex items-center gap-1',
            children: [
              ...RANGES.map(r =>
                jsx('button', {
                  key: r.days,
                  onClick: () => setDays(r.days),
                  className: 'rounded px-2 py-1 text-[0.68rem]',
                  style: {
                    border: '1px solid var(--ui-stroke-tertiary)',
                    color: days === r.days ? 'var(--ui-text-primary)' : 'var(--ui-text-tertiary)',
                    background: days === r.days ? 'var(--ui-bg-tertiary)' : 'transparent'
                  },
                  children: r.label
                }, r.days)
              ),
              jsx('button', {
                onClick: () => run(!!result),
                disabled: busy,
                className: 'ml-1 shrink-0 rounded px-3 py-1 text-[0.7rem] font-medium',
                style: {
                  background: 'color-mix(in srgb, var(--ui-accent) 20%, transparent)',
                  border: '1px solid color-mix(in srgb, var(--ui-accent) 62%, transparent)',
                  color: 'var(--ui-text-primary)',
                  whiteSpace: 'nowrap',
                  opacity: busy ? 0.6 : 1,
                  cursor: busy ? 'default' : 'pointer'
                },
                children: busy ? 'Reading…' : result ? 'Recommend again' : 'Recommend me a plugin'
              })
            ]
          })
        ]
      }),
      error
        ? jsxs('div', {
            className: 'mt-3 rounded p-2 text-[0.7rem]',
            style: { background: 'var(--ui-bg-tertiary)', color: 'var(--ui-text-secondary)' },
            children: [
              jsx('div', { children: error }),
              result && result.fallback
                ? jsx('div', { className: 'mt-1 font-mono text-[0.66rem] text-(--ui-text-quaternary)', children: `ask the agent to run ${result.fallback}` })
                : null
            ]
          })
        : null,
      recs.length
        ? jsxs('div', {
            className: 'mt-3 flex flex-col gap-2',
            children: [
              ...recs.map((rec, i) => jsx(RecCard, { rec }, i)),
              jsxs('div', {
                className: 'flex justify-between text-[0.62rem] text-(--ui-text-quaternary)',
                children: [
                  jsx('div', {
                    children: `${result.stats.sessions} sessions · ${result.stats.tool_calls} tool calls · ${result.llm && result.llm.model ? result.llm.model : 'model'}${result.cached ? ' · cached' : ''}`
                  }),
                  jsx('div', {
                    children: dropped.length
                      ? `${dropped.length} suggestion${dropped.length === 1 ? '' : 's'} discarded — evidence not found in the log`
                      : ''
                  })
                ]
              })
            ]
          })
        : null,
      !recs.length && !error && !busy && result && result.ok === false && result.reason
        ? jsx('div', { className: 'mt-2 text-[0.7rem] text-(--ui-text-tertiary)', children: result.reason })
        : null
    ]
  })
}

RecommendPanel.__api = null

// ---------- page

function ScoutPage() {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    let live = true
    ScoutPage.__api.report()
      .then(payload => { if (live) setData(payload) })
      .catch(err => { if (live) setError(String(err && err.message ? err.message : err)) })
    return () => { live = false }
  }, [])

  if (error) {
    return jsxs('div', {
      className: 'p-6',
      children: [
        jsx('div', { className: 'text-sm font-medium text-foreground', children: 'Scout could not read its backend' }),
        jsx('div', { className: 'mt-1 text-xs text-(--ui-text-tertiary)', children: error }),
        jsx('div', { className: 'mt-3 font-mono text-xs text-(--ui-text-secondary)', children: 'python3 cli.py report' })
      ]
    })
  }
  if (!data) return jsx('div', { className: 'p-6 text-sm text-(--ui-text-tertiary)', children: 'Reading the ledger…' })

  const field = data.field || { cells: [], max: 0, total: 0, active_days: 0 }
  const sources = data.sources || {}

  return jsxs('div', {
    className: 'flex flex-col gap-6 p-5',
    children: [
      jsx('div', {
        className: 'flex items-baseline justify-between',
        children: [
          jsx('div', { className: 'text-sm font-medium text-foreground', children: 'Capability field' }),
          jsx('div', {
            className: 'text-[0.68rem] text-(--ui-text-quaternary)',
            children: `${field.start} → ${field.end} · last ${field.days} days`
          })
        ]
      }),
      jsx(Field, { cells: field.cells, max: field.max }),
      jsxs('div', {
        className: 'grid grid-cols-3 gap-4 rounded border p-3',
        style: { borderColor: 'var(--ui-stroke-tertiary)' },
        children: [
          jsx(Stat, { label: 'gap events', value: String(field.total), hint: 'measured, not inferred' }),
          jsx(Stat, { label: 'active days', value: String(field.active_days), hint: `peak ${field.max}/day` }),
          jsx(Stat, { label: 'peak day', value: String(field.max), hint: 'most gaps in one day' }),
          jsx(Stat, { label: 'sources', value: String(Object.keys(sources).length), hint: Object.keys(sources).join(' · ') || 'none yet' })
        ]
      }),
      jsx(RecommendPanel, {}),
      jsx(ContributionsPanel, {})
    ]
  })
}

// ---------- contributions panel (button two)

const CONTRIB_RANGES = [30, 60, 90]

const VERDICT_LABEL = {
  publish: 'publish',
  scrub: 'needs scrub',
  thin: 'too thin',
  already_covered: 'already covered',
  private: 'keep private'
}

function VerdictChip({ verdict }) {
  const isPublish = verdict === 'publish'
  const isScrub = verdict === 'scrub'
  return jsx('span', {
    className: 'shrink-0 rounded px-1.5 py-0.5 text-[0.58rem] uppercase tracking-wide',
    style: {
      border: `1px solid ${isPublish || isScrub
        ? 'color-mix(in srgb, var(--ui-accent) 55%, transparent)'
        : 'var(--ui-stroke-tertiary)'}`,
      color: isPublish ? 'var(--ui-accent)' : 'var(--ui-text-tertiary)'
    },
    children: VERDICT_LABEL[verdict] || verdict
  })
}

function ContributionCard({ item, days }) {
  const [staged, setStaged] = useState(null)
  const [busy, setBusy] = useState(false)

  function stage() {
    setBusy(true)
    ContributionsPanel.__api
      .packageSkill(item.name, days)
      .then(out => setStaged(out))
      .catch(err => setStaged({ ok: false, error: String(err && err.message ? err.message : err) }))
      .finally(() => setBusy(false))
  }

  const canStage = item.verdict === 'publish' || item.verdict === 'scrub'
  const markers = (item.markers || []).slice(0, 3)
    .map(m => `${m.kind}:${m.line} ${m.text}`)
    .join('   ·   ')

  return jsxs('div', {
    className: 'rounded border p-3',
    style: { borderColor: 'var(--ui-stroke-tertiary)' },
    children: [
      jsxs('div', {
        className: 'flex items-baseline justify-between gap-3',
        children: [
          jsxs('div', {
            className: 'flex min-w-0 items-center gap-2',
            children: [
              jsx('div', { className: 'truncate text-[0.8rem] font-medium text-foreground', children: item.name }),
              jsx(VerdictChip, { verdict: item.verdict }),
              jsx('span', {
                className: 'shrink-0 text-[0.58rem] uppercase tracking-wide text-(--ui-text-quaternary)',
                children: item.contribute_as === 'plugin' ? 'as plugin' : 'as skill'
              })
            ]
          }),
          jsx('div', { className: 'shrink-0 text-[0.6rem] text-(--ui-text-quaternary)', children: item.created || '' })
        ]
      }),
      jsx('div', { className: 'mt-1 text-[0.7rem] text-(--ui-text-secondary)', children: item.description }),
      jsx('div', {
        className: 'mt-1.5 flex flex-col gap-0.5',
        children: (item.reasons || []).map((r, i) =>
          jsx('div', { className: 'text-[0.66rem] text-(--ui-text-tertiary)', children: `· ${r}` }, i))
      }),
      markers
        ? jsx('div', { className: 'mt-1.5 truncate font-mono text-[0.62rem] text-(--ui-text-quaternary)', children: markers })
        : null,
      canStage
        ? jsxs('div', {
            className: 'mt-2 flex items-center gap-2',
            children: [
              jsx('button', {
                onClick: stage,
                disabled: busy,
                className: 'shrink-0 rounded px-2 py-1 text-[0.64rem]',
                style: {
                  border: '1px solid var(--ui-stroke-secondary)',
                  color: 'var(--ui-text-secondary)',
                  whiteSpace: 'nowrap',
                  cursor: busy ? 'default' : 'pointer'
                },
                children: busy ? 'Staging…' : 'Stage for submission'
              }),
              staged
                ? jsx('span', {
                    className: 'truncate font-mono text-[0.62rem]',
                    style: { color: staged.ok ? 'var(--ui-text-tertiary)' : 'var(--ui-text-quaternary)' },
                    children: staged.ok ? staged.dir : (staged.error || 'failed')
                  })
                : null
            ]
          })
        : null
    ]
  })
}

function ContributionsPanel() {
  const [days, setDays] = useState(60)
  const [data, setData] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    let live = true
    setBusy(true)
    ContributionsPanel.__api
      .contributions(days)
      .then(payload => {
        if (!live) return
        setData(payload)
        setError(payload && payload.ok === false ? payload.error || 'scan failed' : '')
      })
      .catch(err => { if (live) setError(String(err && err.message ? err.message : err)) })
      .finally(() => { if (live) setBusy(false) })
    return () => { live = false }
  }, [days])

  const items = (data && data.candidates) || []
  const counts = (data && data.counts) || {}

  return jsxs('div', {
    className: 'rounded border p-3',
    style: { borderColor: 'var(--ui-stroke-secondary)' },
    children: [
      jsxs('div', {
        className: 'flex flex-wrap items-center justify-between gap-3',
        children: [
          jsxs('div', {
            children: [
              jsx('div', { className: 'text-sm font-medium text-foreground', children: 'Skills worth sharing' }),
              jsx('div', {
                className: 'mt-0.5 text-[0.68rem] text-(--ui-text-quaternary)',
                children: 'written by the agent itself · screened for private paths, hosts and accounts · nothing is published'
              })
            ]
          }),
          jsxs('div', {
            className: 'flex items-center gap-1',
            children: [
              ...CONTRIB_RANGES.map(d =>
                jsx('button', {
                  key: d,
                  onClick: () => setDays(d),
                  className: 'rounded px-2 py-1 text-[0.66rem]',
                  style: {
                    border: '1px solid var(--ui-stroke-tertiary)',
                    color: days === d ? 'var(--ui-text-primary)' : 'var(--ui-text-tertiary)',
                    background: days === d ? 'var(--ui-bg-tertiary)' : 'transparent',
                    whiteSpace: 'nowrap'
                  },
                  children: `${d}d`
                }, d)
              ),
              jsx('span', {
                className: 'ml-1 text-[0.64rem] text-(--ui-text-quaternary)',
                children: busy ? 'scanning…' : `${items.length} shown`
              })
            ]
          })
        ]
      }),
      error
        ? jsx('div', { className: 'mt-2 text-[0.68rem] text-(--ui-text-tertiary)', children: error })
        : null,
      items.length
        ? jsx('div', {
            className: 'mt-3 flex flex-col gap-2',
            children: items.slice(0, 8).map((item, i) => jsx(ContributionCard, { item, days }, `${item.name}-${i}`))
          })
        : null,
      jsxs('div', {
        className: 'mt-2 flex justify-between text-[0.6rem] text-(--ui-text-quaternary)',
        children: [
          jsx('div', {
            children: `${(data && data.total_agent_skills) || 0} agent-written · ${counts.publish || 0} publishable · ${counts.scrub || 0} need scrubbing · ${counts.private || 0} keep private`
          }),
          jsx('div', { children: 'deterministic screen — no tokens spent' })
        ]
      })
    ]
  })
}

ContributionsPanel.__api = null

// The loader is injected at register() time, where ctx.rest exists.
ScoutPage.__api = null

function ScoutChip() {
  const [count, setCount] = useState(null)
  useEffect(() => {
    let live = true
    ScoutChip.__api.report()
      .then(payload => { if (live) setCount(payload && payload.gaps ? payload.gaps.total : 0) })
      .catch(() => { if (live) setCount(null) })
    return () => { live = false }
  }, [])
  return jsx('button', {
    className: 'inline-flex h-full items-center px-1.5 text-[0.6875rem] text-(--ui-text-tertiary) hover:text-foreground',
    title: 'Open Scout — capability gaps',
    onClick: () => host.navigate(ROUTE),
    children: count == null ? 'Scout' : `${count} gaps`
  })
}

ScoutChip.__api = null

export default {
  id: ID,
  name: 'Scout',
  register(ctx) {
    const api = makeApi(ctx)
    ScoutPage.__api = api
    ScoutChip.__api = api
    RecommendPanel.__api = api
    ContributionsPanel.__api = api
    ctx.register({ id: 'page', area: ROUTES_AREA, data: { path: ROUTE }, render: () => jsx(ScoutPage, {}) })
    ctx.register({
      id: 'nav',
      area: SIDEBAR_NAV_AREA,
      order: 86,
      data: { path: ROUTE, label: 'Scout', codicon: 'pulse' }
    })
    ctx.register({
      id: 'open',
      area: PALETTE_AREA,
      data: {
        id: 'pluginscout.open',
        label: 'Open Scout',
        keywords: ['gaps', 'capability', 'plugins', 'recommend'],
        run: () => host.navigate(ROUTE)
      }
    })
    ctx.register({ id: 'chip', area: STATUSBAR_AREAS.right, order: 121, render: () => jsx(ScoutChip, {}) })
  }
}