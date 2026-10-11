import Results from './Results'
import YoutubeJourney from './YoutubeJourney'
import SharedReport from './SharedReport'
import { watchJob } from './stream'
import { useJobTitle } from './useJobTitle'
import { useAccount, Projects } from './Account'
import { useEffect, useLayoutEffect, useRef, useState, type FormEvent } from 'react'
import {
  BagIcon,
  ChecklistIcon,
  CompatibilityIcon,
  DocumentIcon,
  EvidenceIcon,
  LinkIcon,
  StoreIcon,
} from './LandingIcons'
import {
  ApiError,
  claimProject,
  pauseJob,
  resumeJob,
  confirmJob,
  createJob,
  getJob,
  updateProject,
  type BomItem,
  type BuyableSpec,
  type Job,
} from './api'
import ChatPanel from './ChatPanel'
import { ChatDrawer, SidePanel, StageSteps, stepOf } from './ProjectFrame'
import { NeedsList, safetyNeeds, type Need } from './ReportSummary'
import Requirements, { requirementPayload, validRequirements } from './Requirements'
import SpecPanel, { specPayload, validSpec } from './SpecPanel'
import { ConfidenceChip, ConflictNotes, EvidenceList, LookalikeNotes, SourcesCard } from './ReviewDetails'

function BrandMark() {
  return <img className="brand-mark" src="/brand-mark.svg" width="44" height="44" alt="" />
}

