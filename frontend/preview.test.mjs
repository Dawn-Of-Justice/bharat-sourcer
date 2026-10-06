import assert from 'node:assert/strict'
import { test } from 'node:test'
import { readFileSync } from 'node:fs'
import ts from 'typescript'

// Run the real frontend preview modules with all network access forbidden.
const storage = new Map()
globalThis.sessionStorage = { getItem: key => storage.get(key) ?? null, setItem: (key, value) => storage.set(key, value), removeItem: key => storage.delete(key) }
globalThis.location = { search: '?preview=1' }
globalThis.window = { location: globalThis.location }
let requests = 0
globalThis.fetch = () => { requests++; throw new Error('Network forbidden in local preview') }
const modules = new Map()
function load(name) {
  if (modules.has(name)) return modules.get(name)
  if (name === 'firebase/app') return { initializeApp: () => { throw new Error('Firebase must not initialize in preview') } }
  if (name === 'firebase/auth') return {}
  const source = readFileSync(new URL('./src/' + name.replace('./', '') + '.ts', import.meta.url), 'utf8').replaceAll('import.meta.env', '({DEV:true, PROD:false})')
  const { outputText } = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } })
  const exports = {}; modules.set(name, exports)
  new Function('require', 'exports', outputText)(load, exports)
  return exports
}
const api = load('./api')
const auth = load('./auth')

test('preview supports signed-out, guest, account, saved project and logout without network', async () => {
  await assert.rejects(api.getSession(), error => error.code === 'IDENTITY_REQUIRED')
  assert.equal((await api.startGuest()).kind, 'guest')
  const guestProjects = await api.listProjects()
  assert.equal(guestProjects.projects.length, 1)
  await auth.googleLogin()
  assert.equal((await api.getSession()).kind, 'account')
  await api.claimProject(guestProjects.projects[0].job_id)
  const saved = await api.getJob(guestProjects.projects[0].job_id, '')
  assert.equal(saved.demo, true)
  assert.equal(saved.items.length, 3)
  assert.equal((await api.getUsage()).daily_projects.remaining, 4)
  await api.logoutSession()
  await auth.firebaseLogout()
  await assert.rejects(api.getSession(), error => error.status === 401)
  assert.equal(requests, 0)
})

test('unsupported preview actions fail closed without falling through to live API', async () => {
  await assert.rejects(api.claimProject('unknown').then(() => api.getJob('unknown', '')), /unavailable in the local preview/)
  assert.equal(requests, 0)
})

test('preview decision endpoint fails closed for unknown dummy proposals without network', async () => {
  const { previewRequest } = load('./preview')
  assert.equal(previewRequest('/v1/jobs/ui-preview', {}).demo, true)
  assert.throws(() => previewRequest('/v1/jobs/ui-preview/messages/missing/decision', { method: 'POST', body: JSON.stringify({ action: 'accept' }) }), error => error.status === 404)
  assert.equal(requests, 0)
})

test('preview labels AI project understanding, inferred qty and inferred build details as dummy data', () => {
  const { previewRequest } = load('./preview')
  const job = previewRequest('/v1/jobs/ui-preview', {})
  assert.equal(job.project.origin, 'ai_inferred')
  assert.match(job.project.summary, /Dummy/)
  const inferredQty = job.items.filter(item => item.qty_source === 'inferred')
  assert.equal(inferredQty.length, 1)
  assert.match(inferredQty[0].qty_reason, /Dummy/)
  const inferredRequirements = job.items.flatMap(item => item.requirements ?? []).filter(item => item.origin === 'inferred')
  assert.ok(inferredRequirements.length > 0)
  assert.ok(inferredRequirements.every(item => /Dummy/.test(item.reason)))
  assert.equal(requests, 0)
})

test('preview saves project details and serves a labelled part fallback without network', async () => {
  const saved = await api.updateProject('ui-preview', 'dummy-token', { title: 'My sample build', description: 'Dummy edited description' })
  assert.equal(saved.project.title, 'My sample build')
  assert.equal(saved.project.title_source, 'user')
  assert.equal((await api.listProjects()).projects[0].title, 'My sample build')
  const images = await api.getPartImages('ui-preview', 'dummy-token', 'L01')
  assert.equal(images.fallback.kind, 'category')
  assert.match(images.fallback.label, /Dummy illustration/)
  assert.equal(requests, 0)
})
