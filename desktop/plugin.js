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
// fallback for a host where the scoped client is not wired.
function makeLoader(ctx) {
  return async function loadReport() {
    if (ctx && typeof ctx.rest === 'function') {
      return parseMaybe(await ctx.rest('/report?format=json'))
    }
    const res = await fetch('/api/plugins/pluginscout/report?format=json', { credentials: 'same-origin' })
    if (!res.ok) throw new Error(`report HTTP ${res.status}`)
    return res.json()
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

// ---------- page

function ScoutPage() {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    let live = true
    ScoutPage.__load()
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
  const gaps = (data.gaps && data.gaps.top) || []
  const sources = data.sources || {}
  const top = gaps[0]

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
        className: 'grid grid-cols-4 gap-4 rounded border p-3',
        style: { borderColor: 'var(--ui-stroke-tertiary)' },
        children: [
          jsx(Stat, { label: 'gap events', value: String(field.total), hint: 'measured, not inferred' }),
          jsx(Stat, { label: 'active days', value: String(field.active_days), hint: `peak ${field.max}/day` }),
          jsx(Stat, { label: 'things lacking', value: String((data.gaps && data.gaps.total) || 0), hint: `${(data.gaps && data.gaps.events) || 0} occurrences` }),
          jsx(Stat, { label: 'sources', value: String(Object.keys(sources).length), hint: Object.keys(sources).join(' · ') || 'none yet' })
        ]
      }),
      jsxs('div', {
        children: [
          jsx('div', { className: 'mb-2 text-sm font-medium text-foreground', children: 'What keeps going missing' }),
          gaps.slice(0, 10).map((gap, i) => jsx(GapRow, { gap, rank: i + 1 }, gap.signature))
        ]
      }),
      top
        ? jsx('div', {
            className: 'rounded border p-3 text-xs text-(--ui-text-tertiary)',
            style: { borderColor: 'var(--ui-stroke-tertiary)' },
            children: `Most-reached-for: ${top.signature} — ${top.seen} times across ${top.sessions || 1} session(s).`
          })
        : null
    ]
  })
}

// The loader is injected at register() time, where ctx.rest exists.
ScoutPage.__load = async () => { throw new Error('loader not wired') }

function ScoutChip() {
  const [count, setCount] = useState(null)
  useEffect(() => {
    let live = true
    ScoutChip.__load()
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

ScoutChip.__load = async () => { throw new Error('loader not wired') }

export default {
  id: ID,
  name: 'Scout',
  register(ctx) {
    const load = makeLoader(ctx)
    ScoutPage.__load = load
    ScoutChip.__load = load
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