function ArrowIcon({ diagonal = false }: { diagonal?: boolean }) {
  return diagonal ? (
    <svg viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <path
        d="M4 16 16 4M6 4h10v10"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  ) : (
    <svg viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <path
        d="M3 10h13m-5-5 5 5-5 5"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

function Header({ onHome, isHome, onProjects }: { onHome: () => void; isHome: boolean; onProjects: () => void }) {
  const account = useAccount()
  return (
    <header className="site-header">
      <div className="container header-inner">
        <a
          className="brand"
          href="/"
          onClick={event => {
            event.preventDefault()
            onHome()
          }}
          aria-label="Bharat Sourcer home"
        >
          <BrandMark />
          <span className="brand-wordmark">
            <span>Bharat</span>
            <span className="brand-light">Sourcer</span>
          </span>
        </a>
        {isHome ? (
          <nav className="header-nav" aria-label="Main navigation">
            <a href="#how-it-works">How it works</a>
            <a href="#why-it-matters">Why it matters</a>
          </nav>
        ) : null}
        <div className="header-account">
          <button className="nav-cta" onClick={onProjects}>
            My projects
          </button>
          <button className="account-link" onClick={account.open}>
            {account.identity && account.identity !== 'legacy'
              ? account.identity.kind === 'guest'
                ? 'Guest account'
                : 'Account'
              : 'Sign in'}
          </button>
        </div>
      </div>
    </header>
  )
}

type LinkSource = 'youtube' | 'article' | 'github'
type SourceType = LinkSource | 'document'

function HeroIllustration({ source }: { source: SourceType }) {
  return <YoutubeJourney key={source} source={source === 'github' ? 'article' : source} />
}
const sourceOptions: { id: SourceType; label: string; symbol: string }[] = [
  { id: 'youtube', label: 'YouTube', symbol: '▶' },
  { id: 'article', label: 'Project links', symbol: '▤' },
  { id: 'document', label: 'Document', symbol: '▤' },
]

const sourceFields: Record<LinkSource, { label: string; placeholder: string }> = {
  youtube: { label: 'Paste a YouTube project link', placeholder: 'https://www.youtube.com/watch?v=...' },
  article: {
    label: 'Paste an article, maker blog or GitHub project link',
    placeholder: 'https://learn.adafruit.com/your-guide',
  },
  github: { label: 'Paste a GitHub repository link', placeholder: 'https://github.com/creator/project' },
}

const bareHost = (url: URL) => url.hostname.toLowerCase().replace(/^www\./, '')
function linkKind(url: URL): LinkSource | 'hackster' | null {
  const host = bareHost(url)
  if (['youtube.com', 'm.youtube.com', 'youtu.be'].includes(host)) return 'youtube'
  if (host === 'github.com') return 'github'
  if (host === 'hackster.io') return 'hackster'
  // Public personal blogs are accepted too; the backend validates and safely fetches them.
  return host.includes('.') && !url.username && !url.password ? 'article' : null
}
const hacksterMessage =
  'Hackster blocks automated reading, so its projects cannot be read yet. Try the project’s GitHub repository or video instead.'

function Landing({ onCreated }: { onCreated: (id: string) => void }) {
  const account = useAccount()
  const [source, setSource] = useState<SourceType>('youtube')
  const calloutRef = useRef<HTMLDivElement>(null)
  const tabRefs = useRef<Partial<Record<SourceType, HTMLButtonElement>>>({})
  const [arrowPosition, setArrowPosition] = useState<{ left: number; top: number } | null>(null)
  const [sourceUrls, setSourceUrls] = useState<Record<LinkSource, string>>({ youtube: '', article: '', github: '' })
  const [extras, setExtras] = useState<string[]>([])
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  useLayoutEffect(() => {
    const callout = calloutRef.current
    const tab = tabRefs.current.youtube
    if (!callout || !tab) return
    const positionArrow = () => {
      const calloutBox = callout.getBoundingClientRect()
      const tabBox = tab.getBoundingClientRect()
      setArrowPosition({
        left: tabBox.left + tabBox.width / 2 - calloutBox.left - 42,
        top: calloutBox.height - 38,
      })
    }
    positionArrow()
    const observer = new ResizeObserver(positionArrow)
    observer.observe(callout)
    observer.observe(tab)
    window.addEventListener('resize', positionArrow)
    return () => {
      observer.disconnect()
      window.removeEventListener('resize', positionArrow)
    }
  }, [])

  function chooseSource(next: SourceType) {
    setSource(next)
    setError('')
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError('')
    if (source === 'document') return
    let parsed: URL
    try {
      parsed = new URL(sourceUrls[source].trim())
      if (!['http:', 'https:'].includes(parsed.protocol)) throw new Error()
    } catch {
      setError('Enter a full project URL, starting with https://.')
      return
    }
    if (source === 'article' && !['article', 'github'].includes(linkKind(parsed) ?? '')) {
      setError(
        linkKind(parsed) === 'hackster'
          ? hacksterMessage
          : 'Use a public project page, personal blog or GitHub repository link.',
      )
      return
    }
    if (source === 'github' && linkKind(parsed) !== 'github') {
      setError('Enter a github.com repository URL.')
      return
    }
    const sources: string[] = []
    for (const [index, extra] of extras.entries()) {
      if (!extra.trim()) continue
      let url: URL
      try {
        url = new URL(extra.trim())
        if (url.protocol !== 'https:' && url.protocol !== 'http:') throw new Error()
      } catch {
        setError(`Extra source ${index + 1}: enter a full URL, starting with https://.`)
        return
      }
      const kind = linkKind(url)
      if (kind === 'hackster') {
        setError(`Extra source ${index + 1}: ${hacksterMessage}`)
        return
      }
      if (!kind) {
        setError(`Extra source ${index + 1}: use a YouTube video, GitHub repository or public project/blog page.`)
        return
      }
      sources.push(url.toString())
    }
    if ([parsed.toString(), ...sources].filter(url => linkKind(new URL(url)) === 'youtube').length > 1) {
      setError('Only one YouTube video can be read per project. Remove the extra video link.')
      return
    }
    if (!account.requireIdentity()) return
    setSubmitting(true)
    try {
      const job = await createJob(parsed.toString(), sources)
      sessionStorage.setItem(`bharat-sourcer:job:${job.job_id}`, job.job_token)
      onCreated(job.job_id)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Something went wrong. Please try again.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <main id="main">
      <section className="hero" id="start">
        <div className="hero-grid" aria-hidden="true" />
        <div className="container hero-layout">
          <div className="hero-copy">
            <div className="eyebrow">
              <span className="eyebrow-line" /> YOUR DIY PROJECT ASSISTANT
            </div>
            <h1 className="hero-headline">
              Found a project you want to build? <span>Can’t find the parts?</span>
            </h1>
            <p className="hero-description">
              Paste a YouTube, blog, or GitHub link, and we’ll help you work out what you need, explore alternatives,
              and find Indian sellers.
            </p>
            <p className="source-support">
              Ask questions, adapt the project to parts you already have, and save your plan for later.
            </p>
            <div className="input-callout" aria-hidden="true" ref={calloutRef}>
              <span>Start with your project link</span>
              <svg
                className={arrowPosition ? 'tab-arrow is-ready' : 'tab-arrow'}
                style={arrowPosition ?? undefined}
                viewBox="0 0 64 48"
                fill="none"
              >
                <defs>
                  <marker
                    id="landing-arrowhead"
                    viewBox="0 0 16 16"
                    refX="12"
                    refY="8"
                    markerWidth="16"
                    markerHeight="16"
                    markerUnits="userSpaceOnUse"
                    orient="auto"
                  >
                    <path
                      d="M3 3 L12 8 L3 13"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2.6"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </marker>
                </defs>
                <path
                  className="draw-arrow"
                  d="M8 7 C8 23 23 24 42 40"
                  markerEnd="url(#landing-arrowhead)"
                  stroke="currentColor"
                  strokeWidth="2.8"
                  strokeLinecap="round"
                  fill="none"
                />
              </svg>
            </div>
            <form className="source-form" onSubmit={submit}>
              <div className="source-options" role="group" aria-label="Choose a project source">
                {sourceOptions.map(option => (
                  <button
                    key={option.id}
                    ref={element => {
                      tabRefs.current[option.id] = element ?? undefined
                    }}
                    type="button"
                    className={`source-option ${source === option.id ? 'selected' : ''}`}
                    aria-pressed={source === option.id}
                    onClick={() => chooseSource(option.id)}
                  >
                    <span aria-hidden="true">
                      {option.id === 'article' ? (
                        <LinkIcon />
                      ) : option.id === 'document' ? (
                        <DocumentIcon />
                      ) : (
                        option.symbol
                      )}
                    </span>
                    {option.label}
                  </button>
                ))}
              </div>
              {source === 'document' ? (
                <div className="document-field">
                  <label htmlFor="document-file">Choose a project PDF or Word document</label>
                  <input
                    id="document-file"
                    type="file"
                    accept=".pdf,.doc,.docx,application/pdf,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                  />
                  <p>Document reading and uploads are planned. A selected file stays on your device for now.</p>
                </div>
              ) : (
                <>
                  <label htmlFor="source-url">{sourceFields[source].label}</label>
                  <div className="url-row">
                    <span className={`url-icon url-icon-${source}`} aria-hidden="true">
                      {source === 'youtube' ? (
                        <svg viewBox="0 0 24 24">
                          <rect x="2" y="5" width="20" height="14" rx="4" fill="currentColor" />
                          <path d="m10 9 6 3-6 3V9Z" fill="#fff" />
                        </svg>
                      ) : source === 'article' ? (
                        <LinkIcon />
                      ) : (
                        '</>'
                      )}
                    </span>
                    <input
                      id="source-url"
                      name="url"
                      type="url"
                      inputMode="url"
                      autoComplete="url"
                      placeholder={sourceFields[source].placeholder}
                      value={sourceUrls[source]}
                      onChange={event => setSourceUrls(current => ({ ...current, [source]: event.target.value }))}
                      required
                    />
                  </div>
                  {source === 'article' ? (
                    <p className="source-note">
                      Paste a public personal blog, project page or GitHub repository. We read the available text and
                      cite it in your parts list. Pages that require login or block automated access may not be
                      readable.
                    </p>
                  ) : source === 'github' ? (
                    <p className="source-note">
                      We read the repository README and its main code files. Each part cites a quote or a code line;
                      review the list before sourcing.
                    </p>
                  ) : null}
                  <div className="extra-sources">
                    {extras.map((extra, index) => (
                      <div className="extra-source-row" key={index}>
                        <label htmlFor={`extra-source-${index}`}>
                          Extra source {index + 1} <span>(optional)</span>
                        </label>
                        <div>
                          <input
                            id={`extra-source-${index}`}
                            type="url"
                            inputMode="url"
                            placeholder="https://github.com/creator/project"
                            value={extra}
                            onChange={event =>
                              setExtras(current =>
                                current.map((value, i) => (i === index ? event.target.value : value)),
                              )
                            }
                          />
                          <button
                            type="button"
                            className="remove-button"
                            aria-label={`Remove extra source ${index + 1}`}
                            onClick={() => setExtras(current => current.filter((_, i) => i !== index))}
                          >
                            Remove
                          </button>
                        </div>
                      </div>
                    ))}
                    {extras.length < 3 && (
                      <button
                        type="button"
                        className="add-source-button"
                        onClick={() => setExtras(current => [...current, ''])}
                      >
                        <span aria-hidden="true">+</span> Add another source
                      </button>
                    )}
                    {extras.length > 0 && (
                      <p className="source-note">
                        Up to 3 extra links (repository, guide or blog) for the same build; we compare them and flag
                        disagreements. Only one YouTube video per project.
                      </p>
                    )}
                  </div>
                </>
              )}
              <div className={`form-bottom ${source === 'document' ? 'document-bottom' : ''}`}>
                <button className="primary-button" type="submit" disabled={submitting || source === 'document'}>
                  {submitting
                    ? 'Starting…'
                    : source === 'document'
                      ? 'Document support coming soon'
                      : 'Find Indian parts'}{' '}
                  {source !== 'document' ? <ArrowIcon /> : null}
                </button>
              </div>
              {error ? (
                <p className="form-error" role="alert">
                  {error}
                </p>
              ) : null}
            </form>
          </div>
          <HeroIllustration source={source} />
        </div>
        <div className="container hero-bottom">
          <a href="#how-it-works">
            Explore how it works <span aria-hidden="true">↓</span>
          </a>
        </div>
      </section>

      <section className="promise-strip" aria-label="What Bharat Sourcer helps you do">
        <div className="container promise-grid">
          <div>
            <span className="promise-symbol">
              <EvidenceIcon />
            </span>
            <span>See the source behind each part</span>
          </div>
          <div>
            <span className="promise-symbol">
              <CompatibilityIcon />
            </span>
            <span>Understand compatibility changes</span>
          </div>
          <div>
            <span className="promise-symbol">
              <StoreIcon />
            </span>
            <span>Explore Indian seller pages</span>
          </div>
        </div>
      </section>

      <section className="section how-section" id="how-it-works">
        <div className="container">
          <div className="section-heading">
            <div>
              <span className="section-kicker">THE SIMPLE IDEA</span>
              <h2>
                From “I want to make that”
                <br />
                to “here’s what I need.”
              </h2>
            </div>
          </div>
          <div className="how-grid">
            <article className="how-card">
              <span className="how-number">01 / INPUT</span>
              <div className="how-icon video-icon">
                <LinkIcon />
              </div>
              <h3>Share a project you want to build</h3>
              <p>
                Paste a YouTube, blog, or GitHub link. We’ll help identify the parts you need. Document support is
                coming soon.
              </p>
            </article>
            <article className="how-card">
              <span className="how-number">02 / REVIEW</span>
              <div className="how-icon review-icon">
                <ChecklistIcon />
              </div>
              <h3>Make the plan your own</h3>
              <p>
                Review the parts list, ask questions, and adapt it to your needs. Change quantities and mark parts you
                already have before confirming.
              </p>
            </article>
            <article className="how-card">
              <span className="how-number">03 / SOURCE</span>
              <div className="how-icon source-icon">
                <BagIcon />
              </div>
              <h3>Find parts from Indian sellers</h3>
              <p>
                Explore seller links, listed prices, and alternatives for your build. See what fits your project and
                what still needs checking before you buy.
              </p>
            </article>
          </div>
        </div>
      </section>

      <section className="trust-section" id="why-it-matters">
        <div className="container trust-layout">
          <div>
            <span className="section-kicker light-kicker">BEFORE YOU BUY</span>
            <h2>
              Know what you need.
              <br />
              Know what to check.
            </h2>
            <p>
              A part can look right and still be wrong for your build. See why it’s on your list, review details that
              need checking, and explore seller options before ordering.
            </p>
            <a href="#start" className="text-link">
              Plan your build <ArrowIcon />
            </a>
          </div>
          <div className="trust-stack">
            <div className="trust-item">
              <span className="trust-item-index">01</span>
              <div>
                <strong>Understand why each part is needed</strong>
                <p>
                  See what the project source tells us about a part, and ask questions about its role in your build.
                </p>
              </div>
            </div>
            <div className="trust-item">
              <span className="trust-item-index">02</span>
              <div>
                <strong>Check whether it fits your build</strong>
                <p>
                  Review compatibility notes, missing specifications, and assumptions that could affect your choice.
                </p>
              </div>
            </div>
            <div className="trust-item">
              <span className="trust-item-index">03</span>
              <div>
                <strong>Check the listing before ordering</strong>
                <p>Open the seller’s page to confirm the exact variant, current price, and availability.</p>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="closing-section">
        <div className="container closing-inner">
          <span className="section-kicker">FOR THE PROJECT YOU SAVED FOR LATER</span>
          <h2>
            Find inspiration anywhere.
            <br />
            <em>Build it with parts you can source in India.</em>
          </h2>
          <a className="primary-button closing-button" href="#start">
            Plan your next build <ArrowIcon />
          </a>
        </div>
      </section>
    </main>
  )
}

function ProjectCard({ project }: { project?: Job['project'] }) {
  if (!project) return null
  const facts = [
    ['Power', project.power],
    ['Controller', project.controller],
    ['Interfaces', (project.interfaces ?? []).join(', ')],
  ].filter(([, value]) => value)
  return (
    <div className="build-overview">
      <div>
        <p>{project.summary}</p>
        {facts.length > 0 && (
          <dl>
            {facts.map(([label, value]) => (
              <div key={label}>
                <dt>{label}</dt>
                <dd>{value}</dd>
              </div>
            ))}
          </dl>
        )}
        {project.assumptions?.length > 0 && (
          <>
            <strong>Assumptions to check</strong>
            <ul>
              {project.assumptions.map((entry, index) => (
                <li key={index}>{entry}</li>
              ))}
            </ul>
          </>
        )}
      </div>
    </div>
  )
}
function jobSourceCopy(job: Job) {
  let kind: LinkSource | 'hackster' | null = null
  try {
    kind = linkKind(new URL(job.input.url))
  } catch {
    /* Older jobs may have an invalid saved URL. */
  }
  if (!kind) {
    const primary = job.source_reports?.find(report => report.role === 'primary')?.kind
    kind = primary === 'video' ? 'youtube' : primary === 'github' ? 'github' : primary ? 'article' : null
  }
  if (kind === 'youtube') return { title: 'From video to parts.', reading: 'Reading the video' }
  if (kind === 'github') return { title: 'From GitHub to parts.', reading: 'Reading the GitHub repository' }
  if (kind === 'article') return { title: 'From project page to parts.', reading: 'Reading the project page' }
  return { title: 'From project to parts.', reading: 'Reading the project source' }
}

function PencilIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="m4 20 4.3-.9L19 8.4a2 2 0 0 0-2.8-2.8L5.5 16.3 4 20Z"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path d="m14.8 7 2.8 2.8" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  )
}

function ProjectHeading({ job, token, onJob }: { job: Job; token: string; onJob: (job: Job) => void }) {
  const [editing, setEditing] = useState<'title' | 'description' | null>(null)
  const [draft, setDraft] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const project = job.project
  function edit(field: 'title' | 'description') {
    setDraft(project?.[field] ?? '')
    setError('')
    setEditing(field)
  }
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!editing) return
    const value = draft.trim()
    if (!value) {
      setError(`${editing === 'title' ? 'Title' : 'Description'} cannot be blank.`)
      return
    }
    if (value === (project?.[editing] ?? '')) {
      setEditing(null)
      return
    }
    setBusy(true)
    setError('')
    try {
      onJob(await updateProject(job.job_id, token, { [editing]: value }))
      setEditing(null)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not save project details.')
    } finally {
      setBusy(false)
    }
  }
  return (
    <section className="project-heading">
      {editing === 'title' ? (
        <form className="inline-project-editor" onSubmit={save}>
          <label htmlFor="project-title">Project title</label>
          <input
            id="project-title"
            autoFocus
            value={draft}
            maxLength={120}
            onChange={event => setDraft(event.target.value)}
          />
          <div>
            <button className="nav-cta" type="submit" disabled={busy}>
              {busy ? 'Saving…' : 'Save'}
            </button>
            <button className="remove-button" type="button" disabled={busy} onClick={() => setEditing(null)}>
              Cancel
            </button>
          </div>
        </form>
      ) : (
        <div className="editable-project-field editable-project-title">
          <h1>
            {project?.title || jobSourceCopy(job).title}
            <button
              type="button"
              className="pencil-button"
              aria-label="Edit project title"
              title="Edit project title"
              onClick={() => edit('title')}
            >
              <PencilIcon />
            </button>
          </h1>
        </div>
      )}
      {editing === 'description' ? (
        <form className="inline-project-editor" onSubmit={save}>
          <label htmlFor="project-description">Description</label>
          <textarea
            id="project-description"
            autoFocus
            value={draft}
            maxLength={600}
            onChange={event => setDraft(event.target.value)}
          />
          <div>
            <button className="nav-cta" type="submit" disabled={busy}>
              {busy ? 'Saving…' : 'Save'}
            </button>
            <button className="remove-button" type="button" disabled={busy} onClick={() => setEditing(null)}>
              Cancel
            </button>
          </div>
        </form>
      ) : (
        <div className="editable-project-field">
          <p>{project?.description || 'Add a description'}</p>
          <button
            type="button"
            className="pencil-button"
            aria-label="Edit project description"
            title="Edit project description"
            onClick={() => edit('description')}
          >
            <PencilIcon />
          </button>
        </div>
      )}
      {/^https:\/\/[^\s]+$/i.test(job.input.url) && (
        <a className="project-source-link" href={job.input.url} target="_blank" rel="noopener noreferrer">
          {/^https:\/\/(?:www\.)?(?:m\.)?(?:youtube\.com|youtu\.be)\//i.test(job.input.url)
            ? 'Watch source video on YouTube ↗'
            : 'Open original project source ↗'}
        </a>
      )}
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
    </section>
  )
}

