import { useId, useState, type CSSProperties, type ReactNode, type SVGProps } from 'react'
import type { BoardSide, OverviewPin, PartVisual } from './api'
import { clamp, frac, MONO, partLayout, partPalette, pinKindColor, type PinSpot } from './partGeometry'

// Deterministic cartoon drawing of one PartVisual (docs/contracts/project-overview.md). AI-drawn, not a photo.

function BodyShape({
  visual: part,
  w,
  h,
  ...props
}: { visual: PartVisual; w: number; h: number } & SVGProps<SVGRectElement & SVGEllipseElement>) {
  const short = Math.min(w, h)
  if (part.body.shape === 'round') return <ellipse cx={w / 2} cy={h / 2} rx={w / 2} ry={h / 2} {...props} />
  const rx = part.body.shape === 'rect' ? 4 : part.body.shape === 'rounded' ? short * 0.08 : short * 0.12
  return <rect x={0} y={0} width={w} height={h} rx={rx} {...props} />
}

function fitText(text: string, width: number, height: number, max = 14) {
  return clamp(Math.min(height * 0.62, width / Math.max(text.length * 0.62, 1)), 3, max)
}

function Feature({
  feature,
  w,
  h,
  part,
}: {
  feature: PartVisual['features'][number]
  w: number
  h: number
  part: PartVisual
}) {
  const x = frac(feature.x) * w
  const y = frac(feature.y) * h
  const fw = Math.max(frac(feature.w) * w, 3)
  const fh = Math.max(frac(feature.h) * h, 3)
  const cx = x + fw / 2
  const cy = y + fh / 2
  const m = Math.min(fw, fh)
  const ink = partPalette[part.body.color]?.ink ?? '#fff'
  switch (feature.type) {
    case 'screen': {
      const eyeW = fw * 0.1
      const eyeH = fh * 0.24
      return (
        <g>
          <rect x={x} y={y} width={fw} height={fh} rx={Math.min(3, m * 0.06)} fill="#0b131b" stroke="#04070a" />
          <rect x={x + 3} y={y + 3} width={fw - 6} height={fh - 6} rx={2} fill="#112230" />
          {part.kind === 'display' && (
            <g className="part-screen-eyes" fill="#7fe3ff" opacity={0.6}>
              <rect x={x + fw * 0.33 - eyeW / 2} y={cy - eyeH / 2} width={eyeW} height={eyeH} rx={eyeW * 0.3} />
              <rect x={x + fw * 0.67 - eyeW / 2} y={cy - eyeH / 2} width={eyeW} height={eyeH} rx={eyeW * 0.3} />
            </g>
          )}
          <path
            d={`M${x + 4} ${y + fh * 0.35} L${x + fw * 0.3} ${y + 4}`}
            stroke="#fff"
            strokeOpacity={0.08}
            strokeWidth={4}
          />
        </g>
      )
    }
    case 'led': {
      const color = /done|full|blue|stdby/i.test(feature.text ?? '') ? '#4aa3ff' : '#ff5a46'
      const r = Math.max(m / 2, 2.5)
      return (
        <g className="part-led">
          <circle cx={cx} cy={cy} r={r * 2.3} fill={color} opacity={0.22} />
          <circle cx={cx} cy={cy} r={r} fill={color} stroke="#00000055" strokeWidth={0.6} />
          <circle cx={cx - r * 0.3} cy={cy - r * 0.3} r={r * 0.35} fill="#fff" opacity={0.7} />
        </g>
      )
    }
    case 'button':
      return (
        <g>
          <rect x={x} y={y} width={fw} height={fh} rx={Math.min(3, m * 0.2)} fill="#3a3d42" stroke="#1e2023" />
          <circle cx={cx} cy={cy} r={m * 0.3} fill="#8b9097" stroke="#5d6168" strokeWidth={0.8} />
        </g>
      )
    case 'antenna': {
      // A meandering trace along the longer direction.
      const horizontal = fw >= fh
      const steps = 6
      let d = ''
      for (let i = 0; i <= steps; i++) {
        const t = i / steps
        if (horizontal) {
          const px = x + t * fw
          d += `${i ? 'L' : 'M'}${px} ${i % 2 ? y + fh * 0.15 : y + fh * 0.85} `
          if (i < steps) d += `L${px} ${i % 2 ? y + fh * 0.85 : y + fh * 0.15} `
        } else {
          const py = y + t * fh
          d += `${i ? 'L' : 'M'}${i % 2 ? x + fw * 0.15 : x + fw * 0.85} ${py} `
          if (i < steps) d += `L${i % 2 ? x + fw * 0.85 : x + fw * 0.15} ${py} `
        }
      }
      return <path d={d} fill="none" stroke="#e5c35c" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
    }
    case 'touch_pad': {
      const r = m / 2
      return (
        <g>
          <circle cx={cx} cy={cy} r={r * 0.92} fill="#d8b25a" stroke="#a9852e" />
          <circle cx={cx} cy={cy} r={r * 0.7} fill="none" stroke="#f6dc94" strokeWidth={1.4} opacity={0.9} />
          <circle cx={cx} cy={cy} r={r * 0.48} fill="none" stroke="#f6dc94" strokeWidth={1.4} opacity={0.7} />
          <circle cx={cx} cy={cy} r={r * 0.26} fill="#f6dc94" opacity={0.6} />
        </g>
      )
    }
    case 'lens': {
      const r = m / 2
      return (
        <g>
          <circle cx={cx} cy={cy} r={r} fill="#15181c" stroke="#000" />
          <circle cx={cx} cy={cy} r={r * 0.6} fill="#2a3a4c" />
          <circle cx={cx - r * 0.25} cy={cy - r * 0.25} r={r * 0.18} fill="#fff" opacity={0.8} />
        </g>
      )
    }
    case 'label':
      if (!feature.text) return null
      return (
        <text
          x={cx}
          y={cy}
          fill={ink}
          opacity={0.85}
          fontFamily={MONO}
          fontWeight={700}
          fontSize={fitText(feature.text, fw, fh, 12)}
          textAnchor="middle"
          dominantBaseline="central"
        >
          {feature.text}
        </text>
      )
    default:
      return null
  }
}

