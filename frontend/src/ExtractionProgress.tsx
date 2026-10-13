import { useEffect, useState } from 'react'
import type { ExtractionStep } from './api'
import { Spinner } from './Skeleton'

// Live steps while a job's sources are read (backend jobs.py `extraction_progress`). Gemini reports no progress
// inside one call, so the bar is an estimate from how long each step usually takes (live timings: a video about
// 45 s, a linked page about 25 s, the list check about 10 s, part details about 4 s). It never reaches 100% until
// the steps say so.
const TYPICAL_S = { description: 2, video: 45, page: 25, reconcile: 10, spec_fill: 4 }

function typical(step: ExtractionStep) {
  if (step.key === 'description') return TYPICAL_S.description
  if (step.key === 'reconcile') return TYPICAL_S.reconcile
  if (step.key === 'spec_fill') return TYPICAL_S.spec_fill
  return step.label === 'Reading the video' ? TYPICAL_S.video : TYPICAL_S.page
}

function seconds(from?: string | null, to?: string | null, now = Date.now()) {
  if (!from) return 0
  return Math.max(0, ((to ? Date.parse(to) : now) - Date.parse(from)) / 1000)
}

// How far one step is: finished steps count fully; a running one eases towards 95% of its usual time.
function fraction(step: ExtractionStep, now: number) {
  if (step.status === 'done' || step.status === 'failed' || step.status === 'skipped') return 1
  if (step.status !== 'running') return 0
  return Math.min(0.95, 1 - Math.exp((-2 * seconds(step.started_at, null, now)) / typical(step)))
}

// Description, then the sources (read in parallel, so they count as one phase as long as the slowest), then the
// list check and part details.
function phases(steps: ExtractionStep[]) {
  const sources = steps.filter(step => step.key.startsWith('source:'))
  const one = (key: string) => steps.filter(step => step.key === key)
  return [one('description'), sources, one('reconcile'), one('spec_fill')].filter(group => group.length)
}

function estimatePercent(steps: ExtractionStep[], now = Date.now()) {
  const groups = phases(steps)
  if (!groups.length) return 2
  let total = 0
  let done = 0
  for (const group of groups) {
    const weight = Math.max(...group.map(typical))
    total += weight
    // A parallel phase ends when its slowest step does.
    done += weight * Math.min(...group.map(step => fraction(step, now)))
  }
  // Sources not added yet (description links) would add work: keep a little room until the last phase runs.
  return Math.max(2, Math.min(99, Math.round((done / total) * 100)))
}

function ordered(steps: ExtractionStep[]) {
  return phases(steps).flat()
}

const mark: Record<ExtractionStep['status'], string> = {
  pending: '',
  running: '',
  done: '✓',
  failed: '×',
  skipped: '–',
}

export function ExtractionProgress({ steps }: { steps: ExtractionStep[] }) {
  const [now, setNow] = useState(() => Date.now())
  const live = steps.some(step => step.status === 'running' || step.status === 'pending') || !steps.length
  useEffect(() => {
    if (!live) return
    const timer = window.setInterval(() => setNow(Date.now()), 500)
    return () => window.clearInterval(timer)
  }, [live])
  const percent = estimatePercent(steps, now)
  return (
    <div className="pp-extract">
      <div className="pp-progress">
        <div
          className="pp-progress-bar"
          role="progressbar"
          aria-label="Reading the project (estimated)"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={percent}
        >
          <span style={{ width: `${percent}%` }} />
        </div>
        <span title="Estimated from how long each step usually takes">About {percent}%</span>
      </div>
      {steps.length > 0 && (
        <ol className="pp-extract-steps">
          {ordered(steps).map(step => {
            const elapsed = Math.round(seconds(step.started_at, step.finished_at, now))
            return (
              <li key={step.key} className={`is-${step.status}`}>
                <span className="pp-extract-mark" aria-hidden="true">
                  {step.status === 'running' ? (
                    <Spinner />
                  ) : step.status === 'pending' ? (
                    <i className="pp-extract-dot" />
                  ) : (
                    mark[step.status]
                  )}
                </span>
                <span className="pp-extract-label">
                  {step.label}
                  {step.detail && <small>{step.detail}</small>}
                </span>
                <span className="pp-extract-time">
                  {step.started_at && (step.status === 'running' || step.status === 'done') ? `${elapsed} s` : ''}
                </span>
              </li>
            )
          })}
        </ol>
      )}
    </div>
  )
}
