import { useEffect, useRef, useState, type FormEvent } from 'react'
import { evidenceText, getPartImages, reportFailedImages, refreshOffers, selectOffer, updateRequirements, type Job, type ReportLine, type ResearchAssessment, type PartRequirement, type PartImages } from './api'
import Requirements, { requirementPayload, validRequirements } from './Requirements'

const money = new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR' })
const price = (value: string) => money.format(Number(value))
const secureLink = (url: string) => /^https:\/\/[^\s]+$/i.test(url) ? url : undefined

type DisplayImage = { url: string; label: string }

// Seller offer photos first, then backend page references (parts without verified offers).
function lineImages(line: ReportLine, demo: boolean): DisplayImage[] {
  const images: DisplayImage[] = []
  for (const offer of line.offers) if (offer.image_url) images.push({ url: offer.image_url, label: 'Seller image · visual reference only' })
  for (const image of line.image_candidates ?? []) images.push({ url: image.url, label: image.label })
  const seen = new Set<string>()
  return images.filter(image => {
    const allowed = secureLink(image.url) || (demo && image.url === '/preview-part.svg')
    if (!allowed || seen.has(image.url)) return false
    seen.add(image.url)
    return true
  })
}

function ProductImage({ job, line, token }: { job: Job; line: ReportLine; token: string }) {
  const [remote, setRemote] = useState<PartImages | null>(null)
  const [failed, setFailed] = useState<string[]>([])
  const requested = useRef(false)
  const local = lineImages(line, job.demo)
  const allowed = (url: string) => secureLink(url) || /^data:image\/(?:svg\+xml,|jpeg;base64,)/i.test(url)
  const candidates = [...local, ...(remote?.candidates ?? []).filter(image => allowed(image.url))]
  const image = candidates.find(candidate => !failed.includes(candidate.url))
    ?? (remote?.fallback && !failed.includes(remote.fallback.url) && allowed(remote.fallback.url) ? remote.fallback : null)

  useEffect(() => {
    if (job.demo) return
    let active = true
    void getPartImages(job.job_id, token, line.item.line_id).then(value => {
      if (active) setRemote(value)
    }).catch(() => { /* Images are optional; preserve the sourcing result. */ })
    return () => { active = false }
  }, [job.job_id, job.demo, token, line.item.line_id])

  useEffect(() => {
    if (job.demo || !remote || requested.current) return
    const remaining = [...local, ...remote.candidates].some(candidate => !failed.includes(candidate.url))
    if (remaining || (failed.length === 0 && remote.fallback.kind !== 'placeholder')) return
    requested.current = true
    void reportFailedImages(job.job_id, token, line.item.line_id, failed.filter(url => secureLink(url)).slice(0, 10)).then(setRemote).catch(() => { /* Keep the labelled fallback. */ })
  }, [job.job_id, job.demo, token, line.item.line_id, remote, failed])

  function imageFailed() {
    if (!image) return
    const next = [...failed, image.url]
    setFailed(next)
  }
  const label = image && ('kind' in image && (image.kind === 'category' || image.kind === 'placeholder') ? `${image.label} · not a product photo` : image.label)
  return <div className="part-image"><div className="product-image">{image ? <img key={image.url} src={image.url} alt={`${label} for ${line.item.raw_name}`} title={label ?? undefined} loading="lazy" referrerPolicy="no-referrer" onError={imageFailed} /> : <span>Image<br />unavailable</span>}</div>{label && <small>{label}</small>}</div>
}

function Assessment({ value }: { value: ResearchAssessment }) {
  return <div className="research-assessment"><strong>AI assessment · {value.status.replaceAll('_', ' ')}</strong><p>{value.explanation}</p>{value.conditions.length > 0 && <p>Conditions: {value.conditions.join('; ')}</p>}{value.questions.length > 0 && <p>Questions to resolve: {value.questions.join('; ')}</p>}{value.checks?.length ? <ul>{value.checks.map((check, index) => <li key={index}>{check.requirement.name} {check.requirement.operator.replaceAll('_', ' ')} {check.requirement.value} {check.requirement.unit}: {check.status.replaceAll('_', ' ')}. {check.reason}</li>)}</ul> : null}</div>
}

