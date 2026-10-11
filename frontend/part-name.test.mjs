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

test('coded result rows and detail headings use the selected listing, even on legacy jobs without specs', () => {
  const line = {
    item: { raw_name: 'C2' },
    selected_offer_url: 'https://seller.example/capacitor',
    offers: [
      { url: 'https://seller.example/other', title: 'Wrong unselected listing' },
      { url: 'https://seller.example/capacitor', title: '10uF 16V Electrolytic Capacitor - ELITE' },
    ],
  }
  assert.equal(exports.reportPartName(line), '10uF 16V Electrolytic Capacitor - ELITE (C2)')
  line.item.raw_name = 'C1, C3'
  assert.equal(exports.reportPartName(line), '10uF 16V Electrolytic Capacitor - ELITE (C1, C3)')
  line.item.raw_name = 'BC548 (T1)'
  line.offers[1].title = 'BC548 NPN Transistor'
  assert.equal(exports.reportPartName(line), 'BC548 NPN Transistor (T1)')
  line.item.raw_name = 'Arduino Uno R3'
  assert.equal(exports.reportPartName(line), 'Arduino Uno R3')
  line.item.raw_name = 'C2'
  line.selected_offer_url = null
  assert.equal(exports.reportPartName(line), 'C2')
})

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
