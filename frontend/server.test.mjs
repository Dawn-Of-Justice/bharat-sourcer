import assert from 'node:assert/strict'
import { once } from 'node:events'
import http from 'node:http'
import { afterEach, test } from 'node:test'
import { createServer } from './server.mjs'

const openServers = []
afterEach(async () => {
  await Promise.all(openServers.splice(0).map(server => new Promise(resolve => server.close(resolve))))
})

async function start(fetchImpl, options = {}) {
  const server = createServer({
    backendBase: 'https://backend.example/',
    integrationKey: 'server-only-key',
    fetchImpl,
    log: () => {},
    ...options,
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
  const base = await start(() => {
    throw new Error('unexpected backend call')
  })
  const response = await fetch(base + '/api/admin')
  assert.equal(response.status, 404)
})

test('serves the frontend and a labelled dummy API response', async () => {
  const base = await start(async () =>
    Response.json({
      job_id: 'dummy-job',
      status: 'awaiting_confirmation',
      demo: true,
      items: [{ line_id: 'L01', raw_name: 'Sample board', qty: 1, evidence: [] }],
    }),
  )
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
  const base = await start(async () =>
    Response.json(
      { projects: [] },
      {
        headers: { 'Cache-Control': 'private, max-age=30' },
      },
    ),
  )
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
  const response = await fetch(base + '/api/v1/jobs/abc/share', {
    method: 'DELETE',
    headers: { 'X-Job-Token': 'job-token', 'X-Requested-With': 'BharatSourcer' },
  })
  assert.equal(response.status, 204)
  assert.equal(received.url, 'https://backend.example/v1/jobs/abc/share')
  assert.equal(received.options.method, 'DELETE')
  assert.equal(received.options.body, undefined)
  assert.equal(received.options.headers['X-Job-Token'], 'job-token')
  assert.equal((await fetch(base + '/api/v1/jobs/abc/share', { method: 'PUT' })).status, 405)
})

function assertSecurityHeaders(response) {
  assert.equal(response.headers.get('strict-transport-security'), 'max-age=31536000; includeSubDomains')
  assert.equal(response.headers.get('x-content-type-options'), 'nosniff')
  assert.equal(response.headers.get('referrer-policy'), 'strict-origin-when-cross-origin')
  assert.equal(response.headers.get('x-frame-options'), 'DENY')
  assert.match(response.headers.get('content-security-policy'), /frame-ancestors 'none'/)
  assert.equal(response.headers.get('permissions-policy'), 'camera=(), microphone=(), geolocation=()')
  assert.equal(response.headers.get('cross-origin-opener-policy'), 'same-origin-allow-popups')
}

test('every response carries the security headers', async () => {
  const base = await start(async url => {
    if (url.pathname === '/v1/broken') throw new Error('backend down')
    return Response.json({ ok: true }, { headers: { 'X-Frame-Options': 'SAMEORIGIN' } })
  })
  const responses = await Promise.all([
    fetch(base + '/'),
    fetch(base + '/shared/abc.def'),
    fetch(base + '/favicon.svg'),
    fetch(base + '/config.js'),
    fetch(base + '/api/v1/projects'),
    fetch(base + '/api/v1/broken'),
    fetch(base + '/api/admin'),
    fetch(base + '/assets/missing-file.js'),
    fetch(base + '/', { method: 'POST' }),
  ])
  assert.deepEqual(
    responses.map(response => response.status),
    [200, 200, 200, 200, 200, 502, 404, 404, 405],
  )
  responses.forEach(assertSecurityHeaders)
})

test('HTML pages get the full CSP without unsafe-eval or inline scripts', async () => {
  const previous = process.env.FIREBASE_AUTH_DOMAIN
  process.env.FIREBASE_AUTH_DOMAIN = 'demo-project.firebaseapp.com'
  try {
    const base = await start(async () => Response.json({}))
    const csp = (await fetch(base + '/')).headers.get('content-security-policy')
    const directives = Object.fromEntries(
      csp.split(';').map(part => {
        const [name, ...sources] = part.trim().split(/\s+/)
        return [name, sources]
      }),
    )
    assert.deepEqual(directives['default-src'], ["'self'"])
    assert.deepEqual(directives['script-src'], ["'self'", 'https://apis.google.com'])
    assert.ok(directives['frame-src'].includes('https://demo-project.firebaseapp.com'))
    assert.ok(directives['img-src'].includes('https:'))
    assert.ok(directives['connect-src'].includes('https://identitytoolkit.googleapis.com'))
    assert.deepEqual(directives['object-src'], ["'none'"])
    assert.deepEqual(directives['frame-ancestors'], ["'none'"])
    assert.doesNotMatch(csp, /unsafe-eval/)
    assert.doesNotMatch(directives['script-src'].join(' '), /unsafe-inline/)
    const api = await fetch(base + '/api/v1/projects')
    assert.equal(api.headers.get('content-security-policy'), "frame-ancestors 'none'")
  } finally {
    if (previous === undefined) delete process.env.FIREBASE_AUTH_DOMAIN
    else process.env.FIREBASE_AUTH_DOMAIN = previous
  }
})

function rawGet(base, pathname, headers) {
  const { port } = new URL(base)
  return new Promise((resolve, reject) => {
    const req = http.request({ host: '127.0.0.1', port, path: pathname, headers }, res => {
      res.resume()
      res.on('end', () => resolve(res))
    })
    req.on('error', reject)
    req.end()
  })
}

test('plain-HTTP requests behind the proxy are redirected to HTTPS', async () => {
  let backendCalls = 0
  const base = await start(async () => {
    backendCalls += 1
    return Response.json({})
  })
  const page = await rawGet(base, '/job/abc?x=1', { Host: 'bharatsourcer.web.app', 'X-Forwarded-Proto': 'http' })
  assert.equal(page.statusCode, 301)
  assert.equal(page.headers.location, 'https://bharatsourcer.web.app/job/abc?x=1')
  assert.equal(page.headers['strict-transport-security'], 'max-age=31536000; includeSubDomains')
  const api = await rawGet(base, '/api/v1/projects', {
    Host: 'bharat-sourcer-web.a.run.app',
    'X-Forwarded-Host': 'bharatsourcer.web.app',
    'X-Forwarded-Proto': 'http',
  })
  assert.equal(api.statusCode, 301)
  assert.equal(api.headers.location, 'https://bharatsourcer.web.app/api/v1/projects')
  assert.equal(backendCalls, 0)

  const secure = await rawGet(base, '/', { Host: 'bharatsourcer.web.app', 'X-Forwarded-Proto': 'https' })
  assert.equal(secure.statusCode, 200)
  for (const host of ['localhost:8080', '127.0.0.1', '[::1]:5173']) {
    const local = await rawGet(base, '/', { Host: host, 'X-Forwarded-Proto': 'http' })
    assert.equal(local.statusCode, 200, host)
  }
  const odd = await rawGet(base, '/', { Host: 'evil.example/phish', 'X-Forwarded-Proto': 'http' })
  assert.equal(odd.headers.location, undefined)
})

const TRACE_ID = '105445aa7843bc8bf206b12000100000'
const W3C_TRACE = '4bf92f3577b34da6a3ce929d0e0e4736'
const TRACEPARENT = '00-' + W3C_TRACE + '-00f067aa0ba902b7-01'

test('proxy forwards well-formed trace headers so one trace spans both services', async () => {
  const received = []
  const base = await start(async (url, options) => {
    received.push(options.headers)
    return Response.json({})
  })
  await fetch(base + '/api/v1/projects', {
    headers: { 'X-Cloud-Trace-Context': TRACE_ID + '/1;o=1', traceparent: TRACEPARENT },
  })
  assert.equal(received[0]['X-Cloud-Trace-Context'], TRACE_ID + '/1;o=1')
  assert.equal(received[0].traceparent, TRACEPARENT)

  await fetch(base + '/api/v1/projects', {
    headers: { 'X-Cloud-Trace-Context': 'not-a-trace', traceparent: '00-xyz' },
  })
  assert.equal(received[1]['X-Cloud-Trace-Context'], undefined)
  assert.equal(received[1].traceparent, undefined)
  await fetch(base + '/api/v1/projects')
  assert.deepEqual(
    Object.keys(received[2]).filter(name => /trace/i.test(name)),
    [],
  )
})

test('proxy failures log one structured JSON line with the trace and no secrets', async () => {
  const lines = []
  const base = await start(
    async url => {
      if (url.pathname.endsWith('/overloaded')) return new Response('busy', { status: 503 })
      if (url.pathname.startsWith('/v1/shared/')) throw new TypeError('fetch failed')
      return Response.json({})
    },
    { log: line => lines.push(line), project: 'synthetic-project' },
  )
  const failed = await fetch(base + '/api/v1/shared/0b8f5a3e.secret-share-token?code=private', {
    headers: {
      'X-Cloud-Trace-Context': TRACE_ID + '/10;o=1',
      Cookie: 'bs_session=private-cookie',
      Authorization: 'Bearer private-id-token',
    },
  })
  assert.equal(failed.status, 502)
  assert.equal(lines.length, 1)
  const entry = JSON.parse(lines[0])
  assert.equal(entry.severity, 'ERROR')
  assert.equal(entry.event, 'PROXY_ERROR')
  assert.equal(entry.message, 'PROXY_ERROR GET /v1/shared/:token status=502 reason=fetch_failed')
  assert.equal(entry.status, 502)
  assert.equal(entry.upstream_status, null)
  assert.equal(entry.reason, 'fetch_failed')
  assert.equal(entry.error, 'TypeError')
  assert.equal(entry.route, '/v1/shared/:token')
  assert.equal(typeof entry.duration_ms, 'number')
  assert.equal(entry['logging.googleapis.com/trace'], 'projects/synthetic-project/traces/' + TRACE_ID)
  assert.equal(entry['logging.googleapis.com/spanId'], '000000000000000a')
  for (const secret of ['secret-share-token', 'private', 'bs_session', 'Bearer']) {
    assert.doesNotMatch(lines[0], new RegExp(secret))
  }

  const busy = await fetch(base + '/api/v1/jobs/0b8f5a3e-1c2d-4e5f-8a9b-0c1d2e3f4a5b/overloaded', {
    headers: { traceparent: TRACEPARENT },
  })
  assert.equal(busy.status, 503)
  assert.equal(await busy.text(), 'busy')
  const gateway = JSON.parse(lines[1])
  assert.equal(gateway.reason, 'upstream_status')
  assert.equal(gateway.status, 503)
  assert.equal(gateway.upstream_status, 503)
  assert.equal(gateway.route, '/v1/jobs/:id/overloaded')
  assert.equal(gateway['logging.googleapis.com/trace'], 'projects/synthetic-project/traces/' + W3C_TRACE)
  assert.equal(gateway['logging.googleapis.com/spanId'], '00f067aa0ba902b7')

  assert.equal((await fetch(base + '/api/v1/projects')).status, 200)
  assert.equal(lines.length, 2) // successes are left to Cloud Run's request log
})
