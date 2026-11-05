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
    const request = options || {}
    const response = await fetch(base + path, {
      headers: { 'content-type': 'application/json' },
      ...request,
      body: request.body && typeof request.body !== 'string'
        ? JSON.stringify(request.body)
        : request.body
    })
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    return response.json()
  }
  return {
    sources: () => rest('/sources'),
    created: () => rest('/created'),
    create: payload => rest('/create', { method: 'POST', body: payload }),
    job: id => rest(`/create/job/${id}`),
    install: name => rest('/created/install', { method: 'POST', body: { name } }),
    publish: (name, openPr) => rest('/created/publish',
      { method: 'POST', body: { name, open_pr: !!openPr } }),
    share: name => rest('/created/share', { method: 'POST', body: { name } })
  }
}

function LazyCat({ size = 30 }) {
  return jsx('svg', {
    width: size,
    height: size,
    viewBox: '0 0 32 32',
    fill: 'none',
    'aria-hidden': 'true',
    children: [
      jsx('path', { d: 'M4 26c0-6 4-10 12-10s12 4 12 10z', fill: 'color-mix(in srgb, var(--ui-accent) 22%, transparent)', stroke: 'var(--ui-accent)', strokeWidth: 1.2 }),
      jsx('path', { d: 'M7 17 5 9l6 3M25 17l2-8-6 3', stroke: 'var(--ui-accent)', strokeWidth: 1.2, strokeLinejoin: 'round' }),
      jsx('circle', { cx: 12, cy: 18.5, r: 1.1, fill: 'var(--ui-accent)' }),
      jsx('circle', { cx: 20, cy: 18.5, r: 1.1, fill: 'var(--ui-accent)' }),
      jsx('path', { d: 'M15 21h2', stroke: 'var(--ui-accent)', strokeWidth: 1.2, strokeLinecap: 'round' }),
      jsx('path', { d: 'M26 24c3 0 4 2 4 4', stroke: 'var(--ui-accent)', strokeWidth: 1.2, strokeLinecap: 'round', opacity: 0.7 })
    ]
  })
}

