import assert from 'node:assert/strict'
import { test } from 'node:test'
import { readFileSync } from 'node:fs'
import ts from 'typescript'

const { outputText } = ts.transpileModule(readFileSync(new URL('./src/chatMarkdown.ts', import.meta.url), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
})
const exports = {}
new Function('exports', outputText)(exports)
const { parseChatMarkdown, parseInline } = exports

test('numbered list items with bold labels render as list items, not literal asterisks', () => {
  const blocks = parseChatMarkdown(
    'A few things to check:\n\n1. **Firmware / Library Updates:** Use the latest `Servo` library.\n2. **Power:** A *separate* 5V supply.',
  )
  assert.deepEqual(blocks, [
    { kind: 'paragraph', lines: [[{ kind: 'text', text: 'A few things to check:' }]] },
    {
      kind: 'list',
      ordered: true,
      start: 1,
      items: [
        [
          [
            { kind: 'strong', children: [{ kind: 'text', text: 'Firmware / Library Updates:' }] },
            { kind: 'text', text: ' Use the latest ' },
            { kind: 'code', text: 'Servo' },
            { kind: 'text', text: ' library.' },
          ],
        ],
        [
          [
            { kind: 'strong', children: [{ kind: 'text', text: 'Power:' }] },
            { kind: 'text', text: ' A ' },
            { kind: 'em', children: [{ kind: 'text', text: 'separate' }] },
            { kind: 'text', text: ' 5V supply.' },
          ],
        ],
      ],
    },
  ])
})

test('bullets, headings, line breaks and continuation lines', () => {
  const blocks = parseChatMarkdown('## Summary\nFirst line\nsecond line\n- one\n  more of one\n* two\n3) three')
  assert.equal(blocks[0].kind, 'heading')
  assert.deepEqual(blocks[1], {
    kind: 'paragraph',
    lines: [[{ kind: 'text', text: 'First line' }], [{ kind: 'text', text: 'second line' }]],
  })
  assert.deepEqual(blocks[2], {
    kind: 'list',
    ordered: false,
    start: 1,
    items: [
      [[{ kind: 'text', text: 'one' }], [{ kind: 'text', text: 'more of one' }]],
      [[{ kind: 'text', text: 'two' }]],
    ],
  })
  assert.deepEqual(blocks[3], { kind: 'list', ordered: true, start: 3, items: [[[{ kind: 'text', text: 'three' }]]] })
})

test('plain text, identifiers and arithmetic stay literal; HTML stays text', () => {
  assert.deepEqual(parseInline('use line_id and 2 * 3 * 4 <b>x</b>'), [
    { kind: 'text', text: 'use line_id and 2 * 3 * 4 <b>x</b>' },
  ])
  assert.deepEqual(parseInline('**unclosed bold'), [{ kind: 'text', text: '**unclosed bold' }])
})

test('the chat panel renders assistant markdown without injecting HTML', () => {
  const source = readFileSync(new URL('./src/ChatPanel.tsx', import.meta.url), 'utf8')
  assert.match(source, /<AssistantText text=\{message\.text\} \/>/)
  assert.doesNotMatch(source, /dangerouslySetInnerHTML/)
})