type ReviewRow = {
  item: BomItem
  name: string
  qty: string
  owned: boolean
  removed: boolean
  requirements: NonNullable<BomItem['requirements']>
  spec: BuyableSpec | null
}

// A short note under a review row's name: the one thing worth checking first.
function reviewNote(row: ReviewRow) {
  if (row.removed) return 'Removed from this build'
  if (row.item.conflicts?.length) return 'Sources disagree'
  if (row.item.clarifications.length) return 'Something is unclear'
  if (row.spec?.needs_value) return 'Needs a value'
  if (row.item.qty_source === 'inferred' && row.qty === (row.item.qty?.toString() ?? '')) return 'Suggested quantity'
  if (row.item.confidence === 'check') return 'Check this part'
  return ''
}

// One part's editable details in the side panel. Edits stay local until the list is confirmed.
function ReviewPartPanel({ row, update }: { row: ReviewRow; update: (id: string, patch: Partial<ReviewRow>) => void }) {
  const id = row.item.line_id
  return (
    <div className="pp-part">
      {row.removed && (
        <div className="pp-part-callout pp-part-callout-input">
          <strong>Removed from this build</strong>
          <p>It will not be searched for or ordered.</p>
          <button type="button" className="pp-text-button" onClick={() => update(id, { removed: false })}>
            Undo remove
          </button>
        </div>
      )}
      <label className="pp-field">
        Part name
        <input value={row.name} disabled={row.removed} onChange={event => update(id, { name: event.target.value })} />
      </label>
      {row.spec && row.spec.origin !== 'user' && row.name.trim() !== row.item.raw_name && (
        <p className="pp-field-note">
          Renaming drops the suggested buying spec; seller search builds one from the new name unless you edit the spec.
        </p>
      )}
      <div className="pp-field-row">
        <label className="pp-field pp-field-qty">
          Quantity
          <input
            type="number"
            min="1"
            max="10000"
            value={row.qty}
            disabled={row.removed}
            onChange={event => update(id, { qty: event.target.value })}
          />
        </label>
        <label className="check-label">
          <input
            type="checkbox"
            checked={row.owned}
            disabled={row.removed}
            onChange={event => update(id, { owned: event.target.checked })}
          />{' '}
          I already have this
        </label>
      </div>
      {row.item.qty_source === 'inferred' && row.qty === (row.item.qty?.toString() ?? '') && (
        <p className="pp-field-note">
          Suggested quantity: {row.item.qty_reason || 'the source did not state a count.'}
        </p>
      )}
      {row.item.clarifications.length > 0 && (
        <div className="pp-part-callout pp-part-callout-input">
          <strong>Still unclear</strong>
          <p>{row.item.clarifications.map(entry => entry.question).join(' ')}</p>
        </div>
      )}
      <ConflictNotes item={row.item} />
      <LookalikeNotes item={row.item} />
      <details className="pp-section">
        <summary>Build details</summary>
        <div className="pp-section-body">
          <Requirements
            value={row.requirements}
            disabled={row.removed}
            onChange={requirements => update(id, { requirements })}
          />
        </div>
      </details>
      <details className="pp-section" open={!!row.spec?.needs_value}>
        <summary>Buying spec</summary>
        <div className="pp-section-body">
          <SpecPanel value={row.spec} disabled={row.removed} onChange={spec => update(id, { spec })} />
        </div>
      </details>
      {row.item.evidence.length > 0 && (
        <details className="pp-section">
          <summary>Why this part is in the list</summary>
          <div className="pp-section-body">
            <ConfidenceChip item={row.item} />
            <EvidenceList evidence={row.item.evidence} />
          </div>
        </details>
      )}
      {!row.removed && (
        <button type="button" className="remove-button pp-remove" onClick={() => update(id, { removed: true })}>
          Remove from this build
        </button>
      )}
    </div>
  )
}