function Connector({ connector }: { connector: ReturnType<typeof partLayout>['connectors'][number] }) {
  const { x, y, width, height } = connector.rect
  const short = Math.min(width, height)
  const inner = { x: x + width * 0.2, y: y + height * 0.2, width: width * 0.6, height: height * 0.6 }
  switch (connector.type) {
    case 'usb_c':
      return (
        <g>
          <rect x={x} y={y} width={width} height={height} rx={short / 2} fill="#c8cdd4" stroke="#7b828b" />
          <rect {...inner} rx={Math.min(inner.width, inner.height) / 2} fill="#2b2f35" />
        </g>
      )
    case 'micro_usb': {
      const k = short * 0.18
      const pts = connector.vertical
        ? `${inner.x},${inner.y + k} ${inner.x + inner.width},${inner.y} ${inner.x + inner.width},${inner.y + inner.height} ${inner.x},${inner.y + inner.height - k}`
        : `${inner.x},${inner.y} ${inner.x + inner.width},${inner.y} ${inner.x + inner.width - k},${inner.y + inner.height} ${inner.x + k},${inner.y + inner.height}`
      return (
        <g>
          <rect x={x} y={y} width={width} height={height} rx={1.5} fill="#c8cdd4" stroke="#7b828b" />
          <polygon points={pts} fill="#2b2f35" />
        </g>
      )
    }
    case 'jst': {
      const slots = [0.3, 0.7]
      return (
        <g>
          <rect x={x} y={y} width={width} height={height} rx={1.5} fill="#f4f1e8" stroke="#b3ac98" />
          {slots.map(t =>
            connector.vertical ? (
              <rect
                key={t}
                x={x + width * 0.3}
                y={y + height * t - height * 0.1}
                width={width * 0.4}
                height={height * 0.2}
                fill="#5c574b"
              />
            ) : (
              <rect
                key={t}
                x={x + width * t - width * 0.1}
                y={y + height * 0.3}
                width={width * 0.2}
                height={height * 0.4}
                fill="#5c574b"
              />
            ),
          )}
        </g>
      )
    }
    case 'barrel':
      return (
        <g>
          <rect x={x} y={y} width={width} height={height} rx={2} fill="#232427" stroke="#000" />
          <circle cx={x + width / 2} cy={y + height / 2} r={short * 0.28} fill="#9aa0a8" stroke="#55595f" />
        </g>
      )
    case 'screw_terminal': {
      const slots = [0.27, 0.73]
      return (
        <g>
          <rect x={x} y={y} width={width} height={height} rx={1.5} fill="#2e7fbf" stroke="#1d5788" />
          {slots.map(t => {
            const sx = connector.vertical ? x + width / 2 : x + width * t
            const sy = connector.vertical ? y + height * t : y + height / 2
            const r = short * 0.28
            return (
              <g key={t}>
                <circle cx={sx} cy={sy} r={r} fill="#c8cdd4" stroke="#7b828b" />
                <line x1={sx - r * 0.6} y1={sy} x2={sx + r * 0.6} y2={sy} stroke="#5d636b" strokeWidth={1} />
              </g>
            )
          })}
        </g>
      )
    }
    case 'pin_socket': {
      const holes = 4
      return (
        <g>
          <rect x={x} y={y} width={width} height={height} rx={1} fill="#1e1f22" />
          {Array.from({ length: holes }, (_, i) => {
            const t = (i + 0.5) / holes
            const s = short * 0.4
            const hx = connector.vertical ? x + width / 2 : x + width * t
            const hy = connector.vertical ? y + height * t : y + height / 2
            return <rect key={i} x={hx - s / 2} y={hy - s / 2} width={s} height={s} fill="#55585e" />
          })}
        </g>
      )
    }
    default:
      return null
  }
}

