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
const BUILD = 'cradle-11'

// Design language: docs/DESIGN.md — one ink, one ground, hairline ornament, monospace for facts.
const CC = {
  ink: '#1B0F26', panel: '#241432', panel2: '#2E1A3F', rule: '#4A2F63',
  paper: '#EFE3F2', muted: '#B79BC8', accent: '#B48CD9', warn: '#D9A66B', fail: '#C9637A',
  serif: 'Cormorant, "EB Garamond", "Iowan Old Style", Georgia, serif',
  mono: 'ui-monospace, SFMono-Regular, Menlo, monospace'
}

const CC_STYLE = `
.cc-page { --cc-hair: color-mix(in srgb, ${CC.rule} 55%, transparent);
  background: ${CC.ink}; color: ${CC.paper}; font-size: .8rem; line-height: 1.45; }
.cc-frame { border: 1px solid ${CC.rule}; padding: 3px; }
.cc-inner { border: 1px solid ${CC.rule}; padding: 20px 22px 22px; position: relative; overflow: hidden; }
.cc-sun { position: absolute; right: -30px; top: -78px; width: 360px; height: 230px; pointer-events: none;
  background: repeating-conic-gradient(from -90deg at 50% 100%, ${CC.rule} 0 .34deg, transparent .34deg 3.6deg);
  opacity: .12;
  -webkit-mask-image: radial-gradient(circle at 50% 100%, #000 0 52%, transparent 80%);
  mask-image: radial-gradient(circle at 50% 100%, #000 0 52%, transparent 80%); }

.cc-hero { display: flex; align-items: flex-start; gap: 16px; position: relative; padding-bottom: 15px; }
.cc-cat { flex: none; color: ${CC.paper}; opacity: .7; }
.cc-hero-main { flex: 1; min-width: 0; }
.cc-word { font-family: ${CC.serif}; font-size: 1.5rem; line-height: 1.1; letter-spacing: .02em;
  color: ${CC.paper}; text-transform: uppercase; }
.cc-thesis { font-family: ${CC.mono}; font-size: .65rem; color: ${CC.muted}; margin-top: 6px;
  letter-spacing: .01em; }
.cc-counts { font-family: ${CC.mono}; font-size: .65rem; color: ${CC.muted}; text-align: right;
  white-space: nowrap; padding-top: 5px; }
.cc-stamp { font-family: ${CC.mono}; font-size: .58rem; color: ${CC.muted}; opacity: .7;
  text-align: right; margin-top: 6px; }
.cc-rule { height: 1px; background: ${CC.rule}; }
.cc-rule-gap { height: 3px; }

.cc-section { display: flex; align-items: baseline; justify-content: space-between; gap: 10px;
  margin: 17px 0 9px; }
.cc-h2 { font-family: ${CC.serif}; font-size: 1rem; letter-spacing: .02em; color: ${CC.paper}; }
.cc-hint { font-family: ${CC.mono}; font-size: .6rem; color: ${CC.muted}; }

.cc-pills { display: flex; flex-wrap: wrap; gap: 6px; }
.cc-chip { font-family: ${CC.mono}; font-size: .6rem; color: ${CC.muted}; background: transparent;
  border: 1px solid ${CC.rule}; border-radius: 2px; padding: 2px 8px; cursor: pointer;
  white-space: nowrap; }
.cc-chip:hover { color: ${CC.paper}; background: ${CC.panel2}; }
.cc-chip:focus-visible { outline: 1px solid ${CC.accent}; outline-offset: 1px; }
.cc-chip.on { color: ${CC.accent}; border-color: ${CC.accent}; }

.cc-area { width: 100%; resize: vertical; background: ${CC.panel}; color: ${CC.paper};
  border: 1px solid ${CC.rule}; border-radius: 2px; padding: 8px 10px; font-size: .75rem;
  font-family: inherit; outline: none; }
.cc-area::placeholder { color: ${CC.muted}; opacity: .65; }
.cc-area:focus { border-color: ${CC.accent}; }
.cc-label { font-family: ${CC.mono}; font-size: .59rem; letter-spacing: .07em;
  text-transform: uppercase; color: ${CC.muted}; }

.cc-btn { font-family: ${CC.mono}; font-size: .6rem; color: ${CC.muted}; background: transparent;
  border: 1px solid ${CC.rule}; border-radius: 2px; padding: 3px 9px; cursor: pointer;
  white-space: nowrap; }
.cc-btn:hover:not(:disabled) { color: ${CC.paper}; border-color: ${CC.muted}; }
.cc-btn:focus-visible { outline: 1px solid ${CC.accent}; outline-offset: 1px; }
.cc-btn:disabled { opacity: .38; cursor: default; }
.cc-btn.pri { color: ${CC.accent}; border-color: ${CC.accent}; }
.cc-btn.pri:hover:not(:disabled) { color: ${CC.paper}; background: ${CC.panel2}; }
.cc-build-status { display: inline-flex; align-items: center; gap: 6px; font-family: ${CC.mono};
  font-size: .62rem; color: ${CC.paper}; }
@keyframes cc-pulse { 0%, 100% { opacity: .2; } 50% { opacity: 1; } }
.cc-dot { width: 5px; height: 5px; border-radius: 50%; background: ${CC.paper};
  animation: cc-pulse 1.3s ease-in-out infinite; }
@media (prefers-reduced-motion: reduce) { .cc-dot { animation: none; opacity: .8; } }
.cc-build-hint { font-family: ${CC.mono}; font-size: .56rem; color: ${CC.muted}; }

.cc-tiles { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
@media (max-width: 760px) { .cc-tiles { grid-template-columns: minmax(0, 1fr); } }
.cc-tile { display: flex; flex-direction: column; gap: 5px; background: ${CC.panel};
  border: 1px solid ${CC.rule}; border-radius: 3px; padding: 11px 12px; }
.cc-tile:hover { background: ${CC.panel2}; }
.cc-tile-head { display: flex; align-items: baseline; justify-content: space-between; gap: 8px; }
.cc-tile-title { font-family: ${CC.serif}; font-size: .94rem; line-height: 1.2; letter-spacing: .01em;
  color: ${CC.paper}; }
.cc-pill { font-family: ${CC.mono}; font-size: .59rem; letter-spacing: .04em; padding: 1px 6px;
  border: 1px solid currentColor; border-radius: 2px; white-space: nowrap; }
.cc-pill.runs { color: ${CC.accent}; }
.cc-pill.key { color: ${CC.warn}; }
.cc-pill.broken { color: ${CC.fail}; }
.cc-pill.quiet { color: ${CC.muted}; }
.cc-sentence { font-size: .68rem; color: ${CC.paper}; }
.cc-desc { font-size: .7rem; color: ${CC.muted}; display: -webkit-box; -webkit-line-clamp: 2;
  -webkit-box-orient: vertical; overflow: hidden; }
.cc-meta { font-family: ${CC.mono}; font-size: .61rem; color: ${CC.muted}; display: flex;
  flex-wrap: wrap; gap: 4px 6px; }
.cc-actions { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; margin-top: 2px;
  opacity: 0; transition: opacity .12s ease; }
.cc-tile:hover .cc-actions, .cc-tile:focus-within .cc-actions { opacity: 1; }

.cc-ledger { margin-top: 16px; border-top: 1px solid ${CC.rule}; padding-top: 12px; }
.cc-ledger-head { display: flex; align-items: baseline; justify-content: space-between; gap: 10px; }
.cc-ledger-name { font-family: ${CC.serif}; font-size: .96rem; color: ${CC.paper}; }
.cc-ledger-dir { font-family: ${CC.mono}; font-size: .58rem; color: ${CC.muted}; overflow: hidden;
  text-overflow: ellipsis; white-space: nowrap; }
.cc-rows { margin-top: 8px; display: flex; flex-direction: column; }
.cc-row { display: grid; grid-template-columns: 4.4rem .9rem minmax(0, 1fr); gap: 8px;
  align-items: baseline; padding: 4px 0; border-bottom: 1px solid var(--cc-hair); }
.cc-row-label { font-family: ${CC.mono}; font-size: .61rem; color: ${CC.muted}; }
.cc-row-mark { font-family: ${CC.mono}; font-size: .62rem; color: ${CC.muted}; }
.cc-row-mark.fail { color: ${CC.fail}; }
.cc-row-mark.warn { color: ${CC.warn}; }
.cc-row-value { font-family: ${CC.mono}; font-size: .64rem; color: ${CC.paper}; min-width: 0;
  overflow-wrap: anywhere; }
.cc-row-sub { font-family: ${CC.mono}; font-size: .6rem; color: ${CC.muted}; margin-top: 2px;
  overflow-wrap: anywhere; }

.cc-empty { display: flex; align-items: flex-start; gap: 18px; padding: 6px 0 2px; }
.cc-empty-line { font-family: ${CC.serif}; font-size: 1.05rem; color: ${CC.paper}; }
.cc-empty-copy { font-size: .72rem; color: ${CC.muted}; margin-top: 4px; max-width: 34rem; }
.cc-example { font-family: ${CC.mono}; font-size: .62rem; color: ${CC.paper}; background: transparent;
  border: 0; border-bottom: 1px dashed ${CC.rule}; padding: 0 0 1px; margin-top: 10px; cursor: pointer;
  text-align: left; }
.cc-example:hover { color: ${CC.accent}; border-color: ${CC.accent}; }
.cc-error { font-family: ${CC.mono}; font-size: .6rem; color: ${CC.warn}; margin-top: 10px; }
.cc-note { font-family: ${CC.mono}; font-size: .6rem; color: ${CC.muted}; }
.cc-details { margin-top: 14px; border-top: 1px solid var(--cc-hair); padding-top: 10px; }
.cc-details summary { font-family: ${CC.mono}; font-size: .58rem; letter-spacing: .06em;
  text-transform: uppercase; color: ${CC.muted}; cursor: pointer; }
.cc-details summary:hover { color: ${CC.paper}; }
.cc-details[open] summary { margin-bottom: 9px; color: ${CC.paper}; }
.cc-grid { display: grid; gap: 10px; grid-template-columns: repeat(auto-fit, minmax(13rem, 1fr)); }
.cc-field { display: flex; flex-direction: column; gap: 3px; }
.cc-preview { font-family: ${CC.mono}; font-size: .58rem; color: ${CC.muted}; margin-top: 8px;
  border-left: 1px solid ${CC.rule}; padding-left: 8px; }
`

