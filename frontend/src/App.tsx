import Results from './Results'
import SharedReport from './SharedReport'
import { watchJob } from './stream'
import { useAccount, Projects } from './Account'
import { useEffect, useLayoutEffect, useRef, useState, type FormEvent } from 'react'
import { BagIcon, ChecklistIcon, CompatibilityIcon, EvidenceIcon, LinkIcon, StoreIcon } from './LandingIcons'
import { ApiError, claimProject, pauseJob, resumeJob, confirmJob, createJob, getJob, updateProject, type BomItem, type BuyableSpec, type Job } from './api'
import ChatPanel from './ChatPanel'
import Requirements, { requirementPayload, validRequirements } from './Requirements'
import SafetyBanners, { SafetyLineBadges } from './SafetyBanners'
import SpecPanel, { specPayload, validSpec } from './SpecPanel'
import { ConfidenceChip, ConflictBanner, ConflictNotes, EvidenceList, LookalikeNotes, SourcesCard } from './ReviewDetails'

function BrandMark() {
  return (
    <svg className="brand-mark" viewBox="0 0 42 42" fill="none" aria-hidden="true">
      <rect width="42" height="42" rx="13" fill="currentColor" />
      <path d="M12 10h13c6 0 9 3 9 7 0 3-2 5-4 6 3 1 5 3 5 6 0 5-4 8-10 8H12V10Zm8 7v5h5c2 0 3-1 3-3 0-1-1-2-3-2h-5Zm0 11v4h5c2 0 3-1 3-2 0-2-1-2-3-2h-5Z" fill="#FAF7EE" />
      <circle cx="33" cy="9" r="5" fill="#F0AA51" />
    </svg>
  )
}

function ArrowIcon({ diagonal = false }: { diagonal?: boolean }) {
  return diagonal ? (
    <svg viewBox="0 0 20 20" fill="none" aria-hidden="true"><path d="M4 16 16 4M6 4h10v10" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" /></svg>
  ) : (
    <svg viewBox="0 0 20 20" fill="none" aria-hidden="true"><path d="M3 10h13m-5-5 5 5-5 5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" /></svg>
  )
}

function Header({ onHome, isHome, onProjects }: { onHome: () => void; isHome: boolean; onProjects: () => void }) {
  const account = useAccount()
  return (
    <header className="site-header">
      <div className="container header-inner">
        <a className="brand" href="/" onClick={(event) => { event.preventDefault(); onHome() }} aria-label="Bharat Sourcer home">
          <BrandMark />
          <span>Bharat<span className="brand-light">Sourcer</span></span>
        </a>
        {isHome ? (
          <nav className="header-nav" aria-label="Main navigation">
            <a href="#how-it-works">How it works</a>
            <a href="#why-it-matters">Why it matters</a>
          </nav>
        ) : null}
        <div className="header-account"><button className="nav-cta" onClick={onProjects}>My projects</button><button className="account-link" onClick={account.open}>{account.identity && account.identity !== 'legacy' ? account.identity.kind === 'guest' ? 'Guest account' : 'Account' : 'Sign in'}</button></div>
      </div>
    </header>
  )
}

type LinkSource = 'youtube' | 'article' | 'github'
type SourceType = LinkSource | 'audio'

const previewCopy: Record<SourceType, { label: string; symbol: string; caption: string; firstStep: string; firstDetail: string; footnote: string; accessibleLabel: string }> = {
  youtube: { label: 'YouTube', symbol: '▶', caption: 'A project you want to make', firstStep: 'Parts found in the video', firstDetail: 'With moments you can revisit', footnote: 'Illustration of the workflow · No sample prices or grades', accessibleLabel: 'A YouTube project becomes a reviewable parts list and Indian seller options' },
  article: { label: 'Article / blog', symbol: '▤', caption: 'A guide worth building from', firstStep: 'Parts mentioned in the guide', firstDetail: 'Review each part before sourcing', footnote: 'Instructables, Adafruit Learn & maker blogs · Each part cites a quote from the guide', accessibleLabel: 'Turning an Instructables project, Adafruit Learn guide or maker blog post into a reviewable parts list, with each part citing a quote from the guide.' },
  github: { label: 'GitHub', symbol: '</>', caption: 'An open-source build idea', firstStep: 'Parts noted in project files', firstDetail: 'Check the list against the repository', footnote: 'Reads the README and code files · Each part cites a quote or code line', accessibleLabel: 'Turning a GitHub repository README into a reviewable parts list, with each part citing a quote from the README.' },
  audio: { label: 'Audio', symbol: '♫', caption: 'A build idea, spoken aloud', firstStep: 'Parts from your description', firstDetail: 'Review what was understood', footnote: 'Preview concept · Audio upload is not available yet', accessibleLabel: 'Preview concept for turning an audio description into a reviewable parts list. Audio upload is not yet available.' },
}