function Review({
  job,
  token,
  onConfirmed,
  openPart,
  onOpenPart,
}: {
  job: Job
  token: string
  onConfirmed: () => void
  openPart: string | null
  onOpenPart: (lineId: string | null) => void
}) {
  const account = useAccount()
  const [rows, setRows] = useState<ReviewRow[]>(() =>
    job.items.map(item => ({
      item,
      name: item.raw_name,
      qty: item.qty?.toString() ?? '',
      owned: item.user_has_it,
      removed: false,
      requirements: item.requirements ?? [],
      spec: item.buyable_spec ?? null,
    })),
  )
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const lastRow = useRef<ReviewRow | null>(null)

  function update(id: string, patch: Partial<ReviewRow>) {
    setRows(current => current.map(row => (row.item.line_id === id ? { ...row, ...patch } : row)))
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError('')
    const retained = rows.filter(row => !row.removed)
    if (!retained.length) {
      setError('Keep at least one part in the list.')
      return
    }
    if (
      retained.some(
        row => !Number.isInteger(Number(row.qty)) || Number(row.qty) < 1 || Number(row.qty) > 10000 || !row.name.trim(),
      )
    ) {
      setError('Every part you keep needs a name and a quantity from 1 to 10,000.')
      return
    }
    if (retained.some(row => !validRequirements(row.requirements))) {
      setError('Every build detail needs a property and a value, or remove the empty row.')
      return
    }
    if (retained.some(row => !validSpec(row.spec))) {
      setError(
        'Every buying spec value needs a property and a value (and an upper value for “Between”), or remove the empty row.',
      )
      return
    }
    if (
      account.identity &&
      account.identity !== 'legacy' &&
      account.identity.kind === 'guest' &&
      retained.filter(row => !row.owned).length > account.identity.part_limit
    ) {
      setError(
        `Guests can search sellers for up to ${account.identity.part_limit} parts. Mark parts you already have, remove some, or sign in with Google for a higher limit.`,
      )
      return
    }
    const edits: Parameters<typeof confirmJob>[2] = []
    for (const row of rows) {
      if (row.removed) {
        edits.push({ op: 'remove', line_id: row.item.line_id })
        continue
      }
      const updateEdit: {
        op: 'update'
        line_id: string
        raw_name?: string
        qty?: number
        requirements?: NonNullable<BomItem['requirements']>
        buyable_spec?: BuyableSpec
      } = { op: 'update', line_id: row.item.line_id }
      if (row.name.trim() !== row.item.raw_name) updateEdit.raw_name = row.name.trim()
      if (Number(row.qty) !== row.item.qty) updateEdit.qty = Number(row.qty)
      if (JSON.stringify(row.requirements) !== JSON.stringify(row.item.requirements ?? []))
        updateEdit.requirements = requirementPayload(row.requirements)
      if (row.spec && JSON.stringify(row.spec) !== JSON.stringify(row.item.buyable_spec ?? null))
        updateEdit.buyable_spec = specPayload(row.spec)
      if (
        updateEdit.raw_name !== undefined ||
        updateEdit.qty !== undefined ||
        updateEdit.requirements !== undefined ||
        updateEdit.buyable_spec !== undefined
      )
        edits.push(updateEdit)
      if (row.owned !== row.item.user_has_it)
        edits.push({ op: 'have_it', line_id: row.item.line_id, user_has_it: row.owned })
    }
    setBusy(true)
    try {
      await confirmJob(job.job_id, token, edits)
      onOpenPart(null)
      onConfirmed()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not confirm the list.')
    } finally {
      setBusy(false)
    }
  }

  const kept = rows.filter(row => !row.removed)
  const toSource = kept.filter(row => !row.owned).length
  const guest =
    account.identity && account.identity !== 'legacy' && account.identity.kind === 'guest' ? account.identity : null
  const needs: Need[] = safetyNeeds(job, id => onOpenPart(id))
  for (const row of rows) {
    if (row.removed) continue
    if (row.item.conflicts?.length)
      needs.push({
        key: `conflict-${row.item.line_id}`,
        tone: 'input',
        title: `${row.name}: sources disagree`,
        detail: row.item.conflicts[0].message,
        action: { label: 'Check part', onClick: () => onOpenPart(row.item.line_id) },
      })
    else if (row.item.clarifications.length)
      needs.push({
        key: `unclear-${row.item.line_id}`,
        tone: 'input',
        title: `${row.name}: something is unclear`,
        detail: row.item.clarifications[0].question,
        action: { label: 'Check part', onClick: () => onOpenPart(row.item.line_id) },
      })
  }
  if (guest && toSource > guest.part_limit)
    needs.push({
      key: 'guest-limit',
      tone: 'input',
      title: `Guests can search sellers for up to ${guest.part_limit} parts`,
      detail: `This list has ${toSource}. Mark parts you already have, remove some, or sign in with Google.`,
      action: { label: 'Sign in', onClick: account.open },
    })
  const current = rows.find(row => row.item.line_id === openPart) ?? null
  // eslint-disable-next-line react-hooks/refs -- keeps the last opened part rendered while the side panel closes
  if (current) lastRow.current = current
  // eslint-disable-next-line react-hooks/refs -- keeps the last opened part rendered while the side panel closes
  const shown = current ?? lastRow.current
  const reports = job.source_reports ?? []
  const skipped = reports.filter(report => report.status === 'failed').length

  return (
    <section className="job-panel pp-stage">
      <header className="pp-stage-head">
        <h2>
          We found {job.items.length} {job.items.length === 1 ? 'part' : 'parts'}.
        </h2>
        <p>
          Check the names and quantities and mark what you already have. Sellers are searched only after you confirm.
        </p>
      </header>
      {job.copied_from && (
        <p className="pp-field-note" role="note">
          Copied from a shared project on {day(job.copied_from.copied_at)}.{' '}
          {job.report ? (
            <>
              Seller prices are from {day(job.copied_from.source_updated_at)} or earlier; refresh to update them. Picks
              marked “Copied choice” were made by the person who shared it.
            </>
          ) : (
            'Review the parts, then confirm to find sellers.'
          )}
        </p>
      )}
      <NeedsList
        needs={needs}
        initiallyOpen={job.safety_flags?.some(flag => flag.code === 'MAINS') ? 'flag-MAINS' : null}
      />
      <form onSubmit={submit}>
        <div className="pp-parts-head">
          <h2>
            Your parts <span>{kept.length}</span>
          </h2>
        </div>
        <ul className="pp-rows pp-review-rows">
          {rows.map(row => {
            const note = reviewNote(row)
            const active = openPart === row.item.line_id
            return (
              <li
                key={row.item.line_id}
                id={`line-${row.item.line_id}`}
                className={`pp-review-row${row.removed ? ' is-removed' : ''}${active ? ' is-active' : ''}`}
              >
                <button
                  type="button"
                  className="pp-review-open"
                  aria-controls="pp-part"
                  aria-expanded={active}
                  onClick={() => onOpenPart(active ? null : row.item.line_id)}
                >
                  <strong>{row.name || 'Unnamed part'}</strong>
                  {note && <small className={row.removed ? '' : 'pp-review-attention'}>{note}</small>}
                </button>
                <label className="pp-review-qty">
                  <span className="visually-hidden">Quantity of {row.name}</span>
                  <span aria-hidden="true">×</span>
                  <input
                    type="number"
                    min="1"
                    max="10000"
                    value={row.qty}
                    disabled={row.removed}
                    onChange={event => update(row.item.line_id, { qty: event.target.value })}
                  />
                </label>
                <label className="pp-review-have">
                  <input
                    type="checkbox"
                    checked={row.owned}
                    disabled={row.removed}
                    onChange={event => update(row.item.line_id, { owned: event.target.checked })}
                  />{' '}
                  I have it
                </label>
                {row.removed ? (
                  <button
                    type="button"
                    className="pp-text-button pp-review-undo"
                    onClick={() => update(row.item.line_id, { removed: false })}
                  >
                    Undo
                  </button>
                ) : (
                  <button
                    type="button"
                    className="pp-review-edit"
                    aria-label={`Edit ${row.name || 'part'}`}
                    onClick={() => onOpenPart(active ? null : row.item.line_id)}
                  >
                    <span className="pp-row-chevron" aria-hidden="true" />
                  </button>
                )}
              </li>
            )
          })}
        </ul>
        {(job.project || reports.length > 0 || job.video_meta) && (
          <details className="pp-section pp-origin">
            <summary>
              Where these came from
              {reports.length > 0 && (
                <span>
                  {reports.length - skipped} {reports.length - skipped === 1 ? 'source' : 'sources'} read
                  {skipped ? `, ${skipped} skipped` : ''}
                </span>
              )}
            </summary>
            <div className="pp-section-body">
              <ProjectCard project={job.project} />
              <SourcesCard job={job} />
            </div>
          </details>
        )}
        <div className="pp-confirm">
          <button className="primary-button" disabled={busy} type="submit">
            {busy
              ? 'Confirming…'
              : toSource
                ? `Confirm and find sellers for ${toSource} ${toSource === 1 ? 'part' : 'parts'}`
                : 'Confirm the list'}{' '}
            <ArrowIcon />
          </button>
          {guest && (
            <p>
              As a guest you can search sellers for up to {guest.part_limit} parts. Parts you already have don't count.
            </p>
          )}
          {error && (
            <p className="form-error" role="alert">
              {error}
            </p>
          )}
        </div>
      </form>
      <SidePanel
        id="pp-part"
        open={!!current}
        title={shown?.name || 'Unnamed part'}
        subtitle={
          shown ? (
            <>
              <span>×{shown.qty || '?'}</span>
              {reviewNote(shown) && <span className="pp-row-status pp-status-input">{reviewNote(shown)}</span>}
            </>
          ) : undefined
        }
        onClose={() => onOpenPart(null)}
      >
        {shown && (
          <ReviewPartPanel
            key={shown.item.line_id}
            row={rows.find(row => row.item.line_id === shown.item.line_id) ?? shown}
            update={update}
          />
        )}
      </SidePanel>
    </section>
  )
}

