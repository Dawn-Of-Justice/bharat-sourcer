import assert from 'node:assert/strict'
import { test } from 'node:test'
import { readFileSync } from 'node:fs'
import ts from 'typescript'

// Run the real frontend preview modules with all network access forbidden.
const storage = new Map()
globalThis.sessionStorage = {
  getItem: key => storage.get(key) ?? null,
  setItem: (key, value) => storage.set(key, value),
  removeItem: key => storage.delete(key),
}
globalThis.location = { search: '?preview=1' }
globalThis.window = { location: globalThis.location }
let requests = 0
globalThis.fetch = () => {
  requests++
  throw new Error('Network forbidden in local preview')
}
const modules = new Map()
function load(name) {
  if (modules.has(name)) return modules.get(name)
  if (name === 'firebase/app')
    return {
      initializeApp: () => {
        throw new Error('Firebase must not initialize in preview')
      },
    }
  if (name === 'firebase/auth') return {}
  const source = readFileSync(new URL('./src/' + name.replace('./', '') + '.ts', import.meta.url), 'utf8').replaceAll(
    'import.meta.env',
    '({DEV:true, PROD:false})',
  )
  const { outputText } = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  })
  const exports = {}
  modules.set(name, exports)
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
  await assert.rejects(
    api.claimProject('unknown').then(() => api.getJob('unknown', '')),
    /unavailable in the local preview/,
  )
  assert.equal(requests, 0)
})

test('preview decision endpoint fails closed for unknown dummy proposals without network', async () => {
  const { previewRequest } = load('./preview')
  assert.equal(previewRequest('/v1/jobs/ui-preview', {}).demo, true)
  assert.throws(
    () =>
      previewRequest('/v1/jobs/ui-preview/messages/missing/decision', {
        method: 'POST',
        body: JSON.stringify({ action: 'accept' }),
      }),
    error => error.status === 404,
  )
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
  const inferredRequirements = job.items
    .flatMap(item => item.requirements ?? [])
    .filter(item => item.origin === 'inferred')
  assert.ok(inferredRequirements.length > 0)
  assert.ok(inferredRequirements.every(item => /Dummy/.test(item.reason)))
  assert.equal(requests, 0)
})

test('plan preview includes a labelled sample code patch without contacting the backend', () => {
  const { previewRequest } = load('./preview')
  const job = previewRequest('/v1/jobs/ui-preview', {})
  const { planPreview } = load('./previewReport')
  const plan = planPreview(job)
  const patch = plan.report.lines.find(line => line.item.line_id === 'L02').code_patch
  assert.equal(patch.status, 'ready')
  assert.equal(patch.check, 'compiles')
  assert.match(patch.compile.board, /dummy/)
  assert.match(patch.compile.size, /Dummy/)
  assert.match(patch.files[0].diff, /Dummy preview only/)
  assert.ok(patch.notes.every(note => /Dummy/.test(note)))
  assert.equal(requests, 0)
})

test('completed preview covers current buyer decisions and offer selection notices without network', () => {
  const { previewRequest } = load('./preview')
  const { planPreview } = load('./previewReport')
  const job = planPreview(previewRequest('/v1/jobs/ui-preview', {}))
  assert.equal(job.status, 'done')
  assert.equal(job.demo, false) // Enables interactions; the preview toolbar and fixtures label all data as dummy.
  assert.equal(job.refresh_count, 1)
  const controller = job.report.lines.find(line => line.item.line_id === 'L01')
  const expired = controller.offers.find(offer => offer.url.endsWith('controller-expired'))
  assert.ok(Date.now() - Date.parse(expired.checked_at) > 24 * 60 * 60 * 1000)
  assert.equal(expired.stock, 'in_stock')
  assert.equal(expired.match.status, 'exact')
  assert.ok(controller.offers.some(offer => offer.stock === 'unknown'))
  assert.ok(controller.offers.some(offer => offer.stock === 'out_of_stock'))
  assert.ok(controller.offers.some(offer => offer.compatibility?.grade === 'B'))
  assert.ok(controller.offers.every(offer => /dummy/.test(offer.title)))
  const sensor = job.report.lines.find(line => line.item.line_id === 'L02')
  assert.equal(sensor.buyer.fit, 'substitute')
  assert.equal(sensor.buyer.offer_url, sensor.selected_offer_url)
  assert.match(sensor.buyer.reason, /Dummy/)
  const wires = job.report.lines.find(line => line.item.line_id === 'L03')
  assert.match(wires.buyer.value, /dummy/)
  assert.match(wires.buyer.value_reason, /Dummy/)
  assert.equal(requests, 0)
})

