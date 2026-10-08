import assert from 'node:assert/strict'
import { once } from 'node:events'
import { afterEach, test } from 'node:test'
import { createServer } from './server.mjs'

const openServers = []
afterEach(async () => {
  await Promise.all(openServers.splice(0).map(server => new Promise(resolve => server.close(resolve))))
})

async function start(fetchImpl) {
  const server = createServer({
    backendBase: 'https://backend.example/',
    integrationKey: 'server-only-key',
    fetchImpl,
  })
  openServers.push(server)
  server.listen(0, '127.0.0.1')
  await once(server, 'listening')
  return 'http://127.0.0.1:' + server.address().port
}

test('proxy injects the server key and forwards only needed request headers', async () => {
  let received
  const base = await start(async (url, options) => {
    received = { url: url.toString(), options }
    return new Response(JSON.stringify({ status: 'queued' }), {
      status: 202,
      headers: { 'Content-Type': 'application/json' },
    })
  })
  const response = await fetch(base + '/api/v1/jobs/abc/messages', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Integration-Key': 'browser-supplied-key',
      'X-Job-Token': 'job-token',
      Cookie: 'private-cookie',
      Authorization: 'Bearer test-id-token',
      'X-Requested-With': 'BharatSourcer',
      Origin: 'https://frontend.example',
      'X-Client-IP': 'spoofed',
    },
    body: '{"text":"hello"}',
  })
  assert.equal(response.status, 202)
  assert.equal(received.url, 'https://backend.example/v1/jobs/abc/messages')
  assert.equal(received.options.headers['X-Integration-Key'], 'server-only-key')
  assert.equal(received.options.headers['X-Job-Token'], 'job-token')
  assert.equal(received.options.headers.Cookie, 'private-cookie')
  assert.equal(received.options.headers.Authorization, 'Bearer test-id-token')
  assert.equal(received.options.headers['X-Requested-With'], 'BharatSourcer')
  assert.equal(received.options.headers.Origin, 'https://frontend.example')
  assert.equal(received.options.headers['X-Client-IP'], undefined)
  assert.equal(received.options.body.toString(), '{"text":"hello"}')
})

test('healthz uses the cloud-safe backend health route', async () => {
  let target
  const base = await start(async url => {
    target = url.toString()
    return Response.json({ status: 'ok' })
  })
  const response = await fetch(base + '/api/healthz')
  assert.equal(response.status, 200)
  assert.equal(target, 'https://backend.example/health')
})

test('proxy rejects unlisted API routes without contacting the backend', async () => {
  const base = await start(() => { throw new Error('unexpected backend call') })
  const response = await fetch(base + '/api/admin')
  assert.equal(response.status, 404)
})

test('serves the frontend and a labelled dummy API response', async () => {
  const base = await start(async () => Response.json({
    job_id: 'dummy-job',
    status: 'awaiting_confirmation',
    demo: true,
    items: [{ line_id: 'L01', raw_name: 'Sample board', qty: 1, evidence: [] }],
  }))
  const page = await fetch(base + '/')
  assert.equal(page.status, 200)
  assert.equal(page.headers.get('www-authenticate'), null)
  assert.match(await page.text(), /id="root"/)
  const created = await fetch(base + '/api/v1/jobs', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url: 'https://example.com/dummy' }),
  })
  assert.equal(created.status, 200)
  const job = await created.json()
  assert.equal(job.demo, true)
  assert.equal(job.items[0].raw_name, 'Sample board')
})

test('share links load the app although their token contains a dot', async () => {
  const base = await start(async () => Response.json({}))
  const shared = await fetch(base + '/shared/0b8f5a3e-1c2d-4e5f-8a9b-0c1d2e3f4a5b.AbC_dEf-123')
  assert.equal(shared.status, 200)
  assert.match(await shared.text(), /id="root"/)
  assert.equal((await fetch(base + '/assets/missing-file.js')).status, 404)
})

test('proxy preserves separate cookies, quota delay, and no-store on identity responses', async () => {
  const base = await start(async () => {
    const headers = new Headers({ 'Retry-After': '3600' })
    headers.append('Set-Cookie', 'bs_guest=demo; HttpOnly; Secure; SameSite=Lax')
    headers.append('Set-Cookie', 'another=value; Expires=Wed, 21 Oct 2026 07:28:00 GMT')
    return new Response(null, { status: 204, headers })
  })
  const response = await fetch(base + '/api/v1/session/logout', { method: 'POST' })
  assert.equal(response.status, 204)
  assert.equal(response.headers.getSetCookie().length, 2)
  assert.equal(response.headers.get('retry-after'), '3600')
  assert.equal(response.headers.get('cache-control'), 'no-store')
  assert.equal(await response.text(), '')
})

test('proxy preserves an upstream Cache-Control policy', async () => {
  const base = await start(async () => Response.json({ projects: [] }, {
    headers: { 'Cache-Control': 'private, max-age=30' },
  }))
  const response = await fetch(base + '/api/v1/projects')
  assert.equal(response.status, 200)
  assert.equal(response.headers.get('cache-control'), 'private, max-age=30')
})

test('proxy forwards DELETE without a body so owners can revoke share links', async () => {
  let received
  const base = await start(async (url, options) => {
    received = { url: url.toString(), options }
    return new Response(null, { status: 204 })
  })
  const response = await fetch(base + '/api/v1/jobs/abc/share', { method: 'DELETE', headers: { 'X-Job-Token': 'job-token', 'X-Requested-With': 'BharatSourcer' } })
  assert.equal(response.status, 204)
  assert.equal(received.url, 'https://backend.example/v1/jobs/abc/share')
  assert.equal(received.options.method, 'DELETE')
  assert.equal(received.options.body, undefined)
  assert.equal(received.options.headers['X-Job-Token'], 'job-token')
  assert.equal((await fetch(base + '/api/v1/jobs/abc/share', { method: 'PUT' })).status, 405)
})
