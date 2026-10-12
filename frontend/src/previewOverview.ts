import type { OverviewPin, PartVisual, ProjectOverview, WireConnection } from './api'

// Sample project overview for ?preview=1: a "Desk Buddy" desk companion (ESP32-C3 Super Mini, 1.3" SH1106 OLED,
// TTP223 touch pad, LiPo cell, TP4056 charger, slide switch). Sample data for the UI preview only: the pinouts and
// verdicts are invented fixtures, not checked against any real board. The board and touch pad reuse the preview parts
// list's L01 and L02 ids so their quantities show; the other parts have no matching line.
const pin = (name: string, kind: OverviewPin['kind'], ...functions: string[]): OverviewPin => ({
  name,
  kind,
  functions,
})

const parts: PartVisual[] = [
  {
    line_id: 'L01',
    label: 'ESP32-C3 Super Mini',
    kind: 'board',
    body: { width_mm: 22.5, height_mm: 18, color: 'blue', shape: 'rect' },
    chip: { label: 'ESP32-C3', x: 0.3, y: 0.27, w: 0.34, h: 0.46 },
    features: [
      { type: 'antenna', x: 0.74, y: 0.22, w: 0.2, h: 0.56, text: null },
      { type: 'button', x: 0.09, y: 0.24, w: 0.1, h: 0.16, text: 'BOOT' },
      { type: 'led', x: 0.11, y: 0.62, w: 0.06, h: 0.1, text: 'PWR' },
      { type: 'label', x: 0.3, y: 0.76, w: 0.34, h: 0.12, text: 'C3 MINI' },
    ],
    connectors: [{ type: 'usb_c', side: 'left', position: 0.5 }],
    headers: [
      {
        side: 'top',
        pins: [
          pin('5V', 'power', 'VBUS'),
          pin('GND', 'ground'),
          pin('3V3', 'power', '3.3 V out'),
          pin('GPIO4', 'gpio', 'ADC1_CH4', 'SCK'),
          pin('GPIO3', 'gpio', 'ADC1_CH3'),
          pin('GPIO2', 'gpio', 'ADC1_CH2', 'Strapping'),
          pin('GPIO1', 'gpio', 'ADC1_CH1'),
          pin('GPIO0', 'gpio', 'ADC1_CH0'),
        ],
      },
      {
        side: 'bottom',
        pins: [
          pin('GPIO5', 'gpio', 'ADC2_CH0', 'MISO'),
          pin('GPIO6', 'gpio', 'MOSI'),
          pin('GPIO7', 'gpio', 'SS'),
          pin('GPIO8', 'i2c', 'SDA', 'Onboard LED', 'Strapping'),
          pin('GPIO9', 'i2c', 'SCL', 'BOOT button', 'Strapping'),
          pin('GPIO10', 'gpio'),
          pin('GPIO20', 'uart', 'RX'),
          pin('GPIO21', 'uart', 'TX'),
        ],
      },
    ],
    pin_source: 'datasheet_knowledge',
    verdict: 'confirmed',
    verdict_reason: null,
  },
  {
    line_id: 'DB02',
    label: '1.3" SH1106 OLED',
    kind: 'display',
    body: { width_mm: 35.4, height_mm: 33.5, color: 'black', shape: 'rounded' },
    chip: null,
    features: [{ type: 'screen', x: 0.06, y: 0.22, w: 0.88, h: 0.62, text: null }],
    connectors: [],
    headers: [
      {
        side: 'top',
        pins: [
          pin('GND', 'ground'),
          pin('VCC', 'power', '3.3–5 V'),
          pin('SCL', 'i2c', 'SCL'),
          pin('SDA', 'i2c', 'SDA'),
        ],
      },
    ],
    pin_source: 'datasheet_knowledge',
    verdict: 'unverified',
    verdict_reason: 'Sample: 1.3-inch modules ship with GND and VCC in either order; read the silkscreen.',
  },
  {
    line_id: 'L02',
    label: 'TTP223 touch pad',
    kind: 'sensor',
    body: { width_mm: 24, height_mm: 15, color: 'red', shape: 'rect' },
    chip: { label: 'TTP223', x: 0.1, y: 0.3, w: 0.3, h: 0.4 },
    features: [
      { type: 'touch_pad', x: 0.48, y: 0.08, w: 0.46, h: 0.84, text: null },
      { type: 'led', x: 0.16, y: 0.8, w: 0.06, h: 0.1, text: null },
    ],
    connectors: [],
    headers: [
      {
        side: 'left',
        pins: [pin('GND', 'ground'), pin('I/O', 'gpio', 'Touch out'), pin('VCC', 'power', '2–5.5 V')],
      },
    ],
    pin_source: 'datasheet_knowledge',
    verdict: 'confirmed',
    verdict_reason: null,
  },
  {
    line_id: 'DB04',
    label: '3.7 V LiPo cell',
    kind: 'battery',
    body: { width_mm: 50, height_mm: 30, color: 'silver', shape: 'pouch' },
    chip: null,
    features: [{ type: 'label', x: 0.2, y: 0.38, w: 0.6, h: 0.24, text: '3.7V 1000mAh' }],
    connectors: [{ type: 'jst', side: 'right', position: 0.25 }],
    headers: [{ side: 'right', pins: [pin('BAT+', 'power', '3.7 V'), pin('BAT-', 'ground')] }],
    pin_source: 'ai_inferred',
    verdict: 'confirmed',
    verdict_reason: null,
  },
  {
    line_id: 'DB05',
    label: 'TP4056 Type-C charger',
    kind: 'module',
    body: { width_mm: 26, height_mm: 17, color: 'blue', shape: 'rect' },
    chip: { label: 'TP4056', x: 0.36, y: 0.3, w: 0.28, h: 0.4 },
    features: [
      { type: 'led', x: 0.24, y: 0.18, w: 0.06, h: 0.1, text: 'CHRG' },
      { type: 'led', x: 0.24, y: 0.72, w: 0.06, h: 0.1, text: 'DONE' },
      { type: 'label', x: 0.68, y: 0.06, w: 0.2, h: 0.14, text: 'OUT' },
    ],
    connectors: [{ type: 'usb_c', side: 'left', position: 0.5 }],
    headers: [
      {
        side: 'right',
        pins: [
          pin('OUT+', 'power', 'Load +'),
          pin('B+', 'power', 'Cell +'),
          pin('B-', 'ground', 'Cell -'),
          pin('OUT-', 'ground', 'Load -'),
        ],
      },
    ],
    pin_source: 'datasheet_knowledge',
    verdict: 'confirmed',
    verdict_reason: null,
  },
  {
    line_id: 'DB06',
    label: 'Slide switch',
    kind: 'switch',
    body: { width_mm: 8.6, height_mm: 3.6, color: 'black', shape: 'rect' },
    chip: null,
    features: [{ type: 'button', x: 0.36, y: 0.15, w: 0.28, h: 0.7, text: null }],
    connectors: [],
    headers: [{ side: 'bottom', pins: [pin('1', 'other'), pin('COM', 'power'), pin('2', 'other')] }],
    pin_source: 'ai_inferred',
    verdict: 'disputed',
    verdict_reason: 'Sample: the second check reads the video as a 2-pin rocker switch, not a 3-pin slide switch.',
  },
]

