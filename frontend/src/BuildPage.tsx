import { Suspense, lazy, useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
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
import { madeToOrder } from './fabrication'
import { safeHref } from './safeUrl'
import { FirstService } from './MadeToOrder'
import { loadProjectOverview } from './prefetch'
import { wireFlagged } from './partGeometry'
import { NeedsList, safetyNeeds } from './ReportSummary'
import { sellerName } from './SellerIdentity'
import { Spinner } from './Skeleton'
import { partName, qtyLabel } from './partName'

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

// The YouTube video id for the thumbnail: the job's video metadata, else the id in the source URL.
function videoIdOf(job: Job, url: URL | null): string | null {
  const id =
    job.video_meta?.video_id ||
    (url?.hostname === 'youtu.be' ? url.pathname.slice(1) : url?.searchParams.get('v')) ||
    url?.pathname.match(/^\/(?:shorts|embed|live)\/([\w-]+)/)?.[1]
  return id && /^[\w-]{6,20}$/.test(id) ? id : null
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
  const videoId = videoIdOf(job, video)
  const facts = [
    ['Power', project?.power],
    ['Controller', project?.controller],
  ].filter((entry): entry is [string, string] => !!entry[1])
  return (
    <section className="pb-card pb-summary" aria-labelledby="pb-summary-title">
      <div className="pb-summary-main">
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
        {video && !videoId && (
          <a className="pb-video-link" href={video.toString()} target="_blank" rel="noopener noreferrer">
            Watch the source video <span aria-hidden="true">↗</span>
            <span className="visually-hidden"> (opens in a new tab)</span>
          </a>
        )}
      </div>
      {video && videoId && (
        <a className="pb-video" href={video.toString()} target="_blank" rel="noopener noreferrer">
          <img src={`https://i.ytimg.com/vi/${videoId}/hqdefault.jpg`} alt="" loading="lazy" />
          <span className="pb-video-play" aria-hidden="true">
            ▶
          </span>
          <span className="pb-video-label">
            Source video<span className="visually-hidden"> (opens in a new tab)</span>
          </span>
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
  highlight,
}: {
  job: Job
  token: string
  onJob: (job: Job) => void
  onShowPlan: () => void
  isReceived: (id: string) => boolean
  setOverrides: (update: (current: Record<string, boolean>) => Record<string, boolean>) => void
  highlight: string[]
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
    <section className="pb-card pb-section pb-checklist" aria-labelledby="pb-parts-title">
      <h2 id="pb-parts-title">
        Parts checklist <span>{job.items.length}</span>
      </h2>
      <ul className="pb-parts">
        {job.items.map(item => {
          const id = item.line_id
          const had = item.user_has_it
          const checked = had || isReceived(id)
          const seller = sellerOf.get(id)
          const reportLine = reportLines.get(id)
          const made = madeToOrder(reportLine) ? reportLine.fabrication : null
          const name = partName(item, reportLines.get(id)?.buyable_spec ?? item.buyable_spec)
          return (
            <li
              key={id}
              className={`pb-part${checked ? ' is-checked' : ''}${highlight.includes(id) ? ' is-in-step' : ''}`}
            >
              <label className="pp-review-have pb-check">
                <input
                  id={`pb-part-${id}`}
                  type="checkbox"
                  checked={checked}
                  disabled={had || !!saving[id]}
                  aria-describedby={`pb-part-${id}-note`}
                  onChange={event => void toggle(id, event.target.checked)}
                />
                <span className="pb-part-name">
                  {name}
                  {highlight.includes(id) && <span className="pb-part-tag">This step</span>}
                </span>
              </label>
              <span className="pb-part-qty">{qtyLabel(item)}</span>
              <span id={`pb-part-${id}-note`} className="pb-part-note">
                {had ? (
                  'You had it'
                ) : seller ? (
                  `From ${seller}`
                ) : made ? (
                  <>
                    <span className="pb-part-made">Made to order</span>
                    {made.services?.length ? (
                      <>
                        {' at '}
                        <FirstService plan={made} />
                      </>
                    ) : null}
                    {!checked && <> · upload {made.upload}</>}
                  </>
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

function Step({
  step,
  number,
  job,
  names,
  behind = false,
}: {
  step: BuildStep
  number: number
  job: Job
  names: Map<string, string>
  // One-at-a-time view: a step stacked under the current one, kept for its height but hidden and unreachable.
  behind?: boolean
}) {
  const parts = step.line_ids.filter(id => names.has(id))
  const link = step.timestamp ? momentUrl(job.input.url, step.timestamp) : null
  return (
    <li className={`pb-step${behind ? ' is-behind' : ''}`} inert={behind} aria-hidden={behind || undefined}>
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

// The step a viewer was on, kept in this browser only so a returning maker picks up where they left off.
const stepKey = (jobId: string) => `bharat-sourcer:build-step:${jobId}`
function savedStep(jobId: string): number {
  try {
    return Math.max(0, Number(localStorage.getItem(stepKey(jobId))) || 0)
  } catch {
    return 0
  }
}
function saveStep(jobId: string, index: number) {
  try {
    localStorage.setItem(stepKey(jobId), String(index))
  } catch {
    // Storage blocked: the step simply starts at 1 next time.
  }
}

function BuildSteps({ job, token, onStepParts }: { job: Job; token: string; onStepParts: (ids: string[]) => void }) {
  const { guide, busy, error, request } = useBuildGuide(job, token)
  const names = new Map(job.items.map(item => [item.line_id, partName(item)]))
  const pending = guide?.status === 'pending' || (busy && !guide)
  const steps = (guide?.status === 'ready' || guide?.status === 'stale') && guide ? guide.steps : []
  const offer = !pending && (!guide || guide.status === 'failed' || guide.status === 'stale')
  const [all, setAll] = useState(false)
  const [picked, setPicked] = useState(() => savedStep(job.job_id))
  const current = Math.min(picked, Math.max(steps.length - 1, 0))
  const step = steps[current]
  const focusParts = !all && step ? step.line_ids.join(' ') : ''
  useEffect(() => {
    onStepParts(focusParts ? focusParts.split(' ') : [])
  }, [focusParts, onStepParts])
  function go(index: number) {
    setPicked(index)
    saveStep(job.job_id, index)
  }
  return (
    <div className="pb-steps-tab">
      <div aria-live="polite">
        {pending && (
          <p className="pb-pending">
            <Spinner />
            Writing your build steps… this takes about half a minute
          </p>
        )}
      </div>
      {offer && (
        <div className="pb-offer">
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
      {step && (
        <>
          <div className="pb-steps-bar">
            <p className="pb-steps-count" aria-live="polite">
              {all ? plural(steps.length, 'step') : `Step ${current + 1} of ${steps.length}`}
            </p>
            <div className="po-segmented" role="group" aria-label="Show steps">
              {[false, true].map(option => (
                <button
                  key={String(option)}
                  type="button"
                  aria-pressed={all === option}
                  className={all === option ? 'is-selected' : ''}
                  onClick={() => setAll(option)}
                >
                  {option ? 'All' : 'One at a time'}
                </button>
              ))}
            </div>
          </div>
          {all ? (
            <ol className="pb-steps">
              {steps.map((entry, index) => (
                <Step key={index} step={entry} number={index + 1} job={job} names={names} />
              ))}
            </ol>
          ) : (
            <>
              <ol className="pb-pips" aria-label="Steps">
                {steps.map((entry, index) => (
                  <li key={index}>
                    <button
                      type="button"
                      className={`pb-pip${index < current ? ' is-past' : ''}${index === current ? ' is-current' : ''}`}
                      aria-current={index === current ? 'step' : undefined}
                      aria-label={`Step ${index + 1}: ${entry.title}`}
                      title={entry.title}
                      onClick={() => go(index)}
                    />
                  </li>
                ))}
              </ol>
              {/* Every step sits in the same grid cell, so the card keeps the tallest step's height. */}
              <ol className="pb-steps is-single">
                {steps.map((entry, index) => (
                  <Step
                    key={index}
                    step={entry}
                    number={index + 1}
                    job={job}
                    names={names}
                    behind={index !== current}
                  />
                ))}
              </ol>
              <div className="pb-step-nav">
                <button type="button" className="pb-step-prev" disabled={current === 0} onClick={() => go(current - 1)}>
                  <span aria-hidden="true">←</span> Previous
                </button>
                {current < steps.length - 1 ? (
                  <button type="button" className="nav-cta" onClick={() => go(current + 1)}>
                    Next step <span aria-hidden="true">→</span>
                  </button>
                ) : (
                  <p className="pb-step-last">Last step. Check the Safety tab before you power it.</p>
                )}
              </div>
            </>
          )}
          {guide?.status === 'ready' && guide.message && <p className="pb-note">{guide.message}</p>}
        </>
      )}
    </div>
  )
}

// The wiring drawing over the whole window, for a diagram too wide for the tab.
function FullWiring({ overview, close }: { overview: NonNullable<Job['overview']>; close: () => void }) {
  const [element, setElement] = useState<HTMLDialogElement | null>(null)
  useEffect(() => {
    if (element && !element.open) element.showModal()
    return () => element?.close()
  }, [element])
  return (
    <dialog
      ref={setElement}
      className="pb-wiring-dialog"
      aria-labelledby="pb-wiring-dialog-title"
      onCancel={event => {
        event.preventDefault()
        close()
      }}
    >
      <div className="pb-wiring-dialog-head">
        <h2 id="pb-wiring-dialog-title">How it’s wired</h2>
        <button type="button" className="dialog-close" onClick={close} aria-label="Close the wiring drawing">
          ×
        </button>
      </div>
      <WiringSection overview={overview} embedded />
    </dialog>
  )
}

function Wiring({ job, onShowReview }: { job: Job; onShowReview: () => void }) {
  const overview = job.overview
  const [full, setFull] = useState(false)
  if (overview && overview.status !== 'failed' && overview.status !== 'pending' && overview.wiring.length > 0)
    return (
      <Suspense fallback={<Spinner />}>
        <WiringSection overview={overview} embedded />
        <button type="button" className="pb-wiring-full" onClick={() => setFull(true)}>
          <span aria-hidden="true">⤢</span> Open full size
        </button>
        {full && <FullWiring overview={overview} close={() => setFull(false)} />}
      </Suspense>
    )
  return (
    <p className="pb-muted">
      {overview?.status === 'pending' ? 'The wiring drawing is still being made.' : 'No wiring drawing yet.'}{' '}
      <button type="button" className="pp-text-button" onClick={onShowReview}>
        Go to Review the parts
      </button>
    </p>
  )
}

function Safety({ job }: { job: Job }) {
  const needs = safetyNeeds(job, id => {
    const box = document.getElementById(`pb-part-${id}`)
    box?.scrollIntoView({ block: 'center' })
    box?.focus({ preventScroll: true })
  })
  const assumptions = job.project?.assumptions ?? []
  return (
    <div className="pb-safety">
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
    </div>
  )
}

// The project's code: the GitHub sources that were read and the code changes drafted for swapped parts.
function codeOf(job: Job) {
  const repos = (job.source_reports ?? []).filter(source => source.kind === 'github' && source.status === 'read')
  const patches = (reportOf(job)?.lines ?? []).filter(line => line.code_patch?.status === 'ready')
  return { repos, patches }
}

// "github.com/owner/repo/tree/main/src" to its owner and repository.
function repoName(url: string) {
  try {
    const [owner, repo] = new URL(url).pathname.split('/').filter(Boolean)
    return owner && repo ? { owner, repo } : null
  } catch {
    return null
  }
}

const checkLabel = { compiles: 'Compiles', compile_failed: 'Did not compile', not_checked: 'Not compiled yet' }

function Code({ job, onShowPlan }: { job: Job; onShowPlan: () => void }) {
  const { repos, patches } = codeOf(job)
  return (
    <div className="pb-code">
      {repos.map(repo => {
        const name = repoName(repo.url)
        return (
          <a key={repo.url} className="pb-repo" href={safeHref(repo.url)} target="_blank" rel="noopener noreferrer">
            <span className="pb-repo-icon" aria-hidden="true">
              {'</>'}
            </span>
            <span className="pb-repo-text">
              <strong>{name ? `${name.owner} / ${name.repo}` : repo.url}</strong>
              <span>
                GitHub
                {repo.code_item_count ? ` · ${plural(repo.code_item_count, 'part')} found in the code` : ''}
              </span>
            </span>
            <span className="pb-repo-open">
              Open <span aria-hidden="true">↗</span>
              <span className="visually-hidden"> (opens in a new tab)</span>
            </span>
          </a>
        )
      })}
      {patches.length > 0 && (
        <div className="pb-patches">
          <h3>Code changes for swapped parts</h3>
          <ul>
            {patches.map(line => {
              const patch = line.code_patch!
              return (
                <li key={line.item.line_id}>
                  <span className="pb-patch-name">
                    {partName(line.item, line.buyable_spec ?? line.item.buyable_spec)}
                  </span>
                  <span className="pb-patch-meta">
                    {plural(patch.files.length, 'file')} · {checkLabel[patch.check]}
                    {patch.accepted ? ' · Accepted' : ''}
                  </span>
                </li>
              )
            })}
          </ul>
          <button type="button" className="pp-text-button" onClick={onShowPlan}>
            Review the changes in the order plan
          </button>
        </div>
      )}
    </div>
  )
}

const plural = (count: number, one: string) => `${count} ${count === 1 ? one : `${one}s`}`

type TabId = 'steps' | 'wiring' | 'code' | 'safety'

// Beside the checklist: the build steps, wiring, code and safety notes as tabs, each shown in place.
function BuildGuidePanel({
  job,
  token,
  onShowPlan,
  onShowReview,
  onStepParts,
}: {
  job: Job
  token: string
  onShowPlan: () => void
  onShowReview: () => void
  onStepParts: (ids: string[]) => void
}) {
  const overview = job.overview
  const wiring = overview && overview.status !== 'failed' && overview.status !== 'pending' ? overview.wiring : []
  const toCheck = wiring.filter(wireFlagged).length
  const { repos, patches } = codeOf(job)
  const safety = (job.safety_flags?.length ?? 0) + (job.project?.assumptions?.length ?? 0)
  const guide = job.build_guide
  const stepCount = guide && (guide.status === 'ready' || guide.status === 'stale') ? guide.steps.length : 0
  const tabs: { id: TabId; label: string; badge?: string; warn?: boolean }[] = [
    { id: 'steps', label: 'Steps', badge: stepCount ? String(stepCount) : undefined },
    { id: 'wiring', label: 'Wiring', badge: toCheck ? `${toCheck} to check` : undefined, warn: toCheck > 0 },
    ...(repos.length || patches.length ? [{ id: 'code' as const, label: 'Code' }] : []),
    ...(safety ? [{ id: 'safety' as const, label: 'Safety', badge: String(safety), warn: true }] : []),
  ]
  const [chosen, setChosen] = useState<TabId>('steps')
  const tab = tabs.some(entry => entry.id === chosen) ? chosen : 'steps'
  const refs = useRef<Record<string, HTMLButtonElement | null>>({})

  // Arrow keys move between tabs (WAI-ARIA tabs pattern).
  function onKey(event: React.KeyboardEvent, index: number) {
    const moves: Record<string, number> = {
      ArrowRight: index + 1,
      ArrowLeft: index - 1,
      Home: 0,
      End: tabs.length - 1,
    }
    if (!(event.key in moves)) return
    event.preventDefault()
    const next = tabs[(moves[event.key] + tabs.length) % tabs.length]
    setChosen(next.id)
    refs.current[next.id]?.focus()
  }

  // Leaving the Steps tab clears the step's highlight in the checklist.
  useEffect(() => {
    if (tab !== 'steps') onStepParts([])
  }, [tab, onStepParts])

  return (
    <section className="pb-card pb-guide" aria-label="Build guide">
      <div className="pb-tabs" role="tablist" aria-label="Build guide">
        {tabs.map((entry, index) => (
          <button
            key={entry.id}
            ref={element => {
              refs.current[entry.id] = element
            }}
            type="button"
            role="tab"
            id={`pb-tab-${entry.id}`}
            aria-selected={tab === entry.id}
            aria-controls={`pb-panel-${entry.id}`}
            tabIndex={tab === entry.id ? 0 : -1}
            className={`pb-tab${tab === entry.id ? ' is-selected' : ''}`}
            onClick={() => setChosen(entry.id)}
            onKeyDown={event => onKey(event, index)}
          >
            {entry.label}
            {entry.badge && <span className={`pb-tab-badge${entry.warn ? ' is-warn' : ''}`}>{entry.badge}</span>}
          </button>
        ))}
      </div>
      <div
        className="pb-tab-panel"
        role="tabpanel"
        id={`pb-panel-${tab}`}
        aria-labelledby={`pb-tab-${tab}`}
        tabIndex={0}
      >
        {tab === 'steps' && <BuildSteps job={job} token={token} onStepParts={onStepParts} />}
        {tab === 'wiring' && <Wiring job={job} onShowReview={onShowReview} />}
        {tab === 'code' && <Code job={job} onShowPlan={onShowPlan} />}
        {tab === 'safety' && <Safety job={job} />}
      </div>
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
  // The parts the open build step uses, highlighted in the checklist.
  const [stepParts, setStepParts] = useState<string[]>([])
  const onStepParts = useCallback(
    (ids: string[]) => setStepParts(current => (current.join(' ') === ids.join(' ') ? current : ids)),
    [],
  )
  return (
    <section className="job-panel pp-stage pb-page">
      <Summary job={job} inHand={inHand} />
      <div className="pb-grid">
        <PartsChecklist
          job={job}
          token={token}
          onJob={onJob}
          onShowPlan={onShowPlan}
          isReceived={isReceived}
          setOverrides={setOverrides}
          highlight={stepParts}
        />
        <BuildGuidePanel
          job={job}
          token={token}
          onShowPlan={onShowPlan}
          onShowReview={onShowReview}
          onStepParts={onStepParts}
        />
      </div>
    </section>
  )
}
