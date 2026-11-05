import {
  PALETTE_AREA,
  ROUTES_AREA,
  SIDEBAR_NAV_AREA,
  STATUSBAR_AREAS,
  host
} from '@hermes/plugin-sdk'
import { useEffect, useState } from 'react'
import { jsx, jsxs } from 'react/jsx-runtime'

const ID = 'lazy-plugin'
const ROUTE = '/lazy-plugin'

const KIND_LABEL = {
  command: 'runs a command',
  http: 'calls an endpoint',
  file: 'reads/writes a path',
  stub: 'scaffold'
}

function makeApi(ctx) {
  const base = `/api/plugins/${ID}`
  const rest = async (path, options) => {
    if (ctx && ctx.rest) return ctx.rest(path, options)
    const response = await fetch(base + path, {
      headers: { 'content-type': 'application/json' },
      ...(options || {})
    })
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    return response.json()
  }
  return {
    sources: () => rest('/sources'),
    created: () => rest('/created'),
    create: payload => rest('/create', { method: 'POST', body: JSON.stringify(payload) })
  }
}

function ToolLine({ tool }) {
  return jsxs('div', {
    className: 'flex items-baseline gap-2 text-[0.68rem]',
    children: [
      jsx('span', { className: 'font-mono text-(--ui-text-secondary)', children: tool.name }),
      jsx('span', {
        className: 'shrink-0 text-[0.6rem] uppercase tracking-wide text-(--ui-text-quaternary)',
        children: KIND_LABEL[tool.kind] || tool.kind
      }),
      jsx('span', { className: 'truncate text-(--ui-text-quaternary)', children: tool.description })
    ]
  })
}

function Built({ out }) {
  const check = out.validation || {}
  const meta = (out.draft && out.draft.meta) || {}
  const metaLine = [meta.lane ? `${meta.lane} lane` : null,
    meta.model ? meta.model : null,
    meta.tokens ? `${meta.tokens} tokens` : null,
    out.source && out.source.name ? `from ${out.source.kind}: ${out.source.name}` : null]
    .filter(Boolean).join(' · ')

  return jsxs('div', {
    className: 'mt-3 rounded border p-3',
    style: { borderColor: 'var(--ui-stroke-secondary)' },
    children: [
      jsxs('div', {
        className: 'flex flex-wrap items-baseline justify-between gap-2',
        children: [
          jsxs('div', {
            className: 'flex items-baseline gap-2',
            children: [
              jsx('span', { className: 'text-[0.85rem] font-medium text-foreground', children: out.name }),
              jsx('span', {
                className: 'text-[0.6rem] uppercase tracking-wide',
                style: { color: check.ok ? 'var(--ui-accent)' : 'var(--ui-text-tertiary)' },
                children: check.ok ? 'validated' : 'needs work'
              })
            ]
          }),
          jsx('div', { className: 'truncate font-mono text-[0.6rem] text-(--ui-text-quaternary)', children: out.dir })
        ]
      }),
      metaLine
        ? jsx('div', { className: 'mt-0.5 text-[0.6rem] text-(--ui-text-quaternary)', children: metaLine })
        : null,
      (out.spec && out.spec.tools)
        ? jsx('div', {
            className: 'mt-2 flex flex-col gap-0.5',
            children: out.spec.tools.map(tool => jsx(ToolLine, { tool }, tool.name))
          })
        : null,
      jsx('div', {
        className: 'mt-2 flex flex-col gap-0.5 font-mono text-[0.62rem]',
        children: (check.ok ? (check.tail || []) : (check.failures || check.tail || [])).map((line, i) =>
          jsx('div', {
            style: {
              color: line.includes('✗') || line.includes('failed')
                ? 'var(--ui-text-tertiary)'
                : 'var(--ui-text-quaternary)'
            },
            children: line
          }, i))
      }),
      out.files
        ? jsx('div', {
            className: 'mt-1.5 font-mono text-[0.6rem] text-(--ui-text-quaternary)',
            children: out.files.join('  ·  ')
          })
        : null,
      jsx('div', {
        className: 'mt-1.5 text-[0.6rem] text-(--ui-text-quaternary)',
        children: 'written to the outbox — nothing installed. Read it, then symlink it yourself.'
      })
    ]
  })
}