const wire = (
  id: string,
  from: [string, string],
  to: [string, string],
  signal: WireConnection['signal'],
  source: WireConnection['source'],
  verdict: WireConnection['verdict'],
  extra: Partial<WireConnection> = {},
): WireConnection => ({
  id,
  from: { line_id: from[0], pin: from[1] },
  to: { line_id: to[0], pin: to[1] },
  signal,
  label: null,
  source,
  evidence: null,
  verdict,
  reason: null,
  problems: [],
  ...extra,
})

const wiring: WireConnection[] = [
  wire('W01', ['DB02', 'SDA'], ['L01', 'GPIO8'], 'i2c_sda', 'code', 'confirmed', {
    label: 'Display data',
    evidence: 'DeskBuddy.ino:14',
  }),
  wire('W02', ['DB02', 'SCL'], ['L01', 'GPIO9'], 'i2c_scl', 'code', 'confirmed', {
    label: 'Display clock',
    evidence: 'DeskBuddy.ino:14',
  }),
  wire('W03', ['DB02', 'VCC'], ['L01', '3V3'], 'power', 'description', 'unverified', {
    evidence: '“OLED runs off the 3.3 V pin”',
    reason: 'Sample: VCC sits in a different place on some 1.3-inch modules.',
  }),
  wire('W04', ['DB02', 'GND'], ['L01', 'GND'], 'ground', 'ai_inferred', 'confirmed'),
  wire('W05', ['L02', 'I/O'], ['L01', 'GPIO3'], 'digital', 'code', 'confirmed', {
    label: 'Touch input',
    evidence: 'DeskBuddy.ino:9',
  }),
  wire('W06', ['L02', 'VCC'], ['L01', '3V3'], 'power', 'ai_inferred', 'unverified'),
  wire('W07', ['L02', 'GND'], ['L01', 'GND'], 'ground', 'ai_inferred', 'confirmed'),
  wire('W08', ['DB04', 'BAT+'], ['DB05', 'B+'], 'power', 'description', 'confirmed', { label: 'Battery +' }),
  wire('W09', ['DB04', 'BAT-'], ['DB05', 'B-'], 'ground', 'description', 'confirmed', { label: 'Battery -' }),
  wire('W10', ['DB05', 'OUT+'], ['DB06', 'COM'], 'power', 'ai_inferred', 'unverified', { label: 'Power switch' }),
  wire('W11', ['DB06', '1'], ['L01', '5V'], 'power', 'description', 'disputed', {
    evidence: '“battery goes to the 5V pin”',
    reason: 'Sample: the second check reads the video as wiring the switch to the 3V3 pad, not 5V.',
    problems: ['Sample: a 4.2 V LiPo on the 5V pin leaves the onboard regulator little headroom.'],
  }),
  wire('W12', ['DB05', 'OUT-'], ['L01', 'GND'], 'ground', 'ai_inferred', 'confirmed'),
]