const KIND_LABEL = {
  command: 'runs a command',
  http: 'calls an endpoint',
  file: 'reads/writes a path',
  stub: 'scaffold'
}

// Colour is a hint; the sentence carries the fact (DESIGN.md, verdict vocabulary).
const VERDICT = {
  works: { word: 'runs', tone: 'runs' },
  'needs-key': { word: 'needs a key', tone: 'key' },
  upstream: { word: 'upstream', tone: 'key' },
  scaffold: { word: 'scaffold', tone: 'broken' },
  broken: { word: 'broken', tone: 'broken' },
  unchecked: { word: 'unchecked', tone: 'quiet' }
}

const FALLBACK_SENTENCE = {
  works: 'the handler returned real results',
  'needs-key': 'sound package, needs a key',
  upstream: 'request works, far end refused it',
  scaffold: 'broken: scaffold — handler never got written',
  broken: 'broken: the loader raised',
  unchecked: 'not dispatched yet — test it'
}

function verdictOf(smoke) {
  const key = (smoke && smoke.verdict) || 'unchecked'
  return { key, ...(VERDICT[key] || VERDICT.unchecked) }
}

function sentenceOf(smoke) {
  if (smoke && smoke.headline) return smoke.headline
  return FALLBACK_SENTENCE[(smoke && smoke.verdict) || 'unchecked'] || FALLBACK_SENTENCE.unchecked
}

function countsLine(rows) {
  const tally = { runs: 0, key: 0, broken: 0 }
  rows.forEach(row => {
    const tone = verdictOf(row.smoke).tone
    if (tone === 'runs') tally.runs += 1
    else if (tone === 'key') tally.key += 1
    else if (tone === 'broken') tally.broken += 1
  })
  const parts = [`${tally.runs} run`]
  if (tally.key) parts.push(`${tally.key} ${tally.key === 1 ? 'needs' : 'need'} a key`)
  if (tally.broken) parts.push(`${tally.broken} broken`)
  return parts.join(' · ')
}

let PLUGIN_CTX = null

function makeApi(ctx) {
  const base = `/api/plugins/${ID}`
  // Every failure names the route and method it tried: a 404 on this page is nearly always a
  // mount question, and "HTTP 404" alone can't tell you which namespace answered.
  const label = (path, request) => `${(request && request.method) || 'GET'} ${base}${path}`

  const viaFetch = async (path, request) => {
    const response = await fetch(base + path, {
      headers: { 'content-type': 'application/json' },
      ...request,
      body: request.body && typeof request.body !== 'string'
        ? JSON.stringify(request.body)
        : request.body
    })
    if (!response.ok) {
      let said = ''
      try { said = (await response.text()).slice(0, 160).replace(/\s+/g, ' ') } catch (err) { said = '' }
      throw new Error(`HTTP ${response.status} · ${label(path, request)}${said ? ` · ${said}` : ''}`)
    }
    return response.json()
  }

  // ctx.rest is the scoped door; the plain fetch is the fallback for a backend that answers the
  // namespace over HTTP but not through the bridge (an older runtime, or a half mounted late).
  const rest = async (path, options) => {
    const request = options || {}
    if (!ctx || !ctx.rest) return viaFetch(path, request)
    try {
      return await ctx.rest(path, request)
    } catch (err) {
      try {
        return await viaFetch(path, request)
      } catch (retry) {
        throw new Error(`${String((err && err.message) || err)} / fallback ${retry.message}`)
      }
    }
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
    smokeTest: name => rest('/created/smoke', { method: 'POST', body: { name } }),
    answers: payload => rest('/create/answers', { method: 'POST', body: payload }),
    files: name => rest(`/created/files?name=${encodeURIComponent(name)}`),
    readFile: (name, path) => rest(`/created/file?name=${encodeURIComponent(name)}&path=${encodeURIComponent(path)}`),
    saveFile: (name, path, content) => rest('/created/file', { method: 'POST', body: { name, path, content } }),
    share: name => rest('/created/share', { method: 'POST', body: { name } })
  }
}