function HeroIllustration({ source }: { source: SourceType }) {
  const preview = previewCopy[source]
  return (
    <div className="hero-visual" role="img" aria-label={preview.accessibleLabel}>
      <div className="orbit orbit-one" aria-hidden="true" />
      <div className="orbit orbit-two" aria-hidden="true" />
      <div className="preview-card">
        <div className="preview-heading">
          <span className="preview-label"><span className="preview-dot" /> THE JOURNEY</span>
          <span className="preview-counter">01 / 03</span>
        </div>
        <div className="video-tile">
          <div className={`video-art source-art-${source}`} key={source} aria-hidden="true">
            {source === 'youtube' ? <>
              <div className="board board-main"><span /><span /><span /><span /></div>
              <div className="board board-small"><span /><span /></div>
              <i className="wire wire-one" /><i className="wire wire-two" /><i className="wire wire-three" />
              <div className="play-button"><svg viewBox="0 0 16 16" aria-hidden="true"><path d="m5 3 8 5-8 5V3Z" fill="currentColor" /></svg></div>
            </> : source === 'article' ? <div className="article-sheet">
              <div className="article-sheet-top"><span>MAKER JOURNAL</span><span>↗</span></div>
              <strong>Build something brilliant</strong>
              <div className="article-rule article-rule-long" /><div className="article-rule" />
              <div className="article-parts"><span>IN THE BUILD</span><b>Controller · display · sensor</b></div>
            </div> : source === 'github' ? <div className="repo-window">
              <div className="repo-top"><span className="repo-dots"><i /><i /><i /></span><span>maker / project</span><span>⌄</span></div>
              <div className="repo-file"><span>▤</span> README.md <small>main</small></div>
              <div className="repo-code"><div><span>01</span><b># Build notes</b></div><div><span>02</span><em>parts:</em> controller, display</div><div><span>03</span><em>power:</em> USB cable</div></div>
            </div> : <div className="audio-stage">
              <div className="audio-mic"><svg viewBox="0 0 32 32" fill="none" aria-hidden="true"><rect x="12" y="4" width="8" height="16" rx="4" stroke="currentColor" strokeWidth="2.5" /><path d="M7 15a9 9 0 0 0 18 0M16 24v5m-5 0h10" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" /></svg></div>
              <div className="audio-wave">{[11, 22, 35, 19, 42, 29, 15, 38, 25, 46, 24, 33, 17, 27, 12].map((height, index) => <i key={index} style={{ height }} />)}</div>
              <span className="audio-time">00:12 / 01:08</span>
            </div>}
          </div>
          <div className="video-caption"><span className={`source-pill source-pill-${source}`}>{preview.symbol} {preview.label}</span><strong>{preview.caption}</strong></div>
        </div>
        <div className="flow-line" aria-hidden="true"><span /></div>
        <div className="preview-steps">
          <div className="preview-step"><span className="step-icon step-icon-one">01</span><span><strong>{preview.firstStep}</strong><small>{preview.firstDetail}</small></span><span className="step-check">✓</span></div>
          <div className="preview-step"><span className="step-icon step-icon-two">02</span><span><strong>You review the list</strong><small>Fix anything before sourcing</small></span><span className="step-check">✓</span></div>
          <div className="preview-step current"><span className="step-icon step-icon-three">03</span><span><strong>India-ready options</strong><small>Seller links & compatibility notes</small></span><span className="step-spark" aria-hidden="true">✦</span></div>
        </div>
        <div className="preview-footnote">{preview.footnote}</div>
      </div>
      <div className="floating-chip chip-top"><span>⌁</span> From inspiration</div>
      <div className="floating-chip chip-bottom"><span>✳</span> To a buildable plan</div>
    </div>
  )
}

const sourceOptions: { id: SourceType; label: string; symbol: string }[] = [
  { id: 'youtube', label: 'YouTube', symbol: '▶' },
  { id: 'article', label: 'Article / blog', symbol: '▤' },
  { id: 'github', label: 'GitHub', symbol: '</>' },
  { id: 'audio', label: 'Audio', symbol: '♫' },
]

const sourceFields: Record<LinkSource, { label: string; placeholder: string }> = {
  youtube: { label: 'Paste a YouTube project link', placeholder: 'https://www.youtube.com/watch?v=...' },
  article: { label: 'Paste an Instructables, Adafruit Learn or maker blog link', placeholder: 'https://learn.adafruit.com/your-guide' },
  github: { label: 'Paste a GitHub repository link', placeholder: 'https://github.com/creator/project' },
}

