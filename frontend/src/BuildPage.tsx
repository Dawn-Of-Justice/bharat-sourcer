import { Suspense, lazy, useEffect, useLayoutEffect, useRef, useState } from 'react'
import {
  getBuildGuide,
  reportOf,
  requestBuildGuide,
  setBuildProgress,
  type BuildGuide,
  type BuildStep,
  offersOf,
  type Job,
  type OrderPlanSeller,
  type ReportLine,
} from './api'
import { loadProjectOverview } from './prefetch'
import { NeedsList, safetyNeeds } from './ReportSummary'
import { sellerName } from './SellerIdentity'
import { Spinner } from './Skeleton'
import { partName } from './partName'

// The "Build it" step for a finished project (docs/contracts/build-guide.md): the parts checklist, AI-written build
// steps, the wiring drawing and the safety notes. The steps are AI-inferred and never verified against the build.

const WiringSection = lazy(() => loadProjectOverview().then(module => ({ default: module.WiringSection })))

const youtubeHosts = ['youtube.com', 'www.youtube.com', 'm.youtube.com', 'youtu.be']
function youtubeUrl(value: string): URL | null {
  try {
    const url = new URL(value)
    return url.protocol === 'https:' && youtubeHosts.includes(url.hostname) ? url : null
  } catch {
    return null
  }
}

// "MM:SS" or "H:MM:SS" to seconds; null when the text is not a timestamp.
function seconds(timestamp: string): number | null {
  if (!/^\d{1,2}(:\d{2}){1,2}$/.test(timestamp)) return null
  return timestamp.split(':').reduce((total, part) => total * 60 + Number(part), 0)
}

// The source video at one moment, or null when the source is not a YouTube video.
function momentUrl(source: string, timestamp: string): string | null {
  const url = youtubeUrl(source)
  const at = seconds(timestamp)
  if (!url || at === null) return null
  url.searchParams.set('t', String(at))
  return url.toString()
}

// Changes whenever the backend's guide changes; a local reply is shown only until then.
const guideKey = (guide: BuildGuide | null | undefined) =>
  guide ? [guide.status, guide.generated_at, guide.items_hash, guide.steps.length].join('|') : 'none'

// Jobs whose guide was requested automatically on this page load: the first view asks once, never again.
const autoRequested = new Set<string>()