function CreatorPanel() {
  const [idea, setIdea] = useState('')
  const [kind, setKind] = useState('skill')
  const [sourceName, setSourceName] = useState('')
  const [sources, setSources] = useState({ skills: [], cron: [] })
  const [busy, setBusy] = useState(false)
  const [stage, setStage] = useState('')
  const [out, setOut] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    let live = true
    CreatorPanel.__api
      .sources()
      .then(payload => {
        if (!live) return
        setSources({ skills: (payload && payload.skills) || [], cron: (payload && payload.cron) || [] })
      })
      .catch(err => { if (live) setError(String(err && err.message ? err.message : err)) })
    return () => { live = false }
  }, [])

  const options = kind === 'skill' ? sources.skills : sources.cron
  const canBuild = !busy && (idea.trim().length >= 10 || !!sourceName)

  function build() {
    setBusy(true)
    setOut(null)
    setError('')
    setStage('asking the model for a spec…')
    CreatorPanel.__api
      .create({ idea: idea.trim(), source_kind: sourceName ? kind : '', source_name: sourceName })
      .then(result => {
        setStage('')
        if (result && result.ok && result.stage === 'written') {
          setOut(result)
          return
        }
        const problems = (result && result.problems) || []
        setError(problems.length ? problems.join(' · ') : (result && result.error) || 'the build produced nothing')
      })
      .catch(err => { setStage(''); setError(String(err && err.message ? err.message : err)) })
      .finally(() => setBusy(false))
  }

  return jsxs('div', {
    className: 'rounded border p-3',
    style: { borderColor: 'var(--ui-stroke-secondary)' },
    children: [
      jsx('div', { className: 'text-sm font-medium text-foreground', children: 'Build a plugin' }),
      jsx('div', {
        className: 'mt-0.5 text-[0.68rem] text-(--ui-text-quaternary)',
        children: 'describe it, or start from something you already do · validated, never installed'
      }),
      jsx('textarea', {
        value: idea,
        onChange: event => setIdea(event.target.value),
        placeholder: 'A plugin that watches GPU listings and tells me when one drops under $600…',
        rows: 3,
        className: 'mt-3 w-full resize-y rounded border bg-transparent p-2 text-[0.75rem] text-foreground outline-none',
        style: { borderColor: 'var(--ui-stroke-tertiary)' }
      }),
      jsxs('div', {
        className: 'mt-2 flex flex-wrap items-center gap-2',
        children: [
          jsx('span', { className: 'text-[0.66rem] text-(--ui-text-quaternary)', children: 'or start from' }),
          jsx('select', {
            value: kind,
            onChange: event => { setKind(event.target.value); setSourceName('') },
            className: 'rounded border bg-transparent px-1.5 py-1 text-[0.68rem] text-(--ui-text-secondary)',
            style: { borderColor: 'var(--ui-stroke-tertiary)' },
            children: [
              jsx('option', { value: 'skill', children: `a skill (${sources.skills.length})` }),
              jsx('option', { value: 'cron', children: `a cron job (${sources.cron.length})` })
            ]
          }),
          jsx('select', {
            value: sourceName,
            onChange: event => setSourceName(event.target.value),
            className: 'min-w-0 max-w-[22rem] flex-1 rounded border bg-transparent px-1.5 py-1 text-[0.68rem] text-(--ui-text-secondary)',
            style: { borderColor: 'var(--ui-stroke-tertiary)' },
            children: [
              jsx('option', { value: '', children: 'choose one…' }),
              ...options.map(item =>
                jsx('option', {
                  value: item.name,
                  children: kind === 'skill'
                    ? `${item.name} · ${item.lines} lines`
                    : `${item.name} · ${item.schedule || 'no schedule'}`
                }, `${kind}-${item.name}`))
            ]
          }),
          jsx('button', {
            onClick: build,
            disabled: !canBuild,
            className: 'shrink-0 rounded px-3 py-1 text-[0.7rem] font-medium',
            style: {
              background: 'color-mix(in srgb, var(--ui-accent) 20%, transparent)',
              border: '1px solid color-mix(in srgb, var(--ui-accent) 62%, transparent)',
              color: 'var(--ui-text-primary)',
              whiteSpace: 'nowrap',
              cursor: canBuild ? 'pointer' : 'default',
              opacity: canBuild ? 1 : 0.5
            },
            children: busy ? 'Building…' : 'Build plugin'
          }),
          busy && stage
            ? jsx('span', { className: 'text-[0.64rem] text-(--ui-text-quaternary)', children: stage })
            : null
        ]
      }),
      error
        ? jsx('div', {
            className: 'mt-2 text-[0.68rem]',
            style: { color: 'var(--ui-text-tertiary)' },
            children: error
          })
        : null,
      out ? jsx(Built, { out }) : null
    ]
  })
}

