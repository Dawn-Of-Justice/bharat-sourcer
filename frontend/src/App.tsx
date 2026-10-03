import { useEffect, useLayoutEffect, useRef, useState, type FormEvent } from 'react'
import { ApiError, confirmJob, createJob, getBackendMode, getJob, type BomItem, type Job } from './api'
import ChatPanel from './ChatPanel'

const money = new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR' })

function formatMoney(value: string) {
  return money.format(Number(value))
}

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

function Header({ onHome, isHome }: { onHome: () => void; isHome: boolean }) {
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
        {!isHome ? <a className="nav-cta" href="/" onClick={(event) => { event.preventDefault(); onHome() }}>Back to start <ArrowIcon /></a> : null}
      </div>
    </header>
  )
}

type LinkSource = 'youtube' | 'article' | 'github'
type SourceType = LinkSource | 'audio'

const previewCopy: Record<SourceType, { label: string; symbol: string; caption: string; firstStep: string; firstDetail: string; footnote: string; accessibleLabel: string }> = {
  youtube: { label: 'YouTube', symbol: '▶', caption: 'A project you want to make', firstStep: 'Parts found in the video', firstDetail: 'With moments you can revisit', footnote: 'Illustration of the workflow · No sample prices or grades', accessibleLabel: 'A YouTube project becomes a reviewable parts list and Indian seller options' },
  article: { label: 'Article / blog', symbol: '▤', caption: 'A guide worth building from', firstStep: 'Parts mentioned in the guide', firstDetail: 'Review each part before sourcing', footnote: 'Preview concept · Live blog extraction is still in development', accessibleLabel: 'Preview concept for turning an article or blog guide into a reviewable parts list. Live blog extraction is not yet available.' },
  github: { label: 'GitHub', symbol: '</>', caption: 'An open-source build idea', firstStep: 'Parts noted in project files', firstDetail: 'Check the list against the repository', footnote: 'Preview concept · Live GitHub extraction is still in development', accessibleLabel: 'Preview concept for turning a GitHub repository into a reviewable parts list. Live GitHub extraction is not yet available.' },
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

const calloutArrowPaths: Record<SourceType, string> = {
  youtube: 'M8 7 C8 23 23 24 42 40',
  article: 'M7 7 C20 14 10 30 42 40',
  github: 'M8 7 C17 3 26 23 42 40',
  audio: 'M8 6 C4 19 26 26 42 40',
}

const sourceFields: Record<LinkSource, { label: string; placeholder: string }> = {
  youtube: { label: 'Paste a YouTube project link', placeholder: 'https://www.youtube.com/watch?v=...' },
  article: { label: 'Paste a tutorial or blog link', placeholder: 'https://www.instructables.com/your-project/' },
  github: { label: 'Paste a GitHub repository link', placeholder: 'https://github.com/creator/project' },
}

function Landing({ onCreated }: { onCreated: (id: string) => void }) {
  const [source, setSource] = useState<SourceType>('youtube')
  const [arrowSource, setArrowSource] = useState<SourceType>('youtube')
  const [arrowVisible, setArrowVisible] = useState(true)
  const arrowTimer = useRef<number | null>(null)
  const calloutRef = useRef<HTMLDivElement>(null)
  const tabRefs = useRef<Partial<Record<SourceType, HTMLButtonElement>>>({})
  const [arrowPosition, setArrowPosition] = useState<{ left: number; top: number } | null>(null)
  const [sourceUrls, setSourceUrls] = useState<Record<LinkSource, string>>({ youtube: '', article: '', github: '' })
  const [pin, setPin] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  useLayoutEffect(() => {
    const callout = calloutRef.current
    const tab = tabRefs.current[arrowSource]
    if (!callout || !tab) return
    const positionArrow = () => {
      const calloutBox = callout.getBoundingClientRect()
      const tabBox = tab.getBoundingClientRect()
      setArrowPosition({
        left: tabBox.left + tabBox.width / 2 - calloutBox.left - 42,
        top: tabBox.top - calloutBox.top - 44,
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
  }, [arrowSource])

  useEffect(() => () => {
    if (arrowTimer.current !== null) window.clearTimeout(arrowTimer.current)
  }, [])

  function chooseSource(next: SourceType) {
    setSource(next)
    setError('')
    if (arrowTimer.current !== null) window.clearTimeout(arrowTimer.current)
    if (next === arrowSource) {
      setArrowVisible(true)
      arrowTimer.current = null
      return
    }
    setArrowVisible(false)
    arrowTimer.current = window.setTimeout(() => {
      setArrowSource(next)
      setArrowVisible(true)
      arrowTimer.current = null
    }, 180)
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
    if (source === 'github' && !['github.com', 'www.github.com'].includes(parsed.hostname.toLowerCase())) {
      setError('Enter a github.com repository URL.')
      return
    }
    if (pin && !/^[1-9][0-9]{5}$/.test(pin)) {
      setError('Enter a valid six-digit Indian PIN code, or leave it blank.')
      return
    }
    setSubmitting(true)
    try {
      if (source !== 'youtube' && await getBackendMode() !== 'demo') {
        setError('Live analysis currently supports public YouTube videos. Article and GitHub extraction are still being built.')
        return
      }
      const job = await createJob(parsed.toString(), pin || undefined)
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
            <div className="input-callout" aria-hidden="true" ref={calloutRef}><span>Your build starts here</span><svg className={arrowPosition && arrowVisible ? 'tab-arrow is-ready' : 'tab-arrow'} style={arrowPosition ?? undefined} viewBox="0 0 64 48" fill="none"><defs><marker id="landing-arrowhead" viewBox="0 0 16 16" refX="12" refY="8" markerWidth="16" markerHeight="16" markerUnits="userSpaceOnUse" orient="auto"><path d="M3 3 L12 8 L3 13" fill="none" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" /></marker></defs><path className="draw-arrow" d={calloutArrowPaths[arrowSource]} markerEnd="url(#landing-arrowhead)" stroke="currentColor" strokeWidth="2.8" strokeLinecap="round" fill="none" /></svg></div>
            <form className="source-form" onSubmit={submit}>
              <div className="source-options" role="group" aria-label="Choose a project source">{sourceOptions.map((option) => <button key={option.id} ref={(element) => { tabRefs.current[option.id] = element ?? undefined }} type="button" className={`source-option ${source === option.id ? 'selected' : ''}`} aria-pressed={source === option.id} onClick={() => chooseSource(option.id)}><span aria-hidden="true">{option.symbol}</span>{option.label}</button>)}</div>
              {source === 'audio' ? <div className="audio-field"><label htmlFor="audio-file">Choose a build description or maker audio file</label><input id="audio-file" type="file" accept="audio/*" /><p>Audio transcription and uploads are planned; this file stays on your device for now.</p></div> : <><label htmlFor="source-url">{sourceFields[source].label}</label><div className="url-row"><span className={`url-icon url-icon-${source}`} aria-hidden="true">{source === 'youtube' ? <svg viewBox="0 0 24 24"><rect x="2" y="5" width="20" height="14" rx="4" fill="currentColor" /><path d="m10 9 6 3-6 3V9Z" fill="#fff" /></svg> : source === 'article' ? '▤' : '</>'}</span><input id="source-url" name="url" type="url" inputMode="url" autoComplete="url" placeholder={sourceFields[source].placeholder} value={sourceUrls[source]} onChange={(event) => setSourceUrls((current) => ({ ...current, [source]: event.target.value }))} required /></div>{source !== 'youtube' ? <p className="source-note">Live {source === 'article' ? 'article and blog' : 'GitHub repository'} extraction is on the roadmap. In backend demo mode, this link shows a labelled sample BOM.</p> : null}</>}
              <div className={`form-bottom ${source === 'audio' ? 'audio-bottom' : ''}`}>
                {source !== 'audio' ? <div className="pin-wrap"><label htmlFor="pin-code">Your PIN code <span>(optional)</span></label><input id="pin-code" name="pin" type="text" inputMode="numeric" maxLength={6} placeholder="e.g. 560001" value={pin} onChange={(event) => setPin(event.target.value.replace(/\D/g, ''))} /></div> : null}
                <button className="primary-button" type="submit" disabled={submitting || source === 'audio'}>{submitting ? 'Starting…' : source === 'audio' ? 'Audio support coming soon' : source === 'youtube' ? 'Find Indian parts' : 'Preview demo flow'} {source !== 'audio' ? <ArrowIcon /> : null}</button>
              </div>
              {error ? <p className="form-error" role="alert">{error}</p> : null}
            </form>
            <div className="hero-reassurance"><span className="reassurance-check">✓</span> Review the parts before any seller search begins <span className="reassurance-separator">·</span> No account needed</div>
          </div>
          <HeroIllustration source={source} />
        </div>
        <div className="container hero-bottom"><span>ONE LINK. A CLEARER WAY TO BUILD.</span><a href="#how-it-works">Explore how it works <span aria-hidden="true">↓</span></a></div>
      </section>

      <section className="promise-strip" aria-label="What Bharat Sourcer helps you do">
        <div className="container promise-grid">
          <div><span className="promise-symbol">◉</span><span>See the source behind each part</span></div>
          <div><span className="promise-symbol">⌁</span><span>Understand compatibility changes</span></div>
          <div><span className="promise-symbol">↗</span><span>Explore Indian seller pages</span></div>
        </div>
      </section>

      <section className="section how-section" id="how-it-works">
        <div className="container">
          <div className="section-heading"><div><span className="section-kicker">THE SIMPLE IDEA</span><h2>From “I want to make that”<br />to “here’s what I need.”</h2></div></div>
          <div className="how-grid">
            <article className="how-card"><span className="how-number">01 / INPUT</span><div className="how-icon video-icon" aria-hidden="true">✳</div><h3>Bring in your project</h3><p>Start with a YouTube video, blog post, GitHub repository, or audio file</p></article>
            <article className="how-card"><span className="how-number">02 / REVIEW</span><div className="how-icon review-icon" aria-hidden="true">✓</div><h3>Shape your build plan</h3><p>Check the evidence, adjust parts and quantities, mark what you own, and ask questions before confirming the list.</p></article>
            <article className="how-card"><span className="how-number">03 / SOURCE</span><div className="how-icon source-icon" aria-hidden="true">↗</div><h3>Explore Indian options</h3><p>After you confirm, inspect seller listings, prices, and compatibility notes—with unknowns left visible for you to verify.</p></article>
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

type ReviewRow = { item: BomItem; name: string; qty: string; owned: boolean; removed: boolean }

function Review({ job, token, onConfirmed }: { job: Job; token: string; onConfirmed: () => void }) {
  const [rows, setRows] = useState<ReviewRow[]>(() => job.items.map((item) => ({ item, name: item.raw_name, qty: item.qty?.toString() ?? '', owned: item.user_has_it, removed: false })))
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  function update(id: string, patch: Partial<ReviewRow>) {
    setRows((current) => current.map((row) => row.item.line_id === id ? { ...row, ...patch } : row))
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError('')
    const retained = rows.filter((row) => !row.removed)
    if (!retained.length) { setError('Keep at least one part in the list.'); return }
    if (retained.some((row) => !Number.isInteger(Number(row.qty)) || Number(row.qty) < 1 || Number(row.qty) > 10000 || !row.name.trim())) {
      setError('Every retained part needs a name and a quantity from 1 to 10,000.'); return
    }
    const edits: Parameters<typeof confirmJob>[2] = []
    for (const row of rows) {
      if (row.removed) { edits.push({ op: 'remove', line_id: row.item.line_id }); continue }
      const updateEdit: { op: 'update'; line_id: string; raw_name?: string; qty?: number } = { op: 'update', line_id: row.item.line_id }
      if (row.name.trim() !== row.item.raw_name) updateEdit.raw_name = row.name.trim()
      if (Number(row.qty) !== row.item.qty) updateEdit.qty = Number(row.qty)
      if (updateEdit.raw_name !== undefined || updateEdit.qty !== undefined) edits.push(updateEdit)
      if (row.owned !== row.item.user_has_it) edits.push({ op: 'have_it', line_id: row.item.line_id, user_has_it: row.owned })
    }
    setBusy(true)
    try { await confirmJob(job.job_id, token, edits); onConfirmed() }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not confirm the list.') }
    finally { setBusy(false) }
  }

  return <section className="job-panel"><span className="section-kicker">YOUR REVIEW</span><h2>Does this parts list look right?</h2><p className="job-panel-intro">AI extraction can miss or misname parts. Check each line before we search sellers.</p><form onSubmit={submit}><div className="review-list">{rows.map((row) => <div id={`line-${row.item.line_id}`} className={`review-row ${row.removed ? 'removed' : ''}`} key={row.item.line_id}><div className="review-fields"><label>Part name<input value={row.name} disabled={row.removed} onChange={(event) => update(row.item.line_id, { name: event.target.value })} /></label><label className="qty-field">Qty<input type="number" min="1" max="10000" value={row.qty} disabled={row.removed} onChange={(event) => update(row.item.line_id, { qty: event.target.value })} /></label></div><div className="review-row-bottom"><label className="check-label"><input type="checkbox" checked={row.owned} disabled={row.removed} onChange={(event) => update(row.item.line_id, { owned: event.target.checked })} /> I already have this</label><button type="button" className="remove-button" onClick={() => update(row.item.line_id, { removed: !row.removed })}>{row.removed ? 'Undo remove' : 'Remove'}</button></div>{row.item.evidence.length ? <div className="evidence-note">Video evidence: {row.item.evidence.map((entry) => `${entry.timestamp} — ${entry.observation}`).join(' · ')}</div> : null}{row.item.clarifications.length ? <div className="evidence-note">Still unclear: {row.item.clarifications.map((entry) => entry.question).join(' ')}</div> : null}</div>)}</div>{error ? <p className="form-error" role="alert">{error}</p> : null}<button className="primary-button job-action" disabled={busy} type="submit">{busy ? 'Confirming…' : 'Confirm BOM and find offers'} <ArrowIcon /></button></form></section>
}

function Results({ job }: { job: Job }) {
  if (!job.report) return null
  return <section className="job-panel"><span className="section-kicker">YOUR DESI BOM</span><h2>Explore the parts</h2>{job.demo ? <div className="demo-alert"><strong>Demo data</strong> · This is a fixed example. Extraction, seller checks, prices, and compatibility grades did not run.</div> : <p className="job-panel-intro">Seller prices are snapshots from product pages. Tax, shipping, and final payable cost are unknown.</p>}<div className="result-list">{job.report.lines.map((line) => <article id={`line-${line.item.line_id}`} className="result-row" key={line.item.line_id}><div className="result-title"><span>{line.item.line_id}</span><div><h3>{line.item.raw_name}</h3><p>Qty {line.item.qty ?? 'unknown'}{line.item.user_has_it ? ' · Already owned' : ''}</p></div></div>{line.item.evidence.length ? <details className="result-evidence"><summary>Saved video evidence</summary><ul>{line.item.evidence.map((entry, index) => <li key={`${entry.timestamp}-${index}`}>{entry.timestamp} — {entry.observation}</li>)}</ul><small>Model-reported; review against the source video.</small></details> : null}{line.sourcing_status === 'offers_found' ? <div className="offers-list">{line.offers.map((offer) => <div className="offer" key={offer.url}><div><strong>{offer.seller}</strong><span>{formatMoney(offer.price_inr)} per piece · {offer.stock.replaceAll('_', ' ')} · checked {new Date(offer.checked_at).toLocaleDateString('en-IN')}</span>{offer.compatibility ? <small>{offer.compatibility.grade ? `Grade ${offer.compatibility.grade}: ` : 'Compatibility unknown: '}{offer.compatibility.reasons.join(' ')} {offer.compatibility.missing_fields.length ? `Missing: ${offer.compatibility.missing_fields.join(', ')}.` : ''}</small> : null}</div><a href={offer.url} target="_blank" rel="noopener noreferrer">Seller page <ArrowIcon diagonal /></a></div>)}</div> : <p className="result-status">{line.sourcing_status === 'already_owned' ? 'Already owned — no seller search needed.' : line.sourcing_status === 'no_verified_offers' ? 'No seller page met the current verification checks.' : line.sourcing_error?.message || 'No seller search was run for this part.'}</p>}</article>)}</div>{job.report.parts_subtotal_inr ? <div className="subtotal"><span>Selected parts subtotal</span><strong>{formatMoney(job.report.parts_subtotal_inr)}</strong></div> : null}<p className="result-disclaimer">A listed offer is seller-reported, and a compatibility grade checks declared specifications only. Verify the product and build before ordering.</p></section>
}

function JobPage({ id }: { id: string }) {
  const token = sessionStorage.getItem(`bharat-sourcer:job:${id}`)
  const [job, setJob] = useState<Job | null>(null)
  const [fatalError, setFatalError] = useState('')
  const [connectionIssue, setConnectionIssue] = useState('')
  const [revision, setRevision] = useState(0)

  function applySnapshot(next: Job) {
    setJob((previous) => previous && Date.parse(next.updated_at) < Date.parse(previous.updated_at) ? previous : next)
  }

  useEffect(() => {
    if (!token) return
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
        if (cause instanceof ApiError && cause.status === 404) {
          setFatalError('This job is no longer available in this backend session, or its access token is invalid.')
          return
        }
        setConnectionIssue('Connection interrupted. Reconnecting to your saved job…')
        timer = setTimeout(poll, retryDelay)
        retryDelay = Math.min(retryDelay * 2, 10000)
      }
    }
    void poll()
    return () => { active = false; clearTimeout(timer) }
  }, [id, token, revision])

  const statusLabel: Record<string, string> = { queued: 'Queued', extracting: 'Reading the video', awaiting_confirmation: 'Ready for your review', resolving: 'Preparing parts', sourcing: 'Checking seller pages', done: 'Analysis finished', failed: 'Analysis stopped' }

  return <main id="main" className="job-page"><div className="container job-container">
    <div className="job-hero"><div className="eyebrow"><span className="eyebrow-line" /> YOUR BUILD PLAN</div><h1>From video to parts.</h1><p>Follow the analysis, review the draft, and inspect the result.</p></div>
    {!token ? <section className="job-panel"><h2>Session access ended</h2><p>This job's private access token was kept in the browser session that created it. Start a new analysis to continue.</p><a className="primary-button job-action" href="/">Start again <ArrowIcon /></a></section> : fatalError ? <section className="job-panel"><h2>We couldn’t load this job</h2><p role="alert">{fatalError}</p><button className="primary-button job-action" onClick={() => { setFatalError(''); setRevision((value) => value + 1) }}>Try again <ArrowIcon /></button></section> : !job ? <section className="job-panel loading-panel" role="status"><span className="loading-indicator" /> Connecting to your job…{connectionIssue ? <p>{connectionIssue}</p> : null}</section> : <>
      <div className="job-status-bar" role="status" aria-live="polite"><span className={`status-pulse ${['done', 'failed', 'awaiting_confirmation'].includes(job.status) ? 'paused' : ''}`} /><strong>{statusLabel[job.status]}</strong><span>{job.demo ? 'Demo mode · sample data' : 'Live analysis'}</span></div>
      {connectionIssue ? <div className="connection-warning" role="status">{connectionIssue} Your saved BOM and conversation remain visible.</div> : null}
      <div className="job-content-grid"><div className="job-primary">
        {job.status === 'failed' ? <section className="job-panel"><h2>Analysis stopped</h2><p>{job.error?.message || 'Please start a new job and try again.'}</p></section> : null}
        {job.status === 'awaiting_confirmation' ? <Review key={JSON.stringify(job.items)} job={job} token={token} onConfirmed={() => setRevision((value) => value + 1)} /> : null}
        {job.status === 'done' ? <Results job={job} /> : null}
        {!['awaiting_confirmation', 'done', 'failed'].includes(job.status) ? <section className="job-panel progress-panel"><span className="section-kicker">IN PROGRESS</span><h2>{statusLabel[job.status]}</h2><p>{job.events.at(-1)?.message || 'Your job is starting.'}</p>{job.report?.lines.length ? <p>{job.report.lines.length} of {job.items.length} parts have a sourcing result so far.</p> : null}{job.items.length ? <ul className="progress-parts">{job.items.map((item) => <li id={`line-${item.line_id}`} key={item.line_id}><strong>{item.line_id}</strong> {item.raw_name} · qty {item.qty ?? 'unknown'}</li>)}</ul> : null}<div className="progress-track"><span /></div></section> : null}
        {job.events.length ? <section className="activity-panel"><h2>Activity</h2><ol>{job.events.slice(-5).reverse().map((event) => <li key={event.seq}><span>{event.message}</span><time>{new Date(event.timestamp).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' })}</time></li>)}</ol></section> : null}
      </div><ChatPanel job={job} token={token} onJob={applySnapshot} /></div>
    </>}
  </div></main>
}

function Footer() {
  return <footer className="site-footer"><div className="container footer-inner"><div className="footer-brand"><BrandMark /><span>Bharat Sourcer<small>For the builders who ask “what if?”</small></span></div><p>Hackathon prototype · Built for the Google Cloud AI Builder Cup 2026</p><a href="#main">Back to top ↑</a></div></footer>
}

export default function App() {
  const [path, setPath] = useState(window.location.pathname)
  useEffect(() => { const handlePop = () => setPath(window.location.pathname); window.addEventListener('popstate', handlePop); return () => window.removeEventListener('popstate', handlePop) }, [])
  function navigate(next: string) { window.history.pushState({}, '', next); setPath(next); window.scrollTo({ top: 0, behavior: 'instant' }) }
  const jobId = path.startsWith('/job/') ? path.slice(5) : null
  return <><a className="skip-link" href="#main">Skip to content</a><Header onHome={() => navigate('/')} isHome={!jobId} />{jobId ? <JobPage id={jobId} /> : <Landing onCreated={(id) => navigate(`/job/${encodeURIComponent(id)}`)} />}<Footer /></>
}
