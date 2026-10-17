import { createReadStream } from 'node:fs'
import { stat } from 'node:fs/promises'
import http from 'node:http'
import path from 'node:path'
import { Readable } from 'node:stream'
import { pipeline } from 'node:stream/promises'
import { fileURLToPath } from 'node:url'

const defaultDist = path.join(path.dirname(fileURLToPath(import.meta.url)), 'dist')
const contentTypes = {
  '.css': 'text/css; charset=utf-8',
  '.html': 'text/html; charset=utf-8',
  '.ico': 'image/x-icon',
  '.js': 'text/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.png': 'image/png',
  '.svg': 'image/svg+xml',
  '.webp': 'image/webp',
}

// Security headers sent on every response: static files, index.html, /config.js, proxied API
// responses, redirects and errors. Browsers ignore HSTS over plain-HTTP localhost, so it is harmless
// in development. COOP is same-origin-allow-popups (not same-origin) because Google sign-in uses
// Firebase signInWithPopup (src/auth.ts), whose popup must keep talking to this page.
// Non-HTML responses carry only the frame-ancestors part of the CSP; HTML gets the full policy.
export const SECURITY_HEADERS = {
  'Strict-Transport-Security': 'max-age=31536000; includeSubDomains',
  'X-Content-Type-Options': 'nosniff',
  'Referrer-Policy': 'strict-origin-when-cross-origin',
  'X-Frame-Options': 'DENY',
  'Content-Security-Policy': "frame-ancestors 'none'",
  'Permissions-Policy': 'camera=(), microphone=(), geolocation=()',
  'Cross-Origin-Opener-Policy': 'same-origin-allow-popups',
}

// The one Content-Security-Policy for HTML pages, derived from what the app actually loads:
// - script-src: the Vite bundle and /config.js are same-origin. Firebase Auth's popup flow loads
//   the gapi loader from https://apis.google.com. No 'unsafe-inline' and no 'unsafe-eval'.
// - style-src: the bundled CSS plus React style props, which need 'unsafe-inline'.
// - img-src: YouTube thumbnails (i.ytimg.com) and seller product photos from arbitrary HTTPS hosts,
//   plus data: and blob: images.
// - font-src: Source Sans 3 is bundled by @fontsource and served from this origin.
// - connect-src: the /api proxy is same-origin. Firebase Auth calls identitytoolkit.googleapis.com
//   (project config, sign-in, account lookup) and securetoken.googleapis.com (ID token refresh).
// - frame-src: Firebase Auth's hidden iframe at https://<FIREBASE_AUTH_DOMAIN>/__/auth/iframe; the
//   auth domain comes from the runtime config, so contentSecurityPolicy() appends it.
export const CONTENT_SECURITY_POLICY = {
  'default-src': ["'self'"],
  'script-src': ["'self'", 'https://apis.google.com'],
  'style-src': ["'self'", "'unsafe-inline'"],
  'img-src': ["'self'", 'data:', 'blob:', 'https:'],
  'font-src': ["'self'", 'data:'],
  'connect-src': ["'self'", 'https://identitytoolkit.googleapis.com', 'https://securetoken.googleapis.com'],
  'frame-src': ["'self'"],
  'object-src': ["'none'"],
  'base-uri': ["'self'"],
  'form-action': ["'self'"],
  'frame-ancestors': ["'none'"],
}

export function contentSecurityPolicy(authDomain = process.env.FIREBASE_AUTH_DOMAIN) {
  const directives = structuredClone(CONTENT_SECURITY_POLICY)
  if (authDomain && /^[a-z0-9.-]+$/i.test(authDomain)) directives['frame-src'].push('https://' + authDomain)
  return Object.entries(directives)
    .map(([name, sources]) => name + ' ' + sources.join(' '))
    .join('; ')
}

const localHosts = new Set(['localhost', '127.0.0.1', '[::1]'])

// Firebase Hosting and Cloud Run terminate TLS and already serve browsers over HTTPS only. This is
// defence in depth: a request a proxy marks as plain HTTP is sent to the same URL over HTTPS.
// Local hosts (development, tests) are left alone.
function httpsRedirect(req) {
  const proto = String(req.headers['x-forwarded-proto'] || '')
    .split(',')[0]
    .trim()
    .toLowerCase()
  if (proto !== 'http') return null
  const host = String(req.headers['x-forwarded-host'] || req.headers.host || '')
    .split(',')[0]
    .trim()
  if (!/^(?:[a-z0-9.-]+|\[[0-9a-f:]+\])(?::\d+)?$/i.test(host)) return null
  const hostname = host.startsWith('[') ? host.slice(0, host.indexOf(']') + 1) : host.split(':')[0]
  if (localHosts.has(hostname.toLowerCase())) return null
  return 'https://' + host + (req.url?.startsWith('/') ? req.url : '/')
}

function send(res, status, body) {
  res.writeHead(status, { 'Content-Type': 'text/plain; charset=utf-8', 'Cache-Control': 'no-store' })
  res.end(body)
}

