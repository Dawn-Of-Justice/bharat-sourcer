import type { PartVisual, WireConnection } from './api'
import { wireColor } from './partGeometry'

// Layout for WiringDiagram. The controller sits in the middle column; power parts (batteries, chargers, switches and
// anything joined to them by power-only wires) go to its left, signal parts to its right. Parts that reach the
// controller only through another part sit one column further out. Every part is a card listing the pins its wires
// use, each pin anchored on the edge facing its counterpart. Pins and cards are ordered by the barycentre of what
// they connect to (a few passes), and wires through the same channel get their own lane so they do not overlap.

const MARGIN = 16
const BOX_W = 184
const CTRL_W = 204
const HEAD = 50
const ROW = 22
const FOOT = 8
const GAP = 18
const ORDER_PASSES = 4

type Side = 'left' | 'right'

export interface DiagramAnchor {
  line_id: string
  pin: string
  side: Side
  x: number
  y: number
  dir: 1 | -1 // the direction a wire leaves the box
  color: string
}
export interface DiagramBox {
  part: PartVisual
  x: number
  y: number
  w: number
  h: number
  controller: boolean
  left: DiagramAnchor[]
  right: DiagramAnchor[]
}
export interface DiagramWire {
  wire: WireConnection
  d: string
  from: DiagramAnchor
  to: DiagramAnchor
}
export interface DiagramLayout {
  width: number
  height: number
  head: number
  row: number
  boxes: DiagramBox[]
  wires: DiagramWire[]
}

const POWER_KINDS: PartVisual['kind'][] = ['battery', 'switch']
const isPowerWire = (wire: WireConnection) => wire.signal === 'power' || wire.signal === 'ground'
const mean = (values: number[], fallback: number) =>
  values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : fallback

export function pickController(parts: PartVisual[], wiring: WireConnection[]) {
  const wires = (part: PartVisual) =>
    wiring.filter(wire => wire.from.line_id === part.line_id || wire.to.line_id === part.line_id).length
  const ranked = [...parts].sort((a, b) => wires(b) - wires(a))
  return ranked.find(part => part.kind === 'board') ?? ranked[0] ?? null
}