function useBuildGuide(job: Job, token: string) {
  const key = guideKey(job.build_guide)
  const [local, setLocal] = useState<{ guide: BuildGuide; base: string } | null>(null)
  const guide = local && local.base === key ? local.guide : (job.build_guide ?? null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const pending = guide?.status === 'pending'

  async function request() {
    setBusy(true)
    setError('')
    try {
      setLocal({ guide: await requestBuildGuide(job.job_id, token), base: key })
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not start writing the build steps.')
    } finally {
      setBusy(false)
    }
  }

  // The job stream carries the guide; polling as well keeps the page moving if the stream is slow.
  useEffect(() => {
    if (!pending) return
    let alive = true
    const timer = setInterval(() => {
      getBuildGuide(job.job_id, token).then(
        next => {
          if (alive) setLocal({ guide: next, base: key })
        },
        () => undefined,
      )
    }, 3000)
    return () => {
      alive = false
      clearInterval(timer)
    }
  }, [pending, job.job_id, token, key])

  // A project without a guide asks for one on the first view, so a returning maker just sees the steps appear.
  // A failed guide is never retried automatically.
  const [auto] = useState(() => !job.build_guide && !autoRequested.has(job.job_id))
  const [autoDone, setAutoDone] = useState(false)
  useEffect(() => {
    if (!auto || autoRequested.has(job.job_id)) return
    autoRequested.add(job.job_id)
    requestBuildGuide(job.job_id, token)
      .then(
        next => setLocal({ guide: next, base: 'none' }),
        (cause: unknown) =>
          setError(cause instanceof Error ? cause.message : 'Could not start writing the build steps.'),
      )
      .finally(() => setAutoDone(true))
  }, [auto, job.job_id, token])

  return { guide, busy: busy || (auto && !autoDone), error, request }
}

function Summary({ job, inHand }: { job: Job; inHand: number }) {
  const project = job.project
  const summary = project?.summary ?? ''
  const summaryRef = useRef<HTMLParagraphElement>(null)
  const [expanded, setExpanded] = useState(false)
  const [overflows, setOverflows] = useState(false)
  useLayoutEffect(() => {
    const element = summaryRef.current
    if (!element || expanded) return
    const measure = () => setOverflows(element.scrollHeight > element.clientHeight + 1)
    measure()
    const observer = new ResizeObserver(measure)
    observer.observe(element)
    return () => observer.disconnect()
  }, [summary, expanded])
  const total = job.items.length
  const video = youtubeUrl(job.input.url)
  const facts = [
    ['Power', project?.power],
    ['Controller', project?.controller],
  ].filter((entry): entry is [string, string] => !!entry[1])
  return (
    <section className="pb-card pb-summary" aria-labelledby="pb-summary-title">
      <h2 id="pb-summary-title">Your build</h2>
      {summary && (
        <div className="pb-summary-text">
          <p ref={summaryRef} id="pb-summary-how" className={`pb-summary-how${expanded ? '' : ' is-clamped'}`}>
            {summary}
          </p>
          {(overflows || expanded) && (
            <button
              type="button"
              className="pp-text-button"
              aria-expanded={expanded}
              aria-controls="pb-summary-how"
              onClick={() => setExpanded(open => !open)}
            >
              {expanded ? 'Show less' : 'Read more'}
            </button>
          )}
        </div>
      )}
      <ul className="pb-chips" aria-label="Build facts">
        <li className={`pb-chip${total > 0 && inHand === total ? ' is-done' : ''}`}>
          {inHand} of {total} parts in hand
        </li>
        {facts.map(([label, value]) => (
          <li key={label} className="pb-chip">
            <span>{label}:</span> {value}
          </li>
        ))}
      </ul>
      {video && (
        <a className="pb-video-link" href={video.toString()} target="_blank" rel="noopener noreferrer">
          Watch the source video <span aria-hidden="true">↗</span>
          <span className="visually-hidden"> (opens in a new tab)</span>
        </a>
      )}
    </section>
  )
}

// The shop's own name unless its offer is a marketplace listing, as the order plan shows it.
function sellerTitle(seller: OrderPlanSeller, lines: Map<string, ReportLine>) {
  const offer = seller.lines
    ?.map(plan => {
      const line = lines.get(plan.line_id)
      return line && offersOf(line).find(entry => entry.url === plan.offer_url)
    })
    .find(Boolean)
  return offer && offer.seller_kind !== 'marketplace' ? sellerName(offer) : seller.seller
}

const without = <T,>(record: Record<string, T>, id: string) => {
  const next = { ...record }
  delete next[id]
  return next
}

function PartsChecklist({
  job,
  token,
  onJob,
  onShowPlan,
  isReceived,
  setOverrides,
}: {
  job: Job
  token: string
  onJob: (job: Job) => void
  onShowPlan: () => void
  isReceived: (id: string) => boolean
  setOverrides: (update: (current: Record<string, boolean>) => Record<string, boolean>) => void
}) {
  // The rows being saved and one error per row; the page keeps the unconfirmed ticks (setOverrides).
  const [saving, setSaving] = useState<Record<string, boolean>>({})
  const [errors, setErrors] = useState<Record<string, string>>({})

  const report = reportOf(job)
  const reportLines = new Map<string, ReportLine>((report?.lines ?? []).map(line => [line.item.line_id, line]))
  const sellerOf = new Map<string, string>()
  for (const seller of report?.order_plan?.sellers ?? [])
    for (const line of seller.lines ?? []) sellerOf.set(line.line_id, sellerTitle(seller, reportLines))

  async function toggle(id: string, value: boolean) {
    setOverrides(current => ({ ...current, [id]: value }))
    setSaving(current => ({ ...current, [id]: true }))
    setErrors(current => without(current, id))
    try {
      onJob(await setBuildProgress(job.job_id, token, id, value))
    } catch (cause) {
      setErrors(current => ({
        ...current,
        [id]: cause instanceof Error ? cause.message : 'Could not save this part. Try again.',
      }))
    } finally {
      setOverrides(current => without(current, id))
      setSaving(current => without(current, id))
    }
  }

  return (
    <section className="pb-section" aria-labelledby="pb-parts-title">
      <h2 id="pb-parts-title">
        Parts <span>{job.items.length}</span>
      </h2>
      <ul className="pb-parts">
        {job.items.map(item => {
          const id = item.line_id
          const had = item.user_has_it
          const checked = had || isReceived(id)
          const seller = sellerOf.get(id)
          const name = partName(item, reportLines.get(id)?.buyable_spec ?? item.buyable_spec)
          return (
            <li key={id} className={`pb-part${checked ? ' is-checked' : ''}`}>
              <label className="pp-review-have pb-check">
                <input
                  id={`pb-part-${id}`}
                  type="checkbox"
                  checked={checked}
                  disabled={had || !!saving[id]}
                  aria-describedby={`pb-part-${id}-note`}
                  onChange={event => void toggle(id, event.target.checked)}
                />
                <span className="pb-part-name">{name}</span>
              </label>
              <span className="pb-part-qty">×{item.qty ?? '?'}</span>
              <span id={`pb-part-${id}-note`} className="pb-part-note">
                {had ? (
                  'You had it'
                ) : seller ? (
                  `From ${seller}`
                ) : checked ? null : (
                  <>
                    <span className="pb-part-warn">Not bought yet</span>{' '}
                    <button type="button" className="pp-text-button" onClick={onShowPlan}>
                      See order plan
                    </button>
                  </>
                )}
              </span>
              {errors[id] && (
                <p className="form-error pb-part-error" role="alert">
                  {errors[id]}
                </p>
              )}
            </li>
          )
        })}
      </ul>
    </section>
  )
}

function Step({ step, number, job, names }: { step: BuildStep; number: number; job: Job; names: Map<string, string> }) {
  const parts = step.line_ids.filter(id => names.has(id))
  const link = step.timestamp ? momentUrl(job.input.url, step.timestamp) : null
  return (
    <li className="pb-step">
      <span className="pb-step-number" aria-hidden="true">
        {number}
      </span>
      <div className="pb-step-body">
        <h3>{step.title}</h3>
        {step.detail && <p>{step.detail}</p>}
        {(parts.length > 0 || step.timestamp) && (
          <div className="pb-step-meta">
            {parts.length > 0 && (
              <ul className="pb-chips" aria-label="Parts used">
                {parts.map(id => (
                  <li key={id} className="pb-chip">
                    {names.get(id)}
                  </li>
                ))}
              </ul>
            )}
            {step.timestamp &&
              (link ? (
                <a
                  className="pb-step-time"
                  href={link}
                  target="_blank"
                  rel="noopener noreferrer"
                  aria-label={`Watch this step in the video at ${step.timestamp} (opens in a new tab)`}
                >
                  <span aria-hidden="true">▶</span> {step.timestamp}
                </a>
              ) : (
                <span className="pb-step-time">Video at {step.timestamp}</span>
              ))}
          </div>
        )}
        {step.caution && (
          <div className="pp-part-callout pp-part-callout-input pb-step-caution">
            <strong>Careful</strong>
            <p>{step.caution}</p>
          </div>
        )}
      </div>
    </li>
  )
}

function BuildSteps({ job, token }: { job: Job; token: string }) {
  const { guide, busy, error, request } = useBuildGuide(job, token)
  const names = new Map(job.items.map(item => [item.line_id, partName(item)]))
  const pending = guide?.status === 'pending' || (busy && !guide)
  const showSteps = (guide?.status === 'ready' || guide?.status === 'stale') && guide.steps.length > 0
  const offer = !pending && (!guide || guide.status === 'failed' || guide.status === 'stale')
  return (
    <section className="pb-section" aria-labelledby="pb-steps-title">
      <h2 id="pb-steps-title">Build steps</h2>
      <div aria-live="polite">
        {pending && (
          <p className="pb-pending">
            <Spinner />
            Writing your build steps… this takes about half a minute
          </p>
        )}
      </div>
      {offer && (
        <div className="pb-card pb-offer">
          <p>
            {guide?.message ||
              (guide?.status === 'failed'
                ? 'The build steps could not be written.'
                : 'Get step-by-step build instructions written from this project’s parts and video.')}
          </p>
          <button type="button" className="nav-cta" disabled={busy} onClick={() => void request()}>
            {busy && <Spinner />}
            {!guide ? 'Write build steps' : guide.status === 'failed' ? 'Try again' : 'Update steps'}
          </button>
        </div>
      )}
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
      {showSteps && (
        <>
          <ol className="pb-steps">
            {guide.steps.map((step, index) => (
              <Step key={index} step={step} number={index + 1} job={job} names={names} />
            ))}
          </ol>
          {guide.status === 'ready' && guide.message && <p className="pb-note">{guide.message}</p>}
        </>
      )}
    </section>
  )
}

function Wiring({ job, onShowReview }: { job: Job; onShowReview: () => void }) {
  const overview = job.overview
  if (overview && overview.status !== 'failed' && overview.status !== 'pending' && overview.wiring.length > 0)
    return (
      <Suspense fallback={null}>
        <div className="pb-wiring">
          <WiringSection overview={overview} />
        </div>
      </Suspense>
    )
  return (
    <section className="pb-section" aria-labelledby="pb-wiring-title">
      <h2 id="pb-wiring-title">How it’s wired</h2>
      <p className="pb-muted">
        {overview?.status === 'pending' ? 'The wiring drawing is still being made.' : 'No wiring drawing yet.'}{' '}
        <button type="button" className="pp-text-button" onClick={onShowReview}>
          Go to Review the parts
        </button>
      </p>
    </section>
  )
}

function BeforePower({ job }: { job: Job }) {
  const needs = safetyNeeds(job, id => {
    const box = document.getElementById(`pb-part-${id}`)
    box?.scrollIntoView({ block: 'center' })
    box?.focus({ preventScroll: true })
  })
  const assumptions = job.project?.assumptions ?? []
  if (!needs.length && !assumptions.length) return null
  return (
    <section className="pb-section" aria-labelledby="pb-power-title">
      <h2 id="pb-power-title">Before you power it</h2>
      {needs.length > 0 && <NeedsList needs={needs} showHeading={false} />}
      {assumptions.length > 0 && (
        <div className="pb-assumptions">
          <h3>Assumptions to check</h3>
          <ul>
            {assumptions.map((entry, index) => (
              <li key={index}>{entry}</li>
            ))}
          </ul>
        </div>
      )}
    </section>
  )
}

export default function BuildPage({
  job,
  token,
  onJob,
  onShowPlan,
  onShowReview,
}: {
  job: Job
  token: string
  onJob: (job: Job) => void
  onShowPlan: () => void
  onShowReview: () => void
}) {
  // Ticks shown before the server confirms them, so the count moves with the checkbox.
  const [overrides, setOverrides] = useState<Record<string, boolean>>({})
  const received = new Set(job.build_received ?? [])
  const isReceived = (id: string) => overrides[id] ?? received.has(id)
  const inHand = job.items.filter(item => item.user_has_it || isReceived(item.line_id)).length
  return (
    <section className="job-panel pp-stage pb-page">
      <Summary job={job} inHand={inHand} />
      <PartsChecklist
        job={job}
        token={token}
        onJob={onJob}
        onShowPlan={onShowPlan}
        isReceived={isReceived}
        setOverrides={setOverrides}
      />
      <BuildSteps job={job} token={token} />
      <Wiring job={job} onShowReview={onShowReview} />
      <BeforePower job={job} />
    </section>
  )
}
