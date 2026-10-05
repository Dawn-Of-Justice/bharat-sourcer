import { useState, type FormEvent } from 'react'
import { refreshOffers, selectOffer, updateRequirements, type Job, type ReportLine, type ResearchAssessment, type PartRequirement } from './api'
import Requirements, { validRequirements } from './Requirements'

const money = new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR' })
const price = (value: string) => money.format(Number(value))
const secureLink = (url: string) => /^https:\/\/[^\s]+$/i.test(url) ? url : undefined

function ProductImage({ url, name, demo }: { url?: string | null; name: string; demo: boolean }) {
  const [failed, setFailed] = useState(false)
  const source = url ? (secureLink(url) || (demo && url === '/preview-part.svg' ? url : undefined)) : undefined
  return <div className="product-image">{source && !failed ? <img src={source} alt={`Seller image for ${name}`} loading="lazy" referrerPolicy="no-referrer" onError={() => setFailed(true)} /> : <span>Image<br />unavailable</span>}</div>
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
  async function save(event: FormEvent) {
    event.preventDefault()
    if (!validRequirements(requirements)) { setError('Every requirement needs a property and value.'); return }
    setBusy(true); setError('')
    try { onJob(await updateRequirements(job.job_id, token, line.item.line_id, requirements.map(({ name, value, unit, operator }) => ({ name: name.trim(), value: value.trim(), unit: unit?.trim() || null, operator })))) }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not save requirements.') }
    finally { setBusy(false) }
  }
  return <details className="requirements-after"><summary>Review or change build requirements ({line.item.requirements?.length ?? 0})</summary><form onSubmit={save}><Requirements value={requirements} onChange={setRequirements} disabled={busy} /><p>Changing requirements may make AI assessments stale and clear affected selections. Refresh is a separate action.</p><button className="nav-cta" type="submit" disabled={busy || JSON.stringify(requirements) === original}>{busy ? 'Saving…' : 'Save requirements'}</button>{error && <p className="form-error" role="alert">{error}</p>}</form></details>
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
    return <article className="offer" key={offer.url}><div><strong>{offer.seller}</strong><span>{price(offer.price_inr)} per piece · {offer.stock.replaceAll('_', ' ')} · checked {new Date(offer.checked_at).toLocaleString('en-IN')}</span><small>Seller-reported quote · shipping and tax unknown</small>{offer.compatibility && <p>Declared-spec grade {offer.compatibility.grade ?? 'unknown'}: {offer.compatibility.reasons.join(' ')} {offer.compatibility.missing_fields.length ? `Missing: ${offer.compatibility.missing_fields.join(', ')}.` : ''}</p>}{changeNeeded && <p>Required changes: {offer.compatibility?.changes.join('; ') || 'Review the report before accepting.'}</p>}{offer.research_assessment && <Assessment value={offer.research_assessment} />}{selected && <strong>{line.research_accepted ? 'Selected with your AI assessment acknowledgement' : 'Selected quote'}</strong>}{eligible && !selected && (changeNeeded || aiChoice) && <label className="offer-ack"><input type="checkbox" checked={acknowledged} onChange={event => setAcknowledge(rows => ({ ...rows, [offer.url]: event.target.checked }))} /> I reviewed {changeNeeded ? 'the required changes' : 'the AI assessment, conditions and unknowns'}</label>}{!job.demo && selected && <button type="button" className="nav-cta" disabled={busy} onClick={() => void choose(null)}>Clear selection</button>}{eligible && !selected && <button type="button" className="nav-cta" disabled={busy || (changeNeeded || aiChoice) && !acknowledged} onClick={() => void choose(offer.url, changeNeeded, aiChoice)}>Select quote</button>}{!eligible && !job.demo && <small>{!fresh ? 'Quote is older than 24 hours; refresh before selection.' : 'Selection unavailable until stock and compatibility are resolved.'}</small>}</div>{secureLink(offer.url) && <a href={offer.url} target="_blank" rel="noopener noreferrer">Seller page ↗</a>}</article>
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
  return <section className="job-panel"><span className="section-kicker">YOUR DESI BOM</span><h2>Explore the parts</h2>{job.demo ? <div className="demo-alert"><strong>Demo data</strong> · Fixed sample. Extraction, seller checks, prices and compatibility were not verified.</div> : <p className="job-panel-intro">Seller quotes are snapshots. Tax, shipping and the final payable cost are unknown.</p>}<div className="result-list">{job.report.lines.map((line, index) => <article id={`line-${line.item.line_id}`} className="result-row" key={line.item.line_id}><div className="result-title"><ProductImage url={line.offers.find(offer => offer.image_url)?.image_url} name={line.item.raw_name} demo={job.demo} /><span>Part {index + 1}</span><div><h3>{line.item.raw_name}</h3><p>Qty {line.item.qty ?? 'unknown'}{line.item.user_has_it ? ' · Already owned' : ''}</p>{line.offers.some(offer => offer.image_url) && <small>Seller image · visual reference only</small>}</div></div>{line.item.evidence.length > 0 && <details className="result-evidence"><summary>Saved video evidence</summary><ul>{line.item.evidence.map((entry, i) => <li key={i}>{entry.timestamp} — {entry.observation}</li>)}</ul><small>Reported by the extraction model; check the video.</small></details>}<OfferList job={job} line={line} token={token} onJob={onJob} /><Research line={line} />{!job.demo && <RequirementReview key={JSON.stringify(line.item.requirements ?? [])} job={job} line={line} token={token} onJob={onJob} />}{refreshable && !line.item.user_has_it && <label className="refresh-check"><input type="checkbox" checked={refreshIds.includes(line.item.line_id)} onChange={event => setRefreshIds(current => event.target.checked ? [...current, line.item.line_id] : current.filter(id => id !== line.item.line_id))} /> Include in new seller search</label>}</article>)}</div>{!job.demo && <div className="subtotal"><span>{job.report.parts_subtotal_inr ? 'Selected parts subtotal' : 'Partial selected parts subtotal'}</span><strong>{price(job.report.parts_subtotal_inr ?? job.report.selected_parts_subtotal_inr)}</strong></div>}{refreshable && <div className="refresh-controls"><p>New seller search may use paid analysis. Selected parts lose their old quotes; other parts stay saved. {2 - (job.refresh_count ?? 0)} of 2 refresh batches remain.</p><button className="nav-cta" disabled={!refreshIds.length || refreshIds.length > 10 || refreshing} onClick={() => void refresh()}>{refreshing ? 'Starting search…' : `Refresh ${refreshIds.length} selected ${refreshIds.length === 1 ? 'part' : 'parts'}`}</button>{refreshIds.length > 10 && <p>Select at most 10 parts per batch.</p>}{error && <p className="form-error" role="alert">{error}</p>}</div>}<p className="result-disclaimer">Research is AI assessed from source quotes. Seller prices, stock and compatibility claims need your review before ordering. Selecting a quote does not purchase anything.</p></section>
}
