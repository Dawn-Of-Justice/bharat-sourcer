import type { ReactNode } from 'react'
import type { BuyableSpec } from './api'

// A stock illustration for a part card that has no AI drawing: the drawing call skips wire, enclosures, screws
// and other non-electronic lines, and a part whose call failed has none either. Picked from the part's name and
// spec category; purely decorative, so it never claims anything about the actual part.

type Kind = 'enclosure' | 'wire' | 'heatshrink' | 'screws' | 'solder' | 'tape' | 'cable' | 'board' | 'bag'

const ELECTRONIC = new Set(['ic', 'module', 'board', 'sensor', 'connector', 'switch', 'battery', 'led', 'ldr'])

function illustrationKind(name: string, category?: BuyableSpec['category']): Kind {
  const text = name.toLowerCase()
  if (/heat\s*-?\s*shrink|shrink tub/.test(text)) return 'heatshrink'
  if (/enclosure|bcaseb|housing|\bbox\b|shell|chassis|3d[- ]?print|\bpla\b|\bpetg\b|filament/.test(text))
    return 'enclosure'
  if (/solder/.test(text)) return 'solder'
  if (/screw|bolt|\bnuts?\b|standoff|spacer|washer|rivet|insert/.test(text)) return 'screws'
  if (/tape|glue|adhesive|velcro|epoxy|zip tie|cable tie/.test(text)) return 'tape'
  if (/usb.*cable|cable.*usb|charging cable|power cable/.test(text)) return 'cable'
  if (/wire|jumper|dupont|bawgb/.test(text) || category === 'wire') return 'wire'
  if (category && ELECTRONIC.has(category)) return 'board'
  return 'bag'
}

const COLOURS: Record<string, string> = {
  white: '#f1efe8',
  black: '#3a3a3a',
  grey: '#a9adb0',
  gray: '#a9adb0',
  red: '#d0574b',
  blue: '#4f73c4',
  green: '#4f9a6b',
  yellow: '#e7be4a',
  orange: '#e58a3c',
  purple: '#8a64b8',
  pink: '#e48fae',
}

function nameColour(name: string, fallback: string) {
  const word = name.toLowerCase().match(new RegExp(`\\b(${Object.keys(COLOURS).join('|')})\\b`))?.[1]
  return word ? COLOURS[word] : fallback
}

// Darken (f < 1) or lighten (f > 1) a #rrggbb colour.
function shade(hex: string, f: number) {
  const n = parseInt(hex.slice(1), 16)
  const channel = (c: number) => Math.max(0, Math.min(255, Math.round(f > 1 ? c + (255 - c) * (f - 1) : c * f)))
  const [r, g, b] = [(n >> 16) & 255, (n >> 8) & 255, n & 255].map(channel)
  return `#${((1 << 24) | (r << 16) | (g << 8) | b).toString(16).slice(1)}`
}

function Enclosure({ colour }: { colour: string }) {
  const edge = shade(colour, 0.6)
  return (
    <g stroke={edge} strokeWidth="1.2" strokeLinejoin="round">
      <polygon points="30,34 82,18 130,34 78,50" fill={shade(colour, 1.08)} />
      <polygon points="30,34 78,50 78,88 30,72" fill={shade(colour, 0.88)} />
      <polygon points="78,50 130,34 130,72 78,88" fill={shade(colour, 0.76)} />
      <polyline points="30,42 78,58 130,42" fill="none" strokeOpacity="0.6" />
      <polygon points="98,60 114,55 114,61 98,66" fill={shade(colour, 0.45)} />
      {[
        [40, 34],
        [80, 22],
        [120, 34],
        [80, 46],
      ].map(([x, y]) => (
        <ellipse key={`${x}-${y}`} cx={x} cy={y} rx="2.6" ry="1.5" fill={shade(colour, 0.55)} stroke="none" />
      ))}
    </g>
  )
}

function Coil({ x, colour }: { x: number; colour: string }) {
  return (
    <g fill="none" stroke={colour} strokeWidth="4" strokeLinecap="round">
      <ellipse cx={x} cy="50" rx="22" ry="22" />
      <ellipse cx={x} cy="50" rx="16" ry="16" stroke={shade(colour, 0.8)} />
      <ellipse cx={x} cy="50" rx="10" ry="10" />
      <path d={`M${x + 20} 58 C ${x + 30} 70, ${x + 18} 80, ${x + 30} 90`} />
      <path d={`M${x + 30} 90 l3 2`} stroke="#c9a46a" strokeWidth="3" />
    </g>
  )
}

function Wire() {
  return (
    <>
      <Coil x={38} colour="#d0443a" />
      <Coil x={80} colour="#2f2f2f" />
      <Coil x={122} colour="#e1b03a" />
    </>
  )
}

function HeatShrink() {
  const tubes = [
    ['#2f2f2f', 12],
    ['#d0443a', 10],
    ['#4f73c4', 9],
    ['#e1b03a', 8],
    ['#4f9a6b', 7],
  ] as const
  return (
    <g transform="rotate(-18 80 50)">
      {tubes.map(([colour, d], index) => {
        const y = 24 + index * 13
        return (
          <g key={colour}>
            <rect x="26" y={y} width="108" height={d} rx={d / 2} fill={colour} />
            <rect x="32" y={y + 2} width="96" height="1.6" rx="0.8" fill="#fff" opacity="0.35" />
            <ellipse cx="131" cy={y + d / 2} rx="2.4" ry={d / 2 - 1.5} fill={shade(colour, 0.45)} />
          </g>
        )
      })}
    </g>
  )
}