function Research({ line }: { line: ReportLine }) {
  const research = line.research
  if (!research) return null
  return <section className="research-block" aria-label={`Research for ${line.item.raw_name}`}><h4>Source research</h4><p>{research.summary || `Research ${research.status.replaceAll('_', ' ')}.`}</p><small>AI-reviewed source quotes are leads for your own checks. They are not verified prices or safety certifications.</small>{research.questions?.length ? <p>Open questions: {research.questions.join('; ')}</p> : null}{research.candidates?.map((candidate, index) => <article className="research-candidate" key={`${candidate.url}-${index}`}><div className="candidate-heading"><strong>{candidate.title}</strong><span>{candidate.kind} · {candidate.match} match</span></div><p>Identity excerpt: “{candidate.identity_quote}”</p><Assessment value={candidate.assessment} />{candidate.facts?.length ? <details><summary>Source facts and quotes</summary><ul>{candidate.facts.map((fact, i) => <li key={i}><strong>{fact.name}: {fact.value} {fact.unit ?? ''}</strong><br />“{fact.quote}”</li>)}</ul></details> : null}{secureLink(candidate.url) && <a href={candidate.url} target="_blank" rel="noopener noreferrer">Review source ↗</a>}</article>)}{research.sources?.length ? <details><summary>Source access and review status</summary><ul>{research.sources.map((source, index) => <li key={index}>{secureLink(source.url) ? <a href={source.url} target="_blank" rel="noopener noreferrer">{source.url}</a> : source.url} · {source.status === 'unavailable' ? `Unavailable: ${source.reason ?? 'not readable'}` : source.reviewed ? 'Read for assessment' : 'Discovered, not reviewed'}</li>)}</ul></details> : null}</section>
}

function RequirementReview({ job, line, token, onJob }: { job: Job; line: ReportLine; token: string; onJob: (job: Job) => void }) {
  const [requirements, setRequirements] = useState<PartRequirement[]>(line.item.requirements ?? [])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const original = JSON.stringify(line.item.requirements ?? [])
  const inferred = (line.item.requirements ?? []).filter(item => item.origin === 'inferred').length
  async function save(event: FormEvent) {
    event.preventDefault()
    if (!validRequirements(requirements)) { setError('Every requirement needs a property and value.'); return }
    setBusy(true); setError('')
    try { onJob(await updateRequirements(job.job_id, token, line.item.line_id, requirementPayload(requirements))) }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not save requirements.') }
    finally { setBusy(false) }
  }
  return <details className="requirements-after"><summary>Review or change build requirements ({line.item.requirements?.length ?? 0}{inferred ? `, ${inferred} AI-inferred` : ''})</summary><form onSubmit={save}><Requirements value={requirements} onChange={setRequirements} disabled={busy} /><p>Changing requirements may make AI assessments stale and clear affected selections. Refresh is a separate action.</p><button className="nav-cta" type="submit" disabled={busy || JSON.stringify(requirements) === original}>{busy ? 'Saving…' : 'Save requirements'}</button>{error && <p className="form-error" role="alert">{error}</p>}</form></details>
}

function OfferList({ job, line, token, onJob }: { job: Job; line: ReportLine; token: string; onJob: (job: Job) => void }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [acknowledge, setAcknowledge] = useState<Record<string, boolean>>({})
  async function choose(url: string | null, changes = false, assessment = false) {
    setBusy(true); setError('')
    try { onJob(await selectOffer(job.job_id, token, line.item.line_id, url, changes, assessment)) }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not update the selection.') }
    finally { setBusy(false) }
  }
  if (!line.offers.length) return <p className="result-status">{line.sourcing_status === 'already_owned' ? 'Already owned; no seller search needed.' : line.sourcing_error?.message || (line.sourcing_status === 'no_verified_offers' ? 'No page passed the current offer checks. Research leads may still be useful.' : 'No verified offer is available yet.')}</p>
  return <div className="offers-list"><h4>Verified seller page quotes</h4>{line.offers.map(offer => {
    const selected = line.selected_offer_url === offer.url
    const changeNeeded = offer.compatibility?.grade === 'B'
    const aiChoice = !offer.compatibility?.grade && offer.research_assessment?.status === 'potential_match'
    const fresh = Date.now() - Date.parse(offer.checked_at) < 24 * 60 * 60 * 1000
    const eligible = !job.demo && offer.stock === 'in_stock' && fresh && (offer.compatibility?.grade === 'A' || changeNeeded || aiChoice)
    const acknowledged = acknowledge[offer.url] ?? false
    return <article className="offer" key={offer.url}><div><strong>{offer.seller}</strong><span>{price(offer.price_inr)} per piece · {offer.stock.replaceAll('_', ' ')} · checked {new Date(offer.checked_at).toLocaleString('en-IN')}</span><small>Seller-reported quote · shipping and tax unknown</small>{offer.spec_conflicts?.length ? <details className="spec-conflicts"><summary>Sellers disagree on {offer.spec_conflicts.map(conflict => conflict.field).join(', ')} · values unknown</summary><ul>{offer.spec_conflicts.map(conflict => <li key={conflict.field}><strong>{conflict.field}: unknown</strong><ul>{conflict.candidates.map((candidate, index) => <li key={index}>{candidate.value} · {candidate.source.replaceAll('_', ' ')}{candidate.locator ? ` (${candidate.locator})` : ''}</li>)}</ul></li>)}</ul></details> : null}{offer.compatibility && <p>Declared-spec grade {offer.compatibility.grade ?? 'unknown'}: {offer.compatibility.reasons.join(' ')} {offer.compatibility.missing_fields.length ? `Missing: ${offer.compatibility.missing_fields.join(', ')}.` : ''}</p>}{changeNeeded && <p>Required changes: {offer.compatibility?.changes.join('; ') || 'Review the report before accepting.'}</p>}{offer.research_assessment && <Assessment value={offer.research_assessment} />}{selected && <strong>{line.research_accepted ? 'Selected with your AI assessment acknowledgement' : 'Selected quote'}</strong>}{eligible && !selected && (changeNeeded || aiChoice) && <label className="offer-ack"><input type="checkbox" checked={acknowledged} onChange={event => setAcknowledge(rows => ({ ...rows, [offer.url]: event.target.checked }))} /> I reviewed {changeNeeded ? 'the required changes' : 'the AI assessment, conditions and unknowns'}</label>}{!job.demo && selected && <button type="button" className="nav-cta" disabled={busy} onClick={() => void choose(null)}>Clear selection</button>}{eligible && !selected && <button type="button" className="nav-cta" disabled={busy || (changeNeeded || aiChoice) && !acknowledged} onClick={() => void choose(offer.url, changeNeeded, aiChoice)}>Select quote</button>}{!eligible && !job.demo && <small>{!fresh ? 'Quote is older than 24 hours; refresh before selection.' : 'Selection unavailable until stock and compatibility are resolved.'}</small>}</div>{secureLink(offer.url) && <a href={offer.url} target="_blank" rel="noopener noreferrer">Seller page ↗</a>}</article>
  })}{error && <p className="form-error" role="alert">{error}</p>}</div>
}