// The confirmed list, shown when the user steps back to "Review the parts" after confirming.
function ConfirmedParts({ job, back }: { job: Job; back: { label: string; onClick: () => void } }) {
  return (
    <section className="job-panel pp-stage pp-lookback">
      <header className="pp-lookback-head">
        <div>
          <h2>The parts you confirmed</h2>
          <p>To change a part now, ask in the chat. Every suggested change needs your approval before it is applied.</p>
        </div>
        <button type="button" className="nav-cta" onClick={back.onClick}>
          {back.label}
        </button>
      </header>
      <ul className="pp-confirmed">
        {job.items.map(item => (
          <li key={item.line_id}>
            <span>{item.raw_name}</span>
            <span className="pp-confirmed-qty">×{item.qty ?? '?'}</span>
            <span className="pp-confirmed-note">{item.user_has_it ? 'You have this' : ''}</span>
          </li>
        ))}
      </ul>
      <details className="pp-section pp-origin">
        <summary>Where these came from</summary>
        <div className="pp-section-body">
          <ProjectCard project={job.project} />
          <SourcesCard job={job} />
        </div>
      </details>
    </section>
  )
}

const progressStatus: Record<string, { label: string; tone: 'ok' | 'input' | 'muted' }> = {
  offers_found: { label: 'Offers found', tone: 'ok' },
  no_verified_offers: { label: 'No verified offers', tone: 'input' },
  failed: { label: 'Check failed', tone: 'input' },
  already_owned: { label: 'You have it', tone: 'muted' },
  not_run: { label: 'Waiting', tone: 'muted' },
}

