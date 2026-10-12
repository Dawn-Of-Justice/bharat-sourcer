import { useId, type CSSProperties } from 'react'
import type { PartVisual, WireConnection } from './api'
import { dashOf, MONO, strokeOf } from './partGeometry'
import { partInitials } from './partName'
import { PartThumb } from './PartSvg'
import { wiringLayout, type DiagramAnchor, type DiagramBox } from './wiringLayout'

// "How it's wired": the controller in the middle, power parts on the left, signal parts on the right, wires coloured
// by signal. Only disputed wires and wires with problems are dashed. Hovering or focusing a wire highlights it.

const CHAR_W = 6.9 // average width of an 11.5px monospace character
const NAME_CHAR_W = 7 // average width of a 12.5px bold sans character

const clip = (text: string, max: number) => (text.length > max ? text.slice(0, Math.max(max - 1, 1)) + '…' : text)

// Up to two lines of a part name, cut at word boundaries where possible.
function nameLines(name: string, max: number) {
  if (name.length <= max) return [name]
  const words = name.split(/\s+/)
  let first = ''
  while (words.length && (first ? first.length + 1 : 0) + words[0].length <= max)
    first += (first ? ' ' : '') + words.shift()
  if (!first) return [clip(name, max)]
  return [first, clip(words.join(' '), max)]
}

function Node({ box, head, row }: { box: DiagramBox; head: number; row: number }) {
  const { part, x, y, w, h } = box
  const thumb = { x: x + 10, y: y + 8, w: 44, h: head - 16 }
  const textX = thumb.x + thumb.w + 10
  const lines = nameLines(part.label, Math.floor((x + w - 10 - textX) / NAME_CHAR_W))
  const twoSided = box.left.length > 0 && box.right.length > 0
  const maxChars = Math.floor((twoSided ? w / 2 - 18 : w - 30) / CHAR_W)
  const pinLabel = (anchor: DiagramAnchor) => (
    <g key={anchor.side + anchor.pin}>
      <text
        x={anchor.side === 'left' ? x + 12 : x + w - 12}
        y={anchor.y}
        textAnchor={anchor.side === 'left' ? 'start' : 'end'}
        dominantBaseline="central"
        fontFamily={MONO}
        fontSize={11.5}
        fill="#33474a"
      >
        {clip(anchor.pin, maxChars)}
      </text>
    </g>
  )
  return (
    <g className={`po-node${box.controller ? ' is-controller' : ''}`}>
      <title>{part.label}</title>
      <rect className="po-node-card" x={x} y={y} width={w} height={h} rx={10} />
      <rect className="po-node-thumb" x={thumb.x} y={thumb.y} width={thumb.w} height={thumb.h} rx={6} />
      {part.headers.length || part.chip || part.features.length ? (
        <PartThumb part={part} x={thumb.x + 3} y={thumb.y + 3} width={thumb.w - 6} height={thumb.h - 6} />
      ) : (
        <text
          x={thumb.x + thumb.w / 2}
          y={thumb.y + thumb.h / 2}
          textAnchor="middle"
          dominantBaseline="central"
          fontSize={12}
          fontWeight={800}
          fill="#5d706c"
        >
          {partInitials(part.label)}
        </text>
      )}
      {lines.map((line, i) => (
        <text
          key={i}
          x={textX}
          y={y + head / 2 + (i - (lines.length - 1) / 2) * 15}
          dominantBaseline="central"
          fontSize={12.5}
          fontWeight={700}
          fill="#0d2630"
        >
          {line}
        </text>
      ))}
      <line className="po-node-rule" x1={x} y1={y + head - 2} x2={x + w} y2={y + head - 2} />
      {box.left.map(pinLabel)}
      {box.right.map(pinLabel)}
      {Array.from({ length: Math.max(box.left.length, box.right.length) - 1 }, (_, i) => (
        <line
          key={i}
          className="po-node-row"
          x1={x + 10}
          x2={x + w - 10}
          y1={y + head + row * (i + 1)}
          y2={y + head + row * (i + 1)}
        />
      ))}
    </g>
  )
}

export function WiringDiagram({
  parts,
  wiring,
  active,
  onActive,
  label,
}: {
  parts: PartVisual[]
  wiring: WireConnection[]
  active: string | null
  onActive: (id: string | null) => void
  label: (wire: WireConnection) => string
}) {
  const uid = useId().replace(/:/g, '')
  const layout = wiringLayout(parts, wiring)
  if (!layout) return null
  return (
    <svg
      className={`po-wiring-svg${active ? ' has-active' : ''}`}
      viewBox={`0 0 ${layout.width} ${layout.height}`}
      style={{ '--diagram-w': `${layout.width}px` } as CSSProperties}
      role="group"
      aria-label={`Wiring diagram with ${layout.wires.length} connections`}
      xmlns="http://www.w3.org/2000/svg"
    >
      <defs>
        <filter id={`${uid}-shadow`} x="-10%" y="-10%" width="120%" height="130%">
          <feDropShadow dx="0" dy="2" stdDeviation="3" floodColor="#0d2630" floodOpacity="0.08" />
        </filter>
        {layout.wires.map((entry, i) => (
          <mask
            key={entry.wire.id}
            id={`${uid}-m${i}`}
            maskUnits="userSpaceOnUse"
            x={0}
            y={0}
            width={layout.width}
            height={layout.height}
          >
            <path
              className="po-wire-reveal"
              style={{ '--i': i } as CSSProperties}
              d={entry.d}
              pathLength={1}
              fill="none"
              stroke="#fff"
              strokeWidth={10}
            />
          </mask>
        ))}
      </defs>
      <g filter={`url(#${uid}-shadow)`}>
        {layout.boxes.map(box => (
          <Node key={box.part.line_id} box={box} head={layout.head} row={layout.row} />
        ))}
      </g>
      {layout.wires.map((entry, i) => {
        const { wire } = entry
        const isActive = active === wire.id
        return (
          <g
            key={wire.id}
            className={`po-wire${isActive ? ' is-active' : ''}`}
            tabIndex={0}
            role="img"
            aria-label={label(wire)}
            onMouseEnter={() => onActive(wire.id)}
            onMouseLeave={() => onActive(null)}
            onFocus={() => onActive(wire.id)}
            onBlur={() => onActive(null)}
          >
            <path className="po-wire-hit" d={entry.d} fill="none" stroke="transparent" strokeWidth={12} />
            <g mask={`url(#${uid}-m${i})`}>
              <path
                d={entry.d}
                fill="none"
                stroke={strokeOf(wire)}
                strokeWidth={isActive ? 3.5 : 2}
                strokeDasharray={dashOf(wire)}
                strokeLinecap="round"
              />
            </g>
          </g>
        )
      })}
      {layout.boxes.flatMap(box =>
        [...box.left, ...box.right].map(anchor => (
          <circle
            key={box.part.line_id + anchor.pin + anchor.side}
            cx={anchor.x}
            cy={anchor.y}
            r={3.6}
            fill={anchor.color}
            stroke="#fff"
            strokeWidth={1.5}
          />
        )),
      )}
    </svg>
  )
}
