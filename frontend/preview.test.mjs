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
  assert.equal(guestProjects.projects[0].job_id, 'ui-preview')
  assert.equal(guestProjects.projects.length, 4)
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

test('evidence text renders code, description, page and video evidence without null placeholders', () => {
  assert.equal(api.evidenceText({ source: 'code', file: 'src/main.cpp', line: 3, quote: '#include <Adafruit_BME280.h>', url: 'https://github.com/o/r/blob/HEAD/src/main.cpp#L3', observation: 'includes the library' }), 'Code src/main.cpp:3 “#include <Adafruit_BME280.h>” — includes the library')
  assert.equal(api.evidenceText({ source: 'youtube_description', quote: 'BME280 module', timestamp: null, observation: 'Listed in the description.' }), 'Video description “BME280 module” — Listed in the description.')
  assert.equal(api.evidenceText({ source: 'project_page', quote: 'Arduino Uno', observation: 'Supplies list' }), 'Page quote “Arduino Uno” — Supplies list')
  assert.equal(api.evidenceText({ timestamp: '03:07', observation: 'Shown on the bench' }), '03:07 — Shown on the bench')
  assert.doesNotMatch(api.evidenceText({ source: 'video', timestamp: null, observation: 'x' }), /null/)
})

test('preview review fixtures are labelled dummy data and accept a buyable spec edit without network', async () => {
  const { previewRequest } = load('./preview')
  const job = previewRequest('/v1/jobs/ui-preview', {})
  assert.ok(job.safety_flags.length > 0 && job.safety_flags.every(flag => /Dummy/.test(flag.title) && /Dummy/.test(flag.message)))
  assert.ok(job.source_reports.some(report => report.status === 'failed' && /Dummy/.test(report.error.message)))
  const needsValue = job.items.find(item => item.buyable_spec?.needs_value)
  assert.ok(needsValue && /Dummy/.test(needsValue.buyable_spec.needs_value_reason))
  assert.ok(job.items.every(item => !item.conflicts?.length))
  assert.equal(needsValue.raw_name, 'Jumper wires')
  const spec = { ...needsValue.buyable_spec, origin: 'user', needs_value: false, params: [{ name: 'wire length', value: '20 cm', operator: 'at_least', origin: 'user' }] }
  await api.confirmJob('ui-preview', 'dummy-token', [{ op: 'update', line_id: needsValue.line_id, buyable_spec: spec }])
  const saved = previewRequest('/v1/jobs/ui-preview', {})
  assert.equal(saved.items.find(item => item.line_id === needsValue.line_id).buyable_spec.params[0].value, '20 cm')
  assert.equal(requests, 0)
})

test('preview saves project details and serves a labelled part fallback without network', async () => {
  const saved = await api.updateProject('ui-preview', 'dummy-token', { title: 'My sample build', description: 'Dummy edited description' })
  assert.equal(saved.project.title, 'My sample build')
  assert.equal(saved.project.title_source, 'user')
  assert.equal((await api.listProjects()).projects[0].title, 'My sample build')
  await api.deleteProject('ui-preview-failed')
  assert.deepEqual((await api.listProjects()).projects.map(project => project.job_id), ['ui-preview', 'ui-preview-github', 'ui-preview-blog'])
  const images = await api.getPartImages('ui-preview', 'dummy-token', 'L01')
  assert.equal(images.fallback.kind, 'category')
  assert.match(images.fallback.label, /Dummy illustration/)
  assert.equal(requests, 0)
})

test('preview report endpoints (share, shared page, markets, plans, extras, exports) stay local and labelled', async () => {
  assert.equal((await api.getShare('ui-preview', 'dummy-token')).active, false)
  const link = await api.createShare('ui-preview', 'dummy-token')
  assert.equal((await api.getShare('ui-preview', 'dummy-token')).active, true)
  const shared = await api.getShared(link.share_token)
  assert.match(shared.notice, /Dummy/)
  assert.ok(shared.report.order_plan.sellers.every(seller => /dummy/.test(seller.seller)))
  assert.ok(shared.report.lines.every(line => line.line_image && line.line_image.label))
  const copied = await api.copyShared('ui-preview.dummy')
  assert.equal(copied.job_id, 'ui-preview')
  assert.ok((await api.getJob('ui-preview', 'dummy-token')).copied_from?.copied_at)
  await api.revokeShare('ui-preview', 'dummy-token')
  assert.equal((await api.getShare('ui-preview', 'dummy-token')).active, false)
  const sample = await api.getMarkets('ui-preview', 'dummy-token', { city: 'Chennai' })
  assert.equal(sample.demo, true)
  assert.equal(sample.attribution.sources.length, 0)
  await assert.rejects(api.getMarkets('ui-preview', 'dummy-token', { city: 'Atlantis' }), error => error.code === 'CITY_NOT_SUPPORTED')
  const plans = await api.getPlans('ui-preview', 'dummy-token')
  assert.deepEqual(plans.plans.map(plan => plan.kind), ['cheapest', 'fewest_sellers', 'recommended'])
  assert.equal((await api.getExtras('ui-preview', 'dummy-token')).explain.enabled, true)
  assert.match(await (await api.exportBlob('/v1/jobs/ui-preview/export.pdf', 'dummy-token')).text(), /^%PDF[\s\S]*DEMO JOB/)
  assert.equal(requests, 0)
})