// Live progress while the project is read and sellers are searched; with `back`, the finished
// summary the user reaches from the step strip.
function AnalysisProgress({ job, back }: { job: Job; back?: { label: string; onClick: () => void } }) {
  const results = new Map(job.report?.lines.map(line => [line.item.line_id, line]) ?? [])
  const statusOf = (item: BomItem) =>
    item.user_has_it ? 'already_owned' : (results.get(item.line_id)?.sourcing_status ?? 'not_run')
  const finished = job.items.filter(item => statusOf(item) !== 'not_run').length
  const found = job.items.filter(item => statusOf(item) === 'offers_found').length
  const searching = job.status === 'sourcing'
  const title = back
    ? 'How the seller search went'
    : searching
      ? 'Finding sellers for your parts'
      : job.status === 'resolving'
        ? 'Preparing your parts'
        : job.status === 'paused'
          ? 'Seller search is paused'
          : job.status === 'extracting'
            ? jobSourceCopy(job).reading
            : 'Waiting to start'
  const intro = back
    ? `${found} of ${job.items.length} parts have seller offers.`
    : searching
      ? 'Each part appears here as it finishes. You can leave this page; progress is saved.'
      : job.status === 'paused'
        ? 'Your progress is saved. Resume when you are ready.'
        : 'Your parts will appear here as soon as they are found.'
  return (
    <section className="job-panel pp-stage progress-panel">
      <header className={back ? 'pp-lookback-head' : 'pp-stage-head'}>
        <div>
          <h2>{title}</h2>
          <p>{intro}</p>
        </div>
        {back && (
          <button type="button" className="nav-cta" onClick={back.onClick}>
            {back.label}
          </button>
        )}
      </header>
      {job.items.length > 0 ? (
        <>
          {!back && (
            <div className="pp-progress">
              <div
                className="pp-progress-bar"
                role="progressbar"
                aria-label="Parts finished"
                aria-valuemin={0}
                aria-valuemax={job.items.length}
                aria-valuenow={finished}
              >
                <span style={{ width: `${(finished / job.items.length) * 100}%` }} />
              </div>
              <span>
                {finished} of {job.items.length} done
              </span>
            </div>
          )}
          <ul className="pp-rows">
            {job.items.map(item => {
              const status = progressStatus[statusOf(item)]
              return (
                <li key={item.line_id} id={'line-' + item.line_id} className="pp-progress-row">
                  <strong>{item.raw_name}</strong>
                  <span className="pp-row-qty">×{item.qty ?? '?'}</span>
                  <span className={`pp-row-status pp-status-${status.tone}`}>
                    {statusOf(item) === 'not_run' && searching && <i className="pp-live" aria-hidden="true" />}
                    {status.label}
                  </span>
                </li>
              )
            })}
          </ul>
        </>
      ) : (
        <div className="progress-track" aria-label="Reading the project">
          <span />
        </div>
      )}
    </section>
  )
}

