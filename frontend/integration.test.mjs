import assert from 'node:assert/strict'
import { test } from 'node:test'
import { readFileSync } from 'node:fs'
import ts from 'typescript'

// Real client against an owner-aware backend fake: no Firebase or network calls.
const source = readFileSync(new URL('./src/api.ts', import.meta.url), 'utf8').replaceAll('import.meta.env', '({DEV:false, PROD:true})')
const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText
let bearer = null, guestCookie = null, failure = null
let calls = []
const projects = new Map([['guest', ['guest-project']], ['alice', ['alice-project']], ['bob', ['bob-project']]])
const api = {}
new Function('require', 'exports', compiled)(name => name === './auth' ? { identityToken: async () => bearer } : null, api)
globalThis.window = { location: { search: '' }, dispatchEvent: () => {} }
globalThis.fetch = async (url, options) => {
  calls.push({ url, options })
  const json = (status, body, headers = {}) => new Response(JSON.stringify(body), { status, headers })
  if (failure) return json(failure.status, { error: { code: failure.code, message: failure.code } }, failure.headers)
  const path = new URL(url, 'https://front.example').pathname
  if (path === '/api/v1/session/guest') { guestCookie = 'guest'; return json(200, { kind: 'guest', part_limit: 3 }) }
  const owner = bearer || guestCookie
  if (!owner) return json(401, { error: { code: 'IDENTITY_REQUIRED' } })
  if (path === '/api/v1/session') return json(200, { kind: bearer ? 'account' : 'guest' })
  if (path === '/api/v1/session/usage') return json(200, { daily_projects: { remaining: 0 }, daily_actions: { remaining: 0 } })
  if (path === '/api/v1/projects/guest-project/claim' && bearer && guestCookie) { projects.set(bearer, [...projects.get(bearer), ...projects.get('guest')]); projects.set('guest', []); return json(200, {}) }
  if (path === '/api/v1/projects') return json(200, { projects: (projects.get(owner) ?? []).map(job_id => ({ job_id })), next_cursor: null })
  const id = path.match(/^\/api\/v1\/jobs\/([^/]+)$/)?.[1]
  if (id && projects.get(owner)?.includes(id)) return json(200, { job_id: id, items: [], messages: [{ text: 'Saved chat' }], report: { lines: [{ research: { candidates: [] }, offers: [] }] } })
  return json(404, { error: { code: 'JOB_NOT_FOUND' } })
}

test('returning account reopens saved BOM, chat, research and offers without job creation', async () => {
  bearer = 'alice'; guestCookie = null; calls = []
  const saved = await api.listProjects()
  const job = await api.getJob(saved.projects[0].job_id, '')
  assert.equal(job.messages[0].text, 'Saved chat')
  assert.deepEqual(job.report.lines[0].offers, [])
  assert.deepEqual(job.report.lines[0].research.candidates, [])
  assert.ok(calls.every(call => call.options.method !== 'POST'))
  assert.ok(calls.every(call => call.options.credentials === 'include' && call.options.headers.Authorization === 'Bearer alice'))
})

test('guest claim sends bearer and cookie-capable request, then denies old guest', async () => {
  bearer = null; await api.startGuest()
  assert.equal((await api.listProjects()).projects[0].job_id, 'guest-project')
  bearer = 'alice'; await api.claimProject('guest-project')
  const claim = calls.at(-1).options
  assert.equal(claim.headers.Authorization, 'Bearer alice')
  assert.equal(claim.credentials, 'include')
  assert.equal(claim.headers['X-Requested-With'], 'BharatSourcer')
  assert.ok((await api.listProjects()).projects.some(p => p.job_id === 'guest-project'))
  bearer = null; assert.equal((await api.listProjects()).projects.length, 0)
})

test('account switch isolates projects', async () => {
  bearer = 'bob'
  assert.deepEqual((await api.listProjects()).projects.map(p => p.job_id), ['bob-project'])
  await assert.rejects(api.getJob('alice-project', ''), e => e.status === 404)
})

test('expired session and temporary provider failure do not create guests', async () => {
  bearer = 'alice'; calls = []
  failure = { status: 401, code: 'IDENTITY_REQUIRED' }
  await assert.rejects(api.getJob('alice-project', ''), e => e.status === 401)
  failure = { status: 503, code: 'IDENTITY_UNAVAILABLE' }
  await assert.rejects(api.getSession(), e => e.status === 503)
  failure = null
  assert.equal(calls.some(call => call.url.endsWith('/session/guest')), false)
})

test('429 is not retried and saved work stays readable at zero quota', async () => {
  bearer = 'alice'; calls = []
  failure = { status: 429, code: 'USAGE_LIMIT', headers: { 'Retry-After': '90' } }
  await assert.rejects(api.createJob('https://example.com/build'), e => e.status === 429 && /saved projects remain available/.test(e.message))
  assert.equal(calls.length, 1)
  failure = null
  assert.ok((await api.listProjects()).projects.length)
  assert.equal((await api.getUsage()).daily_projects.remaining, 0)
})