// Trace headers forwarded to the API so one Cloud Trace id spans this server and the backend
// (backend/infra/observability.md). Only well-formed values are forwarded or logged.
const CLOUD_TRACE = /^([0-9a-f]{32})(?:\/(\d{1,20}))?(?:;o=\d)?$/i
const TRACEPARENT = /^[0-9a-f]{2}-([0-9a-f]{32})-([0-9a-f]{16})-[0-9a-f]{2}$/i

function traceHeaders(req) {
  const headers = {}
  const cloud = String(req.headers['x-cloud-trace-context'] || '').trim()
  if (CLOUD_TRACE.test(cloud)) headers['X-Cloud-Trace-Context'] = cloud
  const parent = String(req.headers.traceparent || '').trim()
  if (TRACEPARENT.test(parent)) headers.traceparent = parent
  return headers
}

// Cloud Logging trace fields for a request: X-Cloud-Trace-Context first, as Cloud Run uses it.
function traceFields(req, project) {
  if (!project) return {}
  const cloud = CLOUD_TRACE.exec(String(req.headers['x-cloud-trace-context'] || '').trim())
  const parent = TRACEPARENT.exec(String(req.headers.traceparent || '').trim())
  let traceId = null
  let spanId = null
  if (cloud && !/^0+$/.test(cloud[1])) {
    traceId = cloud[1].toLowerCase()
    const span = cloud[2] ? BigInt(cloud[2]) : 0n
    if (span > 0n && span < 2n ** 64n) spanId = span.toString(16).padStart(16, '0')
  } else if (parent && !/^0+$/.test(parent[1])) {
    traceId = parent[1].toLowerCase()
    spanId = parent[2].toLowerCase()
  }
  if (!traceId) return {}
  const fields = { 'logging.googleapis.com/trace': 'projects/' + project + '/traces/' + traceId }
  if (spanId) fields['logging.googleapis.com/spanId'] = spanId
  return fields
}

// A low-cardinality route for logs: share tokens and job ids never reach a log line.
function routeLabel(pathname) {
  return pathname
    .replace(/^\/v1\/shared\/[^/]+/, '/v1/shared/:token')
    .replace(/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/gi, ':id')
    .slice(0, 200)
}

// One JSON line per proxy failure, in the shape Cloud Logging parses (successes are covered by
// Cloud Run's request log). No URLs with query strings, headers, cookies or tokens.
function proxyError(log, req, context, details) {
  try {
    const entry = {
      severity: 'ERROR',
      message:
        'PROXY_ERROR ' + req.method + ' ' + context.route + ' status=' + details.status + ' reason=' + details.reason,
      event: 'PROXY_ERROR',
      method: req.method,
      route: context.route,
      status: details.status,
      upstream_status: details.upstreamStatus ?? null,
      reason: details.reason,
      error: details.error ?? null,
      duration_ms: Math.round(performance.now() - context.started),
      ...traceFields(req, context.project),
    }
    log(JSON.stringify(entry))
  } catch {
    // Logging must never affect the response.
  }
}

const writeLine = line => process.stdout.write(line + '\n')

async function proxy(req, res, backendBase, integrationKey, fetchImpl, log, project) {
  // DELETE is needed to revoke share links (DELETE /v1/jobs/{id}/share) and delete my data (DELETE /v1/account).
  if (!['GET', 'POST', 'DELETE'].includes(req.method)) return send(res, 405, 'Method not allowed')
  const parsed = new URL(req.url, 'http://localhost')
  const upstreamPath =
    parsed.pathname === '/api/healthz' || parsed.pathname === '/api/health'
      ? '/health'
      : parsed.pathname.startsWith('/api/v1/')
        ? parsed.pathname.slice('/api'.length)
        : null
  if (!upstreamPath) return send(res, 404, 'Not found')
  if (upstreamPath === '/health' && req.method !== 'GET') return send(res, 405, 'Method not allowed')

  const chunks = []
  let size = 0
  for await (const chunk of req) {
    size += chunk.length
    if (size > 1024 * 1024) return send(res, 413, 'Request too large')
    chunks.push(chunk)
  }
  const headers = { 'X-Integration-Key': integrationKey }
  if (req.headers['x-job-token']) headers['X-Job-Token'] = req.headers['x-job-token']
  if (req.headers.accept) headers.Accept = req.headers.accept
  if (req.headers['content-type']) headers['Content-Type'] = req.headers['content-type']
  for (const name of ['Authorization', 'Cookie', 'X-Requested-With', 'Origin']) {
    if (req.headers[name.toLowerCase()]) headers[name] = req.headers[name.toLowerCase()]
  }
  Object.assign(headers, traceHeaders(req))
  const target = new URL(upstreamPath + parsed.search, backendBase)
  const context = { route: routeLabel(upstreamPath), started: performance.now(), project }
  let upstream = null
  try {
    upstream = await fetchImpl(target, {
      method: req.method,
      headers,
      // DELETE /v1/account carries a {"confirm":"DELETE"} body; a bodyless DELETE stays bodyless.
      body: req.method === 'POST' || (req.method === 'DELETE' && size > 0) ? Buffer.concat(chunks) : undefined,
      redirect: 'manual',
    })
    const responseHeaders = { 'Cache-Control': upstream.headers.get('cache-control') || 'no-store' }
    for (const name of ['content-type', 'retry-after']) {
      const value = upstream.headers.get(name)
      if (value) responseHeaders[name] = value
    }
    const cookies = upstream.headers.getSetCookie()
    if (cookies.length) responseHeaders['Set-Cookie'] = cookies
    if (upstream.status >= 502 && upstream.status <= 504) {
      // Gateway-type answers (backend down, overloaded or timed out) are passed through as before.
      proxyError(log, req, context, {
        status: upstream.status,
        upstreamStatus: upstream.status,
        reason: 'upstream_status',
      })
    }
    res.writeHead(upstream.status, responseHeaders)
    if (upstream.body) await pipeline(Readable.fromWeb(upstream.body), res)
    else res.end()
  } catch (error) {
    const reason = upstream ? 'stream_failed' : 'fetch_failed'
    const status = res.headersSent ? (upstream?.status ?? null) : 502
    proxyError(log, req, context, {
      status,
      upstreamStatus: upstream?.status ?? null,
      reason,
      error: error?.name || 'Error',
    })
    if (!res.headersSent) send(res, 502, 'Backend unavailable')
    else res.destroy()
  }
}