function Crimp({ side, w, h }: { side: BoardSide; w: number; h: number }) {
  const depth = Math.min(w, h) * 0.12
  const lines: ReactNode[] = []
  const vertical = side === 'left' || side === 'right'
  const len = vertical ? h : w
  const count = Math.max(6, Math.round(len / 7))
  for (let i = 1; i < count; i++) {
    const t = (i / count) * len
    lines.push(
      vertical ? (
        <line key={i} x1={side === 'left' ? 2 : w - depth} y1={t} x2={side === 'left' ? depth : w - 2} y2={t} />
      ) : (
        <line key={i} x1={t} y1={side === 'top' ? 2 : h - depth} x2={t} y2={side === 'top' ? depth : h - 2} />
      ),
    )
  }
  const band =
    side === 'left'
      ? { x: 0, y: 0, width: depth, height: h }
      : side === 'right'
        ? { x: w - depth, y: 0, width: depth, height: h }
        : side === 'top'
          ? { x: 0, y: 0, width: w, height: depth }
          : { x: 0, y: h - depth, width: w, height: depth }
  return (
    <g>
      <rect {...band} fill="#d9dde3" opacity={0.75} />
      <g stroke="#8d939c" strokeWidth={0.8} opacity={0.8}>
        {lines}
      </g>
    </g>
  )
}

const pinText = (pin: OverviewPin) => (pin.functions?.length ? `${pin.name}: ${pin.functions.join(', ')}` : pin.name)

