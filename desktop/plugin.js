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
const PAGE_ENV = { os: null }

function openExternal(url) {
  if (!url) return
  if (PAGE_ENV.os && typeof PAGE_ENV.os.openExternal === 'function') {
    PAGE_ENV.os.openExternal(url)
    return
  }
  window.open(url, '_blank', 'noopener,noreferrer')
}

function Link({ href, children }) {
  return jsx('button', {
    onClick: () => openExternal(href),
    style: { color: 'var(--ui-accent)', background: 'none', border: 'none', padding: 0, cursor: 'pointer' },
    className: 'text-[0.66rem] hover:underline',
    children
  })
}
const ROUTE = '/pluginscout'

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
    contributions: days => rest(`/contributions?days=${days}`),
    packageSkill: (name, days) =>
      rest('/contributions/package', { method: 'POST', body: JSON.stringify({ name, days }) }),
    submitSkill: (name, days) =>
      rest('/contributions/submit', { method: 'POST', body: JSON.stringify({ name, days }) }),
    submitAll: days =>
      rest('/contributions/submit-all', { method: 'POST', body: JSON.stringify({ days }) })
  }
}

// ---------- page

function ScoutPage() {
  return jsx('div', {
    className: 'flex flex-col gap-4 p-5',
    children: [jsx(ContributionsPanel, {})]
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

  function submit() {
    setBusy(true)
    ContributionsPanel.__api
      .submitSkill(item.name, days)
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
            className: 'mt-2 flex flex-wrap items-center gap-2',
            children: [
              jsx('button', {
                onClick: submit,
                disabled: busy,
                className: 'shrink-0 rounded px-2.5 py-1 text-[0.66rem] font-medium',
                style: {
                  background: 'color-mix(in srgb, var(--ui-accent) 20%, transparent)',
                  border: '1px solid color-mix(in srgb, var(--ui-accent) 62%, transparent)',
                  color: 'var(--ui-text-primary)',
                  whiteSpace: 'nowrap',
                  cursor: busy ? 'default' : 'pointer'
                },
                children: busy ? 'Preparing…' : 'Prepare submission'
              }),
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
                children: 'Scrubbed copy only'
              })
            ]
          })
        : null,
      staged
        ? jsxs('div', {
            className: 'mt-2 rounded p-2',
            style: { background: 'var(--ui-bg-tertiary)' },
            children: [
              jsx('div', {
                className: 'truncate font-mono text-[0.62rem]',
                style: { color: staged.ok ? 'var(--ui-text-secondary)' : 'var(--ui-text-quaternary)' },
                children: staged.ok ? staged.dir : (staged.error || 'failed')
              }),
              staged.ok && staged.files
                ? jsx('div', {
                    className: 'mt-1 font-mono text-[0.6rem] text-(--ui-text-quaternary)',
                    children: staged.files.join('  ·  ')
                  })
                : null,
              staged.validation
                ? jsx('div', {
                    className: 'mt-1 font-mono text-[0.6rem]',
                    style: { color: staged.validation.ok ? 'var(--ui-accent)' : 'var(--ui-text-tertiary)' },
                    children: staged.validation.ok
                      ? 'hermes plugins validate: PASS'
                      : `blocked — ${(staged.validation.output || []).filter(l => l.includes('✗')).join(' ') || 'validation failed'}`
                  })
                : null,
              (staged.steps || []).length
                ? jsx('div', {
                    className: 'mt-1.5 flex flex-col gap-0.5',
                    children: staged.steps.map((s, i) =>
                      jsx('div', { className: 'font-mono text-[0.6rem] text-(--ui-text-tertiary)', children: `${i + 1}. ${s}` }, i))
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
  const [batch, setBatch] = useState(null)
  const [batchBusy, setBatchBusy] = useState(false)

  function prepareAll() {
    setBatchBusy(true)
    ContributionsPanel.__api
      .submitAll(days)
      .then(out => setBatch(out))
      .catch(err => setBatch({ ok: false, error: String(err && err.message ? err.message : err) }))
      .finally(() => setBatchBusy(false))
  }

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
              }),
              jsx('button', {
                onClick: prepareAll,
                disabled: batchBusy || !items.length,
                className: 'ml-2 shrink-0 rounded px-2.5 py-1 text-[0.66rem] font-medium',
                style: {
                  background: 'color-mix(in srgb, var(--ui-accent) 20%, transparent)',
                  border: '1px solid color-mix(in srgb, var(--ui-accent) 62%, transparent)',
                  color: 'var(--ui-text-primary)',
                  whiteSpace: 'nowrap',
                  cursor: batchBusy ? 'default' : 'pointer',
                  opacity: items.length ? 1 : 0.5
                },
                children: batchBusy ? 'Preparing…' : 'Prepare all'
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
      batch
        ? jsx('div', {
            className: 'mt-2 rounded px-2 py-1 font-mono text-[0.62rem]',
            style: { background: 'var(--ui-bg-tertiary)', color: 'var(--ui-text-secondary)' },
            children: batch.ok
              ? `${batch.total} prepared · ${batch.passed} passed validate · ${batch.total - batch.passed} blocked · ${Object.entries(batch.skipped || {}).map(([k, v]) => v + ' ' + k).join(', ')}`

              : (batch.error || 'batch failed')
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
    ScoutChip.__api.contributions(60)
      .then(payload => {
        if (!live) return
        const publishable = payload && payload.counts ? payload.counts.publish : 0
        setCount(publishable || 0)
      })
      .catch(() => { if (live) setCount(null) })
    return () => { live = false }
  }, [])
  return jsx('button', {
    className: 'inline-flex h-full items-center px-1.5 text-[0.6875rem] text-(--ui-text-tertiary) hover:text-foreground',
    title: 'Open Scout — package your skills for the marketplace',
    onClick: () => host.navigate(ROUTE),
    children: count == null ? 'Scout' : `${count} to share`
  })
}

ScoutChip.__api = null

export default {
  id: ID,
  name: 'Scout',
  register(ctx) {
    PAGE_ENV.os = (ctx && ctx.os) || null
    const api = makeApi(ctx)
    ScoutPage.__api = api
    ScoutChip.__api = api
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
        keywords: ['skills', 'marketplace', 'submit', 'catalog', 'contribution'],
        run: () => host.navigate(ROUTE)
      }
    })
    ctx.register({ id: 'chip', area: STATUSBAR_AREAS.right, order: 121, render: () => jsx(ScoutChip, {}) })
  }
}