const count = (verdict: WireConnection['verdict']) =>
  parts.filter(part => part.verdict === verdict).length + wiring.filter(entry => entry.verdict === verdict).length

export function sampleOverview(): ProjectOverview {
  return structuredClone({
    status: 'ready',
    message: null,
    generated_at: new Date().toISOString(),
    items_hash: 'sample',
    demo: true,
    parts,
    wiring,
    judge: {
      status: 'issues',
      summary:
        'Sample data: the display and touch wiring match the code; the switch and its 5V connection need a second look.',
      confirmed: count('confirmed'),
      unverified: count('unverified'),
      disputed: count('disputed'),
    },
    notes: ['Sample: the code also defines BUZZER_PIN 4, but no buzzer is in the parts list.'],
  } satisfies ProjectOverview)
}

const emptyJudge = { status: 'pending', summary: null, confirmed: 0, unverified: 0, disputed: 0 } as const

// The other overview states, chosen with ?overview=pending|failed|stale|missing in the preview.
export function sampleOverviewState(state: string | null): ProjectOverview | null {
  if (state === 'missing') return null
  if (state === 'pending')
    return {
      ...sampleOverview(),
      status: 'pending',
      generated_at: null,
      parts: [],
      wiring: [],
      notes: [],
      judge: { ...emptyJudge },
    }
  if (state === 'failed')
    return {
      ...sampleOverview(),
      status: 'failed',
      message: 'Sample failure: the drawing step timed out.',
      generated_at: null,
      parts: [],
      wiring: [],
      notes: [],
      judge: { ...emptyJudge, status: 'skipped' },
    }
  if (state === 'stale')
    return { ...sampleOverview(), status: 'stale', message: 'Sample: the parts list changed after this was drawn.' }
  return sampleOverview()
}