// The board itself: shadow, body, sheen, features, chip and connectors (everything except the pins).
function PartBody({ part, uid, layout }: { part: PartVisual; uid: string; layout: ReturnType<typeof partLayout> }) {
  const { w, h, connectors } = layout
  const palette = partPalette[part.body.color] ?? partPalette.green
  const crimpSide: BoardSide = part.headers?.[0]?.side ?? part.connectors?.[0]?.side ?? (w >= h ? 'left' : 'top')
  return (
    <>
      <defs>
        <clipPath id={`body-${uid}`}>
          <BodyShape visual={part} w={w} h={h} />
        </clipPath>
        <linearGradient id={`sheen-${uid}`} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#fff" stopOpacity="0" />
          <stop offset="0.45" stopColor="#fff" stopOpacity="0.55" />
          <stop offset="0.6" stopColor="#fff" stopOpacity="0" />
        </linearGradient>
      </defs>
      <g className="part-svg-body">
        <BodyShape visual={part} w={w} h={h} transform="translate(4 5)" fill="#0d2630" opacity={0.13} />
        <BodyShape visual={part} w={w} h={h} fill={palette.fill} stroke={palette.edge} strokeWidth={2} />
        <g clipPath={`url(#body-${uid})`}>
          <rect x={0} y={0} width={w} height={h * 0.2} fill="#fff" opacity={0.14} />
          {part.body.shape === 'pouch' && (
            <>
              <rect x={0} y={0} width={w} height={h} fill={`url(#sheen-${uid})`} opacity={0.7} />
              <Crimp side={crimpSide} w={w} h={h} />
            </>
          )}
        </g>
        {part.features?.map((feature, i) => (
          <Feature key={'f' + i} feature={feature} w={w} h={h} part={part} />
        ))}
        {part.chip && <Chip chip={part.chip} w={w} h={h} />}
        {/* Connectors overhang the body edge, so they are drawn above the outline. */}
        {connectors.map((connector, i) => (
          <Connector key={'c2' + i} connector={connector} />
        ))}
      </g>
    </>
  )
}

// Compact drawing for part cards and diagram nodes: body, chip, connectors and pins as plain dots; no labels or
// tooltips. Decorative (the name sits next to it). Pass x/y/width/height to nest it inside another SVG.
export function PartThumb({
  part,
  className,
  x,
  y,
  width,
  height,
}: {
  part: PartVisual
  className?: string
  x?: number
  y?: number
  width?: number
  height?: number
}) {
  const uid = useId().replace(/:/g, '')
  const layout = partLayout(part, true)
  const { view } = layout
  return (
    <svg
      className={className}
      viewBox={`${view.x} ${view.y} ${view.w} ${view.h}`}
      x={x}
      y={y}
      width={width}
      height={height}
      preserveAspectRatio="xMidYMid meet"
      aria-hidden="true"
      focusable="false"
      xmlns="http://www.w3.org/2000/svg"
    >
      <PartBody part={part} uid={uid} layout={layout} />
      {layout.pins.map(spot => (
        <circle
          key={spot.side + spot.index}
          cx={spot.x}
          cy={spot.y}
          r={spot.r}
          fill="#e8bf4a"
          stroke="#9c741c"
          strokeWidth={Math.max(spot.r * 0.35, 0.8)}
        />
      ))}
    </svg>
  )
}