test('evidence text renders code, description, page and video evidence without null placeholders', () => {
  assert.equal(
    api.evidenceText({
      source: 'code',
      file: 'src/main.cpp',
      line: 3,
      quote: '#include <Adafruit_BME280.h>',
      url: 'https://github.com/o/r/blob/HEAD/src/main.cpp#L3',
      observation: 'includes the library',
    }),
    'Code src/main.cpp:3 “#include <Adafruit_BME280.h>” — includes the library',
  )
  assert.equal(
    api.evidenceText({
      source: 'youtube_description',
      quote: 'BME280 module',
      timestamp: null,
      observation: 'Listed in the description.',
    }),
    'Video description “BME280 module” — Listed in the description.',
  )
  assert.equal(
    api.evidenceText({ source: 'project_page', quote: 'Arduino Uno', observation: 'Supplies list' }),
    'Page quote “Arduino Uno” — Supplies list',
  )
  assert.equal(
    api.evidenceText({ timestamp: '03:07', observation: 'Shown on the bench' }),
    '03:07 — Shown on the bench',
  )
  assert.doesNotMatch(api.evidenceText({ source: 'video', timestamp: null, observation: 'x' }), /null/)
})

test('preview review fixtures are labelled dummy data and accept a buyable spec edit without network', async () => {
  const { previewRequest } = load('./preview')
  const job = previewRequest('/v1/jobs/ui-preview', {})
  assert.ok(
    job.safety_flags.length > 0 &&
      job.safety_flags.every(flag => /Dummy/.test(flag.title) && /Dummy/.test(flag.message)),
  )
  assert.ok(job.source_reports.some(report => report.status === 'failed' && /Dummy/.test(report.error.message)))
  const needsValue = job.items.find(item => item.buyable_spec?.needs_value)
  assert.ok(needsValue && /Dummy/.test(needsValue.buyable_spec.needs_value_reason))
  assert.ok(job.items.every(item => !item.conflicts?.length))
  assert.equal(needsValue.raw_name, 'Jumper wires')
  const spec = {
    ...needsValue.buyable_spec,
    origin: 'user',
    needs_value: false,
    params: [{ name: 'wire length', value: '20 cm', operator: 'at_least', origin: 'user' }],
  }
  await api.confirmJob('ui-preview', 'dummy-token', [{ op: 'update', line_id: needsValue.line_id, buyable_spec: spec }])
  const saved = previewRequest('/v1/jobs/ui-preview', {})
  assert.equal(saved.items.find(item => item.line_id === needsValue.line_id).buyable_spec.params[0].value, '20 cm')
  assert.equal(requests, 0)
})

test('preview saves project details and serves a labelled part fallback without network', async () => {
  const saved = await api.updateProject('ui-preview', 'dummy-token', {
    title: 'My sample build',
    description: 'Dummy edited description',
  })
  assert.equal(saved.project.title, 'My sample build')
  assert.equal(saved.project.title_source, 'user')
  assert.equal((await api.listProjects()).projects[0].title, 'My sample build')
  await api.deleteProject('ui-preview-failed')
  assert.deepEqual(
    (await api.listProjects()).projects.map(project => project.job_id),
    ['ui-preview', 'ui-preview-github', 'ui-preview-blog'],
  )
  const images = await api.getPartImages('ui-preview', 'dummy-token', 'L01')
  assert.equal(images.fallback.kind, 'category')
  assert.match(images.fallback.label, /Dummy illustration/)
  assert.equal(requests, 0)
})

test('preview seller selection switches directly, clears and reselects without network', async () => {
  const { planPreview, previewReportRequest } = load('./previewReport')
  const fixture = planPreview(await api.getJob('ui-preview', 'dummy-token'))
  const line = fixture.report.lines.find(line => line.item.line_id === 'L01')
  const original = line.selected_offer_url
  const alternate = line.offers.find(offer => offer.seller_name === 'Sample Seller C (dummy)').url
  for (const offer_url of [alternate, original, null, alternate]) {
    const result = previewReportRequest(
      '/v1/jobs/ui-preview/selections',
      { method: 'POST', body: JSON.stringify({ selections: [{ line_id: 'L01', offer_url }] }) },
      fixture,
    )
    assert.equal(result.report.lines.find(line => line.item.line_id === 'L01').selected_offer_url, offer_url)
    const picks = result.report.order_plan.sellers
      .flatMap(seller => seller.lines)
      .filter(line => line.line_id === 'L01')
    assert.equal(picks.length, offer_url ? 1 : 0)
    if (offer_url) assert.equal(picks[0].offer_url, offer_url)
  }
  assert.equal(requests, 0)
})

test('preview report endpoints (share, shared page, plans, exports) stay local and labelled', async () => {
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
  const plans = await api.getPlans('ui-preview', 'dummy-token')
  assert.deepEqual(
    plans.plans.map(plan => plan.kind),
    ['cheapest', 'fewest_sellers', 'recommended'],
  )
  assert.match(
    await (await api.exportBlob('/v1/jobs/ui-preview/export.pdf', 'dummy-token')).text(),
    /^%PDF[\s\S]*DEMO JOB/,
  )
  assert.equal(requests, 0)
})

