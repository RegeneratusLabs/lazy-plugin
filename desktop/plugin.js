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
    readiness: () => rest('/readiness'),
    preparePlugin: name =>
      rest('/readiness/prepare', { method: 'POST', body: JSON.stringify({ name }) })
  }
}

// ---------- page

function ScoutPage() {
  return jsx('div', {
    className: 'flex flex-col gap-4 p-5',
    children: [jsx(ReadinessPanel, {})]
  })
}

// ---------- page

const STATUS_STYLE = {
  ready: { label: 'ready to submit', color: 'var(--ui-accent)' },
  blocked: { label: 'blocked', color: 'var(--ui-text-tertiary)' },
  listed: { label: 'in catalog', color: 'var(--ui-text-quaternary)' }
}

function CheckLine({ item }) {
  return jsxs('div', {
    className: 'flex items-baseline gap-1.5 text-[0.64rem]',
    children: [
      jsx('span', { style: { color: item.ok ? 'var(--ui-accent)' : 'var(--ui-text-quaternary)' }, children: item.ok ? '✓' : '✗' }),
      jsx('span', { className: 'text-(--ui-text-tertiary)', children: item.check }),
      jsx('span', { className: 'truncate text-(--ui-text-quaternary)', children: item.detail })
    ]
  })
}

function PluginRow({ item }) {
  const [out, setOut] = useState(null)
  const [busy, setBusy] = useState(false)
  const status = item.in_catalog ? 'listed' : item.ready ? 'ready' : 'blocked'
  const style = STATUS_STYLE[status]

  function prepare() {
    setBusy(true)
    ReadinessPanel.__api
      .preparePlugin(item.name)
      .then(res => setOut(res))
      .catch(err => setOut({ ok: false, error: String(err && err.message ? err.message : err) }))
      .finally(() => setBusy(false))
  }

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
              jsx('span', { className: 'truncate text-[0.8rem] font-medium text-foreground', children: item.name }),
              jsx('span', { className: 'shrink-0 text-[0.58rem] uppercase tracking-wide', style: { color: style.color }, children: style.label }),
              item.tier
                ? jsx('span', { className: 'shrink-0 text-[0.58rem] text-(--ui-text-quaternary)', children: item.tier })
                : null
            ]
          }),
          !item.in_catalog
            ? jsx('button', {
                onClick: prepare,
                disabled: busy,
                className: 'shrink-0 rounded px-2.5 py-1 text-[0.64rem] font-medium',
                style: {
                  background: 'color-mix(in srgb, var(--ui-accent) 20%, transparent)',
                  border: '1px solid color-mix(in srgb, var(--ui-accent) 62%, transparent)',
                  color: 'var(--ui-text-primary)',
                  whiteSpace: 'nowrap',
                  cursor: busy ? 'default' : 'pointer'
                },
                children: busy ? 'Writing…' : 'Prepare catalog entry'
              })
            : null
        ]
      }),
      jsx('div', {
        className: 'mt-1.5 flex flex-col gap-0.5',
        children: (item.blockers || []).map((b, i) =>
          jsx('div', { className: 'text-[0.66rem]', style: { color: 'var(--ui-text-tertiary)' }, children: `✗ ${b}` }, `b${i}`))
      }),
      jsx('div', {
        className: 'mt-1 flex flex-col gap-0.5',
        children: (item.review || []).map((r, i) =>
          jsx('div', { className: 'text-[0.64rem] text-(--ui-text-quaternary)', children: `· ${r}` }, `r${i}`))
      }),
      (item.checks || []).length
        ? jsx('details', {
            className: 'mt-1.5',
            children: [
              jsx('summary', { className: 'cursor-pointer text-[0.62rem] text-(--ui-text-quaternary)', children: `${item.checks.length} checks` }),
              jsx('div', { className: 'mt-1 flex flex-col gap-0.5', children: (item.checks || []).map((c, i) => jsx(CheckLine, { item: c }, i)) })
            ]
          })
        : null,
      out
        ? jsxs('div', {
            className: 'mt-2 rounded p-2',
            style: { background: 'var(--ui-bg-tertiary)' },
            children: [
              jsx('div', { className: 'truncate font-mono text-[0.62rem] text-(--ui-text-secondary)', children: out.ok ? out.dir : (out.error || 'failed') }),
              out.ok ? jsx('div', { className: 'mt-1 font-mono text-[0.6rem] text-(--ui-text-quaternary)', children: (out.files || []).join('  ·  ') }) : null
            ]
          })
        : null
    ]
  })
}

function ReadinessPanel() {
  const [data, setData] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [showListed, setShowListed] = useState(false)

  useEffect(() => {
    let live = true
    setBusy(true)
    ReadinessPanel.__api
      .readiness()
      .then(payload => { if (live) { setData(payload); setError(payload && payload.ok === false ? payload.error || 'audit failed' : '') } })
      .catch(err => { if (live) setError(String(err && err.message ? err.message : err)) })
      .finally(() => { if (live) setBusy(false) })
    return () => { live = false }
  }, [])

  const plugins = (data && data.plugins) || []
  const unlisted = plugins.filter(p => !p.in_catalog)
  const ready = unlisted.filter(p => p.ready).length
  const listed = plugins.filter(p => p.in_catalog)

  return jsxs('div', {
    className: 'rounded border p-3',
    style: { borderColor: 'var(--ui-stroke-secondary)' },
    children: [
      jsxs('div', {
        className: 'flex flex-wrap items-center justify-between gap-3',
        children: [
          jsxs('div', {
            children: [
              jsx('div', { className: 'text-sm font-medium text-foreground', children: 'Plugins you could submit' }),
              jsx('div', {
                className: 'mt-0.5 text-[0.68rem] text-(--ui-text-quaternary)',
                children: 'every installed plugin against the catalog admission rules · nothing is pushed'
              })
            ]
          }),
          jsxs('div', {
            className: 'flex items-center gap-1 text-[0.64rem] text-(--ui-text-quaternary)',
            children: [
              jsx('span', { children: busy ? 'auditing…' : `${unlisted.length} not listed` }),
              jsx('span', { children: '·' }),
              jsx('span', { style: { color: 'var(--ui-accent)' }, children: `${ready} ready` }),
              jsx('span', { children: '·' }),
              jsx('span', { children: `${unlisted.length - ready} blocked` })
            ]
          })
        ]
      }),
      error ? jsx('div', { className: 'mt-2 text-[0.68rem] text-(--ui-text-tertiary)', children: error }) : null,
      jsx('div', {
        className: 'mt-3 flex flex-col gap-2',
        children: unlisted.map(p => jsx(PluginRow, { item: p }, p.name))
      }),
      listed.length
        ? jsxs('div', {
            className: 'mt-3',
            children: [
              jsx('button', {
                onClick: () => setShowListed(!showListed),
                className: 'text-[0.64rem] text-(--ui-text-quaternary)',
                style: { background: 'none', border: 'none', cursor: 'pointer', padding: 0 },
                children: `${showListed ? '▾' : '▸'} ${listed.length} already in the catalog`
              }),
              showListed
                ? jsx('div', { className: 'mt-2 flex flex-col gap-2', children: listed.map(p => jsx(PluginRow, { item: p }, p.name)) })
                : null
            ]
          })
        : null
    ]
  })
}

ReadinessPanel.__api = null

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
    ReadinessPanel.__api = api
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