// What the page asks the agent to do, when the build runs as a chat turn. The rules are the same
// ones the deterministic path enforces in code — here they are stated so the reader of the turn
// can see them, and the gate below still decides whether anything ships.
function chatPrompt(payload) {
  const target = payload.source_name
    ? `Source ${payload.source_kind}: "${payload.source_name}" — read it before you design anything ` +
      `(skill_view for a skill, or lazyplugin_pending / the cron job's own file).`
    : `The job, as described: ${payload.idea}`
  return [
    'Build one plugin for Cat\'s Cradle (the lazy-plugin page). Follow the lazy-plugin-builder ' +
      'skill exactly — load it first with skill_view; its body is the brief, not a suggestion.',
    '',
    target,
    '',
    'Hard rules:',
    '1. Spec first, in words: a lowercase-hyphenated name that says what it acts on, 1–3 tools, and ' +
      'for each tool: what it does, what it reads or fetches (URL / path / argv), what it returns, ' +
      'and whether it needs an API key. Show me that spec before you build.',
    '2. Code comes from templates only: call lazyplugin_create with that spec. Never hand-write ' +
      '__init__.py or plugin.yaml. Handler bodies are one of four shapes — command, http, file, stub.',
    '3. Every http tool needs a request.url; every command tool needs a target (the argv); every ' +
      'file tool needs a target or a declared `path` parameter. A tool with no target is refused, ' +
      'and rightly so.',
    '4. Never install anything, never touch ~/.hermes/plugins, never edit the catalog. The bundle ' +
      'stays in ~/.hermes/lazy-plugin/created/<name>/ and I decide about installing.',
    '5. lazyplugin_create returns a validation line and a dispatch report. The bundle counts as ' +
      'done only when the dispatch verdict is `works`. If it is not, fix the spec (target, params, ' +
      'projection) and call lazyplugin_create again under a new name — or stop and quote me the ' +
      'exact failing line.',
    '6. End your reply with three lines: the plugin name, the validate line, the dispatch line.'
  ].join('\n')
}

// An edit is a chat turn too: the agent is the only thing that can read a bundle, change a handler
// and re-validate it, and the page keeps owning the gate afterwards.
function editPrompt(name, request) {
  return [
    `Edit the generated plugin "${name}" in ~/.hermes/lazy-plugin/created/${name}/.`,
    '',
    `What I want changed: ${request}`,
    '',
    'Rules:',
    '1. Read the files before changing them (the lazy-plugin-builder skill is the brief if you have ' +
      'not loaded it this session).',
    '2. Keep plugin.yaml and __init__.py in step: a declared tool that is not registered, or the ' +
      'other way round, fails capability matching.',
    '3. Handler bodies stay one of the four shapes — command, http, file, stub — take one positional ' +
      'params plus **kwargs, and return json.dumps(...). No hand-rolled signatures the registry ' +
      'cannot fill.',
    '4. Do not install it, do not touch ~/.hermes/plugins, do not edit the catalog entry.',
    '5. Finish with: hermes plugins validate ~/.hermes/lazy-plugin/created/' + name +
      ' — and quote its result. The page dispatches the bundle again itself, so do not claim it works.',
    '6. End with two lines: the files you changed, and the validate line.'
  ].join('\n')
}

// The gateway RPC the desktop app itself uses to start a turn: `session.create` mints a real
// runtime id, then `prompt.submit { session_id, text }` writes the user row and starts the turn.
// This needs no mounted composer and no focus, so it works from a plugin page.
async function submitToChat(prompt) {
  const request = host && host.request
  if (typeof request !== 'function') return { ok: false, stage: 'host.request is missing' }
  const profileAtom = host && host.state && host.state.profile
  const profile = profileAtom && typeof profileAtom.get === 'function' ? profileAtom.get() : undefined
  let created = null
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
  // The route and the sidebar address a session by its STORED id; prompt.submit wants the runtime
  // one. Holding both is what lets us submit and then actually show the turn.
  const stored = created.stored_session_id || created.session_id
  try {
    // Exactly the contract's fields: PromptSubmitParams is session_id + profile + text (+ truncation
    // and voice extras). `source` is not one of them — it belongs to session.create — and the schema
    // rejects unknown keys outright, so an invented field reads as a version mismatch.
    await request('prompt.submit', { profile, session_id: sessionId, text: prompt })
  } catch (err) {
    return { ok: false, stage: 'prompt.submit failed: ' + String(err && err.message ? err.message : err) }
  }
  let opened = false
  try {
    if (host.openSession) {
      host.openSession(stored, { profile, intent: 'in-place' })
      opened = true
    }
  } catch (err) { opened = false }
  if (!opened) {
    // No open verb on this host: fall back to the stored session's route so the turn is visible.
    try { if (host.navigate) { host.navigate(`/session/${encodeURIComponent(stored)}`); opened = true } } catch (err) { opened = false }
  }
  return { ok: true, session: stored, opened }
}

// What the page remembers across navigation. The build is a backend turn, so leaving this page and
// coming back must reattach to it instead of pretending nothing is running.
const INFLIGHT_KEY = 'lazy-plugin.build.v1'
const INFLIGHT_TTL = 20 * 60 * 1000

function readInflight() {
  try {
    const raw = window.localStorage.getItem(INFLIGHT_KEY)
    const value = raw ? JSON.parse(raw) : null
    if (!value || !value.at) return null
    if (Date.now() - value.at > INFLIGHT_TTL) {
      window.localStorage.removeItem(INFLIGHT_KEY)
      return null
    }
    return value
  } catch (err) {
    return null
  }
}

function writeInflight(value) {
  try {
    if (value) window.localStorage.setItem(INFLIGHT_KEY, JSON.stringify(value))
    else window.localStorage.removeItem(INFLIGHT_KEY)
  } catch (err) { /* a plugin without storage still builds; it just forgets */ }
}