export function PartSvg({ part, maxHeight = 180 }: { part: PartVisual; maxHeight?: number }) {
  const uid = useId().replace(/:/g, '')
  const [tip, setTip] = useState<PinSpot | null>(null)
  const layout = partLayout(part)
  const { pins, view } = layout
  const tipStyle = tip
    ? {
        // Kept away from the edges so the tooltip stays inside the card.
        left: `${clamp(((tip.x - view.x) / view.w) * 100, 20, 80)}%`,
        top: `${((tip.y - view.y) / view.h) * 100}%`,
      }
    : undefined
  return (
    <div className="part-svg" style={{ maxWidth: `${(maxHeight * view.w) / view.h}px` }}>
      <svg
        viewBox={`${view.x} ${view.y} ${view.w} ${view.h}`}
        role="img"
        aria-label={`Drawing of ${part.label}`}
        xmlns="http://www.w3.org/2000/svg"
      >
        <PartBody part={part} uid={uid} layout={layout} />
        <g className="part-svg-pins">
          {pins.map(spot => {
            const rotate = spot.side === 'top' || spot.side === 'bottom'
            const anchor = spot.side === 'top' || spot.side === 'right' ? 'start' : 'end'
            const active = tip?.pin === spot.pin
            return (
              <g
                key={spot.side + spot.index}
                className={`part-pin${active ? ' is-active' : ''}`}
                style={{ '--i': spot.index } as CSSProperties}
                tabIndex={0}
                role="button"
                aria-label={`Pin ${pinText(spot.pin)}`}
                onMouseEnter={() => setTip(spot)}
                onMouseLeave={() => setTip(current => (current === spot ? null : current))}
                onFocus={() => setTip(spot)}
                onBlur={() => setTip(current => (current === spot ? null : current))}
              >
                <circle
                  className="part-pin-hit"
                  cx={spot.x}
                  cy={spot.y}
                  r={Math.max(spot.r * 2, 7)}
                  fill="transparent"
                />
                <circle
                  cx={spot.x}
                  cy={spot.y}
                  r={spot.r}
                  fill="#e8bf4a"
                  stroke="#9c741c"
                  strokeWidth={Math.max(spot.r * 0.35, 0.8)}
                />
                <circle cx={spot.x} cy={spot.y} r={spot.r * 0.38} fill="#7c5b12" />
                <circle cx={spot.dot[0]} cy={spot.dot[1]} r={2.2} fill={pinKindColor[spot.pin.kind] ?? '#8a949a'} />
                <text
                  x={spot.label[0]}
                  y={spot.label[1]}
                  transform={rotate ? `rotate(-90 ${spot.label[0]} ${spot.label[1]})` : undefined}
                  textAnchor={rotate ? (spot.side === 'top' ? 'start' : 'end') : anchor}
                  dominantBaseline="central"
                  fontFamily={MONO}
                  fontSize={spot.font}
                  fontWeight={700}
                  fill="#3f5552"
                >
                  {spot.pin.name}
                </text>
              </g>
            )
          })}
        </g>
      </svg>
      {tip && (
        <div className="part-pin-tip" role="tooltip" style={tipStyle}>
          <strong>{tip.pin.name}</strong>
          {tip.pin.functions?.length > 0 && <span>{tip.pin.functions.join(' · ')}</span>}
        </div>
      )}
    </div>
  )
}

function Chip({ chip, w, h }: { chip: NonNullable<PartVisual['chip']>; w: number; h: number }) {
  const x = frac(chip.x) * w
  const y = frac(chip.y) * h
  const cw = Math.max(frac(chip.w) * w, 6)
  const ch = Math.max(frac(chip.h) * h, 6)
  const legs = Math.max(2, Math.min(6, Math.round(ch / 6)))
  return (
    <g>
      <g stroke="#c4c9d0" strokeWidth={1.2}>
        {Array.from({ length: legs }, (_, i) => {
          const ly = y + ((i + 0.5) / legs) * ch
          return (
            <g key={i}>
              <line x1={x - 2.5} y1={ly} x2={x} y2={ly} />
              <line x1={x + cw} y1={ly} x2={x + cw + 2.5} y2={ly} />
            </g>
          )
        })}
      </g>
      <rect
        x={x}
        y={y}
        width={cw}
        height={ch}
        rx={Math.min(cw, ch) * 0.12}
        fill="#1d1f23"
        stroke="#000"
        strokeOpacity={0.6}
      />
      <circle
        cx={x + Math.min(cw, ch) * 0.14}
        cy={y + Math.min(cw, ch) * 0.14}
        r={Math.min(cw, ch) * 0.05}
        fill="#4a4e55"
      />
      {chip.label && (
        <text
          x={x + cw / 2}
          y={y + ch / 2}
          fill="#d3d7db"
          fontFamily={MONO}
          fontWeight={700}
          fontSize={fitText(chip.label, cw * 0.88, ch, 12)}
          textAnchor="middle"
          dominantBaseline="central"
        >
          {chip.label}
        </text>
      )}
    </g>
  )
}
