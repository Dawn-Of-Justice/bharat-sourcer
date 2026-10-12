import { useId, useLayoutEffect, useRef, useState, type CSSProperties, type ReactNode } from 'react'
import type { Job, PartVisual, ProjectOverview as Overview, WireConnection } from './api'
import { PartSvg, PartThumb } from './PartSvg'
import { strokeOf, wireColor, wireFlagged } from './partGeometry'
import { WiringDiagram } from './WiringDiagram'
import { pickController } from './wiringLayout'

// Review-step project overview pieces (docs/contracts/project-overview.md): the "How it works" card, part drawings
// for the parts grid and the part panel, and the collapsible "How it's wired" section. All AI-inferred and checked
// by a second AI call; never verified against the physical board. Loaded lazily with the drawing code.

export function ProjectHero({ job }: { job: Job }) {
  // The title, description and source link already sit in the page heading above the step strip.
  const project = job.project
  const summaryRef = useRef<HTMLParagraphElement>(null)
  const [expanded, setExpanded] = useState(false)
  const [overflows, setOverflows] = useState(false)
  const summary = project?.summary ?? ''

  useLayoutEffect(() => {
    const element = summaryRef.current
    if (!element || expanded) return
    const measure = () => setOverflows(element.scrollHeight > element.clientHeight + 1)
    measure()
    const observer = new ResizeObserver(measure)
    observer.observe(element)
    return () => observer.disconnect()
  }, [summary, expanded])

  if (!project) return null
  const chips = [
    ['Power', project.power],
    ['Controller', project.controller],
    ['Interfaces', (project.interfaces ?? []).join(', ')],
  ].filter(([, value]) => value)
  if (!summary && !chips.length) return null
  return (
    <section className="po-hero" aria-labelledby="po-hero-title">
      <h2 id="po-hero-title">How it works</h2>
      <div className="po-hero-body">
        {summary && (
          <div className="po-hero-summary">
            <p ref={summaryRef} id="po-hero-how" className={`po-hero-how${expanded ? '' : ' is-clamped'}`}>
              {summary}
            </p>
            {(overflows || expanded) && (
              <button
                type="button"
                className="pp-text-button po-hero-more"
                aria-expanded={expanded}
                aria-controls="po-hero-how"
                onClick={() => setExpanded(open => !open)}
              >
                {expanded ? 'Show less' : 'Read more'}
              </button>
            )}
          </div>
        )}
        {chips.length > 0 && (
          <dl className="po-hero-facts">
            {chips.map(([label, value]) => (
              <div key={label}>
                <dt>{label}</dt>
                <dd>{value}</dd>
              </div>
            ))}
          </dl>
        )}
      </div>
    </section>
  )
}

// The small drawing in a part card.
export function PartArt({ part }: { part: PartVisual }) {
  return <PartThumb part={part} className="pp-card-thumb" />
}

const pinSource: Record<PartVisual['pin_source'], string> = {
  code: 'Pins from the project code',
  datasheet_knowledge: 'Pins from datasheet knowledge',
  ai_inferred: 'Pins inferred by AI',
}

// Top of the part panel: the large drawing with pin labels and tooltips, where the pins came from, and why the
// second check is unsure, if it is.
export function PartDetail({ part }: { part: PartVisual }) {
  return (
    <div className="pp-part-drawing">
      <div className="pp-part-drawing-art">
        <PartSvg part={part} maxHeight={200} />
      </div>
      <p className="pp-part-drawing-source">{pinSource[part.pin_source] ?? pinSource.ai_inferred}</p>
      {part.verdict !== 'confirmed' && part.verdict_reason && (
        <p className={part.verdict === 'disputed' ? 'po-reason' : 'po-reason-soft'}>{part.verdict_reason}</p>
      )}
    </div>
  )
}

const legend = [
  ['Power', wireColor.power],
  ['Ground', wireColor.ground],
  ['I²C', wireColor.i2c_sda],
  ['Signal', wireColor.digital],
] as const

const sourceInfo: Record<WireConnection['source'], { title: string; icon: ReactNode }> = {
  code: {
    title: 'From the project code',
    icon: <path d="M5.5 4 2 8l3.5 4M10.5 4 14 8l-3.5 4" />,
  },
  description: {
    title: 'From the project description',
    icon: <path d="M3 5h6M3 8h10M3 11h7" />,
  },
  ai_inferred: {
    title: 'Inferred by AI',
    icon: <path d="M8 2.5 9.3 6.7 13.5 8 9.3 9.3 8 13.5 6.7 9.3 2.5 8 6.7 6.7Z" />,
  },
}
const verdictInfo: Record<WireConnection['verdict'], { title: string; icon: ReactNode }> = {
  confirmed: { title: 'Confirmed by the second check', icon: <path d="m3.5 8.5 3 3 6-7" /> },
  unverified: {
    title: 'Not confirmed by the second check — double-check it',
    icon: <path d="M6 6a2 2 0 1 1 2.8 1.8C8.3 8 8 8.5 8 9.2M8 12v.01" />,
  },
  disputed: { title: 'The second check disagrees', icon: <path d="M8 3.5v5.5M8 12v.01" /> },
}

function MiniIcon({ title, tone, children }: { title: string; tone: string; children: ReactNode }) {
  return (
    <span className={`po-mini-icon po-mini-${tone}`} title={title} role="img" aria-label={title}>
      <svg viewBox="0 0 16 16" aria-hidden="true" focusable="false">
        {children}
      </svg>
    </span>
  )
}

const phone = () => typeof window !== 'undefined' && window.matchMedia('(max-width: 639px)').matches