// Hosts the backend reads (docs/contracts/multi-source-intake.md §1). Hackster refuses automated access.
const blogHosts = ['randomnerdtutorials.com', 'dronebotworkshop.com', 'lastminuteengineers.com', 'circuitdigest.com', 'howtomechatronics.com', 'makerguides.com', 'microcontrollerslab.com', 'eater.net', 'circuitbasics.com', 'electronicshub.org']
const articleHosts = ['instructables.com', 'learn.adafruit.com', ...blogHosts]
const bareHost = (url: URL) => url.hostname.toLowerCase().replace(/^www\./, '')
function linkKind(url: URL): LinkSource | 'hackster' | null {
  const host = bareHost(url)
  if (['youtube.com', 'm.youtube.com', 'youtu.be'].includes(host)) return 'youtube'
  if (host === 'github.com') return 'github'
  if (host === 'hackster.io') return 'hackster'
  return articleHosts.includes(host) ? 'article' : null
}
const hacksterMessage = 'Hackster blocks automated reading, so its projects cannot be read yet. Try the project’s GitHub repository or video instead.'

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
    if (source === 'audio') return
    let parsed: URL
    try {
      parsed = new URL(sourceUrls[source].trim())
      if (!['http:', 'https:'].includes(parsed.protocol)) throw new Error()
    } catch {
      setError('Enter a full project URL, starting with https://.')
      return
    }
    if (source === 'article' && linkKind(parsed) !== 'article') {
      setError(linkKind(parsed) === 'hackster' ? hacksterMessage : 'Article links can be Instructables projects, Adafruit Learn guides or a supported maker blog (listed below the field).')
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
      try { url = new URL(extra.trim()); if (url.protocol !== 'https:' && url.protocol !== 'http:') throw new Error() }
      catch { setError(`Extra source ${index + 1}: enter a full URL, starting with https://.`); return }
      const kind = linkKind(url)
      if (kind === 'hackster') { setError(`Extra source ${index + 1}: ${hacksterMessage}`); return }
      if (!kind) { setError(`Extra source ${index + 1}: use a YouTube video, GitHub repository, Instructables project, Adafruit Learn guide or supported maker blog.`); return }
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
            <div className="eyebrow"><span className="eyebrow-line" /> BUILT FOR MAKERS IN INDIA</div>
            <h1 className="hero-headline">Found your next project? <span>Source it. Plan it. Build it.</span></h1>
            <p className="hero-description">Saved a project you want to make? Get a practical parts list, Indian seller options, and clear notes on what to change.</p>
            <p className="source-support">This works for projects found in videos, blogs, or elsewhere.</p>
            <div className="input-callout" aria-hidden="true" ref={calloutRef}><span>Your build starts here</span><svg className={arrowPosition ? 'tab-arrow is-ready' : 'tab-arrow'} style={arrowPosition ?? undefined} viewBox="0 0 64 48" fill="none"><defs><marker id="landing-arrowhead" viewBox="0 0 16 16" refX="12" refY="8" markerWidth="16" markerHeight="16" markerUnits="userSpaceOnUse" orient="auto"><path d="M3 3 L12 8 L3 13" fill="none" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" /></marker></defs><path className="draw-arrow" d="M8 7 C8 23 23 24 42 40" markerEnd="url(#landing-arrowhead)" stroke="currentColor" strokeWidth="2.8" strokeLinecap="round" fill="none" /></svg></div>
            <form className="source-form" onSubmit={submit}>
              <div className="source-options" role="group" aria-label="Choose a project source">{sourceOptions.map((option) => <button key={option.id} ref={(element) => { tabRefs.current[option.id] = element ?? undefined }} type="button" className={`source-option ${source === option.id ? 'selected' : ''}`} aria-pressed={source === option.id} onClick={() => chooseSource(option.id)}><span aria-hidden="true">{option.symbol}</span>{option.label}</button>)}</div>
              {source === 'audio' ? <div className="audio-field"><label htmlFor="audio-file">Choose a build description or maker audio file</label><input id="audio-file" type="file" accept="audio/*" /><p>Audio transcription and uploads are planned; this file stays on your device for now.</p></div> : <><label htmlFor="source-url">{sourceFields[source].label}</label><div className="url-row"><span className={`url-icon url-icon-${source}`} aria-hidden="true">{source === 'youtube' ? <svg viewBox="0 0 24 24"><rect x="2" y="5" width="20" height="14" rx="4" fill="currentColor" /><path d="m10 9 6 3-6 3V9Z" fill="#fff" /></svg> : source === 'article' ? '▤' : '</>'}</span><input id="source-url" name="url" type="url" inputMode="url" autoComplete="url" placeholder={sourceFields[source].placeholder} value={sourceUrls[source]} onChange={(event) => setSourceUrls((current) => ({ ...current, [source]: event.target.value }))} required /></div>{source === 'article' ? <p className="source-note">We read Instructables projects, Adafruit Learn guides and these maker blogs: {blogHosts.join(', ')}. Each part cites a quote from the page; review the list before sourcing. Hackster pages cannot be read yet.</p> : source === 'github' ? <p className="source-note">We read the repository README and its main code files. Each part cites a quote or a code line; review the list before sourcing.</p> : null}<div className="extra-sources">{extras.map((extra, index) => <div className="extra-source-row" key={index}><label htmlFor={`extra-source-${index}`}>Extra source {index + 1} <span>(optional)</span></label><div><input id={`extra-source-${index}`} type="url" inputMode="url" placeholder="https://github.com/creator/project" value={extra} onChange={(event) => setExtras(current => current.map((value, i) => i === index ? event.target.value : value))} /><button type="button" className="remove-button" aria-label={`Remove extra source ${index + 1}`} onClick={() => setExtras(current => current.filter((_, i) => i !== index))}>Remove</button></div></div>)}{extras.length < 3 && <button type="button" className="add-source-button" onClick={() => setExtras(current => [...current, ''])}><span aria-hidden="true">+</span> Add another source</button>}{extras.length > 0 && <p className="source-note">Up to 3 extra links (repository, guide or blog) for the same build; we compare them and flag disagreements. Only one YouTube video per project.</p>}</div></>}
              <div className={`form-bottom ${source === 'audio' ? 'audio-bottom' : ''}`}>
                <button className="primary-button" type="submit" disabled={submitting || source === 'audio'}>{submitting ? 'Starting…' : source === 'audio' ? 'Audio support coming soon' : 'Find Indian parts'} {source !== 'audio' ? <ArrowIcon /> : null}</button>
              </div>
              {error ? <p className="form-error" role="alert">{error}</p> : null}
            </form>
            <div className="hero-reassurance"><span className="reassurance-check">✓</span> Review the parts before any seller search begins <span className="reassurance-separator">·</span> Sign in to keep track of your projects</div>
          </div>
          <HeroIllustration source={source} />
        </div>
        <div className="container hero-bottom"><a href="#how-it-works">Explore how it works <span aria-hidden="true">↓</span></a></div>
      </section>

      <section className="promise-strip" aria-label="What Bharat Sourcer helps you do">
        <div className="container promise-grid">
          <div><span className="promise-symbol"><EvidenceIcon /></span><span>See the source behind each part</span></div>
          <div><span className="promise-symbol"><CompatibilityIcon /></span><span>Understand compatibility changes</span></div>
          <div><span className="promise-symbol"><StoreIcon /></span><span>Explore Indian seller pages</span></div>
        </div>
      </section>

      <section className="section how-section" id="how-it-works">
        <div className="container">
          <div className="section-heading"><div><span className="section-kicker">THE SIMPLE IDEA</span><h2>From “I want to make that”<br />to “here’s what I need.”</h2></div></div>
          <div className="how-grid">
            <article className="how-card"><span className="how-number">01 / INPUT</span><div className="how-icon video-icon"><LinkIcon /></div><h3>Bring in your project</h3><p>Start with a YouTube video, blog post, GitHub repository, or audio file</p></article>
            <article className="how-card"><span className="how-number">02 / REVIEW</span><div className="how-icon review-icon"><ChecklistIcon /></div><h3>Shape your build plan</h3><p>Check the evidence, adjust parts and quantities, mark what you own, and ask questions before confirming the list.</p></article>
            <article className="how-card"><span className="how-number">03 / SOURCE</span><div className="how-icon source-icon"><BagIcon /></div><h3>Explore Indian options</h3><p>After you confirm, inspect seller listings, prices, and compatibility notes with unknowns left visible for you to verify.</p></article>
          </div>
        </div>
      </section>

      <section className="trust-section" id="why-it-matters">
        <div className="container trust-layout">
          <div><span className="section-kicker light-kicker">MADE FOR THE REAL BUILD</span><h2>Build with context.<br />Not guesswork.</h2><p>A useful build plan shows where parts came from, what still needs checking, and how Indian seller options compare. Bharat Sourcer keeps that context visible as you plan.</p><a href="#start" className="text-link">Start with a project <ArrowIcon /></a></div>
          <div className="trust-stack">
            <div className="trust-item"><span className="trust-item-index">01</span><div><strong>Inspect the evidence</strong><p>See the saved observations behind a part and decide what deserves a closer look.</p></div></div>
            <div className="trust-item"><span className="trust-item-index">02</span><div><strong>See what is still unknown</strong><p>Compatibility notes separate declared-spec matches from missing details and assumptions.</p></div></div>
            <div className="trust-item"><span className="trust-item-index">03</span><div><strong>Check the seller's page</strong><p>Open Indian listings and review seller-reported prices and availability before ordering.</p></div></div>
          </div>
        </div>
      </section>

      <section className="closing-section"><div className="container closing-inner"><span className="section-kicker">FOR THE PROJECT YOU SAVED FOR LATER</span><h2>Find inspiration anywhere.<br /><em>Build it with parts you can source in India.</em></h2><a className="primary-button closing-button" href="#start">Plan your next build <ArrowIcon /></a></div></section>
    </main>
  )
}

