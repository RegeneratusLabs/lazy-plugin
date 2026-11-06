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
const BUILD = 'cat-turn-13'

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
    questions: () => rest('/questions'),
    prefill: idea => rest('/create/prefill', { method: 'POST', body: { idea } }),
    request: payload => rest('/agent/request', { method: 'POST', body: payload }),
    run: payload => rest('/agent/run', { method: 'POST', body: payload }),
    runState: id => rest('/agent/run/' + id),
    pending: () => rest('/agent/pending'),
    remove: name => rest('/created/remove', { method: 'POST', body: { name } }),
    answers: payload => rest('/create/answers', { method: 'POST', body: payload }),
    files: name => rest(`/created/files?name=${encodeURIComponent(name)}`),
    readFile: (name, path) => rest(`/created/file?name=${encodeURIComponent(name)}&path=${encodeURIComponent(path)}`),
    saveFile: (name, path, content) => rest('/created/file', { method: 'POST', body: { name, path, content } }),
    share: name => rest('/created/share', { method: 'POST', body: { name } })
  }
}

// The gateway RPC the desktop app itself uses to start a turn: `session.create` mints a real
// runtime id, then `prompt.submit { session_id, text }` writes the user row and starts the turn.
// This needs no mounted composer and no focus, so it works from a plugin page.
async function submitToChat(prompt) {
  const request = host && host.request
  if (typeof request !== 'function') return { ok: false, stage: 'host.request is missing' }
  const atom = host && host.state && host.state.focusedSessionId
  const focused = atom && typeof atom.get === 'function' ? atom.get() : null
  if (focused) {
    try {
      await request('prompt.submit', { profile, session_id: focused, text: prompt, source: 'desktop' })
      return { ok: true }
    } catch (err) { /* the focused session may be a stale tile: mint a fresh one below */ }
  }
  let created = null
  const profileAtom = host && host.state && host.state.profile
  const profile = profileAtom && typeof profileAtom.get === 'function' ? profileAtom.get() : undefined
  for (const params of [
    { profile, title: 'Lazy Plugin build', source: 'desktop' },
    { source: 'desktop' }
  ]) {
    try {
      created = await request('session.create', params)
      if (created && created.session_id) break
    } catch (err) { created = null }
  }
  const sessionId = created && created.session_id
  if (!sessionId) return { ok: false, stage: 'session.create returned no session_id' }
  try {
    await request('prompt.submit', { profile, session_id: sessionId, text: prompt, source: 'desktop' })
  } catch (err) {
    return { ok: false, stage: 'prompt.submit failed: ' + String(err && err.message ? err.message : err) }
  }
  try {
    if (host.openSession) host.openSession(sessionId)
  } catch (err) { /* the chat opens on its own in the primary pane */ }
  return { ok: true }
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
                children: check.ok ? 'passes checks' : 'needs work'
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

function Questionnaire({ onResult, initial }) {
  const [fields, setFields] = useState([])
  const [answers, setAnswers] = useState({})
  const [busy, setBusy] = useState(false)
  const [note, setNote] = useState('')

  useEffect(() => {
    let live = true
    CreatorPanel.__api
      .questions()
      .then(payload => {
        if (!live) return
        const list = (payload && payload.questions) || []
        setFields(list)
        setAnswers(Object.fromEntries(list.map(q => [q.id, q.default || ''])))
      })
      .catch(err => setNote(String(err && err.message ? err.message : err)))
    return () => { live = false }
  }, [])

  useEffect(() => {
    if (initial && initial.purpose) setAnswers(prev => ({ ...prev, ...initial }))
  }, [initial])

  const ready = (answers.purpose || '').trim().length >= 10
  const act = String(answers.action || '')
  const doing = act === 'fetch a URL'
    ? `fetch ${answers.target || '⚠ no URL yet'}`
    : act === 'read or write a file'
      ? `${answers.target ? 'read or write ' + answers.target : '⚠ no path yet'}`
      : act === 'run a command'
        ? `run ${answers.target || '⚠ no command yet'}`
        : 'be a scaffold to fill in later'
  const preview = ready
    ? `It will ${doing}${answers.returns ? `, and give back ${answers.returns}` : ', and give nothing back ⚠'}` +
      ` · ${String(answers.trigger || '').startsWith('after') ? 'after every session' : 'when you ask'}`
    : ''

  function submit() {
    setBusy(true)
    setNote('')
    CreatorPanel.__api
      .answers(answers)
      .then(result => {
        if (result && result.ok) {
          setNote('')
          if (onResult) onResult(result)
          return
        }
        setNote(((result && result.problems) || []).join(' · ') || 'the answers did not make a plugin')
      })
      .catch(err => setNote(String(err && err.message ? err.message : err)))
      .finally(() => setBusy(false))
  }

  function field(item) {
    const value = answers[item.id] || ''
    const set = next => setAnswers(prev => ({ ...prev, [item.id]: next }))
    const shared = {
      value,
      onChange: event => set(event.target.value),
      className: 'w-full rounded border bg-transparent px-1.5 py-1 text-[0.7rem] text-foreground outline-none',
      style: { borderColor: 'var(--ui-stroke-tertiary)' }
    }
    const wide = item.id === 'purpose'
    return jsxs('div', {
      className: 'flex flex-col gap-0.5',
      style: wide ? { gridColumn: '1 / -1' } : undefined,
      children: [
        jsx('label', { className: 'text-[0.6rem] uppercase tracking-wide text-(--ui-text-quaternary)', children: item.label }),
        item.type === 'select'
          ? jsx('select', { ...shared, children: (item.options || []).map(option => jsx('option', { value: option, children: option }, option)) })
          : jsx('textarea', { ...shared, rows: wide ? 3 : (item.rows || 1), placeholder: item.placeholder || '' })
      ]
    }, item.id)
  }

  return jsxs('div', {
    className: 'mt-3 flex flex-col gap-2',
    children: [
      jsx('div', {
        className: 'text-[0.6rem] uppercase tracking-wide text-(--ui-text-quaternary)',
        children: 'seven answers, no model needed'
      }),
      jsx('div', {
        className: 'grid gap-2',
        style: { gridTemplateColumns: 'repeat(auto-fit, minmax(13rem, 1fr))' },
        children: fields.map(field)
      }),
      jsxs('div', {
        className: 'flex items-center gap-2',
        children: [
          jsx('button', {
            onClick: submit,
            disabled: !ready || busy,
            className: 'rounded px-3 py-1 text-[0.7rem] font-medium',
            style: {
              background: 'color-mix(in srgb, var(--ui-accent) 20%, transparent)',
              border: '1px solid color-mix(in srgb, var(--ui-accent) 62%, transparent)',
              color: 'var(--ui-text-primary)',
              whiteSpace: 'nowrap',
              cursor: ready ? 'pointer' : 'default',
              opacity: ready ? 1 : 0.5
            },
            children: busy ? 'making it…' : 'make it'
          }),
          jsx('span', {
            className: 'text-[0.6rem] text-(--ui-text-quaternary)',
            children: note || (ready ? '' : 'start with what it should do')
          })
        ]
      }),
      preview
        ? jsx('div', {
            className: 'rounded px-2 py-1 text-[0.62rem]',
            style: { background: 'var(--ui-bg-tertiary)', color: 'var(--ui-text-tertiary)' },
            children: preview
          })
        : null,
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
  const [prefill, setPrefill] = useState(null)
  const [handoff, setHandoff] = useState('')

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

  CreatorPanel.__setPrefill = setPrefill
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
    } else if (String(state.error || '').includes('provider API key')) {
      buildWithAgent()
      return true
    } else {
      setError(state.error || 'the build did not produce a plugin')
    }
    return true
  }

  // The provider key resolves inside a turn, not inside a background job: this process serves
  // several profiles and secrets are scoped per turn. So the page hands the build to the agent,
  // which calls lazyplugin_create itself, and the tile appears when it lands.
  function buildWithAgent() {
    const payload = { idea: idea.trim(), source_kind: sourceName ? kind : '', source_name: sourceName }
    setBusy(true)
    setOut(null)
    setError('')
    setStage('starting a turn with your agent…')

    // The route spawns `hermes chat -q … --oneshot`: a real turn of the user's own agent, with
    // their model and credentials. It works in a browser, on a phone, and on the desktop app —
    // none of which can reach a chat composer from a plugin page.
    CreatorPanel.__api
      .run(payload)
      .then(result => {
        if (result && result.ok && result.run) {
          setStage('your agent is building it… this is a real turn, so it takes a minute')
          pollForTile(result.run)
          return
        }
        handOff(payload, (result && (result.error || (result.problems || []).join(' · '))) || '')
      })
      .catch(() => handOff(payload, 'could not start a turn'))
  }

  function handOff(payload, why) {
    CreatorPanel.__api
      .request(payload)
      .then(result => {
        if (!result || !result.ok) {
          fail(((result && result.problems) || []).join(' · ') || 'could not hand this to the agent')
          return
        }
        setHandoff(result.prompt || '')
        setBusy(false)
        setStage('')
        setError((why ? why + ' · ' : '') + 'queued — copy it into chat, or say “build the plugin I queued”')
        if (CreatorPanel.__onBuilt) CreatorPanel.__onBuilt()
      })
      .catch(err => fail(String(err && err.message ? err.message : err)))
  }

  function pollForTile(runId) {
    let waited = 0
    const tick = () => {
      CreatorPanel.__api
        .created()
        .then(payload => {
          const rows = (payload && payload.created) || []
          const landed = rows.find(row => !CreatorPanel.__seen.includes(row.name))
          if (landed) {
            CreatorPanel.__seen = rows.map(row => row.name)
            setBusy(false)
            setStage('')
            setError('')
            if (CreatorPanel.__onBuilt) CreatorPanel.__onBuilt()
            return
          }
          waited += 3000
          if (waited > 300000) {
            CreatorPanel.__api
              .runState(runId)
              .then(state => fail('no plugin yet — the agent said: '
                + ((state && state.tail) || 'nothing').trim().split('\n').slice(-3).join(' ')))
              .catch(() => fail('no plugin yet — the run is still going'))
            return
          }
          setTimeout(tick, 3000)
        })
        .catch(() => setTimeout(tick, 3000))
    }
    setTimeout(tick, 5000)
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
              jsxs('div', {
                className: 'flex items-baseline gap-1.5',
                children: [
                  jsx('span', { className: 'text-sm font-medium text-foreground', children: 'Make a plugin' }),
                  jsx('span', { className: 'text-[0.55rem] text-(--ui-text-quaternary)', children: BUILD })
                ]
              }),
              jsx('div', {
                className: 'mt-0.5 text-[0.7rem] text-(--ui-text-tertiary)',
                children: 'Say what you want Hermes to do. Or start from a job you already run.'
              })
            ]
          })
        ]
      }),
      jsx(Questionnaire, { onResult: setOut, initial: prefill }),
      jsx('div', { className: 'mt-1 text-[0.6rem] uppercase tracking-wide text-(--ui-text-quaternary)', children: 'or describe it' }),
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
        ? jsxs('div', {
            className: 'mt-2 flex flex-wrap items-center gap-2 text-[0.68rem]',
            style: { color: 'var(--ui-text-tertiary)' },
            children: [
              jsx('span', { children: error }),
              handoff
                ? jsx(TileButton, {
                    onClick: () => {
                      if (navigator.clipboard) navigator.clipboard.writeText(handoff)
                      setError('copied — paste it into chat and the agent will build it')
                    },
                    children: 'copy the request for chat'
                  })
                : null
            ]
          })
        : null,
      out ? jsx(Built, { out }) : null
    ]
  })
}

