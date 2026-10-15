import assert from 'node:assert/strict'
import { test } from 'node:test'
import { readFileSync } from 'node:fs'
import ts from 'typescript'

const { outputText } = ts.transpileModule(readFileSync(new URL('./src/safeUrl.ts', import.meta.url), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
})
const exports = {}
new Function('exports', outputText)(exports)
const { safeHref } = exports

test('links keep only absolute http and https URLs', () => {
  assert.equal(safeHref('https://seller.example/item?id=1'), 'https://seller.example/item?id=1')
  assert.equal(safeHref('http://seller.example/'), 'http://seller.example/')
  for (const url of [
    'javascript:alert(1)',
    ' JavaScript:alert(1)',
    'java\tscript:alert(1)',
    'data:text/html,<script>alert(1)</script>',
    'vbscript:msgbox(1)',
    '//evil.example/',
    '/relative/path',
    'not a url',
    '',
    null,
    undefined,
  ]) {
    assert.equal(safeHref(url), undefined, String(url))
  }
})
