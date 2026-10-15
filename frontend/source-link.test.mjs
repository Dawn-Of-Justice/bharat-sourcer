import assert from 'node:assert/strict'
import { test } from 'node:test'
import { readFileSync } from 'node:fs'
import ts from 'typescript'

const { outputText } = ts.transpileModule(readFileSync(new URL('./src/sourceLink.ts', import.meta.url), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
})
const exports = {}
new Function('exports', outputText)(exports)
const { checkLinks, parseLink } = exports

const VIDEO = 'https://www.youtube.com/watch?v=abcdefghijk'
const REPO = 'https://github.com/creator/project'
const BLOG = 'https://maker.example/my-weather-station'

test('any supported link is accepted in the main field, whichever tab it was typed in', () => {
  for (const url of [VIDEO, REPO, BLOG, 'https://youtu.be/abcdefghijk']) {
    assert.deepEqual(checkLinks(url, []), { url: new URL(url).toString(), sources: [] })
  }
})

test('a missing https:// is added and surrounding spaces are ignored', () => {
  assert.equal(checkLinks('  github.com/creator/project ', []).url, REPO)
  assert.equal(checkLinks('www.youtube.com/watch?v=abcdefghijk', []).url, VIDEO)
  assert.equal(parseLink('youtu.be/abcdefghijk')?.toString(), 'https://youtu.be/abcdefghijk')
  assert.equal(parseLink('ftp://example.com/x'), null)
  assert.equal(parseLink('   '), null)
})

test('extra sources may be any kind, including the video', () => {
  assert.deepEqual(checkLinks(REPO, ['', VIDEO, 'maker.example/my-weather-station']), {
    url: REPO,
    sources: [VIDEO, BLOG],
  })
})

test('unsupported links, Hackster and two videos are still refused with a clear message', () => {
  assert.match(checkLinks('not a link', []).error, /YouTube video, GitHub repository/)
  assert.match(checkLinks('https://www.hackster.io/maker/project', []).error, /Hackster/)
  assert.match(checkLinks(REPO, ['https://hackster.io/x/y']).error, /^Extra source 1: Hackster/)
  assert.match(checkLinks(REPO, ['localhost']).error, /^Extra source 1:/)
  assert.match(checkLinks(VIDEO, ['https://youtu.be/bbbbbbbbbbb']).error, /Only one YouTube video/)
})