CreatorPanel.__api = null

function BuiltSoFar() {
  const [rows, setRows] = useState([])
  useEffect(() => {
    let live = true
    CreatorPanel.__api
      .created()
      .then(payload => { if (live) setRows((payload && payload.created) || []) })
      .catch(() => {})
    return () => { live = false }
  }, [])
  if (!rows.length) return null
  return jsxs('div', {
    className: 'rounded border p-3',
    style: { borderColor: 'var(--ui-stroke-tertiary)' },
    children: [
      jsx('div', {
        className: 'text-[0.7rem] font-medium text-foreground',
        children: `Built so far (${rows.length})`
      }),
      jsx('div', {
        className: 'mt-1.5 flex flex-col gap-1',
        children: rows.map(row =>
          jsxs('div', {
            className: 'flex items-baseline justify-between gap-3',
            children: [
              jsx('span', { className: 'font-mono text-[0.66rem] text-(--ui-text-secondary)', children: row.name }),
              jsx('span', {
                className: 'truncate font-mono text-[0.58rem] text-(--ui-text-quaternary)',
                children: row.dir
              })
            ]
          }, row.name))
      })
    ]
  })
}

function LazyPage() {
  return jsxs('div', {
    className: 'flex flex-col gap-4 p-5',
    children: [jsx(CreatorPanel, {}), jsx(BuiltSoFar, {})]
  })
}

function LazyChip() {
  const [count, setCount] = useState(null)
  useEffect(() => {
    let live = true
    LazyChip.__api
      .created()
      .then(payload => { if (live) setCount(((payload && payload.created) || []).length) })
      .catch(() => { if (live) setCount(null) })
    return () => { live = false }
  }, [])
  return jsx('button', {
    className: 'inline-flex h-full items-center px-1.5 text-[0.6875rem] text-(--ui-text-tertiary) hover:text-foreground',
    title: 'Open Lazy Plugin — build a plugin from a description or a workflow you already have',
    onClick: () => host.navigate(ROUTE),
    children: count == null ? 'Lazy' : `${count} built`
  })
}

LazyChip.__api = null

export default {
  id: ID,
  name: 'Lazy Plugin',
  register(ctx) {
    const api = makeApi(ctx)
    CreatorPanel.__api = api
    LazyChip.__api = api
    ctx.register({ id: 'page', area: ROUTES_AREA, data: { path: ROUTE }, render: () => jsx(LazyPage, {}) })
    ctx.register({
      id: 'nav',
      area: SIDEBAR_NAV_AREA,
      order: 86,
      data: { path: ROUTE, label: 'Lazy Plugin', codicon: 'wand' }
    })
    ctx.register({
      id: 'open',
      area: PALETTE_AREA,
      data: {
        id: 'lazy-plugin.open',
        label: 'Build a plugin',
        keywords: ['plugin', 'create', 'generate', 'scaffold', 'skill', 'cron'],
        run: () => host.navigate(ROUTE)
      }
    })
    ctx.register({ id: 'chip', area: STATUSBAR_AREAS.right, order: 121, render: () => jsx(LazyChip, {}) })
  }
}