export default function Results({ job, token, onJob }: { job: Job; token: string; onJob: (job: Job) => void }) {
  const [refreshIds, setRefreshIds] = useState<string[]>([])
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState('')
  if (!job.report) return null
  const refreshable = !job.demo && job.status === 'done' && (job.refresh_count ?? 0) < 2
  async function refresh() {
    setRefreshing(true); setError('')
    try { await refreshOffers(job.job_id, token, refreshIds); setRefreshIds([]); onJob(await import('./api').then(api => api.getJob(job.job_id, token))) }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not start a seller refresh. Check the saved job before retrying.') }
    finally { setRefreshing(false) }
  }
  return <section className="job-panel"><span className="section-kicker">YOUR DESI BOM</span><h2>Explore the parts</h2>{job.demo ? <div className="demo-alert"><strong>Demo data</strong> · Fixed sample. Extraction, seller checks, prices and compatibility were not verified.</div> : <p className="job-panel-intro">Seller quotes are snapshots. Tax, shipping and the final payable cost are unknown.</p>}<div className="result-list">{job.report.lines.map((line, index) => <article id={`line-${line.item.line_id}`} className="result-row" key={line.item.line_id}><div className="result-title"><ProductImage job={job} line={line} token={token} /><span>Part {index + 1}</span><div><h3>{line.item.raw_name}</h3><p>Qty {line.item.qty ?? 'unknown'}{line.item.qty_source === 'inferred' && <span className="inferred-tag" title={line.item.qty_reason ?? 'Quantity inferred by AI; the source did not state a count.'}>inferred</span>}{line.item.user_has_it ? ' · Already owned' : ''}</p></div></div>{line.item.evidence.length > 0 && <details className="result-evidence"><summary>Saved evidence</summary><ul>{line.item.evidence.map((entry, i) => <li key={i}>{evidenceText(entry)}</li>)}</ul><small>Reported by the extraction model; check the source.</small></details>}<OfferList job={job} line={line} token={token} onJob={onJob} /><Research line={line} />{!job.demo && <RequirementReview key={JSON.stringify(line.item.requirements ?? [])} job={job} line={line} token={token} onJob={onJob} />}{refreshable && !line.item.user_has_it && <label className="refresh-check"><input type="checkbox" checked={refreshIds.includes(line.item.line_id)} onChange={event => setRefreshIds(current => event.target.checked ? [...current, line.item.line_id] : current.filter(id => id !== line.item.line_id))} /> Include in new seller search</label>}</article>)}</div>{!job.demo && <div className="subtotal"><span>{job.report.parts_subtotal_inr ? 'Selected parts subtotal' : 'Partial selected parts subtotal'}</span><strong>{price(job.report.parts_subtotal_inr ?? job.report.selected_parts_subtotal_inr)}</strong></div>}{refreshable && <div className="refresh-controls"><p>New seller search may use paid analysis. Selected parts lose their old quotes; other parts stay saved. {2 - (job.refresh_count ?? 0)} of 2 refresh batches remain.</p><button className="nav-cta" disabled={!refreshIds.length || refreshIds.length > 10 || refreshing} onClick={() => void refresh()}>{refreshing ? 'Starting search…' : `Refresh ${refreshIds.length} selected ${refreshIds.length === 1 ? 'part' : 'parts'}`}</button>{refreshIds.length > 10 && <p>Select at most 10 parts per batch.</p>}{error && <p className="form-error" role="alert">{error}</p>}</div>}<p className="result-disclaimer">Research is AI assessed from source quotes. Seller prices, stock and compatibility claims need your review before ordering. Selecting a quote does not purchase anything.</p></section>
}
