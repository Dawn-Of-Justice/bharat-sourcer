import assert from 'node:assert/strict'
import { test } from 'node:test'
import { readFileSync } from 'node:fs'
import ts from 'typescript'

const { outputText } = ts.transpileModule(readFileSync(new URL('./src/partName.ts', import.meta.url), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS },
})
const exports = {}
new Function('exports', outputText)(exports)
const { partName } = exports

test('old saved schematic references get readable names without promoting inferred values', () => {
  const spec = {
    category: 'resistor',
    params: [{ name: 'resistance', value: '10k ohm', origin: 'stated', operator: 'equals' }],
  }
  assert.equal(partName({ raw_name: 'R1' }, spec), '10k ohm resistor (R1)')
  assert.equal(partName({ raw_name: 'VR1' }, spec), '10k ohm potentiometer (VR1)')
  assert.equal(partName({ raw_name: 'Arduino Uno R3' }, spec), 'Arduino Uno R3')
  assert.equal(partName({ raw_name: 'R1' }), 'R1')
  spec.params[0].origin = 'inferred'
  assert.equal(partName({ raw_name: 'R4, R5' }, spec), 'resistor (R4, R5)')
})