// The plate's cat: a plump tabby asleep on a cushion, engraved as one hairline line. Ink is
// `--cc-paper` at 70% on the dark ground (DESIGN.md, "the cat").
function Cat({ size = 96 }) {
  return jsx('svg', {
    width: size,
    height: Math.round(size * 0.72),
    viewBox: '0 0 140 100',
    fill: 'none',
    stroke: 'currentColor',
    strokeWidth: 1,
    strokeLinecap: 'round',
    strokeLinejoin: 'round',
    className: 'cc-cat',
    'aria-hidden': 'true',
    children: [
      jsx('path', { d: 'M22 88c14-7 82-7 96 0', strokeWidth: 0.7, opacity: 0.8 }, '26645'),
      jsx('path', { d: 'M57 50C64 32 91 27 106 39C119 50 118 69 103 77C88 84 63 82 52 76', strokeWidth: 1.55 }, '18969'),
      jsx('path', { d: 'M27 55C29 44 37 39 46 40C55 41 61 48 58 56C56 65 48 71 39 72C32 73 26 69 26 63C25 60 26 57 27 55', strokeWidth: 1.5 }, '48677'),
      jsx('path', { d: 'M32 47C29 41 27 36 26 32C32 35 38 38 41 40', strokeWidth: 1.35 }, '63260'),
      jsx('path', { d: 'M44 41C49 37 54 34 57 33C57 38 57 44 56 47', strokeWidth: 1.35 }, '84975'),
      jsx('path', { d: 'M33 56c2 3 6 3 8 1', strokeWidth: 1.0 }, '98095'),
      jsx('path', { d: 'M46 55c2 3 6 3 8 1', strokeWidth: 1.0 }, '6398'),
      jsx('path', { d: 'M37 62h5l-2.5 3v3c-2 1.4-4 1.4-5.5 0M39.5 68c2 1.4 4 1.4 5.5 0', strokeWidth: 0.8 }, '3792'),
      jsx('path', { d: 'M32 64c-4-1.2-7-1.6-9-1.2M32 67c-3.4.8-6 2.2-8 3.6', strokeWidth: 0.5, opacity: 0.65 }, '29580'),
      jsx('path', { d: 'M46 63c3.4-1.2 6.4-1.6 8.4-1.2M46 66c3 1 5.4 2 7.2 3.2', strokeWidth: 0.5, opacity: 0.65 }, '85000'),
      jsx('path', { d: 'M30 75c7 4 17 4 24 0', strokeWidth: 0.9 }, '85131'),
      jsx('path', { d: 'M35 78c5 2.6 11 2.6 16 0', strokeWidth: 0.5, opacity: 0.6 }, '9606'),
      jsx('path', { d: 'M58 69c5 2.6 11 2.6 16 0.6M73 72c4 1.6 8 0.8 12-1', strokeWidth: 0.5, opacity: 0.6 }, '29849'),
      jsx('path', { d: 'M92 78l4 4M97 76l4 4M86 80l3 4', strokeWidth: 0.45, opacity: 0.45 }, '48874'),
      jsx('path', { d: 'M44 71l2 4M49 73l2 4', strokeWidth: 0.45, opacity: 0.45 }, '91588'),
      jsx('path', { d: 'M104 73c10 4 14 10 6 13-9 3-25 2-39-1-6-1-11-2-16-4', strokeWidth: 1.45 }, '46661'),
      jsx('g', { fill: 'currentColor', stroke: 'none', opacity: 0.6, children: [
        jsx('path', { d: 'M66 32c6 10 7 21 5 30-3-9-5-20-5-30z' }, '67195'),
        jsx('path', { d: 'M77 29c8 11 9 24 6 34-4-11-6-23-6-34z' }, '4890'),
        jsx('path', { d: 'M88 29c8 12 9 25 6 35-4-11-6-24-6-35z' }, '66406'),
        jsx('path', { d: 'M98 33c6 10 7 20 5 29-3-9-5-19-5-29z' }, '14318'),
        jsx('path', { d: 'M108 46c4 6 4 12 2 17-2-5-3-11-2-17z' }, '80475'),
      ] }, 'stripes'),
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

// Opening a URL is `ctx.os.openExternal` on this SDK; `host.openExternal` was never a thing, which
// is why the repo link did nothing. Falls back to the clipboard so a refused open still gives the
// reader something they can use.
async function openExternal(url) {
  if (!url) return false
  try {
    if (PLUGIN_CTX && PLUGIN_CTX.os && typeof PLUGIN_CTX.os.openExternal === 'function') {
      const opened = await PLUGIN_CTX.os.openExternal(url)
      if (opened !== false) return 'opened'
    }
  } catch (err) { /* fall through to the other doors */ }
  try {
    if (host && typeof host.openExternal === 'function') {
      const opened = await host.openExternal(url)
      if (opened !== false) return 'opened'
    }
  } catch (err) { /* ditto */ }
  try {
    const opened = window.open(url, '_blank', 'noopener')
    if (opened) return 'opened'
  } catch (err) { /* ditto */ }
  try {
    if (navigator.clipboard) {
      await navigator.clipboard.writeText(url)
      return 'copied'
    }
  } catch (err) { /* nothing left to try */ }
  return false
}

function TileButton({ onClick, disabled, primary, title, children }) {
  return jsx('button', {
    onClick,
    disabled,
    title,
    className: primary ? 'cc-btn pri' : 'cc-btn',
    children
  })
}

function secs(value) {
  const number = Number(value)
  if (!Number.isFinite(number) || number <= 0) return '—'
  return number >= 10 ? `${Math.round(number)}s` : `${number.toFixed(1)}s`
}

function LedgerRow({ label, mark, tone, value, sub }) {
  return jsxs('div', {
    className: 'cc-row',
    children: [
      jsx('span', { className: 'cc-row-label', children: label }),
      jsx('span', { className: tone ? `cc-row-mark ${tone}` : 'cc-row-mark', children: mark }),
      jsxs('span', {
        className: 'cc-row-value',
        children: [
          value,
          ...(sub || []).map((line, index) =>
            jsx('div', { className: 'cc-row-sub', children: line }, index))
        ]
      })
    ]
  })
}

function PublishResult({ action, onPr }) {
  const [note, setNote] = useState('')

  // Same chip, same door as the tile's repo link: the URL is a thing you open, not text you copy.
  function openLink(url) {
    openExternal(url).then(result => {
      if (result === 'copied') setNote('link copied — open it in a browser')
      else if (!result) setNote('could not open that link')
      else setNote('')
    })
  }

  if (!action.ok) {
    return jsx('div', {
      className: 'cc-row-value',
      style: { color: 'var(--cc-fail)' },
      children: action.error || action.stage || 'publishing failed'
    })
  }
  const lines = (action.steps || []).map(step =>
    jsxs('div', {
      style: { display: 'flex', gap: '8px' },
      children: [
        jsx('span', { style: { color: step.ok ? CC.paper : CC.muted }, children: step.ok ? '✓' : '✗' }),
        jsx('span', { style: { color: CC.muted, minWidth: '5.5rem' }, children: step.step }),
        jsx('span', { children: (step.detail || []).join('  ') })
      ]
    }, step.step))

  return jsxs('div', {
    className: 'cc-row-value',
    children: [
      jsx('div', { style: { display: 'flex', flexDirection: 'column', gap: '2px' }, children: lines }),
      jsxs('div', { style: { marginTop: '6px' }, children: [
        jsx('div', { children: `repo   ${action.repo}` }, 'r'),
        jsx('div', { children: `sha    ${action.sha}` }, 's'),
        jsx('div', { children: `entry  ${action.entry}` }, 'e'),
        jsx('div', { className: 'cc-row-sub', children: `installable anywhere: ${action.install_command}` }, 'i')
      ] }),
      (action.repo || action.pr)
        ? jsxs('div', {
            style: { marginTop: '7px', display: 'flex', alignItems: 'center', gap: '6px', flexWrap: 'wrap' },
            children: [
              action.repo
                ? jsx(TileButton, {
                    onClick: () => openLink(action.repo),
                    title: action.repo,
                    children: 'repo ↗'
                  }, 'repo-link')
                : null,
              action.pr
                ? jsx(TileButton, {
                    onClick: () => openLink(action.pr),
                    title: action.pr,
                    children: 'pull request ↗'
                  }, 'pr-link')
                : null,
              note ? jsx('span', { className: 'cc-row-sub', children: note }, 'note') : null
            ]
          }, 'links')
        : null,
      (action.stage === 'pinned' || action.pr_error)
        ? jsxs('div', {
            style: { marginTop: '6px', display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' },
            children: [
              jsx(TileButton, { onClick: onPr, children: 'open the catalog PR' }),
              jsx('span', {
                className: 'cc-row-sub',
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

// The result card is a ledger: spec · files · validate · dispatch. Every row is monospace and
// carries a tick or the exact failing line — never a bare "all good".
function Ledger({ out }) {
  const check = out.validation || {}
  const smoke = out.smoke || {}
  const spec = out.spec || {}
  const tools = spec.tools || []
  const files = out.files || []
  const fileCount = out.file_count != null ? out.file_count : files.length
  const verdict = verdictOf(smoke)
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

  const failLine = (check.failures && check.failures[0])
    || (check.tail || []).filter(line => line.trim()).slice(-1)[0]
    || 'the validator rejected it'
  const dispatchOk = ['works', 'needs-key', 'upstream'].includes(verdict.key)
  const dispatchLine = smoke.verdict
    ? `${verdict.word} · ${sentenceOf(smoke)}${smoke.seconds ? ` · ${Number(smoke.seconds).toFixed(1)}s` : ''}`
    : 'not dispatched'

  return jsxs('div', {
    className: 'cc-ledger',
    children: [
      jsxs('div', {
        className: 'cc-ledger-head',
        children: [
          jsxs('div', {
            style: { display: 'flex', alignItems: 'baseline', gap: '8px', minWidth: 0 },
            children: [
              jsx('span', { className: 'cc-ledger-name', children: out.name }),
              jsx('span', { className: `cc-pill ${verdict.tone}`, children: verdict.word })
            ]
          }),
          jsx('span', { className: 'cc-ledger-dir', children: out.dir })
        ]
      }),
      jsxs('div', {
        className: 'cc-rows',
        children: [
          jsx(LedgerRow, {
            label: 'spec',
            mark: tools.length ? '✓' : '✗',
            tone: tools.length ? '' : 'fail',
            value: tools.length
              ? `${tools.length} tool${tools.length === 1 ? '' : 's'} · ${tools.map(tool => tool.name).join(', ')}`
              : 'no tools declared',
            sub: tools.map(tool => `${tool.name} — ${KIND_LABEL[tool.kind] || tool.kind}`)
          }, 'spec'),
          jsx(LedgerRow, {
            label: 'files',
            mark: fileCount ? '✓' : '✗',
            tone: fileCount ? '' : 'fail',
            value: `${fileCount} written`,
            sub: files.length ? [files.join('  ')] : []
          }, 'files'),
          jsx(LedgerRow, {
            label: 'validate',
            mark: check.ok ? '✓' : '✗',
            tone: check.ok ? '' : 'fail',
            value: check.ok
              ? 'passed — no collisions, no core override, safe to load'
              : 'failed',
            sub: check.ok ? [] : [failLine]
          }, 'validate'),
          jsx(LedgerRow, {
            label: 'dispatch',
            mark: dispatchOk ? '✓' : '✗',
            tone: dispatchOk ? '' : (verdict.key === 'unchecked' ? 'warn' : 'fail'),
            value: dispatchLine
          }, 'dispatch'),
          out.timings
            ? jsx(LedgerRow, {
                label: 'timing',
                mark: '·',
                tone: '',
                value: `model ${secs(out.timings.model)} · files ${secs(out.timings.files)} · ` +
                  `total ${secs(out.timings.total)}`,
                sub: [
                  out.timings.source ? `reading the source took ${secs(out.timings.source)}` : '',
                  out.draft && out.draft.meta && out.draft.meta.lane
                    ? `the spec came back on the ${out.draft.meta.lane} lane in ` +
                      `${secs(out.draft.meta.seconds)}`
                    : '',
                  out.draft && out.draft.meta && out.draft.meta.structured_error
                    ? `structured lane failed first, ${secs(out.draft.meta.structured_seconds)}: ` +
                      out.draft.meta.structured_error
                    : ''
                ].filter(Boolean)
              }, 'timing')
            : null
        ]
      }),
      jsxs('div', {
        className: 'cc-actions',
        style: { opacity: 1, marginTop: '11px' },
        children: [
          jsx(TileButton, {
            onClick: () => act('install'),
            disabled: !check.ok || !!busyAction,
            primary: !!check.ok,
            children: busyAction === 'install' ? 'installing…' : 'install it'
          }),
          jsx(TileButton, {
            onClick: () => act('publish'),
            disabled: !check.ok || !!busyAction,
            children: busyAction === 'publish' ? 'publishing…' : 'publish to community'
          }),
          jsx('span', { className: 'cc-note', children: 'nothing runs until you install it' })
        ]
      }),
      action
        ? jsx('div', {
            style: {
              marginTop: '9px', paddingTop: '8px', borderTop: `1px solid ${CC.rule}`,
              fontFamily: CC.mono, fontSize: '.6rem', color: CC.paper
            },
            children: action.kind === 'publish'
              // A component, not a function call: it holds useState now, and calling it inline puts
              // its hooks in the Ledger's hook order (React then throws on the publish render).
              ? jsx(PublishResult, { action, onPr: () => act('publish', true) })
              : jsx('div', {
                  style: { fontFamily: CC.mono, fontSize: '.6rem' },
                  children: jsx('div', {
                    style: action.ok ? undefined : { color: CC.fail },
                    children: action.ok ? `installed → ${action.installed}` : (action.error || 'failed')
                  })
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
      className: 'cc-area',
      style: { padding: '5px 7px', fontSize: '.7rem' }
    }
    const wide = item.id === 'purpose'
    return jsxs('div', {
      className: 'cc-field',
      style: wide ? { gridColumn: '1 / -1' } : undefined,
      children: [
        jsx('label', { className: 'cc-label', children: item.label }),
        item.type === 'select'
          ? jsx('select', { ...shared, children: (item.options || []).map(option => jsx('option', { value: option, children: option }, option)) })
          : jsx('textarea', { ...shared, rows: wide ? 3 : (item.rows || 1), placeholder: item.placeholder || '' })
      ]
    }, item.id)
  }

  return jsxs('details', {
    className: 'cc-details',
    children: [
      jsx('summary', { children: 'or answer seven questions · no model needed' }),
      jsx('div', { className: 'cc-grid', style: { marginTop: '8px' }, children: fields.map(field) }),
      jsxs('div', {
        style: { display: 'flex', alignItems: 'center', gap: '9px', marginTop: '9px' },
        children: [
          jsx(TileButton, { onClick: submit, disabled: !ready || busy, primary: ready && !busy,
            children: busy ? 'making it…' : 'make it' }),
          jsx('span', { className: 'cc-note', children: note || (ready ? '' : 'start with what it should do') })
        ]
      }),
      preview
        ? jsx('div', { className: 'cc-preview', children: preview })
        : null
    ]
  })
}

function CreatorPanel() {
  const [idea, setIdea] = useState('')
  const [mode, setMode] = useState('describe')
  const [sourceName, setSourceName] = useState('')
  const [sources, setSources] = useState({ skills: [], cron: [] })
  const [busy, setBusy] = useState(false)
  const [stage, setStage] = useState('')
  const [out, setOut] = useState(null)
  const [error, setError] = useState('')
  const [note, setNote] = useState('')
  const [prefill, setPrefill] = useState(null)
  const [elapsed, setElapsed] = useState(0)
  const [stageAt, setStageAt] = useState(0)
  const [latch, setLatch] = useState(CreatorPanel.__building)

  // Coming back to the page: pick the running build up where it was left.
  useEffect(() => {
    const inflight = readInflight()
    if (!inflight) return
    CreatorPanel.__seen = inflight.seen || []
    CreatorPanel.__building = { at: inflight.at, idea: inflight.idea || '' }
    setLatch(CreatorPanel.__building)
    setBusy(true)
    setStage(inflight.stage || 'your agent is still building — watching for the tile')
    setStageAt((inflight.stageAt || inflight.at) / 1000)
    pollForTile(null)
  }, [])

  // A build outlives the click and the page: it is a thread on the backend. Without a module-level
  // latch a reload (or a second click) starts a second identical build, which is how two plugins
  // for one idea get made.
  useEffect(() => {
    if (!busy) {
      setElapsed(0)
      return
    }
    // Count from the phase's own start, not the click: "writing the files · 3s" after 40s of model
    // is honest, and a stale clock would read as a hang.
    const started = stageAt ? stageAt * 1000 : Date.now()
    const tick = setInterval(
      () => setElapsed(Math.max(0, Math.round((Date.now() - started) / 1000))), 500)
    return () => clearInterval(tick)
  }, [busy, stageAt])

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
  CreatorPanel.__setIdea = setIdea
  const kind = mode === 'cron' ? 'cron' : 'skill'
  const options = kind === 'skill' ? sources.skills : sources.cron
  const canBuild = !busy && (idea.trim().length >= 10 || !!sourceName)


  function fail(message) {
    CreatorPanel.__building = null
    writeInflight(null)
    setLatch(null)
    setBusy(false)
    setStage('')
    setStageAt(0)
    setError(message)
  }

  // The provider key resolves inside a turn, not inside a background job: this process serves
  // several profiles and secrets are scoped per turn. So the page hands the build to the agent,
  // which calls lazyplugin_create itself, and the tile appears when it lands.
  // The build as a visible turn. The tile is not trusted when it appears: this page dispatches it
  // itself, so the verdict is never taken from the agent's word.
  function buildInChat() {
    setNote('')
    if (CreatorPanel.__building) {
      fail('a build is already running — it lands in Built so far when it finishes')
      return
    }
    const payload = {
      idea: idea.trim() || (sourceName ? `Turn the ${kind} "${sourceName}" into a plugin.` : ''),
      source_kind: sourceName ? kind : '',
      source_name: sourceName
    }
    CreatorPanel.__building = { at: Date.now(), idea: payload.idea }
    setLatch(CreatorPanel.__building)
    setBusy(true)
    setOut(null)
    setError('')
    setStage('handing this to your agent…')
    setStageAt(Date.now() / 1000)

    // Baseline the shelf first, so the tile we watch for is genuinely new.
    CreatorPanel.__api
      .created()
      .then(payload => {
        CreatorPanel.__seen = ((payload && payload.created) || []).map(row => row.name)
        writeInflight({
          at: Date.now(),
          idea: payload.idea,
          seen: CreatorPanel.__seen,
          stage: 'your agent is building it in chat',
          stageAt: Date.now()
        })
      })
      .catch(() => { CreatorPanel.__seen = [] })
      .then(() => submitToChat(chatPrompt(payload)))
      .then(result => {
        if (result && result.ok) {
          setStage('your agent is building it in chat — the tile lands when the dispatch passes')
          setStageAt(Date.now() / 1000)
          pollForTile(null)
          return
        }
        // Builds are agent turns now: a surface with no chat cannot build, and says so instead of
        // quietly falling back to a different pipeline with a different trust story.
        CreatorPanel.__building = null
        setLatch(null)
        setBusy(false)
        setStage('')
        setStageAt(0)
        fail(`this surface cannot start a turn (${(result && result.stage) || 'no chat'}) — ` +
          'open Cat\'s Cradle in the desktop app to build')
      })
      .catch(err => fail(String(err && err.message ? err.message : err)))
  }

  // The agent's bundle is checked the way any bundle is: dispatch it, then show the ledger.
  function adoptTile(row) {
    const handWritten = !row.smoke
    CreatorPanel.__api
      .smokeTest(row.name)
      .then(result => {
        const smoke = (result && result.smoke) || row.smoke || { verdict: 'unchecked' }
        setOut({
          name: row.name,
          dir: row.dir,
          file_count: row.files,
          files: [],
          spec: { tools: (row.tools || []).map(name => ({ name })) },
          validation: { ok: row.validated, tail: row.validation || [] },
          smoke,
          headline: (result && result.headline) || ''
        })
        if (handWritten) {
          setError('that bundle appeared without a dispatch report, so the agent wrote it by hand — ' +
            'the dispatch below is the only gate it has passed')
        }
        if (CreatorPanel.__onBuilt) CreatorPanel.__onBuilt()
      })
      .catch(err => setError(`the tile landed but could not be dispatched: ${err && err.message ? err.message : err}`))
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
            setStageAt(0)
            writeInflight(null)
            adoptTile(landed)
            return
          }
          waited += 3000
          if (waited > 300000) {
            if (!runId) {
              fail('no tile yet — the chat turn may still be working. Tell me to keep watching, ' +
                'or hit Reload desktop plugins once it lands')
              return
            }
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

  function chip(label, on, onClick) {
    return jsx('button', {
      onClick,
      className: on ? 'cc-chip on' : 'cc-chip',
      'aria-pressed': on,
      children: label
    }, label)
  }

  const pillRow = jsxs('div', {
    className: 'cc-pills',
    children: [
      chip('describe it', mode === 'describe', () => { setMode('describe'); setSourceName('') }),
      chip(`a skill (${sources.skills.length})`, mode === 'skill',
        () => { setMode('skill'); setSourceName('') }),
      chip(`a cron job (${sources.cron.length})`, mode === 'cron',
        () => { setMode('cron'); setSourceName('') })
    ]
  })

  return jsxs('div', {
    children: [
      jsxs('div', {
        className: 'cc-section',
        style: { marginTop: '15px' },
        children: [
          jsx('div', { className: 'cc-h2', children: 'Weave one' }),
          jsx('div', { className: 'cc-hint', children: 'the page is the form, the agent is the craftsman' })
        ]
      }),
      pillRow,
      mode === 'describe'
        ? jsx('textarea', {
            value: idea,
            onChange: event => setIdea(event.target.value),
            placeholder: 'Watch GPU prices and tell me when one drops under $600',
            rows: 3,
            className: 'cc-area',
            style: { marginTop: '9px' }
          })
        : jsxs('div', { style: { marginTop: '9px' }, children: [
            jsx('div', { className: 'cc-label', children: mode === 'cron' ? 'pick a job you already run' : 'pick something the agent already knows how to do' }),
            jsx('div', {
              className: 'cc-pills',
              style: { marginTop: '6px', maxHeight: '8.5rem', overflowY: 'auto' },
              children: options.length
                ? options.map(item =>
                    chip(
                      kind === 'skill'
                        ? `${item.name} · ${item.lines} lines`
                        : `${item.name} · ${item.schedule || 'no schedule'}`,
                      sourceName === item.name,
                      () => setSourceName(sourceName === item.name ? '' : item.name)
                    ))
                : jsx('span', { className: 'cc-note', children: kind === 'cron' ? 'no cron jobs yet' : 'no skills yet' })
            })
          ] }),
      jsxs('div', {
        style: { display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: '9px', marginTop: '10px' },
        children: [
          jsx(TileButton, { onClick: buildInChat, disabled: !canBuild, primary: canBuild,
            children: busy ? 'making it…' : 'make it' }),
          sourceName
            ? jsx('span', { className: 'cc-note', children: `from ${kind}: ${sourceName}` })
            : null,
          busy
            ? jsxs('span', {
                className: 'cc-build-status',
                children: [
                  jsx('span', { className: 'cc-dot' }),
                  jsx('span', {
                    children: `${stage || 'starting…'}${elapsed ? ` · ${elapsed}s` : ''}`
                  })
                ]
              })
            : null,
          busy
            ? jsx('span', {
                className: 'cc-build-hint',
                children: 'watch the chat pane — this page lights up when the tile lands'
              })
            : null,
          latch && !busy
            ? jsx('span', {
                className: 'cc-note',
                children: 'a build from this page is still running — it lands in Built so far'
              })
            : null,
          !busy && note
            ? jsx('span', { className: 'cc-note', children: note })
            : null,
        ]
      }),
      error
        ? jsxs('div', {
            className: 'cc-error',
            style: { display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: '9px' },
            children: [
              jsx('span', { children: error })
            ]
          })
        : null,
      out ? jsx(Ledger, { out }) : null,
      jsx(Questionnaire, { onResult: setOut, initial: prefill })
    ]
  })
}

CreatorPanel.__api = null
CreatorPanel.__onBuilt = null
CreatorPanel.__seen = []
CreatorPanel.__setPrefill = null
CreatorPanel.__setIdea = null
CreatorPanel.__building = null

function ChatEdit({ name, onSaved }) {
  const [text, setText] = useState('')
  const [note, setNote] = useState('')
  const [sending, setSending] = useState(false)

  // The edit lands when the bundle changes, not when the agent says so: keep asking the shelf while
  // the turn runs, so the tile's pill and metadata catch up on their own.
  function watchForEdit() {
    let waited = 0
    const tick = () => {
      CreatorPanel.__api
        .created()
        .then(() => { if (onSaved) onSaved() })
        .catch(() => {})
        .finally(() => {
          waited += 6000
          if (waited < 180000) setTimeout(tick, 6000)
        })
    }
    setTimeout(tick, 6000)
  }

  function ask() {
    const request = text.trim()
    if (request.length < 4 || sending) return
    setSending(true)
    setNote('handing this to your agent…')
    submitToChat(editPrompt(name, request))
      .then(result => {
        if (!result || !result.ok) {
          setNote(`could not start the turn: ${(result && result.stage) || 'no chat on this surface'}`)
          return
        }
        setText('')
        setNote(result.opened
          ? 'handed over — the chat is open, watch the edit, the tile follows'
          : 'handed over — open the chat to watch it, the tile follows')
        watchForEdit()
      })
      .catch(err => setNote(String(err && err.message ? err.message : err)))
      .finally(() => setSending(false))
  }

  return jsxs('div', {
    style: { marginTop: '6px', paddingTop: '8px', borderTop: `1px solid ${CC.rule}` },
    children: [
      jsx('div', { className: 'cc-label', children: 'ask for a change' }),
      jsxs('div', {
        style: { display: 'flex', alignItems: 'flex-end', gap: '6px', marginTop: '5px' },
        children: [
          jsx('textarea', {
            value: text,
            onChange: event => setText(event.target.value),
            rows: 2,
            placeholder: 'make the price ceiling $700, and say which listing won',
            className: 'cc-area cc-edit-area',
            style: { flex: 1, minWidth: 0, fontSize: '.68rem', padding: '5px 7px' }
          }),
          jsx(TileButton, {
            onClick: ask,
            disabled: text.trim().length < 4 || sending,
            primary: text.trim().length >= 4 && !sending,
            children: sending ? 'sending…' : 'send'
          })
        ]
      }),
      jsx('div', {
        className: 'cc-note',
        style: { marginTop: '5px' },
        children: note || 'plain english — the agent reads the files, edits them and re-validates'
      })
    ]
  })
}

// Tile: title + verdict pill on one line, the verdict sentence under it (the fact before the
// prose), description clamped to two, monospace metadata, actions on hover or focus.
function PluginTile({ plugin, onChanged }) {
  const [busy, setBusy] = useState('')
  const [note, setNote] = useState('')
  const [editing, setEditing] = useState(false)
  const [confirming, setConfirming] = useState(false)
  const verdict = verdictOf(plugin.smoke)

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

  function smoke() {
    setBusy('smoke')
    setNote('')
    CreatorPanel.__api
      .smokeTest(plugin.name)
      .then(result => {
        if (result && result.ok) {
          setNote((result.headline || 'dispatched') +
            (result.first_failure ? ` · ${result.first_failure}` : ''))
          if (onChanged) onChanged()
          return
        }
        setNote((result && result.error) || 'smoke test could not run')
      })
      .catch(err => setNote(String(err && err.message ? err.message : err)))
      .finally(() => setBusy(''))
  }

  const toolCount = (plugin.tools || []).length
  const meta = [`${toolCount} tool${toolCount === 1 ? '' : 's'}`, `${plugin.files} files`]
  if (plugin.version) meta.push(`v${plugin.version}`)
  if (plugin.validated === false) meta.push('validate failed')
  if (plugin.installed) meta.push('installed')
  if (plugin.published) meta.push('on github')

  return jsxs('article', {
    className: 'cc-tile',
    children: [
      jsxs('div', {
        className: 'cc-tile-head',
        children: [
          jsx('h3', { className: 'cc-tile-title', children: plugin.title || plugin.name }),
          jsx('span', { className: `cc-pill ${verdict.tone}`, children: verdict.word })
        ]
      }),
      jsx('div', { className: 'cc-sentence', children: sentenceOf(plugin.smoke) }),
      jsx('p', { className: 'cc-desc', children: plugin.description || 'no description' }),
      jsx('div', {
        className: 'cc-meta',
        children: meta.map((part, index) => jsx('span', { children: index ? `· ${part}` : part }, index))
      }),
      jsxs('div', {
        className: 'cc-actions',
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
            onClick: smoke,
            disabled: !!busy,
            children: busy === 'smoke' ? 'testing…' : 'test it'
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
            ? jsx(TileButton, {
                onClick: () => {
                  openExternal(plugin.published.repo).then(result => {
                    if (result === 'copied') setNote('link copied — open it in a browser')
                    else if (!result) setNote('could not open the repo link')
                  })
                },
                title: plugin.published.repo,
                children: 'repo ↗'
              })
            : null
        ]
      }),
      note
        ? jsx('div', { className: 'cc-note', children: note })
        : null,
      editing ? jsx(ChatEdit, { name: plugin.name, onSaved: onChanged }) : null
    ]
  })
}

function EmptyState() {
  const example = 'Watch GPU prices and tell me when one drops under $600'
  return jsxs('div', {
    className: 'cc-empty',
    children: [
      jsx(Cat, { size: 128 }),
      jsxs('div', {
        children: [
          jsx('div', { className: 'cc-empty-line', children: 'Nothing woven yet.' }),
          jsx('div', {
            className: 'cc-empty-copy',
            children: 'Pick a skill or a cron job you already run, or describe the job in one sentence. ' +
              'Every build lands as files you can read, validates itself, and gets dispatched once before it ships.'
          }),
          jsx('button', {
            className: 'cc-example',
            title: 'use this example',
            onClick: () => {
              if (CreatorPanel.__setIdea) CreatorPanel.__setIdea(example)
            },
            children: `try: ${example}`
          })
        ]
      })
    ]
  })
}

function Hero({ rows }) {
  const ready = rows && rows.length
  return jsxs('div', {
    className: 'cc-hero',
    children: [
      jsx('div', { className: 'cc-sun' }),
      ready ? jsx(Cat, { size: 96 }) : null,
      jsxs('div', {
        className: 'cc-hero-main',
        children: [
          jsx('div', { className: 'cc-word', children: 'Lazy Plugin' }),
          jsx('div', {
            className: 'cc-thesis',
            children: 'a plugin is a spec, a validation, and one dispatch that proves it runs'
          })
        ]
      }),
      jsxs('div', {
        children: [
          rows
            ? jsx('div', {
                className: 'cc-counts',
                children: rows.length ? countsLine(rows) : 'nothing woven yet'
              })
            : null,
          jsx('div', { className: 'cc-stamp', children: BUILD })
        ]
      })
    ]
  })
}

function LazyPage() {
  const [version, setVersion] = useState(0)
  const [rows, setRows] = useState(null)
  const [error, setError] = useState('')
  CreatorPanel.__onBuilt = () => setVersion(value => value + 1)

  useEffect(() => {
    let live = true
    CreatorPanel.__api
      .created()
      .then(payload => {
        if (!live) return
        setError('')
        setRows((payload && payload.created) || [])
      })
      .catch(err => {
        if (!live) return
        setError(String(err && err.message ? err.message : err))
        setRows([])
      })
    return () => { live = false }
  }, [version])

  const count = (rows || []).length
  const tools = (rows || []).reduce((total, row) => total + (row.tools || []).length, 0)

  return jsxs('div', {
    className: 'cc-page',
    children: [
      jsx('style', { children: CC_STYLE }),
      jsx('div', {
        className: 'cc-frame',
        children: jsxs('div', {
          className: 'cc-inner',
          children: [
            jsx(Hero, { rows }),
            jsx('div', { className: 'cc-rule' }),
            jsx('div', { className: 'cc-rule-gap' }),
            jsx(CreatorPanel, {}),
            jsx('div', { className: 'cc-rule', style: { marginTop: '18px' } }),
            jsx('div', { className: 'cc-rule-gap' }),
            error
              ? jsx('div', { className: 'cc-error', children: `could not list what you have built: ${error}` })
              : null,
            jsxs('div', {
              className: 'cc-section',
              children: [
                jsx('div', { className: 'cc-h2', children: 'Built so far' }),
                jsx('div', {
                  className: 'cc-hint',
                  children: rows === null
                    ? 'reading the shelf…'
                    : `${count} plugin${count === 1 ? '' : 's'} · ${tools} tool${tools === 1 ? '' : 's'}`
                })
              ]
            }),
            rows === null
              ? null
              : count
                ? jsx('div', {
                    className: 'cc-tiles',
                    children: rows.map(row =>
                      jsx(PluginTile, {
                        plugin: row,
                        onChanged: () => setVersion(value => value + 1)
                      }, row.name))
                  })
                : jsx(EmptyState, {})
          ]
        })
      })
    ]
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
    title: 'Lazy Plugin — make a plugin from a description or a job you already run',
    onClick: () => host.navigate(ROUTE),
    children: count == null ? 'Lazy Plugin' : `Lazy Plugin · ${count}`
  })
}

LazyChip.__api = null

export default {
  id: ID,
  name: 'Lazy Plugin',
  register(ctx) {
    PLUGIN_CTX = ctx
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