export function wiringLayout(parts: PartVisual[], wiring: WireConnection[]): DiagramLayout | null {
  const byId = new Map(parts.map(part => [part.line_id, part]))
  const wires = wiring.filter(wire => byId.has(wire.from.line_id) && byId.has(wire.to.line_id))
  const controller = pickController(
    parts.filter(part => wires.some(wire => wire.from.line_id === part.line_id || wire.to.line_id === part.line_id)),
    wires,
  )
  if (!controller || !wires.length) return null
  const cid = controller.line_id

  // Peripherals joined by wires that skip the controller form one group and stay on one side.
  const parent = new Map<string, string>()
  const find = (id: string): string => {
    const up = parent.get(id) ?? id
    if (up === id) return id
    const root = find(up)
    parent.set(id, root)
    return root
  }
  const peripherals = parts.filter(
    part =>
      part.line_id !== cid &&
      wires.some(wire => wire.from.line_id === part.line_id || wire.to.line_id === part.line_id),
  )
  for (const wire of wires)
    if (wire.from.line_id !== cid && wire.to.line_id !== cid) parent.set(find(wire.from.line_id), find(wire.to.line_id))
  const groups = new Map<string, PartVisual[]>()
  for (const part of peripherals) groups.set(find(part.line_id), [...(groups.get(find(part.line_id)) ?? []), part])

  const side = new Map<string, -1 | 1>() // -1 = left (power), 1 = right (signal)
  for (const group of groups.values()) {
    const ids = new Set(group.map(part => part.line_id))
    const touching = wires.filter(wire => ids.has(wire.from.line_id) || ids.has(wire.to.line_id))
    const power = group.some(part => POWER_KINDS.includes(part.kind)) || touching.every(isPowerWire)
    for (const part of group) side.set(part.line_id, power ? -1 : 1)
  }

  // Distance from the controller decides the column: 1 = next to it, 2 = one further out, ...
  const depth = new Map<string, number>([[cid, 0]])
  const queue = [cid]
  while (queue.length) {
    const id = queue.shift()!
    for (const wire of wires) {
      const other = wire.from.line_id === id ? wire.to.line_id : wire.to.line_id === id ? wire.from.line_id : null
      if (other && !depth.has(other)) {
        depth.set(other, depth.get(id)! + 1)
        queue.push(other)
      }
    }
  }
  const col = (id: string) => (id === cid ? 0 : (side.get(id) ?? 1) * (depth.get(id) ?? 1))

  // Which edge a wire end sits on: facing the other end, or for two parts in one column, facing the controller.
  const endSide = (here: string, there: string): Side => {
    const a = col(here)
    const b = col(there)
    if (b !== a) return b > a ? 'right' : 'left'
    if (a === 0) return 'right'
    return a < 0 ? 'right' : 'left'
  }
  type End = { line_id: string; pin: string; side: Side }
  const endsOf = (wire: WireConnection): [End, End] => [
    { ...wire.from, side: endSide(wire.from.line_id, wire.to.line_id) },
    { ...wire.to, side: endSide(wire.to.line_id, wire.from.line_id) },
  ]
  const keyOf = (end: End) => `${end.line_id}|${end.pin}|${end.side}`

  // Pins per box side, first-seen order; colour = the signal of the first wire on that pin.
  const pinLists = new Map<string, { left: string[]; right: string[] }>()
  const pinColor = new Map<string, string>()
  const partners = new Map<string, string[]>() // anchor key -> counterpart anchor keys
  for (const wire of wires) {
    const ends = endsOf(wire)
    ends.forEach((end, i) => {
      const lists = pinLists.get(end.line_id) ?? { left: [], right: [] }
      if (!lists[end.side].includes(end.pin)) lists[end.side].push(end.pin)
      pinLists.set(end.line_id, lists)
      const key = keyOf(end)
      if (!pinColor.has(key)) pinColor.set(key, wireColor[wire.signal] ?? wireColor.other)
      partners.set(key, [...(partners.get(key) ?? []), keyOf(ends[1 - i])])
    })
  }

  // Columns, left to right.
  const columns = new Map<number, PartVisual[]>()
  for (const part of [controller, ...peripherals]) {
    const c = col(part.line_id)
    columns.set(c, [...(columns.get(c) ?? []), part])
  }
  const order = [...columns.keys()].sort((a, b) => a - b)

  // Channel widths grow with the number of wires through them.
  const channelOf = (end: End) => {
    const c = col(end.line_id)
    return end.side === 'right' ? c : c - 1 // channel k lies between columns k and k + 1
  }
  const channelCount = new Map<number, number>()
  for (const wire of wires) {
    const k = channelOf(endsOf(wire)[0])
    channelCount.set(k, (channelCount.get(k) ?? 0) + 1)
  }
  const channelWidth = (k: number) => Math.min(176, Math.max(92, 56 + (channelCount.get(k) ?? 0) * 9))
  const columnX = new Map<number, number>()
  let x = MARGIN
  order.forEach((c, i) => {
    if (i > 0) x += channelWidth(order[i - 1])
    columnX.set(c, x)
    x += c === 0 ? CTRL_W : BOX_W
  })
  // A channel outside the outermost column (a loop between two parts of that column) still needs room.
  const width = x + (channelCount.has(order[order.length - 1]) ? channelWidth(order[order.length - 1]) : 0) + MARGIN
  const leftPad = channelCount.has(order[0] - 1) ? channelWidth(order[0] - 1) : 0
  for (const [c, value] of columnX) columnX.set(c, value + leftPad)

  const boxHeight = (id: string) => {
    const lists = pinLists.get(id)!
    return HEAD + Math.max(lists.left.length, lists.right.length, 1) * ROW + FOOT
  }
  const columnHeight = (list: PartVisual[]) =>
    list.reduce((sum, part) => sum + boxHeight(part.line_id), 0) + GAP * Math.max(list.length - 1, 0)
  const height = Math.max(...[...columns.values()].map(columnHeight)) + MARGIN * 2

  // Positions for the current order of cards and pins.
  const anchorY = new Map<string, number>()
  const boxY = new Map<string, number>()
  const place = () => {
    for (const list of columns.values()) {
      let y = (height - columnHeight(list)) / 2
      for (const part of list) {
        boxY.set(part.line_id, y)
        const lists = pinLists.get(part.line_id)!
        for (const s of ['left', 'right'] as const)
          lists[s].forEach((pin, i) => anchorY.set(`${part.line_id}|${pin}|${s}`, y + HEAD + ROW * (i + 0.5)))
        y += boxHeight(part.line_id) + GAP
      }
    }
  }
  const barycentre = (key: string) =>
    mean(
      (partners.get(key) ?? []).map(other => anchorY.get(other) ?? height / 2),
      anchorY.get(key) ?? height / 2,
    )
  place()
  for (let pass = 0; pass < ORDER_PASSES; pass++) {
    for (const [id, lists] of pinLists)
      for (const s of ['left', 'right'] as const) {
        const scores = new Map(lists[s].map(pin => [pin, barycentre(`${id}|${pin}|${s}`)]))
        lists[s].sort((a, b) => scores.get(a)! - scores.get(b)!)
      }
    place()
    for (const [c, list] of columns) {
      if (c === 0) continue
      const scores = new Map(
        list.map(part => {
          const lists = pinLists.get(part.line_id)!
          const keys = [
            ...lists.left.map(pin => `${part.line_id}|${pin}|left`),
            ...lists.right.map(pin => `${part.line_id}|${pin}|right`),
          ]
          return [part.line_id, mean(keys.map(barycentre), height / 2)]
        }),
      )
      list.sort((a, b) => scores.get(a.line_id)! - scores.get(b.line_id)!)
    }
    place()
  }

  const anchors = new Map<string, DiagramAnchor>()
  const boxes: DiagramBox[] = [...columns.entries()].flatMap(([c, list]) =>
    list.map(part => {
      const w = c === 0 ? CTRL_W : BOX_W
      const bx = columnX.get(c)!
      const lists = pinLists.get(part.line_id)!
      const make = (s: Side) =>
        lists[s].map(pin => {
          const key = `${part.line_id}|${pin}|${s}`
          const anchor: DiagramAnchor = {
            line_id: part.line_id,
            pin,
            side: s,
            x: s === 'left' ? bx : bx + w,
            y: anchorY.get(key)!,
            dir: s === 'left' ? -1 : 1,
            color: pinColor.get(key) ?? wireColor.other,
          }
          anchors.set(key, anchor)
          return anchor
        })
      return {
        part,
        x: bx,
        y: boxY.get(part.line_id)!,
        w,
        h: boxHeight(part.line_id),
        controller: c === 0,
        left: make('left'),
        right: make('right'),
      }
    }),
  )

  // Lanes: within a channel, a wire heading down whose left end is higher takes a lane further right (and the
  // mirror for wires heading up), which keeps their vertical runs from crossing each other's horizontal ones.
  const routed = wires.map(wire => {
    const [fromEnd, toEnd] = endsOf(wire)
    const from = anchors.get(keyOf(fromEnd))!
    const to = anchors.get(keyOf(toEnd))!
    const [left, right] = from.x <= to.x ? [from, to] : [to, from]
    return { wire, from, to, left, right, channel: channelOf(fromEnd) }
  })
  const byChannel = new Map<number, typeof routed>()
  for (const entry of routed) byChannel.set(entry.channel, [...(byChannel.get(entry.channel) ?? []), entry])
  const laneX = new Map<string, number>()
  for (const [k, list] of byChannel) {
    const start = columnX.has(k) ? columnX.get(k)! + (k === 0 ? CTRL_W : BOX_W) : columnX.get(k + 1)! - channelWidth(k)
    const cw = channelWidth(k)
    const score = (entry: (typeof routed)[number]) =>
      entry.right.y >= entry.left.y ? -entry.left.y : 100000 + entry.left.y
    const sorted = [...list].sort((a, b) => score(a) - score(b))
    const spacing = Math.min(10, (cw - 40) / Math.max(sorted.length - 1, 1))
    sorted.forEach((entry, i) => laneX.set(entry.wire.id, start + cw / 2 + (i - (sorted.length - 1) / 2) * spacing))
  }

  const diagramWires: DiagramWire[] = routed.map(({ wire, from, to }) => {
    const lane = laneX.get(wire.id)!
    // Same edge (two parts in one column): a loop out to the lane and back.
    const d =
      from.x === to.x
        ? `M${from.x} ${from.y} C${lane + (lane - from.x) * 0.35} ${from.y} ${lane + (lane - from.x) * 0.35} ${to.y} ${to.x} ${to.y}`
        : `M${from.x} ${from.y} C${lane} ${from.y} ${lane} ${to.y} ${to.x} ${to.y}`
    return { wire, from, to, d }
  })

  return { width, height, head: HEAD, row: ROW, boxes, wires: diagramWires }
}