export function WiringSection({ overview }: { overview: Overview }) {
  const id = useId()
  const [open, setOpen] = useState(false)
  const [view, setView] = useState<'diagram' | 'list'>(() => (phone() ? 'list' : 'diagram'))
  const [active, setActive] = useState<string | null>(null)
  const { parts, wiring } = overview
  if (!wiring.length) return null
  const labelOf = (lineId: string) => parts.find(part => part.line_id === lineId)?.label ?? lineId
  const toCheck = wiring.filter(wireFlagged).length
  const describe = (wire: WireConnection) =>
    `${labelOf(wire.from.line_id)} ${wire.from.pin} to ${labelOf(wire.to.line_id)} ${wire.to.pin}` +
    (wire.label ? ` (${wire.label})` : '')

  // List view: one group per part; a wire sits under its non-controller end (or its first end).
  const controller = pickController(parts, wiring)
  const groups = new Map<string, { wire: WireConnection; pin: string; otherId: string; otherPin: string }[]>()
  for (const wire of wiring) {
    const fromFirst = wire.from.line_id !== controller?.line_id || wire.to.line_id === controller?.line_id
    const [here, there] = fromFirst ? [wire.from, wire.to] : [wire.to, wire.from]
    groups.set(here.line_id, [
      ...(groups.get(here.line_id) ?? []),
      { wire, pin: here.pin, otherId: there.line_id, otherPin: there.pin },
    ])
  }
  const order = parts.map(part => part.line_id)
  const grouped = [...groups.entries()].sort(
    ([a], [b]) => (order.indexOf(a) + 1 || 999) - (order.indexOf(b) + 1 || 999),
  )

  return (
    <section className={`po-wiring${open ? ' is-open' : ''}`} aria-labelledby={`${id}-title`}>
      <h2 className="po-wiring-heading" id={`${id}-title`}>
        <button
          type="button"
          className="po-wiring-toggle"
          aria-expanded={open}
          aria-controls={`${id}-panel`}
          onClick={() => setOpen(value => !value)}
        >
          <span className="po-wiring-title">How it’s wired</span>
          <span className="po-wiring-count">
            {wiring.length} {wiring.length === 1 ? 'connection' : 'connections'}
          </span>
          {toCheck > 0 && <span className="po-wiring-check">{toCheck} to check</span>}
          <span className="po-wiring-chevron" aria-hidden="true" />
        </button>
      </h2>
      <div className="po-wiring-panel" id={`${id}-panel`} hidden={!open}>
        <div className="po-wiring-bar">
          <div className="po-segmented" role="group" aria-label="Show wiring as">
            {(['diagram', 'list'] as const).map(option => (
              <button
                key={option}
                type="button"
                aria-pressed={view === option}
                className={view === option ? 'is-selected' : ''}
                onClick={() => setView(option)}
              >
                {option === 'diagram' ? 'Diagram' : 'List'}
              </button>
            ))}
          </div>
          <ul className="po-legend" aria-label="Wire colours">
            {legend.map(([name, color]) => (
              <li key={name}>
                <span className="po-legend-swatch" style={{ '--wire': color } as CSSProperties} aria-hidden="true" />
                {name}
              </li>
            ))}
          </ul>
        </div>
        {open && view === 'diagram' && (
          <div className="po-wiring-frame">
            <WiringDiagram parts={parts} wiring={wiring} active={active} onActive={setActive} label={describe} />
          </div>
        )}
        {open && view === 'list' && (
          <div className="po-wire-list">
            {grouped.map(([lineId, rows]) => (
              <div key={lineId} className="po-wire-group">
                <h3>{labelOf(lineId)}</h3>
                <ul onMouseLeave={() => setActive(null)}>
                  {rows.map(({ wire, pin, otherId, otherPin }) => {
                    const source = sourceInfo[wire.source] ?? sourceInfo.ai_inferred
                    const verdict = verdictInfo[wire.verdict] ?? verdictInfo.unverified
                    const sourceTitle = source.title + (wire.evidence ? ` · ${wire.evidence}` : '')
                    const verdictTitle =
                      verdict.title + (wire.verdict === 'unverified' && wire.reason ? `: ${wire.reason}` : '')
                    return (
                      <li
                        key={wire.id}
                        className={`po-wire-row${active === wire.id ? ' is-active' : ''}${wireFlagged(wire) ? ' is-flagged' : ''}`}
                        title={wire.label ?? undefined}
                        onMouseEnter={() => setActive(wire.id)}
                      >
                        <span
                          className={`po-swatch${wireFlagged(wire) ? ' is-dashed' : ''}`}
                          style={{ '--wire': strokeOf(wire) } as CSSProperties}
                          aria-hidden="true"
                        />
                        <span className="po-wire-ends">
                          <code>{pin}</code> <span aria-label="to">→</span> {labelOf(otherId)} · <code>{otherPin}</code>
                        </span>
                        <span className="po-wire-icons">
                          <MiniIcon title={sourceTitle} tone="source">
                            {source.icon}
                          </MiniIcon>
                          <MiniIcon title={verdictTitle} tone={wire.verdict}>
                            {verdict.icon}
                          </MiniIcon>
                        </span>
                        {wire.verdict === 'disputed' && wire.reason && <p className="po-wire-problem">{wire.reason}</p>}
                        {wire.problems.map((problem, index) => (
                          <p key={index} className="po-wire-problem">
                            {problem}
                          </p>
                        ))}
                      </li>
                    )
                  })}
                </ul>
              </div>
            ))}
          </div>
        )}
        <div className="po-wiring-caption">
          <p>AI-drawn from the project code — check the labels printed on your board before wiring.</p>
          {overview.notes.length > 0 && (
            <ul>
              {overview.notes.map((note, index) => (
                <li key={index}>{note}</li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </section>
  )
}