CreatorPanel.__api = null
CreatorPanel.__onBuilt = null
CreatorPanel.__seen = []
CreatorPanel.__setPrefill = null

function Badge({ tone = 'quiet', children }) {
  const styles = {
    good: { color: 'var(--ui-accent)', border: '1px solid color-mix(in srgb, var(--ui-accent) 45%, transparent)' },
    quiet: { color: 'var(--ui-text-quaternary)', border: '1px solid var(--ui-stroke-tertiary)' },
    warn: { color: 'var(--ui-text-tertiary)', border: '1px solid var(--ui-stroke-secondary)' }
  }
  return jsx('span', {
    className: 'rounded-full px-1.5 py-[1px] text-[0.56rem] uppercase tracking-wide',
    style: { ...(styles[tone] || styles.quiet), whiteSpace: 'nowrap' },
    children
  })
}

function TileButton({ onClick, disabled, primary, children }) {
  return jsx('button', {
    onClick,
    disabled,
    className: 'rounded px-2 py-[3px] text-[0.63rem]',
    style: {
      whiteSpace: 'nowrap',
      cursor: disabled ? 'default' : 'pointer',
      opacity: disabled ? 0.5 : 1,
      background: primary ? 'color-mix(in srgb, var(--ui-accent) 18%, transparent)' : 'transparent',
      border: primary
        ? '1px solid color-mix(in srgb, var(--ui-accent) 55%, transparent)'
        : '1px solid var(--ui-stroke-secondary)',
      color: primary ? 'var(--ui-text-primary)' : 'var(--ui-text-secondary)'
    },
    children
  })
}