function Screw({ x, y, angle }: { x: number; y: number; angle: number }) {
  return (
    <g transform={`translate(${x} ${y}) rotate(${angle})`}>
      <rect x="-3.5" y="0" width="7" height="44" rx="1.5" fill="#b9bec2" stroke="#7d8388" />
      {Array.from({ length: 9 }, (_, i) => (
        <line key={i} x1="-3.5" y1={6 + i * 4.4} x2="3.5" y2={8 + i * 4.4} stroke="#7d8388" strokeWidth="1" />
      ))}
      <ellipse cx="0" cy="0" rx="9" ry="4" fill="#cfd3d6" stroke="#7d8388" />
      <line x1="-5" y1="0" x2="5" y2="0" stroke="#6b7176" strokeWidth="1.6" />
    </g>
  )
}

function Screws() {
  return (
    <>
      <Screw x={48} y={26} angle={-20} />
      <Screw x={80} y={22} angle={8} />
      <polygon
        points="112,52 124,45 136,52 136,66 124,73 112,66"
        fill="#c4c8cb"
        stroke="#7d8388"
        strokeLinejoin="round"
      />
      <circle cx="124" cy="59" r="5" fill="#f5f7f1" stroke="#7d8388" />
    </>
  )
}

function Solder() {
  return (
    <g>
      <circle cx="74" cy="50" r="34" fill="#4f73c4" stroke="#33518f" strokeWidth="1.5" />
      <circle cx="74" cy="50" r="26" fill="#c8ccd0" stroke="#9aa0a5" />
      {[22, 18, 14].map(r => (
        <circle key={r} cx="74" cy="50" r={r} fill="none" stroke="#a8aeb3" strokeWidth="1" />
      ))}
      <circle cx="74" cy="50" r="8" fill="#f5f7f1" stroke="#33518f" />
      <path d="M98 62 C 112 70, 120 60, 138 78" fill="none" stroke="#b5bbc0" strokeWidth="3" strokeLinecap="round" />
    </g>
  )
}

function Tape() {
  return (
    <g>
      <circle cx="80" cy="50" r="32" fill="#e8d9a8" stroke="#b9a66c" strokeWidth="1.5" />
      <circle cx="80" cy="50" r="18" fill="#f5f7f1" stroke="#b9a66c" />
      <circle cx="80" cy="50" r="25" fill="none" stroke="#d6c58e" />
      <path d="M108 64 L140 76 L136 86 L104 72 Z" fill="#efe3b8" stroke="#b9a66c" strokeLinejoin="round" />
    </g>
  )
}

function Cable() {
  return (
    <g>
      <path
        d="M30 70 C 30 30, 70 30, 80 50 S 120 80, 124 40"
        fill="none"
        stroke="#3a3a3a"
        strokeWidth="5"
        strokeLinecap="round"
      />
      <rect x="20" y="70" width="20" height="16" rx="3" fill="#4a4a4a" />
      <rect x="25" y="86" width="10" height="7" rx="1.5" fill="#c4c8cb" stroke="#7d8388" />
      <rect x="114" y="22" width="20" height="18" rx="3" fill="#4a4a4a" />
      <rect x="118" y="14" width="12" height="8" rx="1.5" fill="#c4c8cb" stroke="#7d8388" />
    </g>
  )
}

function Board() {
  return (
    <g>
      <rect x="34" y="20" width="92" height="60" rx="5" fill="#3f7f5c" stroke="#2d5e44" strokeWidth="1.5" />
      <rect x="64" y="38" width="30" height="24" rx="2" fill="#262626" />
      {Array.from({ length: 10 }, (_, i) => (
        <g key={i}>
          <circle cx={42 + i * 8.4} cy="27" r="2.4" fill="#e1b03a" stroke="#9b7a24" strokeWidth="0.8" />
          <circle cx={42 + i * 8.4} cy="73" r="2.4" fill="#e1b03a" stroke="#9b7a24" strokeWidth="0.8" />
        </g>
      ))}
      <circle cx="108" cy="44" r="2.6" fill="#e2564a" />
    </g>
  )
}

function Bag() {
  return (
    <g>
      <rect x="44" y="16" width="72" height="72" rx="6" fill="#e9efe8" stroke="#a9b8b3" strokeWidth="1.5" />
      <rect x="44" y="16" width="72" height="9" rx="3" fill="#7fa79a" />
      <rect x="56" y="40" width="22" height="16" rx="2" fill="#2f2f2f" />
      <rect x="86" y="46" width="18" height="6" rx="3" fill="#d6b57a" />
      <circle cx="68" cy="72" r="6" fill="#4f73c4" />
      <circle cx="94" cy="70" r="4" fill="#d0443a" />
    </g>
  )
}

export function PartIllustration({ name, category }: { name: string; category?: BuyableSpec['category'] }) {
  const kind = illustrationKind(name, category)
  const art: Record<Kind, ReactNode> = {
    enclosure: <Enclosure colour={nameColour(name, COLOURS.white)} />,
    wire: <Wire />,
    heatshrink: <HeatShrink />,
    screws: <Screws />,
    solder: <Solder />,
    tape: <Tape />,
    cable: <Cable />,
    board: <Board />,
    bag: <Bag />,
  }
  return (
    <svg className="pp-card-thumb pp-card-illustration" viewBox="0 0 160 100" role="presentation">
      {art[kind]}
    </svg>
  )
}