async function staticFile(req, res, distDir) {
  if (!['GET', 'HEAD'].includes(req.method)) return send(res, 405, 'Method not allowed')
  const parsed = new URL(req.url, 'http://localhost')
  let pathname
  try {
    pathname = decodeURIComponent(parsed.pathname)
  } catch {
    return send(res, 400, 'Invalid path')
  }
  if (pathname.includes('\\') || pathname.includes('\0')) return send(res, 400, 'Invalid path')
  const filePath = path.resolve(distDir, '.' + pathname)
  if (filePath !== distDir && !filePath.startsWith(distDir + path.sep)) return send(res, 403, 'Forbidden')
  let target = filePath
  let details = await stat(target).catch(() => null)
  if (!details?.isFile()) {
    // A missing file with an extension is a 404, except app routes whose last segment
    // contains a dot: share links are /shared/<project id>.<secret>.
    if (path.extname(pathname) && !pathname.startsWith('/shared/')) return send(res, 404, 'Not found')
    target = path.join(distDir, 'index.html')
    details = await stat(target).catch(() => null)
  }
  if (!details?.isFile()) return send(res, 404, 'Not found')
  res.writeHead(200, {
    'Content-Type': contentTypes[path.extname(target)] || 'application/octet-stream',
    'Cache-Control': pathname.startsWith('/assets/') ? 'public, max-age=31536000, immutable' : 'no-store',
    ...(path.extname(target) === '.html' ? { 'Content-Security-Policy': contentSecurityPolicy() } : {}),
  })
  if (req.method === 'HEAD') return res.end()
  await pipeline(createReadStream(target), res)
}

export function createServer({
  backendBase,
  integrationKey,
  distDir = defaultDist,
  fetchImpl = fetch,
  log = writeLine,
  // The trace field names the GCP project; the deploy script requires the Firebase project to be
  // the deployment project, so FIREBASE_PROJECT_ID is the fallback.
  project = process.env.GOOGLE_CLOUD_PROJECT || process.env.FIREBASE_PROJECT_ID,
} = {}) {
  const backend = new URL(backendBase)
  if (backend.protocol !== 'https:') throw new Error('BACKEND_BASE_URL must be HTTPS')
  if (!integrationKey) throw new Error('INTEGRATION_KEY is required')
  const root = path.resolve(distDir)
  return http.createServer((req, res) => {
    for (const [name, value] of Object.entries(SECURITY_HEADERS)) res.setHeader(name, value)
    const secureUrl = httpsRedirect(req)
    if (secureUrl) {
      res.writeHead(301, { Location: secureUrl, 'Cache-Control': 'no-store' })
      return res.end()
    }
    if (req.url === '/config.js') {
      if (req.method !== 'GET') return send(res, 405, 'Method not allowed')
      const config = {
        apiKey: process.env.FIREBASE_API_KEY,
        authDomain: process.env.FIREBASE_AUTH_DOMAIN,
        projectId: process.env.FIREBASE_PROJECT_ID,
        appId: process.env.FIREBASE_APP_ID,
      }
      const body = 'window.__BS_FIREBASE_CONFIG=' + JSON.stringify(config).replaceAll('<', '\\u003c') + ';'
      res.writeHead(200, {
        'Content-Type': 'text/javascript; charset=utf-8',
        'Cache-Control': 'no-store',
      })
      return res.end(body)
    }
    const work = req.url?.startsWith('/api/')
      ? proxy(req, res, backend, integrationKey, fetchImpl, log, project)
      : staticFile(req, res, root)
    work.catch(() => {
      if (!res.headersSent) send(res, 500, 'Server error')
      else res.destroy()
    })
  })
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const server = createServer({
    backendBase: process.env.BACKEND_BASE_URL,
    integrationKey: process.env.INTEGRATION_KEY,
  })
  server.listen(Number(process.env.PORT || 8080), process.env.HOST || '0.0.0.0')
}
