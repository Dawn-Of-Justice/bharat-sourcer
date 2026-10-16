import assert from 'node:assert/strict'
import { test } from 'node:test'
import { readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import ts from 'typescript'

// Server-renders the real Privacy, Terms, footer and delete-my-data components; no DOM or network.
const require = createRequire(import.meta.url)
const React = require('react')
const { renderToStaticMarkup } = require('react-dom/server')
globalThis.location = { search: '' }
globalThis.window = { location: globalThis.location }

function load(name) {
  const source = readFileSync(new URL('./src/' + name, import.meta.url), 'utf8').replaceAll(
    'import.meta.env',
    '({DEV:false, PROD:true})',
  )
  const { outputText } = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX },
  })
  const exports = {}
  // Only React is real; the account module's other imports are not used by the rendered pieces.
  const stub = dep => (dep === 'react' || dep.startsWith('react/') || dep === 'react-dom' ? require(dep) : {})
  new Function('require', 'exports', outputText)(stub, exports)
  return exports
}
const legal = load('Legal.tsx')
const account = load('Account.tsx')
const render = (Component, props) => renderToStaticMarkup(React.createElement(Component, props))
const text = html =>
  html
    .replace(/<[^>]+>/g, ' ')
    .replace(/&#x27;|’/g, "'")
    .replace(/\s+/g, ' ')

test('privacy page renders the draft notice, retention rules, controls and contact', () => {
  const html = render(legal.PrivacyPage, { onNavigate: () => {} })
  const body = text(html)
  assert.match(html, /<h1>Privacy<\/h1>/)
  assert.match(body, /Last updated: /)
  assert.match(body, /Draft notice/)
  assert.match(body, /30 days after their last update/)
  assert.match(body, /365 days without an update/)
  assert.match(body, /Delete my data/)
  assert.match(body, /no advertising or analytics trackers/)
  assert.match(html, /href="https:\/\/github.com\/Dawn-Of-Justice\/bharat-sourcer\/issues"/)
  assert.match(html, /id="contact"/)
  assert.match(html, /href="\/"[^>]*>← Back to Bharat Sourcer/)
  assert.doesNotMatch(body, /@[a-z0-9-]+\.[a-z]/i, 'no personal email address')
  assert.ok(body.split(' ').length < 650, 'privacy page stays short')
})

test('terms page renders the key sections', () => {
  const html = render(legal.TermsPage, { onNavigate: () => {} })
  const body = text(html)
  assert.match(html, /<h1>Terms<\/h1>/)
  for (const heading of [
    'A free tool',
    'Check before you buy',
    'Acceptable use',
    'No warranty',
    'Limitation of liability',
  ])
    assert.match(html, new RegExp('<h2>' + heading + '</h2>'))
  assert.match(body, /Verify every part, price and listing/)
  assert.ok(body.split(' ').length < 650, 'terms page stays short')
})

test('footer links to privacy and terms', () => {
  const html = render(legal.SiteFooter, { onNavigate: () => {} })
  assert.match(html, /<footer class="site-footer">/)
  assert.match(html, /<a href="\/privacy">Privacy<\/a>/)
  assert.match(html, /<a href="\/terms">Terms<\/a>/)
})

test('App routes /privacy and /terms and shows the footer on every page', () => {
  const app = readFileSync(new URL('./src/App.tsx', import.meta.url), 'utf8')
  assert.match(app, /path === '\/privacy' \? \(\s*<PrivacyPage/)
  assert.match(app, /path === '\/terms' \? \(\s*<TermsPage/)
  assert.match(app, /<SiteFooter onNavigate=\{navigate\} \/>\s*<\/>/)
})

const base = {
  projectCount: null,
  error: '',
  result: null,
  disabled: false,
  onStart() {},
  onCancel() {},
  onConfirm() {},
}

test('delete section starts with the warning and a danger text button', () => {
  const body = text(render(account.DeleteData, { ...base, kind: 'guest', step: 'idle' }))
  assert.match(body, /Delete my data/)
  assert.match(body, /Deletes all your projects, share links and settings. This can't be undone./)
  assert.match(render(account.DeleteData, { ...base, kind: 'guest', step: 'idle' }), /class="text-danger"/)
})

test('confirm step names what goes for accounts and guests', () => {
  assert.match(
    text(render(account.DeleteData, { ...base, kind: 'account', step: 'confirm', projectCount: 3 })),
    /Delete 3 projects and your account\?/,
  )
  assert.match(
    text(render(account.DeleteData, { ...base, kind: 'account', step: 'confirm' })),
    /Delete your projects and your account\?/,
  )
  const guest = render(account.DeleteData, { ...base, kind: 'guest', step: 'confirm' })
  assert.match(text(guest), /Delete your guest projects\?/)
  assert.match(guest, /class="danger-button"[^>]*>Delete permanently/)
  assert.match(guest, />Cancel</)
})

test('deleting disables the button, errors show inline', () => {
  const busy = render(account.DeleteData, { ...base, kind: 'guest', step: 'deleting' })
  assert.match(busy, /disabled=""[^>]*>Deleting…/)
  const failed = render(account.DeleteData, {
    ...base,
    kind: 'account',
    step: 'confirm',
    error: 'Usage limit reached. Try again after 17/10/2026, 10:01:00.',
  })
  assert.match(failed, /class="form-error" role="alert">Usage limit reached. Try again after/)
})

test('success shows counts and asks to finish when the sign-in record remains', () => {
  const result = {
    kind: 'account',
    projects_deleted: 3,
    share_links_revoked: 1,
    settings_deleted: true,
    auth_user_deleted: false,
  }
  const html = render(account.DeleteData, { ...base, kind: 'account', step: 'done', result })
  const body = text(html)
  assert.match(body, /Your data was deleted./)
  assert.match(body, /Removed 3 projects and 1 share link, and your saved settings/)
  assert.match(body, /Your sign-in record could not be removed; contact us to finish./)
  assert.match(html, /href="\/privacy#contact"/)
  const clean = text(
    render(account.DeleteData, {
      ...base,
      kind: 'guest',
      step: 'done',
      result: { ...result, kind: 'guest', settings_deleted: false, auth_user_deleted: null },
    }),
  )
  assert.doesNotMatch(clean, /sign-in record/)
  assert.match(clean, /fresh guest session/)
})