function ChatEdit({ name, prompt, onSaved }) {
  const [text, setText] = useState('')
  const [note, setNote] = useState('')
  const [sent, setSent] = useState(false)

  function ask() {
    const request = text.trim()
    if (request.length < 4) return
    const composer = host && host.composer
    if (!composer || typeof composer.submit !== 'function') {
      setNote('this surface has no chat — paste the request there instead')
      return
    }
    const sent = composer.submit(null, 
      `Change the generated plugin "${name}" in ~/.hermes/lazy-plugin/created/${name}/. ` +
      `Request: ${request}. Load the lazy-plugin-builder skill, read the files before editing, ` +
      `keep plugin.yaml and __init__.py in step, then run: hermes plugins validate ` +
      `~/.hermes/lazy-plugin/created/${name}`
    )
    if (!sent) {
      setNote('nothing is focused in chat — open a chat and try again')
      return
    }
    setText('')
    setSent(true)
    setNote('handed to the agent — it will read the bundle, edit it and re-validate')
    if (onSaved) onSaved()
  }

  return jsxs('div', {
    className: 'mt-1 flex flex-col gap-1.5 rounded p-2',
    style: { background: 'var(--ui-bg-tertiary)' },
    children: [
      jsx('div', {
        className: 'text-[0.58rem] uppercase tracking-wide text-(--ui-text-quaternary)',
        children: 'ask for a change'
      }),
      jsxs('div', {
        className: 'flex items-end gap-1.5',
        children: [
          jsx('textarea', {
            value: text,
            onChange: event => setText(event.target.value),
            rows: 2,
            placeholder: 'make the price ceiling $700, and say which listing won',
            className: 'min-w-0 flex-1 resize-y rounded border bg-transparent p-1.5 text-[0.68rem] text-foreground outline-none',
            style: { borderColor: 'var(--ui-stroke-tertiary)' }
          }),
          jsx(TileButton, {
            onClick: ask,
            disabled: text.trim().length < 4,
            primary: text.trim().length >= 4,
            children: 'send'
          })
        ]
      }),
      jsx('div', {
        className: 'text-[0.58rem] text-(--ui-text-quaternary)',
        children: note || (sent ? 'sent' : 'plain English — the agent edits the files and re-validates')
      })
    ]
  })
}

