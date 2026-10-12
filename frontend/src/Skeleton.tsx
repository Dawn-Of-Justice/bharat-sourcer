import type { CSSProperties, ReactNode } from 'react'

// Loading placeholders shaped like the content they stand in for. They share the overview skeleton's shimmer
// (.sk in styles.css), which stops under reduced motion. Each group is aria-busy with one spoken label.

export function Spinner() {
  return <span className="btn-spinner" aria-hidden="true" />
}

function Block({ className = '', style }: { className?: string; style?: CSSProperties }) {
  return <span className={`sk ${className}`} style={style} aria-hidden="true" />
}

function Busy({ label, className, children }: { label: string; className: string; children: ReactNode }) {
  return (
    <div className={className} aria-busy="true" role="status">
      <span className="visually-hidden">{label}</span>
      {children}
    </div>
  )
}

export function ProjectsSkeleton() {
  return (
    <Busy label="Loading your projects…" className="project-grid sk-group">
      {[0, 1, 2].map(index => (
        <div key={index} className="project-card sk-card" aria-hidden="true">
          <div className="project-card-top">
            <Block className="sk-circle" />
            <Block className="sk-pill" />
          </div>
          <Block className="sk-line sk-title" />
          <Block className="sk-line" />
          <Block className="sk-line is-short" />
          <div className="sk-meta">
            <Block className="sk-line sk-tiny" />
            <Block className="sk-line sk-tiny" />
          </div>
        </div>
      ))}
    </Busy>
  )
}

function RowSkeletons({ count, thumb = false }: { count: number; thumb?: boolean }) {
  return (
    <ul className="sk-rows" aria-hidden="true">
      {Array.from({ length: count }, (_, index) => (
        <li key={index} className="sk-row">
          {thumb && <Block className="sk-thumb" />}
          <span className="sk-row-text">
            <Block className="sk-line" style={{ width: `${70 - (index % 3) * 12}%` }} />
            <Block className="sk-line sk-tiny" />
          </span>
          <Block className="sk-pill" />
        </li>
      ))}
    </ul>
  )
}

// The job page before its first snapshot: heading, the three-step strip and the parts rows.
export function JobSkeleton({ note }: { note?: string }) {
  return (
    <Busy label="Opening your project…" className="sk-group sk-job">
      <Block className="sk-line sk-heading" />
      <Block className="sk-line is-short" />
      <div className="sk-steps" aria-hidden="true">
        {[0, 1, 2].map(index => (
          <span key={index} className="sk-step">
            <Block className="sk-circle" />
            <Block className="sk-line sk-tiny" />
          </span>
        ))}
      </div>
      <RowSkeletons count={5} />
      {note ? <p className="sk-note">{note}</p> : null}
    </Busy>
  )
}

// Results and the order plan while their view loads: the summary band, then parts rows with thumbnails.
export function ResultsSkeleton({ label = 'Loading your order plan…' }: { label?: string }) {
  return (
    <Busy label={label} className="sk-group sk-results">
      <div className="sk-band" aria-hidden="true">
        <Block className="sk-line sk-heading" />
        <Block className="sk-line is-short" />
      </div>
      <RowSkeletons count={4} thumb />
    </Busy>
  )
}