function pollJob(api, job, onStage) {
  return new Promise((resolve, reject) => {
    let waited = 0
    const tick = () => {
      api
        .job(job)
        .then(state => {
          if (state.stage === 'gone') {
            reject(new Error('the job expired — check Built so far'))
            return
          }
          if (state.stage && onStage) onStage(state.stage, state.steps || [])
          if (state.ok === null || state.ok === undefined) {
            waited += 1200
            if (waited > 420000) {
              reject(new Error('this is taking longer than it should'))
              return
            }
            setTimeout(tick, 1200)
            return
          }
          resolve(state)
        })
        .catch(reject)
    }
    setTimeout(tick, 800)
  })
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

function ExtLink({ href, children }) {
  return jsx('a', {
    href,
    onClick: event => {
      event.preventDefault()
      if (host && host.openExternal) host.openExternal(href)
      else window.open(href, '_blank', 'noopener')
    },
    className: 'underline',
    style: { color: 'var(--ui-accent)', cursor: 'pointer' },
    children
  })
}

function PublishResult({ action, onPr }) {
  if (!action.ok) {
    return jsx('div', {
      className: 'font-mono text-[0.62rem]',
      children: action.error || action.stage || 'publishing failed'
    })
  }
  const lines = (action.steps || []).map(step =>
    jsxs('div', {
      className: 'flex items-baseline gap-2',
      children: [
        jsx('span', { style: { color: step.ok ? 'var(--ui-accent)' : 'var(--ui-text-tertiary)' },
          children: step.ok ? '✓' : '✗' }),
        jsx('span', { className: 'w-[6.5rem] shrink-0 text-(--ui-text-quaternary)', children: step.step }),
        jsx('span', {
          className: 'truncate font-mono text-[0.6rem]',
          children: (step.detail || []).join('  ')
        })
      ]
    }, step.step))

  return jsxs('div', {
    children: [
      jsx('div', { className: 'flex flex-col gap-0.5', children: lines }),
      jsxs('div', {
        className: 'mt-1.5 font-mono text-[0.6rem]',
        children: [
          jsx('div', { children: `repo  ${action.repo}` }, 'r'),
          jsx('div', { children: `sha   ${action.sha}` }, 's'),
          jsx('div', { children: `entry ${action.entry}` }, 'e'),
          jsx('div', { className: 'text-(--ui-text-quaternary)', children: `now installable anywhere: ${action.install_command}` }, 'i')
        ]
      }),
      action.pr
        ? jsxs('div', {
            className: 'mt-1',
            children: ['pull request  ', jsx(ExtLink, { href: action.pr, children: action.pr })]
          }, 'pr')
        : null,
      (action.stage === 'pinned' || action.pr_error)
        ? jsxs('div', {
            className: 'mt-1.5 flex flex-wrap items-center gap-2',
            children: [
              jsx('button', {
                onClick: onPr,
                className: 'rounded px-2 py-0.5 text-[0.62rem]',
                style: { border: '1px solid color-mix(in srgb, var(--ui-accent) 45%, transparent)',
                  color: 'var(--ui-text-primary)', cursor: 'pointer' },
                children: 'Open the catalog PR'
              }),
              jsx('span', {
                className: 'text-[0.58rem] text-(--ui-text-quaternary)',
                children: action.pr_error
                  ? action.pr_error
                  : 'one PR to NousResearch/hermes-agent, reviewed by a maintainer'
              })
            ]
          })
        : null
    ]
  })
}

function Built({ out }) {
  const check = out.validation || {}
  const [action, setAction] = useState(null)
  const [busyAction, setBusyAction] = useState('')

  function act(kind, openPr = false) {
    setBusyAction(kind)
    setAction({ kind, stage: 'starting…' })
    if (kind === 'install') {
      CreatorPanel.__api
        .install(out.name)
        .then(result => setAction({ kind, ...(result || {}) }))
        .catch(err => setAction({ kind, ok: false, error: String(err && err.message ? err.message : err) }))
        .finally(() => setBusyAction(''))
      return
    }
    CreatorPanel.__api
      .publish(out.name, openPr)
      .then(start => {
        if (!start || !start.job) {
          throw new Error((start && start.error) || 'could not start publishing')
        }
        return pollJob(CreatorPanel.__api, start.job, (stage, steps) =>
          setAction({ kind, stage, steps }))
      })
      .then(state => setAction({ kind: 'publish', ...(state.result || {}), ok: state.ok,
        error: state.error, stage: '' }))
      .catch(err => setAction({ kind: 'publish', ok: false, error: String(err && err.message ? err.message : err) }))
      .finally(() => setBusyAction(''))
  }
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
      jsxs('div', {
        className: 'mt-2.5 flex flex-wrap items-center gap-2',
        children: [
          jsx('button', {
            onClick: () => act('install'),
            disabled: !check.ok || !!busyAction,
            className: 'rounded px-2.5 py-1 text-[0.68rem] font-medium',
            style: {
              background: 'color-mix(in srgb, var(--ui-accent) 20%, transparent)',
              border: '1px solid color-mix(in srgb, var(--ui-accent) 62%, transparent)',
              color: 'var(--ui-text-primary)',
              whiteSpace: 'nowrap',
              cursor: check.ok ? 'pointer' : 'default',
              opacity: check.ok ? 1 : 0.5
            },
            children: busyAction === 'install' ? 'Installing…' : 'Install it'
          }),
          jsx('button', {
            onClick: () => act('publish'),
            disabled: !check.ok || !!busyAction,
            className: 'rounded px-2 py-1 text-[0.66rem]',
            style: {
              border: '1px solid var(--ui-stroke-secondary)',
              color: 'var(--ui-text-secondary)',
              whiteSpace: 'nowrap',
              cursor: check.ok ? 'pointer' : 'default',
              opacity: check.ok ? 1 : 0.5
            },
            children: busyAction === 'publish' ? 'Publishing…' : 'Publish to community'
          }),
          jsx('span', {
            className: 'text-[0.6rem] text-(--ui-text-quaternary)',
            children: 'nothing runs until you install it'
          })
        ]
      }),
      action
        ? jsxs('div', {
            className: 'mt-2 rounded p-2 text-[0.64rem]',
            style: { background: 'var(--ui-bg-tertiary)', color: 'var(--ui-text-secondary)' },
            children: action.kind === 'publish' ? PublishResult({ action, onPr: () => act('publish', true) })
              : jsxs('div', {
                  className: 'font-mono text-[0.62rem]',
                  children: action.ok
                    ? [
                        jsx('div', { children: `installed → ${action.installed}` }, 'a'),
                        jsx('div', { className: 'mt-1 text-(--ui-text-quaternary)', children: action.next }, 'b')
                      ]
                    : (action.error || 'failed')
                })
          })
        : null
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

  const STAGE_TEXT = {
    'reading what you picked': 'reading what you picked…',
    'asking the model for a spec': 'asking the model…',
    'writing the files and validating': 'writing and checking the files…'
  }

  function fail(message) {
    setBusy(false)
    setStage('')
    setError(message)
  }

  function handle(state) {
    if (state.stage === 'gone') {
      fail('the build finished but its result expired — check Built so far')
      return
    }
    if (state.stage && STAGE_TEXT[state.stage]) setStage(STAGE_TEXT[state.stage])
    if (state.ok === null || state.ok === undefined) return false
    setBusy(false)
    setStage('')
    if (state.ok && state.result) {
      setOut(state.result)
      if (CreatorPanel.__onBuilt) CreatorPanel.__onBuilt()
    } else {
      setError(state.error || 'the build did not produce a plugin')
    }
    return true
  }

  function build() {
    setBusy(true)
    setOut(null)
    setError('')
    setStage('starting…')
    CreatorPanel.__api
      .create({ idea: idea.trim(), source_kind: sourceName ? kind : '', source_name: sourceName })
      .then(start => {
        if (!start || !start.job) {
          const problems = (start && start.problems) || []
          fail(problems.length ? problems.join(' · ') : (start && start.error) || 'could not start the build')
          return
        }
        let waited = 0
        const tick = () => {
          CreatorPanel.__api
            .job(start.job)
            .then(state => {
              if (handle(state)) return
              waited += 1200
              if (waited > 300000) {
                fail('this is taking longer than it should — check Built so far in a moment')
                return
              }
              setTimeout(tick, 1200)
            })
            .catch(err => fail(String(err && err.message ? err.message : err)))
        }
        setTimeout(tick, 800)
      })
      .catch(err => fail(String(err && err.message ? err.message : err)))
  }

  return jsxs('div', {
    className: 'rounded border p-3',
    style: { borderColor: 'var(--ui-stroke-secondary)' },
    children: [
      jsxs('div', {
        className: 'flex items-center gap-2',
        children: [
          jsx(LazyCat, {}),
          jsxs('div', {
            children: [
              jsx('div', { className: 'text-sm font-medium text-foreground', children: 'Make a plugin' }),
              jsx('div', {
                className: 'mt-0.5 text-[0.7rem] text-(--ui-text-tertiary)',
                children: 'Say what you want Hermes to do. Or start from a job you already run.'
              })
            ]
          })
        ]
      }),
      jsx('textarea', {
        value: idea,
        onChange: event => setIdea(event.target.value),
        placeholder: 'Watch GPU prices and tell me when one drops under $600',
        rows: 3,
        className: 'mt-3 w-full resize-y rounded border bg-transparent p-2 text-[0.75rem] text-foreground outline-none',
        style: { borderColor: 'var(--ui-stroke-tertiary)' }
      }),
      jsxs('div', {
        className: 'mt-2 flex flex-wrap items-center gap-2',
        children: [
          jsx('span', { className: 'text-[0.68rem] text-(--ui-text-tertiary)', children: 'Or start from' }),
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
            children: busy ? 'Making it…' : 'Make it'
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
CreatorPanel.__onBuilt = null

function BuiltSoFar({ version }) {
  const [rows, setRows] = useState([])
  useEffect(() => {
    let live = true
    CreatorPanel.__api
      .created()
      .then(payload => { if (live) setRows((payload && payload.created) || []) })
      .catch(() => {})
    return () => { live = false }
  }, [version])
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
  const [version, setVersion] = useState(0)
  CreatorPanel.__onBuilt = () => setVersion(value => value + 1)
  return jsxs('div', {
    className: 'flex flex-col gap-4 p-5',
    children: [jsx(CreatorPanel, {}), jsx(BuiltSoFar, { version })]
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
    title: 'Lazy Cat — make a plugin from a description or a job you already run',
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
      data: { path: ROUTE, label: '🐱 Lazy Cat', codicon: 'wand' }
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