function PluginTile({ plugin, onChanged }) {
  const [busy, setBusy] = useState('')
  const [note, setNote] = useState('')
  const [editing, setEditing] = useState(false)
  const [confirming, setConfirming] = useState(false)

  function install() {
    setBusy('install')
    setNote('')
    CreatorPanel.__api
      .install(plugin.name)
      .then(result => {
        setNote(result && result.ok ? 'installed — enable it to load' : (result && result.error) || 'failed')
        if (result && result.ok && onChanged) onChanged()
      })
      .catch(err => setNote(String(err && err.message ? err.message : err)))
      .finally(() => setBusy(''))
  }

  function publish() {
    setBusy('publish')
    setNote('')
    CreatorPanel.__api
      .publish(plugin.name, false)
      .then(start => {
        if (!start || !start.job) throw new Error((start && start.error) || 'could not start publishing')
        return pollJob(CreatorPanel.__api, start.job, stage => setNote(stage))
      })
      .then(state => {
        const result = (state && state.result) || {}
        setNote(state.ok ? `published at ${String(result.sha || '').slice(0, 7)} — the entry is beside it` : (state.error || 'failed'))
        if (state.ok && onChanged) onChanged()
      })
      .catch(err => setNote(String(err && err.message ? err.message : err)))
      .finally(() => setBusy(''))
  }

  return jsxs('div', {
    className: 'flex flex-col gap-1.5 rounded border p-3',
    style: { borderColor: 'var(--ui-stroke-secondary)' },
    children: [
      jsxs('div', {
        className: 'flex items-baseline justify-between gap-2',
        children: [
          jsxs('div', {
            className: 'flex items-baseline gap-1.5',
            children: [
              jsx('span', { className: 'text-[0.84rem] font-medium text-foreground', children: plugin.title || plugin.name }),
              plugin.validated === true
                ? jsx(Badge, { tone: 'good', children: 'checked' })
                : plugin.validated === false
                  ? jsx(Badge, { tone: 'warn', children: 'needs a fix' })
                  : jsx(Badge, { tone: 'quiet', children: 'unchecked' })
            ]
          }),
          jsx('span', { className: 'font-mono text-[0.56rem] text-(--ui-text-quaternary)', children: plugin.version ? `v${plugin.version}` : '' })
        ]
      }),
      jsx('div', {
        className: 'text-[0.68rem] leading-[1.35] text-(--ui-text-tertiary)',
        style: { display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' },
        children: plugin.description || 'no description'
      }),
      jsxs('div', {
        className: 'flex flex-wrap items-center gap-1.5 text-[0.6rem] text-(--ui-text-quaternary)',
        children: [
          jsx('span', { children: `${(plugin.tools || []).length} tools` }),
          jsx('span', { children: '·' }),
          jsx('span', { children: `${plugin.files} files` }),
          plugin.installed ? jsx(Badge, { tone: 'good', children: 'installed' }) : null,
          plugin.published ? jsx(Badge, { tone: 'quiet', children: 'on github' }) : null
        ]
      }),
      jsxs('div', {
        className: 'mt-0.5 flex flex-wrap items-center gap-1.5',
        children: [
          jsx(TileButton, {
            onClick: install,
            disabled: !!busy || plugin.installed || plugin.validated === false,
            primary: !plugin.installed && plugin.validated !== false,
            children: busy === 'install' ? 'installing…' : plugin.installed ? 'installed' : 'install'
          }),
          jsx(TileButton, {
            onClick: publish,
            disabled: !!busy || plugin.validated === false,
            title: plugin.published
              ? 'commit the current files to the same repo and repoint the catalog entry at the new commit'
              : 'create a public repo, pin the commit, write the catalog entry',
            children: busy === 'publish' ? 'publishing…' : plugin.published ? 'republish' : 'publish'
          }),
          jsx(TileButton, {
            onClick: () => setEditing(value => !value),
            children: editing ? 'close' : 'edit'
          }),
          jsx(TileButton, {
            onClick: () => {
              if (!confirming) { setConfirming(true); return }
              setBusy('remove')
              CreatorPanel.__api
                .remove(plugin.name)
                .then(result => {
                  if (result && result.ok) { if (onChanged) onChanged(); return }
                  setNote((result && result.error) || 'could not remove it')
                })
                .catch(err => setNote(String(err && err.message ? err.message : err)))
                .finally(() => setBusy(''))
            },
            disabled: !!busy || plugin.installed,
            children: busy === 'remove' ? 'removing…' : confirming ? 'sure?' : 'remove'
          }),
          plugin.published
            ? jsx(ExtLink, { href: plugin.published.repo, children: 'repo ↗' })
            : null,
          note
            ? jsx('span', { className: 'truncate text-[0.58rem] text-(--ui-text-quaternary)', children: note })
            : null
        ]
      }),
      editing ? jsx(ChatEdit, { name: plugin.name, onSaved: onChanged }) : null
    ]
  })
}

function CreatedTiles({ version }) {
  const [rows, setRows] = useState([])
  const [tick, setTick] = useState(0)
  const [error, setError] = useState('')

  useEffect(() => {
    let live = true
    CreatorPanel.__api
      .created()
      .then(payload => {
        if (!live) return
        setError('')
        setRows((payload && payload.created) || [])
      })
      .catch(err => { if (live) setError(String(err && err.message ? err.message : err)) })
    return () => { live = false }
  }, [version, tick])

  if (error) {
    return jsx('div', {
      className: 'rounded border p-3 text-[0.68rem]',
      style: { borderColor: 'var(--ui-stroke-secondary)', color: 'var(--ui-text-tertiary)' },
      children: `could not list what you have built: ${error}`
    })
  }
  if (!rows.length) return null
  return jsxs('div', {
    className: 'flex flex-col gap-2',
    children: [
      jsx('div', {
        className: 'text-[0.72rem] font-medium text-foreground',
        children: `Built so far (${rows.length})`
      }),
      jsx('div', {
        className: 'grid gap-2',
        style: { gridTemplateColumns: 'repeat(auto-fill, minmax(17rem, 1fr))' },
        children: rows.map(row =>
          jsx(PluginTile, { plugin: row, onChanged: () => setTick(value => value + 1) }, row.name))
      })
    ]
  })
}

function LazyPage() {
  const [version, setVersion] = useState(0)
  CreatorPanel.__onBuilt = () => setVersion(value => value + 1)
  return jsxs('div', {
    className: 'flex flex-col gap-4 p-5',
    children: [jsx(CreatorPanel, {}), jsx(CreatedTiles, { version })]
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