function JobPage({ id }: { id: string }) {
  const account = useAccount()
  const localPreview = import.meta.env.DEV && new URLSearchParams(window.location.search).get('preview') === '1'
  const token = (localPreview ? 'dummy-token' : null) || sessionStorage.getItem(`bharat-sourcer:job:${id}`) || ''
  const [job, setJob] = useState<Job | null>(null)
  const [fatalError, setFatalError] = useState('')
  const [connectionIssue, setConnectionIssue] = useState('')
  useJobTitle(job, fatalError, connectionIssue)
  const [revision, setRevision] = useState(0)
  const [actionBusy, setActionBusy] = useState(false)
  const [actionError, setActionError] = useState('')
  // One side panel at a time: chat, attention, or one part's details.
  const [chatOpen, setChatOpenState] = useState(false)
  const [attentionOpen, setAttentionOpen] = useState(false)
  const [openPart, setOpenPartState] = useState<string | null>(null)
  function setChatOpen(open: boolean) {
    setChatOpenState(open)
    if (open) {
      setOpenPartState(null)
      setAttentionOpen(false)
    }
  }
  function setOpenPart(lineId: string | null) {
    setOpenPartState(lineId)
    if (lineId) {
      setChatOpenState(false)
      setAttentionOpen(false)
    }
  }
  function setAttention(open: boolean) {
    setAttentionOpen(open)
    if (open) {
      setChatOpenState(false)
      setOpenPartState(null)
    }
  }
  // null follows the live stage; a number is an earlier step the user chose to look at.
  const [viewStep, setViewStep] = useState<number | null>(null)
  // Which way the content slides in: back to an earlier step, or forward.
  const [direction, setDirection] = useState<'back' | 'forward'>('forward')
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- resets local state when the effect inputs change; restructuring would change render timing
    setViewStep(null)
    setDirection('forward')
  }, [job?.status])

  function applySnapshot(next: Job) {
    setJob(previous => (previous && Date.parse(next.updated_at) < Date.parse(previous.updated_at) ? previous : next))
  }

  useEffect(() => {
    if (!account.ready || (!token && (!account.identity || account.identity === 'legacy'))) return
    if (new URLSearchParams(window.location.search).get('preview') !== '1') {
      const controller = new AbortController()
      void watchJob({
        jobId: id,
        token,
        signal: controller.signal,
        onSnapshot: next => {
          setJob(previous =>
            previous && Date.parse(next.updated_at) < Date.parse(previous.updated_at) ? previous : next,
          )
          setFatalError('')
          setConnectionIssue('')
        },
        onError: (message, status) => {
          if (status === 401 || status === 404) setFatalError(message)
          else setConnectionIssue(message)
        },
      })
      return () => controller.abort()
    }
    let active = true
    let timer: ReturnType<typeof setTimeout>
    let retryDelay = 1500
    async function poll() {
      try {
        const next = await getJob(id, token)
        if (!active) return
        setJob(previous =>
          previous && Date.parse(next.updated_at) < Date.parse(previous.updated_at) ? previous : next,
        )
        setFatalError('')
        setConnectionIssue('')
        retryDelay = 1500
        timer = setTimeout(() => void poll(), 1500)
      } catch (cause) {
        if (!active) return
        if (cause instanceof ApiError && (cause.status === 404 || cause.status === 401)) {
          setFatalError(
            cause.status === 401
              ? 'Sign in again to access this project.'
              : 'This project is unavailable or belongs to another account.',
          )
          return
        }
        setConnectionIssue('Connection interrupted. Reconnecting to your saved job…')
        timer = setTimeout(() => void poll(), retryDelay)
        retryDelay = Math.min(retryDelay * 2, 10000)
      }
    }
    void poll()
    return () => {
      active = false
      clearTimeout(timer)
    }
  }, [id, token, revision, account.ready, account.identity])

  const currentStep = job ? stepOf(job) : 0
  const viewing = viewStep ?? currentStep
  function view(step: number) {
    if (step === viewing) return
    setAttentionOpen(false)
    setDirection(step < viewing ? 'back' : 'forward')
    setViewStep(step === currentStep ? null : step)
  }
  const back = {
    label: currentStep === 2 ? 'Back to order plan' : 'Back to seller search',
    onClick: () => view(currentStep),
  }
  const pauseControl =
    job && !job.demo && ['resolving', 'sourcing', 'paused'].includes(job.status) ? (
      <button
        className="nav-cta"
        title={job.status === 'paused' ? 'Your progress is saved.' : 'Pausing does not use your action quota.'}
        disabled={actionBusy || (job.pause_requested && job.status !== 'paused')}
        onClick={async () => {
          setActionBusy(true)
          setActionError('')
          try {
            await (job.status === 'paused' ? resumeJob(id, token) : pauseJob(id, token))
            setRevision(n => n + 1)
          } catch (cause) {
            setActionError(cause instanceof Error ? cause.message : 'Could not update sourcing')
          } finally {
            setActionBusy(false)
          }
        }}
      >
        {job.pause_requested && job.status !== 'paused'
          ? 'Pausing after this part…'
          : actionBusy
            ? 'Updating…'
            : job.status === 'paused'
              ? 'Resume'
              : 'Pause'}
      </button>
    ) : undefined

  return (
    <main id="main" className={`job-page project-page${chatOpen || openPart || attentionOpen ? ' sheet-open' : ''}`}>
      <div className="container job-container pp-container">
        {!job && (
          <div className="job-hero">
            <h1>Opening your project</h1>
          </div>
        )}
        {!account.ready ? (
          <p role="status">Checking your session…</p>
        ) : !token && (!account.identity || account.identity === 'legacy') ? (
          <section className="job-panel">
            <h2>Session access ended</h2>
            <p>
              Sign in to the account that owns this project to continue. Older projects also need their original
              browser-session token.
            </p>
            <button className="primary-button job-action" onClick={account.open}>
              Sign in to continue <ArrowIcon />
            </button>
          </section>
        ) : fatalError ? (
          <section className="job-panel">
            <h2>We couldn’t load this job</h2>
            <p role="alert">{fatalError}</p>
            <button
              className="primary-button job-action"
              onClick={() => {
                setFatalError('')
                setRevision(value => value + 1)
              }}
            >
              Try again <ArrowIcon />
            </button>
            {token && account.identity && account.identity !== 'legacy' && account.identity.kind === 'account' && (
              <div className="legacy-claim">
                <p>
                  If this project was created before accounts were enabled in this browser, you can save it to your
                  account using its original access token.
                </p>
                <button
                  className="nav-cta"
                  disabled={actionBusy}
                  onClick={async () => {
                    setActionBusy(true)
                    setActionError('')
                    try {
                      await claimProject(id, token)
                      setFatalError('')
                      setRevision(n => n + 1)
                    } catch (cause) {
                      setActionError(cause instanceof Error ? cause.message : 'Could not claim this project.')
                    } finally {
                      setActionBusy(false)
                    }
                  }}
                >
                  Save older project to my account
                </button>
                {actionError && (
                  <p className="form-error" role="alert">
                    {actionError}
                  </p>
                )}
              </div>
            )}
          </section>
        ) : !job ? (
          <section className="job-panel loading-panel" role="status">
            <span className="loading-indicator" /> Connecting to your job…
            {connectionIssue ? <p>{connectionIssue}</p> : null}
          </section>
        ) : (
          <>
            {connectionIssue ? (
              <div className="connection-warning" role="status">
                {connectionIssue} Your saved parts and conversation remain visible.
              </div>
            ) : null}
            {(job.demo || localPreview) && <p className="pp-demo-tag">Demo project with sample data</p>}
            <ProjectHeading
              key={job.project?.title_source + ':' + job.project?.title + ':' + job.project?.description}
              job={job}
              token={token}
              onJob={applySnapshot}
            />
            <StageSteps
              job={job}
              reading={jobSourceCopy(job).reading}
              viewing={viewing}
              onView={view}
              action={pauseControl}
            />
            {actionError && (
              <p className="form-error" role="alert">
                {actionError}
              </p>
            )}
            <div className={`pp-main pp-view pp-view-${direction}`} key={`${viewing}:${currentStep}`}>
              {viewing !== currentStep ? (
                viewing === 0 ? (
                  <ConfirmedParts job={job} back={back} />
                ) : (
                  <AnalysisProgress job={job} back={back} />
                )
              ) : (
                <>
                  {job.status === 'failed' ? (
                    <section className="job-panel pp-stage">
                      <div className="pp-part-callout pp-part-callout-input" role="alert">
                        <strong>The analysis stopped</strong>
                        <p>{job.error?.message || 'Start a new project from the home page to try again.'}</p>
                      </div>
                    </section>
                  ) : null}
                  {job.status === 'awaiting_confirmation' ? (
                    <Review
                      key={JSON.stringify(job.items)}
                      job={job}
                      token={token}
                      onConfirmed={() => setRevision(value => value + 1)}
                      openPart={openPart}
                      onOpenPart={setOpenPart}
                    />
                  ) : null}
                  {job.status === 'done' ? (
                    <Results
                      attentionOpen={attentionOpen}
                      onAttentionChange={setAttention}
                      job={job}
                      token={token}
                      onJob={applySnapshot}
                      onOpenChat={() => setChatOpen(true)}
                      openPart={openPart}
                      onOpenPart={setOpenPart}
                    />
                  ) : null}
                  {!['awaiting_confirmation', 'done', 'failed'].includes(job.status) ? (
                    <AnalysisProgress job={job} />
                  ) : null}
                </>
              )}
            </div>
            <ChatDrawer job={job} open={chatOpen} onOpenChange={setChatOpen}>
              <ChatPanel job={job} token={token} onJob={applySnapshot} bare />
            </ChatDrawer>
          </>
        )}
      </div>
    </main>
  )
}

