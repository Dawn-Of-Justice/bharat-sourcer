import { spawn } from 'node:child_process'
import { mkdtemp, readFile, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

const profile = await mkdtemp(join(tmpdir(), 'bharat-layout-'))
const chrome = spawn('C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe', [
  '--headless=new', '--disable-gpu', '--no-first-run', '--no-default-browser-check',
  '--remote-debugging-port=0', `--user-data-dir=${profile}`,
  'http://127.0.0.1:5173/job/ui-preview?preview=1&stage=done',
], { stdio: 'ignore' })
let socket
try {
  let port
  for (let i = 0; i < 100; i++) {
    try { port = Number((await readFile(join(profile, 'DevToolsActivePort'), 'utf8')).split('\n')[0]); break }
    catch { await new Promise(resolve => setTimeout(resolve, 100)) }
  }
  if (!port) throw new Error('Chrome did not start')
  const targets = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json()
  const page = targets.find(target => target.type === 'page')
  socket = new WebSocket(page.webSocketDebuggerUrl)
  await new Promise((resolve, reject) => { socket.onopen = resolve; socket.onerror = reject })
  let id = 0
  const pending = new Map()
  socket.onmessage = event => {
    const message = JSON.parse(event.data)
    if (message.id && pending.has(message.id)) {
      const { resolve, reject } = pending.get(message.id)
      pending.delete(message.id)
      message.error ? reject(new Error(message.error.message)) : resolve(message.result)
    }
  }
  const send = (method, params = {}) => new Promise((resolve, reject) => {
    const next = ++id
    pending.set(next, { resolve, reject })
    socket.send(JSON.stringify({ id: next, method, params }))
  })
  const evaluate = async expression => (await send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true })).result.value
  for (const width of [320, 390, 600, 768, 1024, 1440, 1920]) {
    await send('Emulation.setDeviceMetricsOverride', { width, height: 900, deviceScaleFactor: 1, mobile: false })
    await send('Page.navigate', { url: 'http://127.0.0.1:5173/job/ui-preview?preview=1&stage=done' })
    await new Promise(resolve => setTimeout(resolve, 500))
    const before = await evaluate(`(() => ({ viewport: innerWidth, client: document.documentElement.clientWidth, document: document.documentElement.scrollWidth, body: document.body.scrollWidth, cards: document.querySelectorAll('.part-card').length, estimate: document.querySelector('.cost-summary-main strong')?.textContent, source: document.querySelector('.job-source-link')?.textContent }))()`)
    await evaluate(`(() => { document.querySelector('.part-card > summary')?.click(); document.querySelector('.build-details-button')?.click(); })()`)
    await new Promise(resolve => setTimeout(resolve, 250))
    const after = await evaluate(`(() => ({ document: document.documentElement.scrollWidth, openCard: !!document.querySelector('.part-card[open]'), openDetails: document.querySelector('.build-details-button')?.getAttribute('aria-expanded'), iconSize: Math.round(document.querySelector('.part-expand .disclosure-chevron')?.getBoundingClientRect().width ?? 0) }))()`)
    console.log(JSON.stringify({ width, before, after }))
    if (width === 320 || width === 768) {
      const screenshot = await send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: false })
      const path = join(profile, `parts-${width}.png`)
      await writeFile(path, Buffer.from(screenshot.data, 'base64'))
      console.log(`SCREENSHOT ${path}`)
    }
    for (const [name, path] of [['home', '/?preview=1'], ['projects', '/projects?preview=1']]) {
      await send('Page.navigate', { url: `http://127.0.0.1:5173${path}` })
      await new Promise(resolve => setTimeout(resolve, 350))
      const size = await evaluate(`(() => ({ client: document.documentElement.clientWidth, document: document.documentElement.scrollWidth }))()`)
      console.log(JSON.stringify({ width, page: name, ...size }))
    }
  }
} finally {
  socket?.close()
  chrome.kill()
  // Keep screenshots for visual inspection; the caller can remove this temporary profile.
}