function ProjectCard({ project }: { project?: Job['project'] }) {
  if (!project) return null
  const facts = [['Power', project.power], ['Controller', project.controller], ['Interfaces', (project.interfaces ?? []).join(', ')]].filter(([, value]) => value)
  return <details className="build-overview"><summary>Build overview</summary><div><p>{project.summary}</p>{facts.length > 0 && <dl>{facts.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>}{project.assumptions?.length > 0 && <><strong>Assumptions to check</strong><ul>{project.assumptions.map((entry, index) => <li key={index}>{entry}</li>)}</ul></>}</div></details>
}

function PencilIcon() {
  return <svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="m4 20 4.3-.9L19 8.4a2 2 0 0 0-2.8-2.8L5.5 16.3 4 20Z" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" /><path d="m14.8 7 2.8 2.8" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" /></svg>
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
    if (!value) { setError(`${editing === 'title' ? 'Title' : 'Description'} cannot be blank.`); return }
    if (value === (project?.[editing] ?? '')) { setEditing(null); return }
    setBusy(true); setError('')
    try { onJob(await updateProject(job.job_id, token, { [editing]: value })); setEditing(null) }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not save project details.') }
    finally { setBusy(false) }
  }
  return <section className="project-heading">
    {editing === 'title' ? <form className="inline-project-editor" onSubmit={save}><label htmlFor="project-title">Project title</label><input id="project-title" autoFocus value={draft} maxLength={120} onChange={event => setDraft(event.target.value)} /><div><button className="nav-cta" type="submit" disabled={busy}>{busy ? 'Saving…' : 'Save'}</button><button className="remove-button" type="button" disabled={busy} onClick={() => setEditing(null)}>Cancel</button></div></form> : <div className="editable-project-field"><h1>{project?.title || 'From video to parts.'}</h1><button type="button" className="pencil-button" aria-label="Edit project title" title="Edit project title" onClick={() => edit('title')}><PencilIcon /></button></div>}
    {editing === 'description' ? <form className="inline-project-editor" onSubmit={save}><label htmlFor="project-description">Description</label><textarea id="project-description" autoFocus value={draft} maxLength={600} onChange={event => setDraft(event.target.value)} /><div><button className="nav-cta" type="submit" disabled={busy}>{busy ? 'Saving…' : 'Save'}</button><button className="remove-button" type="button" disabled={busy} onClick={() => setEditing(null)}>Cancel</button></div></form> : <div className="editable-project-field"><p>{project?.description || 'Add a description'}</p><button type="button" className="pencil-button" aria-label="Edit project description" title="Edit project description" onClick={() => edit('description')}><PencilIcon /></button></div>}
    {/^https:\/\/[^\s]+$/i.test(job.input.url) && <a className="project-source-link" href={job.input.url} target="_blank" rel="noopener noreferrer">{/^https:\/\/(?:www\.)?(?:m\.)?(?:youtube\.com|youtu\.be)\//i.test(job.input.url) ? 'Watch source video on YouTube ↗' : 'Open original project source ↗'}</a>}
    {error && <p className="form-error" role="alert">{error}</p>}
  </section>
}

type ReviewRow = { item: BomItem; name: string; qty: string; owned: boolean; removed: boolean; requirements: NonNullable<BomItem['requirements']>; spec: BuyableSpec | null }

function ReviewPartCard({ row, index, job, update }: { row: ReviewRow; index: number; job: Job; update: (id: string, patch: Partial<ReviewRow>) => void }) {
  const flagged = job.safety_flags?.some(flag => flag.line_ids.includes(row.item.line_id))
  return <details id={`line-${row.item.line_id}`} className={`review-card result-card ${row.removed ? 'removed' : ''}`}>
    <summary className="result-card-summary">
      <div className="review-part-icon" aria-hidden="true">{String(index + 1).padStart(2, '0')}</div>
      <div className="result-card-identity"><small>PART {index + 1} · QTY {row.qty || 'unknown'}</small><h3>{row.name || 'Unnamed part'}</h3><span>{row.removed ? 'Removed from this build' : row.owned ? 'Already owned' : 'Ready to review'}</span></div>
      <div className="result-card-end"><b className="result-card-toggle">Edit details</b></div>
    </summary>
    <div className="result-card-content review-card-content">
      {(row.item.confidence || flagged) && <div className="review-row-meta"><span>{row.item.line_id}</span><ConfidenceChip item={row.item} /><SafetyLineBadges flags={job.safety_flags} lineId={row.item.line_id} /></div>}
      <div className="review-fields"><label>Part name<input value={row.name} disabled={row.removed} onChange={event => update(row.item.line_id, { name: event.target.value })} /></label><label className="qty-field">Qty<input type="number" min="1" max="10000" value={row.qty} disabled={row.removed} onChange={event => update(row.item.line_id, { qty: event.target.value })} /></label></div>
      {row.item.qty_source === 'inferred' && row.qty === (row.item.qty?.toString() ?? '') && <p className="qty-inferred" title={row.item.qty_reason ?? undefined}><span className="inferred-tag">Suggested quantity</span> {row.item.qty_reason || 'The source did not state a count.'}</p>}
      <ConflictNotes item={row.item} /><LookalikeNotes item={row.item} />
      <div className="review-row-bottom"><label className="check-label"><input type="checkbox" checked={row.owned} disabled={row.removed} onChange={event => update(row.item.line_id, { owned: event.target.checked })} /> I already have this</label><button type="button" className="remove-button" onClick={() => update(row.item.line_id, { removed: !row.removed })}>{row.removed ? 'Undo remove' : 'Remove'}</button></div>
      <Requirements value={row.requirements} disabled={row.removed} onChange={requirements => update(row.item.line_id, { requirements })} />
      <SpecPanel value={row.spec} disabled={row.removed} onChange={spec => update(row.item.line_id, { spec })} />
      {row.spec && row.spec.origin !== 'user' && row.name.trim() !== row.item.raw_name && <p className="qty-inferred"><span className="inferred-tag">Renamed</span> Renaming drops this suggested buying spec; sourcing builds one from the new name unless you edit the spec.</p>}
      <EvidenceList evidence={row.item.evidence} />
      {row.item.clarifications.length > 0 && <div className="evidence-note">Still unclear: {row.item.clarifications.map(entry => entry.question).join(' ')}</div>}
    </div>
  </details>
}

function Review({ job, token, onConfirmed }: { job: Job; token: string; onConfirmed: () => void }) {
  const account = useAccount()
  const [rows, setRows] = useState<ReviewRow[]>(() => job.items.map((item) => ({ item, name: item.raw_name, qty: item.qty?.toString() ?? '', owned: item.user_has_it, removed: false, requirements: item.requirements ?? [], spec: item.buyable_spec ?? null })))
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  function update(id: string, patch: Partial<ReviewRow>) {
    setRows((current) => current.map((row) => row.item.line_id === id ? { ...row, ...patch } : row))
  }

  function showLine(lineId: string) {
    const card = document.getElementById(`line-${lineId}`) as HTMLDetailsElement | null
    if (card) { card.open = true; card.scrollIntoView({ behavior: 'smooth', block: 'start' }) }
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError('')
    const retained = rows.filter((row) => !row.removed)
    if (!retained.length) { setError('Keep at least one part in the list.'); return }
    if (retained.some((row) => !Number.isInteger(Number(row.qty)) || Number(row.qty) < 1 || Number(row.qty) > 10000 || !row.name.trim())) {
      setError('Every retained part needs a name and a quantity from 1 to 10,000.'); return
    }
    if (retained.some(row => !validRequirements(row.requirements))) { setError('Every requirement needs a property and value, or remove the empty row.'); return }
    if (retained.some(row => !validSpec(row.spec))) { setError('Every buying spec value needs a property and value (and an upper value for “Between”), or remove the empty row.'); return }
    if (account.identity && account.identity !== 'legacy' && account.identity.kind === 'guest' && retained.filter(row => !row.owned).length > account.identity.part_limit) {
      setError(`Guests can source up to ${account.identity.part_limit} parts. Mark parts you already own, remove others, or sign in with Google for the account limit.`); return
    }
    const edits: Parameters<typeof confirmJob>[2] = []
    for (const row of rows) {
      if (row.removed) { edits.push({ op: 'remove', line_id: row.item.line_id }); continue }
      const updateEdit: { op: 'update'; line_id: string; raw_name?: string; qty?: number; requirements?: NonNullable<BomItem['requirements']>; buyable_spec?: BuyableSpec } = { op: 'update', line_id: row.item.line_id }
      if (row.name.trim() !== row.item.raw_name) updateEdit.raw_name = row.name.trim()
      if (Number(row.qty) !== row.item.qty) updateEdit.qty = Number(row.qty)
      if (JSON.stringify(row.requirements) !== JSON.stringify(row.item.requirements ?? [])) updateEdit.requirements = requirementPayload(row.requirements)
      if (row.spec && JSON.stringify(row.spec) !== JSON.stringify(row.item.buyable_spec ?? null)) updateEdit.buyable_spec = specPayload(row.spec)
      if (updateEdit.raw_name !== undefined || updateEdit.qty !== undefined || updateEdit.requirements !== undefined || updateEdit.buyable_spec !== undefined) edits.push(updateEdit)
      if (row.owned !== row.item.user_has_it) edits.push({ op: 'have_it', line_id: row.item.line_id, user_has_it: row.owned })
    }
    setBusy(true)
    try { await confirmJob(job.job_id, token, edits); onConfirmed() }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not confirm the list.') }
    finally { setBusy(false) }
  }

  return <section className="job-panel review-panel">
    <header className="review-heading"><span className="section-kicker">YOUR REVIEW</span><h2>Review your parts</h2><p>Open a part to change its name, quantity or build details.</p></header>
    <ProjectCard project={job.project} />
    {job.copied_from && <p className="copied-note" role="note"><strong>Copied from a shared project</strong> on {day(job.copied_from.copied_at)}. {job.report ? <>Seller prices are from {day(job.copied_from.source_updated_at)} or earlier; refresh to update them. Picks marked “Copied choice” were made by the person who shared it.</> : 'Review the parts, then confirm to find sellers.'}</p>}
    <SourcesCard job={job} />
    {account.identity && account.identity !== 'legacy' && account.identity.kind === 'guest' && <p className="guest-limit">Guest limit: source up to {account.identity.part_limit} parts in this build. You can mark owned parts without using this limit.</p>}
    <ConflictBanner items={job.items} onShowLine={showLine} />
    <form onSubmit={submit}>
      <div className={job.safety_flags?.length ? 'review-layout' : ''}>
        <div className="review-list">{rows.map((row, index) => <ReviewPartCard key={row.item.line_id} row={row} index={index} job={job} update={update} />)}</div>
        {!!job.safety_flags?.length && <aside className="review-safety"><SafetyBanners flags={job.safety_flags} lineNames={Object.fromEntries(job.items.map(item => [item.line_id, item.raw_name]))} onShowLine={showLine} /></aside>}
      </div>
      {error && <p className="form-error" role="alert">{error}</p>}
      <button className="primary-button job-action" disabled={busy} type="submit">{busy ? 'Confirming…' : 'Confirm BOM and find offers'} <ArrowIcon /></button>
    </form>
  </section>
}

function AnalysisProgress({ job }: { job: Job }) {
  const results = new Map(job.report?.lines.map(line => [line.item.line_id, line]) ?? [])
  const finished = job.items.filter(item => item.user_has_it || (results.has(item.line_id) && results.get(item.line_id)?.sourcing_status !== 'not_run')).length
  const labels = { offers_found: 'Offers found', no_verified_offers: 'No verified offers', failed: 'Check failed', already_owned: 'Already owned', not_run: 'Pending result' }
  return <section className="job-panel progress-panel">
    <span className="section-kicker">IN PROGRESS</span>
    <h2>{job.status === 'sourcing' ? 'Finding offers for your parts' : job.status === 'resolving' ? 'Preparing your parts' : job.status === 'extracting' ? 'Reading the video' : 'Waiting to start'}</h2>
    <p>{job.status === 'sourcing' ? 'Results appear as each part finishes. Multiple parts can be processed together.' : 'Your parts will appear here as the analysis progresses.'}</p>
    {job.items.length > 0 && <>
      <div className="parts-progress-summary"><strong>{finished} / {job.items.length} parts completed</strong><span>{job.items.length - finished} pending</span></div>
      <progress className="parts-progress-meter" value={finished} max={job.items.length} aria-label="Parts completed" />
      <ul className="parallel-parts">{job.items.map((item, index) => {
        const line = results.get(item.line_id)
        const status = item.user_has_it ? 'already_owned' : line?.sourcing_status ?? 'not_run'
        return <li id={'line-' + item.line_id} key={item.line_id} className={'part-progress ' + status}><div><small>Part {index + 1}</small><strong>{item.raw_name}</strong><span>Qty {item.qty ?? 'unknown'}</span></div><span className="part-status">{labels[status]}</span></li>
      })}</ul>
    </>}
    {!job.items.length && <div className="progress-track" aria-label="Analysis in progress"><span /></div>}
  </section>
}

function JobPage({ id }: { id: string }) {
  const account = useAccount()
  const token = (import.meta.env.DEV && new URLSearchParams(window.location.search).get('preview') === '1' ? 'dummy-token' : null) || (sessionStorage.getItem(`bharat-sourcer:job:${id}`) || '')
  const [job, setJob] = useState<Job | null>(null)
  const [fatalError, setFatalError] = useState('')
  const [connectionIssue, setConnectionIssue] = useState('')
  const [revision, setRevision] = useState(0)
  const [actionBusy, setActionBusy] = useState(false)
  const [actionError, setActionError] = useState('')

  function applySnapshot(next: Job) {
    setJob((previous) => previous && Date.parse(next.updated_at) < Date.parse(previous.updated_at) ? previous : next)
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
          setJob(previous => previous && Date.parse(next.updated_at) < Date.parse(previous.updated_at) ? previous : next)
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
        const next = await getJob(id, token!)
        if (!active) return
        setJob((previous) => previous && Date.parse(next.updated_at) < Date.parse(previous.updated_at) ? previous : next)
        setFatalError('')
        setConnectionIssue('')
        retryDelay = 1500
        timer = setTimeout(poll, 1500)
      } catch (cause) {
        if (!active) return
        if (cause instanceof ApiError && (cause.status === 404 || cause.status === 401)) {
          setFatalError(cause.status === 401 ? 'Sign in again to access this project.' : 'This project is unavailable or belongs to another account.')
          return
        }
        setConnectionIssue('Connection interrupted. Reconnecting to your saved job…')
        timer = setTimeout(poll, retryDelay)
        retryDelay = Math.min(retryDelay * 2, 10000)
      }
    }
    void poll()
    return () => { active = false; clearTimeout(timer) }
  }, [id, token, revision, account.ready, account.identity])

  const statusLabel: Record<string, string> = { queued: 'Queued', extracting: 'Reading the video', awaiting_confirmation: 'Ready for your review', resolving: 'Preparing parts', sourcing: 'Checking seller pages', done: 'Analysis finished', failed: 'Analysis stopped', paused: 'Sourcing paused' }

  return <main id="main" className="job-page"><div className="container job-container">
    {!job && <div className="job-hero"><div className="eyebrow"><span className="eyebrow-line" /> YOUR BUILD PLAN</div><h1>Opening your project</h1></div>}
    {!account.ready ? <p role="status">Checking your session…</p> : (!token && (!account.identity || account.identity === 'legacy')) ? <section className="job-panel"><h2>Session access ended</h2><p>Sign in to the account that owns this project to continue. Older projects also need their original browser-session token.</p><button className="primary-button job-action" onClick={account.open}>Sign in to continue <ArrowIcon /></button></section> : fatalError ? <section className="job-panel"><h2>We couldn’t load this job</h2><p role="alert">{fatalError}</p><button className="primary-button job-action" onClick={() => { setFatalError(''); setRevision((value) => value + 1) }}>Try again <ArrowIcon /></button>{token && account.identity && account.identity !== 'legacy' && account.identity.kind === 'account' && <div className="legacy-claim"><p>If this project was created before accounts were enabled in this browser, you can save it to your account using its original access token.</p><button className="nav-cta" disabled={actionBusy} onClick={async () => { setActionBusy(true); setActionError(''); try { await claimProject(id, token); setFatalError(''); setRevision(n => n + 1) } catch (cause) { setActionError(cause instanceof Error ? cause.message : 'Could not claim this project.') } finally { setActionBusy(false) } }}>Save older project to my account</button>{actionError && <p className="form-error" role="alert">{actionError}</p>}</div>}</section> : !job ? <section className="job-panel loading-panel" role="status"><span className="loading-indicator" /> Connecting to your job…{connectionIssue ? <p>{connectionIssue}</p> : null}</section> : <>
      <div className="job-status-bar" role="status" aria-live="polite"><span className={`status-pulse ${['done', 'failed', 'awaiting_confirmation'].includes(job.status) ? 'paused' : ''}`} /><strong>{statusLabel[job.status]}</strong><span>{job.demo ? 'Demo mode · sample data' : 'Live analysis'}</span></div>
      {connectionIssue ? <div className="connection-warning" role="status">{connectionIssue} Your saved BOM and conversation remain visible.</div> : null}
      <ProjectHeading key={job.project?.title_source + ':' + job.project?.title + ':' + job.project?.description} job={job} token={token} onJob={applySnapshot} />
      {!job.demo && ['resolving', 'sourcing', 'paused'].includes(job.status) && <div className="guest-banner"><p>{job.status === 'paused' ? 'Your progress is saved. Resume when you are ready.' : 'You can pause sourcing without using your action quota.'}</p><button className="nav-cta" disabled={actionBusy || job.pause_requested && job.status !== 'paused'} onClick={async () => { setActionBusy(true); setActionError(''); try { await (job.status === 'paused' ? resumeJob(id, token) : pauseJob(id, token)); setRevision(n => n + 1) } catch (cause) { setActionError(cause instanceof Error ? cause.message : 'Could not update sourcing') } finally { setActionBusy(false) } }}>{job.pause_requested && job.status !== 'paused' ? 'Pausing after current part…' : actionBusy ? 'Updating…' : job.status === 'paused' ? 'Resume sourcing' : 'Pause sourcing'}</button></div>}
      {actionError && <p className="form-error" role="alert">{actionError}</p>}
      <div className="job-content-grid"><div className="job-primary">
        {job.status === 'failed' ? <section className="job-panel"><h2>Analysis stopped</h2><p>{job.error?.message || 'Please start a new job and try again.'}</p></section> : null}
        {job.status === 'awaiting_confirmation' ? <Review key={JSON.stringify(job.items)} job={job} token={token} onConfirmed={() => setRevision((value) => value + 1)} /> : null}
        {job.status === 'done' ? <Results job={job} token={token} onJob={applySnapshot} /> : null}
        {!['awaiting_confirmation', 'done', 'failed'].includes(job.status) ? <AnalysisProgress job={job} /> : null}
      </div><ChatPanel job={job} token={token} onJob={applySnapshot} /></div>
    </>}
  </div></main>
}