export default function App() {
  const [path, setPath] = useState(window.location.pathname)
  useEffect(() => {
    const handlePop = () => setPath(window.location.pathname)
    window.addEventListener('popstate', handlePop)
    return () => window.removeEventListener('popstate', handlePop)
  }, [])
  function navigate(next: string) {
    if (import.meta.env.DEV && new URLSearchParams(window.location.search).get('preview') === '1') next += '?preview=1'
    window.history.pushState({}, '', next)
    setPath(next.split('?')[0])
    window.scrollTo({ top: 0, behavior: 'instant' })
  }
  const account = useAccount()
  const jobId = path.startsWith('/job/') ? path.slice(5) : null
  const shareToken = path.startsWith('/shared/') ? path.slice(8) : null
  return (
    <>
      {import.meta.env.DEV && new URLSearchParams(window.location.search).get('preview') === '1' && (
        <div className="preview-toolbar">
          <strong>LOCAL DEMO · Sample data · No API calls</strong>
          <a href="/?preview=1">Landing</a>
          <a href="/projects?preview=1">My projects</a>
          <a href="/job/ui-preview?preview=1">Review</a>
          <a href="/job/ui-preview?preview=1&stage=sourcing">Parallel progress</a>
          <a href="/job/ui-preview?preview=1&stage=done">Results</a>
          <a href="/job/ui-preview?preview=1&stage=plan">Order plan</a>
          <a href="/shared/ui-preview.dummy?preview=1">Shared link</a>
        </div>
      )}
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <Header onHome={() => navigate('/')} isHome={path === '/'} onProjects={() => navigate('/projects')} />
      {shareToken ? (
        <SharedReport shareToken={shareToken} onCopied={id => navigate('/job/' + id)} />
      ) : path === '/projects' ? (
        <Projects onOpen={id => navigate(`/job/${encodeURIComponent(id)}`)} onNew={() => navigate('/')} />
      ) : jobId ? (
        <JobPage
          key={
            jobId +
            account.revision +
            (account.identity && account.identity !== 'legacy' ? account.identity.kind : 'none')
          }
          id={jobId}
        />
      ) : (
        <Landing onCreated={id => navigate(`/job/${encodeURIComponent(id)}`)} />
      )}
    </>
  )
}

const day = (value: string) =>
  new Date(value).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })
