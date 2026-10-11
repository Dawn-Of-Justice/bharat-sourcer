import assert from 'node:assert/strict'
import { test } from 'node:test'
import { readFileSync } from 'node:fs'
import ts from 'typescript'

test('background job updates change the title and navigation cleans up the listener', () => {
  const listeners = new Set()
  const originalDocument = globalThis.document
  globalThis.document = {
    title: 'Bharat Sourcer — Build it in India',
    hidden: false,
    addEventListener: (event, callback) => listeners.add(callback),
    removeEventListener: (event, callback) => listeners.delete(callback),
  }
  const document = globalThis.document
  let cleanup
  const exports = {}
  const source = readFileSync(new URL('./src/useJobTitle.ts', import.meta.url), 'utf8')
  const { outputText } = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  })
  new Function('require', 'exports', outputText)(
    () => ({
      useEffect: effect => {
        cleanup?.()
        cleanup = effect()
      },
    }),
    exports,
  )
  const render = (status, error = '') =>
    exports.useJobTitle({ status, project: { title: 'Synthetic weather station' } }, '', error)
  try {
    render('sourcing')
    assert.equal(document.title, 'Synthetic weather station — Bharat Sourcer')
    document.hidden = true
    listeners.forEach(callback => callback())
    assert.equal(document.title, 'Finding sellers… — Bharat Sourcer')
    render('done')
    assert.equal(document.title, '✓ Results ready — Bharat Sourcer')
    assert.equal(listeners.size, 1)
    render('awaiting_confirmation')
    assert.match(document.title, /Parts list ready to review/)
    render('paused')
    assert.match(document.title, /Run paused/)
    render('failed')
    assert.match(document.title, /Run needs attention/)
    render('sourcing', 'Connection lost')
    assert.match(document.title, /Updates interrupted/)
    render('sourcing')
    assert.match(document.title, /Finding sellers/)
    document.hidden = false
    listeners.forEach(callback => callback())
    assert.equal(document.title, 'Synthetic weather station — Bharat Sourcer')
    cleanup()
    assert.equal(listeners.size, 0)
    assert.equal(document.title, 'Bharat Sourcer — Build it in India')
  } finally {
    cleanup?.()
    globalThis.document = originalDocument
  }
})