export default function App() {
  const [path, setPath] = useState(window.location.pathname)
  useEffect(() => { const handlePop = () => setPath(window.location.pathname); window.addEventListener('popstate', handlePop); return () => window.removeEventListener('popstate', handlePop) }, [])
  function navigate(next: string) { if (import.meta.env.DEV && new URLSearchParams(window.location.search).get('preview') === '1') next += '?preview=1'; window.history.pushState({}, '', next); setPath(next.split('?')[0]); window.scrollTo({ top: 0, behavior: 'instant' }) }
  const account = useAccount()
  const jobId = path.startsWith('/job/') ? path.slice(5) : null
  const shareToken = path.startsWith('/shared/') ? path.slice(8) : null
  return <>{import.meta.env.DEV && new URLSearchParams(window.location.search).get('preview') === '1' && <div className="preview-toolbar"><strong>LOCAL DEMO · Sample data · No API calls</strong><a href="/?preview=1">Landing</a><a href="/projects?preview=1">My projects</a><a href="/job/ui-preview?preview=1">Review</a><a href="/job/ui-preview?preview=1&stage=sourcing">Parallel progress</a><a href="/job/ui-preview?preview=1&stage=done">Results</a><a href="/job/ui-preview?preview=1&stage=plan">Order plan</a><a href="/shared/ui-preview.dummy?preview=1">Shared link</a></div>}<a className="skip-link" href="#main">Skip to content</a><Header onHome={() => navigate('/')} isHome={path === '/'} onProjects={() => navigate('/projects')} />{shareToken ? <SharedReport shareToken={shareToken} onCopied={id => navigate('/job/' + id)} /> : path === '/projects' ? <Projects onOpen={id => navigate(`/job/${encodeURIComponent(id)}`)} onNew={() => navigate('/')} /> : jobId ? <JobPage key={jobId + account.revision + (account.identity && account.identity !== 'legacy' ? account.identity.kind : 'none')} id={jobId} /> : <Landing onCreated={(id) => navigate(`/job/${encodeURIComponent(id)}`)} />}</>
}

const day = (value: string) => new Date(value).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })
