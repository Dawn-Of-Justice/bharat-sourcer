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

function send(res, status, body) {
  res.writeHead(status, { 'Content-Type': 'text/plain; charset=utf-8', 'Cache-Control': 'no-store' })
  res.end(body)
}

async function proxy(req, res, backendBase, integrationKey, fetchImpl) {
  if (!['GET', 'POST'].includes(req.method)) return send(res, 405, 'Method not allowed')
  const parsed = new URL(req.url, 'http://localhost')
  const upstreamPath = parsed.pathname === '/api/healthz' || parsed.pathname === '/api/health'
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
  const target = new URL(upstreamPath + parsed.search, backendBase)
  try {
    const upstream = await fetchImpl(target, {
      method: req.method,
      headers,
      body: req.method === 'POST' ? Buffer.concat(chunks) : undefined,
      redirect: 'manual',
    })
    const responseHeaders = { 'Cache-Control': 'no-store' }
    for (const name of ['content-type', 'retry-after']) {
      const value = upstream.headers.get(name)
      if (value) responseHeaders[name] = value
    }
    const cookies = upstream.headers.getSetCookie()
    if (cookies.length) responseHeaders['Set-Cookie'] = cookies
    res.writeHead(upstream.status, responseHeaders)
    if (upstream.body) await pipeline(Readable.fromWeb(upstream.body), res)
    else res.end()
  } catch {
    if (!res.headersSent) send(res, 502, 'Backend unavailable')
    else res.destroy()
  }
}

async function staticFile(req, res, distDir) {
  if (!['GET', 'HEAD'].includes(req.method)) return send(res, 405, 'Method not allowed')
  const parsed = new URL(req.url, 'http://localhost')
  let pathname
  try { pathname = decodeURIComponent(parsed.pathname) } catch { return send(res, 400, 'Invalid path') }
  if (pathname.includes('\\') || pathname.includes('\0')) return send(res, 400, 'Invalid path')
  const filePath = path.resolve(distDir, '.' + pathname)
  if (filePath !== distDir && !filePath.startsWith(distDir + path.sep)) return send(res, 403, 'Forbidden')
  let target = filePath
  let details = await stat(target).catch(() => null)
  if (!details?.isFile()) {
    if (path.extname(pathname)) return send(res, 404, 'Not found')
    target = path.join(distDir, 'index.html')
    details = await stat(target).catch(() => null)
  }
  if (!details?.isFile()) return send(res, 404, 'Not found')
  res.writeHead(200, {
    'Content-Type': contentTypes[path.extname(target)] || 'application/octet-stream',
    'Cache-Control': pathname.startsWith('/assets/') ? 'public, max-age=31536000, immutable' : 'no-store',
    'X-Content-Type-Options': 'nosniff',
  })
  if (req.method === 'HEAD') return res.end()
  await pipeline(createReadStream(target), res)
}

export function createServer({ backendBase, integrationKey, distDir = defaultDist, fetchImpl = fetch } = {}) {
  const backend = new URL(backendBase)
  if (backend.protocol !== 'https:') throw new Error('BACKEND_BASE_URL must be HTTPS')
  if (!integrationKey) throw new Error('INTEGRATION_KEY is required')
  const root = path.resolve(distDir)
  return http.createServer((req, res) => {
    const work = req.url?.startsWith('/api/')
      ? proxy(req, res, backend, integrationKey, fetchImpl)
      : staticFile(req, res, root)
    work.catch(() => { if (!res.headersSent) send(res, 500, 'Server error'); else res.destroy() })
  })
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const server = createServer({
    backendBase: process.env.BACKEND_BASE_URL,
    integrationKey: process.env.INTEGRATION_KEY,
  })
  server.listen(Number(process.env.PORT || 8080), process.env.HOST || '0.0.0.0')
}
