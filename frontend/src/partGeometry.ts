import type { BoardSide, OverviewPin, PartColor, PartVisual, WireConnection } from './api'

// Geometry for PartSvg (docs/contracts/project-overview.md). The body keeps the part's aspect ratio with its longer
// side scaled to LONG_SIDE units; chip, features and connectors are fractions of the body, x/y = top-left corner.

export const partPalette: Record<PartColor, { fill: string; edge: string; ink: string }> = {
  blue: { fill: '#2f6fd6', edge: '#1d4a96', ink: '#eef4ff' },
  black: { fill: '#2b2d31', edge: '#111214', ink: '#e9e9e4' },
  green: { fill: '#2f8f5b', edge: '#1d6440', ink: '#effaf3' },
  red: { fill: '#d24b4b', edge: '#932c2c', ink: '#fff3f1' },
  purple: { fill: '#7a52c7', edge: '#52348f', ink: '#f6f0ff' },
  yellow: { fill: '#e6b93a', edge: '#a8841f', ink: '#3a2c05' },
  white: { fill: '#f3f3f0', edge: '#b4b4ac', ink: '#3a3a36' },
  silver: { fill: '#b9bec7', edge: '#7d838d', ink: '#2c3036' },
  orange: { fill: '#e8863a', edge: '#a75a1c', ink: '#fff6ee' },
}

export const pinKindColor: Record<OverviewPin['kind'], string> = {
  power: '#d64545',
  ground: '#1f2124',
  i2c: '#159a8c',
  spi: '#7a52c7',
  uart: '#e8863a',
  gpio: '#2f9a52',
  analog: '#2f9a52',
  control: '#8a949a',
  other: '#8a949a',
}

const LONG_SIDE = 200 // body units for the longer side
const MIN_SHORT = 44
export const clamp = (value: number, min: number, max: number) => Math.min(max, Math.max(min, value))
export const frac = (value: number) => clamp(Number.isFinite(value) ? value : 0, 0, 1)
export const MONO = 'Consolas, ui-monospace, SFMono-Regular, Menlo, monospace'

// Connector size in mm: length along the edge, depth into the board.
const connectorMm: Record<PartVisual['connectors'][number]['type'], [number, number]> = {
  usb_c: [9, 3.6],
  micro_usb: [8, 3],
  jst: [6, 4.5],
  barrel: [9, 14],
  screw_terminal: [10, 7.5],
  pin_socket: [12, 2.5],
}

export interface PinSpot {
  pin: OverviewPin
  side: BoardSide
  index: number
  x: number
  y: number
  r: number
  dot: [number, number]
  label: [number, number]
  font: number
}

// `compact` drops the room kept for pin labels (card thumbnails and diagram nodes show pins as dots only).
export function partLayout(part: PartVisual, compact = false) {
  const wmm = clamp(part.body.width_mm || 1, 1, 300)
  const hmm = clamp(part.body.height_mm || 1, 1, 300)
  const u = LONG_SIDE / Math.max(wmm, hmm)
  const w = Math.max(wmm * u, MIN_SHORT)
  const h = Math.max(hmm * u, MIN_SHORT)
  const sideLen = (side: BoardSide) => (side === 'top' || side === 'bottom' ? w : h)

  // Several headers on one side share it.
  const bySide = new Map<BoardSide, OverviewPin[]>()
  for (const header of part.headers ?? []) {
    const seen = new Set((bySide.get(header.side) ?? []).map(pin => pin.name))
    const pins = header.pins.filter(pin => !seen.has(pin.name))
    bySide.set(header.side, [...(bySide.get(header.side) ?? []), ...pins])
  }
  const pins: PinSpot[] = []
  const labelPad: Record<BoardSide, number> = { top: 0, bottom: 0, left: 0, right: 0 }
  let order = 0
  for (const [side, list] of bySide) {
    const len = sideLen(side)
    const spacing = len / Math.max(list.length, 1)
    const r = clamp(spacing * 0.3, 1.8, 5.5)
    const font = clamp(spacing * 0.85, 5, 10)
    const inset = r + 3
    const longest = Math.max(...list.map(pin => pin.name.length), 1)
    labelPad[side] = compact ? 0 : 12 + longest * font * 0.62 + 4
    list.forEach((pin, i) => {
      const along = (i + 0.5) * spacing
      const spot =
        side === 'top'
          ? { x: along, y: inset, dot: [along, -6], label: [along, -12] }
          : side === 'bottom'
            ? { x: along, y: h - inset, dot: [along, h + 6], label: [along, h + 12] }
            : side === 'left'
              ? { x: inset, y: along, dot: [-6, along], label: [-12, along] }
              : { x: w - inset, y: along, dot: [w + 6, along], label: [w + 12, along] }
      pins.push({ pin, side, index: order++, r, font, ...spot } as PinSpot)
    })
  }

  const overhang: Record<BoardSide, number> = { top: 0, bottom: 0, left: 0, right: 0 }
  const connectors = (part.connectors ?? []).map(connector => {
    const len = sideLen(connector.side)
    const other = connector.side === 'top' || connector.side === 'bottom' ? h : w
    const [mmL, mmD] = connectorMm[connector.type] ?? [8, 5]
    const L = clamp(mmL * u, 10, len * 0.45)
    const D = clamp(mmD * u, 6, other * 0.4)
    const over = D * 0.3
    overhang[connector.side] = Math.max(overhang[connector.side], over)
    const along = clamp(frac(connector.position) * len, L / 2, len - L / 2)
    const rect =
      connector.side === 'top'
        ? { x: along - L / 2, y: -over, width: L, height: D }
        : connector.side === 'bottom'
          ? { x: along - L / 2, y: h - D + over, width: L, height: D }
          : connector.side === 'left'
            ? { x: -over, y: along - L / 2, width: D, height: L }
            : { x: w - D + over, y: along - L / 2, width: D, height: L }
    return { ...connector, rect, vertical: connector.side === 'left' || connector.side === 'right' }
  })

  const pad = (side: BoardSide) => (compact ? 4 : 10) + Math.max(labelPad[side], overhang[side])
  const view = { x: -pad('left'), y: -pad('top'), w: w + pad('left') + pad('right'), h: h + pad('top') + pad('bottom') }
  return { w, h, pins, connectors, view }
}

// Wire colours by signal (the diagram legend groups them as Power, Ground, I²C and Signal).
export const wireColor: Record<WireConnection['signal'], string> = {
  power: '#d9534f',
  ground: '#3a3f45',
  i2c_sda: '#1f9e9a',
  i2c_scl: '#17807c',
  spi: '#7a52c7',
  uart: '#e8863a',
  digital: '#3f9b5b',
  pwm: '#3f9b5b',
  analog: '#c9a227',
  other: '#8a949a',
}
export const DISPUTED_WIRE = '#b3261e'
export const PROBLEM_WIRE = '#c7790a'
// Only disputed wires and wires with validator problems are flagged (dashed); confirmed and unverified stay solid.
export const wireFlagged = (wire: WireConnection) => wire.verdict === 'disputed' || wire.problems.length > 0
export const strokeOf = (wire: WireConnection) =>
  wire.verdict === 'disputed'
    ? DISPUTED_WIRE
    : wire.problems.length
      ? PROBLEM_WIRE
      : (wireColor[wire.signal] ?? wireColor.other)
export const dashOf = (wire: WireConnection) => (wireFlagged(wire) ? '6 5' : undefined)