test('seller retry separates missing details and available offers from retryable parts', async () => {
  const { planPreview } = load('./previewReport')
  const { sellerSearchOutcomes } = load('./sellerSearch')
  const fixture = planPreview(await api.getJob('ui-preview', 'dummy-token'))
  const rows = sellerSearchOutcomes(fixture)
  assert.deepEqual(
    rows.filter(row => row.kind === 'ready').map(row => row.item.line_id),
    ['L01', 'L02'],
  )
  assert.deepEqual(
    rows.filter(row => row.kind === 'details').map(row => row.item.line_id),
    ['L03', 'L04'],
  )
  assert.deepEqual(
    rows.filter(row => row.kind === 'retry').map(row => row.item.line_id),
    ['L05', 'L06'],
  )
  const controller = fixture.report.lines.find(line => line.item.line_id === 'L01')
  controller.offers = [controller.offers.find(offer => offer.url.endsWith('controller-expired'))]
  assert.equal(sellerSearchOutcomes(fixture)[0].reason, 'Quotes expired')
  fixture.items[0].user_has_it = true
  assert.equal(sellerSearchOutcomes(fixture)[0].kind, 'owned')
})

test('seller-search completion stays on Find sellers while reopening a completed job keeps its order plan', () => {
  const { sellerSearchViewAfterUpdate } = load('./sellerSearch')
  for (const status of ['resolving', 'sourcing', 'paused'])
    assert.equal(sellerSearchViewAfterUpdate(status, 'done', false), 1)
  assert.equal(sellerSearchViewAfterUpdate(undefined, 'done', false), null)
  assert.equal(sellerSearchViewAfterUpdate(undefined, 'done', true), 1)
  assert.equal(sellerSearchViewAfterUpdate('done', 'sourcing', false), null)
})

test('local retry progresses, preserves untouched parts, and enforces batch and retry limits without network', async () => {
  const { planPreview, previewReportRequest } = load('./previewReport')
  const { sellerSearchOutcomes } = load('./sellerSearch')
  const fixture = planPreview(await api.getJob('ui-preview', 'dummy-token'))
  const original = structuredClone(fixture.report.lines.slice(0, 4))
  const post = ids =>
    previewReportRequest(
      '/v1/jobs/ui-preview/refresh',
      {
        method: 'POST',
        body: JSON.stringify({ line_ids: ids }),
      },
      fixture,
    )
  for (const ids of [[], ['L05', 'L05'], ['missing'], Array.from({ length: 11 }, (_, i) => `L${i}`)])
    assert.throws(
      () => post(ids),
      error => error.status === 422,
    )
  post(['L05', 'L06'])
  assert.equal(fixture.status, 'sourcing')
  assert.equal(fixture.refresh_count, 2)
  assert.equal(fixture.report.lines.find(line => line.item.line_id === 'L06').sourcing_status, 'not_run')
  assert.throws(
    () => post(['L05']),
    error => error.status === 409,
  )
  const originalNow = Date.now
  const later = originalNow() + 4000
  try {
    Date.now = () => later
    previewReportRequest('/v1/jobs/ui-preview', {}, fixture)
  } finally {
    Date.now = originalNow
  }
  assert.equal(fixture.status, 'done')
  assert.deepEqual(fixture.report.lines.slice(0, 4), original)
  const outcomes = sellerSearchOutcomes(fixture)
  assert.equal(outcomes.find(row => row.item.line_id === 'L06').kind, 'ready')
  assert.equal(outcomes.find(row => row.item.line_id === 'L05').kind, 'retry')
  assert.throws(
    () => post(['L05']),
    error => error.status === 409,
  )
  assert.equal(requests, 0)
})

test('preview project overview is labelled sample data and every wire names an existing part and pin', () => {
  const { previewRequest } = load('./preview')
  const overview = previewRequest('/v1/jobs/ui-preview/overview', {})
  assert.equal(overview.status, 'ready')
  assert.equal(overview.demo, true)
  assert.match(overview.judge.summary, /Sample/)
  const pins = new Map(overview.parts.map(part => [part.line_id, part.headers.flatMap(h => h.pins.map(p => p.name))]))
  for (const wire of overview.wiring)
    for (const end of [wire.from, wire.to]) assert.ok(pins.get(end.line_id)?.includes(end.pin), wire.id + ' ' + end.pin)
  const verdicts = [...overview.parts, ...overview.wiring].map(entry => entry.verdict)
  for (const verdict of ['confirmed', 'unverified', 'disputed'])
    assert.equal(overview.judge[verdict], verdicts.filter(value => value === verdict).length)
  assert.equal(previewRequest('/v1/jobs/ui-preview', {}).overview.status, 'ready')
  assert.equal(requests, 0)
})
