import { useState, type FormEvent } from 'react'
import { evidenceText, offersOf, refreshOffers, reportOf, selectOffer, updateRequirements, type Job, type ReportLine, type ResearchAssessment, type PartRequirement } from './api'
import Requirements, { requirementPayload, validRequirements } from './Requirements'
import { CostSummary, GradeChip, GstChip, MatchChip, PackPrice, ProductImage, TrustBadges, price, secureLink } from './ReportBits'
import OrderPlanView, { ImportCard } from './OrderPlan'
import Markets from './Markets'
import { ExplainAloud, ExportButtons, ShareControl } from './ReportActions'
import SafetyBanners from './SafetyBanners'

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

// The offer picker, also used by the order plan's Change action. Choosing posts /selections and makes it the user's choice.
function OfferList({ job, line, token, onJob, readOnly }: { job: Job; line: ReportLine; token: string; onJob: (job: Job) => void; readOnly: boolean }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [acknowledge, setAcknowledge] = useState<Record<string, boolean>>({})
  const offers = offersOf(line)
  const editable = !job.demo && !readOnly
  async function choose(url: string | null, changes = false, assessment = false) {
    setBusy(true); setError('')
    try { onJob(await selectOffer(job.job_id, token, line.item.line_id, url, changes, assessment)) }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not update the selection.') }
    finally { setBusy(false) }
  }
  const leads = line.seller_search?.candidate_urls ?? []
  if (!offers.length) return <><p className="result-status">{line.sourcing_status === 'already_owned' ? 'Already owned; no seller search needed.' : line.sourcing_error?.message || (line.sourcing_status === 'no_verified_offers' ? 'No page passed the current offer checks. Research leads may still be useful.' : 'No verified offer is available yet.')}</p>{leads.length > 0 && <details className="result-evidence"><summary>Unverified seller leads ({leads.length})</summary><ul>{leads.map(url => <li key={url}>{secureLink(url) ? <a href={url} target="_blank" rel="noopener noreferrer">{url}</a> : url}</li>)}</ul><small>Search results that did not pass the offer checks. They are not offers; check price and stock yourself.</small></details>}</>
  return <div className="offers-list"><h4>Verified seller page quotes</h4>{offers.map(offer => {
    const selected = line.selected_offer_url === offer.url
    const grade = offer.compatibility?.grade
    const changeNeeded = grade === 'B'
    const judged = !grade && (offer.match?.status === 'exact' || offer.match?.status === 'compatible')
    const aiChoice = !grade && !judged && offer.research_assessment?.status === 'potential_match'
    const fresh = Date.now() - Date.parse(offer.checked_at) < 24 * 60 * 60 * 1000
    const eligible = editable && offer.stock === 'in_stock' && fresh && (grade === 'A' || changeNeeded || judged || aiChoice)
    const acknowledged = acknowledge[offer.url] ?? false
    const recommended = line.recommendation?.offer_url === offer.url
    return <article className="offer" key={offer.url}><div><strong>{offer.seller}</strong><TrustBadges trust={offer.trust} /><span className="offer-title">{offer.title}{offer.match?.variant ? ` · Variant: ${offer.match.variant}` : ''}</span><span><PackPrice offer={offer} /> · {offer.stock.replaceAll('_', ' ')} · checked {new Date(offer.checked_at).toLocaleString('en-IN')}</span><div className="plan-chips"><MatchChip match={offer.match} /><GradeChip compatibility={offer.compatibility} match={offer.match} /><GstChip offer={offer} />{recommended && <span className="report-chip choice-recommended">★ Recommended</span>}</div><small>Seller-reported quote · shipping depends on the seller’s policy</small>{offer.spec_conflicts?.length ? <details className="spec-conflicts"><summary>Sellers disagree on {offer.spec_conflicts.map(conflict => conflict.field).join(', ')} · values unknown</summary><ul>{offer.spec_conflicts.map(conflict => <li key={conflict.field}><strong>{conflict.field}: unknown</strong><ul>{conflict.candidates.map((candidate, index) => <li key={index}>{candidate.value} · {candidate.source.replaceAll('_', ' ')}{candidate.locator ? ` (${candidate.locator})` : ''}</li>)}</ul></li>)}</ul></details> : null}{changeNeeded && <p>Required changes: {offer.compatibility?.changes?.join('; ') || 'Review the report before accepting.'}</p>}{offer.research_assessment && <Assessment value={offer.research_assessment} />}{selected && <strong>{line.selection_source === 'user' ? '✓ Your choice' : line.selection_source === 'recommended' ? '★ Recommended pick, applied automatically' : line.research_accepted ? 'Selected with your AI assessment acknowledgement' : 'Selected quote'}</strong>}{eligible && !selected && (changeNeeded || aiChoice) && <label className="offer-ack"><input type="checkbox" checked={acknowledged} onChange={event => setAcknowledge(rows => ({ ...rows, [offer.url]: event.target.checked }))} /> I reviewed {changeNeeded ? 'the required changes' : 'the AI assessment, conditions and unknowns'}</label>}{editable && selected && <button type="button" className="nav-cta" disabled={busy} onClick={() => void choose(null)}>Clear selection</button>}{editable && selected && changeNeeded && line.selection_source !== 'user' && !line.changes_accepted && <><label className="offer-ack"><input type="checkbox" checked={acknowledged} onChange={event => setAcknowledge(rows => ({ ...rows, [offer.url]: event.target.checked }))} /> I reviewed the required changes</label><button type="button" className="nav-cta" disabled={busy || !acknowledged} onClick={() => void choose(offer.url, true)}>Keep this offer</button></>}{eligible && !selected && <button type="button" className="nav-cta" disabled={busy || (changeNeeded || aiChoice) && !acknowledged} onClick={() => void choose(offer.url, changeNeeded, aiChoice)}>Select quote</button>}{!eligible && editable && !selected && <small>{!fresh ? 'Quote is older than 24 hours; refresh before selection.' : grade === 'C' || grade === 'D' || grade === 'X' ? 'Grade C, D and X offers can’t be selected yet.' : 'Selection unavailable until stock and compatibility are resolved.'}</small>}</div>{secureLink(offer.url) && <a href={offer.url} target="_blank" rel="noopener noreferrer">Seller page ↗</a>}</article>
  })}{error && <p className="form-error" role="alert">{error}</p>}</div>
}

// The report after sourcing. `shareToken` renders the read-only public share view: no chat, edit, select, refresh or image generation.
export default function Results({ job, token, onJob, shareToken }: { job: Job; token: string; onJob: (job: Job) => void; shareToken?: string }) {
  const report = reportOf(job)
  const readOnly = !!shareToken
  const [view, setView] = useState<'plan' | 'parts'>(report?.order_plan ? 'plan' : 'parts')
  const [refreshIds, setRefreshIds] = useState<string[]>([])
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState('')
  if (!report) return null
  const hasPlan = !!report.order_plan
  const shown = hasPlan ? view : 'parts'
  const refreshable = !readOnly && !job.demo && job.status === 'done' && (job.refresh_count ?? 0) < 2
  const names = Object.fromEntries(report.lines.map(line => [line.item.line_id, line.item.raw_name]))
  async function refresh() {
    setRefreshing(true); setError('')
    try { await refreshOffers(job.job_id, token, refreshIds); setRefreshIds([]); onJob(await import('./api').then(api => api.getJob(job.job_id, token))) }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not start a seller refresh. Check the saved job before retrying.') }
    finally { setRefreshing(false) }
  }
  function showLine(lineId: string) {
    setView('parts')
    requestAnimationFrame(() => document.getElementById(`line-${lineId}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' }))
  }
  const offerPicker = (line: ReportLine) => <OfferList job={job} line={line} token={token} onJob={onJob} readOnly={readOnly} />
  const cost = job.cost_estimate?.total_usd
  return <section className="job-panel"><span className="section-kicker">YOUR DESI BOM</span><h2>{hasPlan && shown === 'plan' ? 'Your order plan' : 'Explore the parts'}</h2>{job.demo ? <div className="demo-alert"><strong>Demo data</strong> · Fixed sample. Extraction, seller checks, prices and compatibility were not verified.</div> : <p className="job-panel-intro">{hasPlan ? `Parts were picked and grouped by seller to save shipping.${readOnly ? '' : ' Change any pick;'} Prices are seller snapshots and totals are estimates.` : 'Seller quotes are snapshots. Tax, shipping and the final payable cost are estimates at best.'}</p>}<SafetyBanners flags={job.safety_flags} lineNames={names} /><div className="report-toolbar"><ExportButtons base={readOnly ? '/v1/shared/' + encodeURIComponent(shareToken!) : '/v1/jobs/' + encodeURIComponent(job.job_id)} token={readOnly ? undefined : token} name={(job.project?.title || 'bharat-sourcer-bom').replace(/[^\w-]+/g, '-').slice(0, 60)} />{!readOnly && <ShareControl job={job} token={token} />}</div>{!readOnly && <ExplainAloud job={job} token={token} />}{hasPlan && <div className="report-views" role="group" aria-label="Report view"><button type="button" className="nav-cta" aria-pressed={shown === 'plan'} onClick={() => setView('plan')}>{shown === 'plan' ? '● ' : '○ '}Order plan</button><button type="button" className="nav-cta" aria-pressed={shown === 'parts'} onClick={() => setView('parts')}>{shown === 'parts' ? '● ' : '○ '}All parts and offers</button></div>}{shown === 'plan' ? <OrderPlanView job={job} token={token} onJob={onJob} readOnly={readOnly} renderOffers={offerPicker} onShowLine={showLine} /> : <><div className="result-list">{report.lines.map((line, index) => <article id={`line-${line.item.line_id}`} className="result-row" key={line.item.line_id}><div className="result-title"><ProductImage job={job} line={line} token={token} readOnly={readOnly} /><span>Part {index + 1}</span><div><h3>{line.item.raw_name}</h3><p>Qty {line.item.qty ?? 'unknown'}{line.item.qty_source === 'inferred' && <span className="inferred-tag" title={line.item.qty_reason ?? 'Quantity inferred by AI; the source did not state a count.'}>inferred</span>}{line.item.user_has_it ? ' · Already owned' : ''}{line.selection_source === 'user' ? ' · ✓ Your choice' : line.selection_source === 'recommended' ? ' · ★ Recommended pick' : ''}</p>{line.recommendation?.blocked_reason && !line.selected_offer_url && <p className="plan-blocked">Recommended, not selected: {line.recommendation.blocked_reason}</p>}</div></div>{line.item.evidence.length > 0 && <details className="result-evidence"><summary>Saved evidence</summary><ul>{line.item.evidence.map((entry, i) => <li key={i}>{evidenceText(entry)}</li>)}</ul><small>Reported by the extraction model; check the source.</small></details>}{offerPicker(line)}<Research line={line} />{!job.demo && !readOnly && <RequirementReview key={JSON.stringify(line.item.requirements ?? [])} job={job} line={line} token={token} onJob={onJob} />}{refreshable && !line.item.user_has_it && <label className="refresh-check"><input type="checkbox" checked={refreshIds.includes(line.item.line_id)} onChange={event => setRefreshIds(current => event.target.checked ? [...current, line.item.line_id] : current.filter(id => id !== line.item.line_id))} /> Include in new seller search</label>}</article>)}</div>{report.costing ? <CostSummary costing={report.costing} title={report.costing.complete ? 'Selected parts estimate' : 'Partial estimate (selected parts only)'} lineNames={names} /> : !job.demo && <div className="subtotal"><span>{report.parts_subtotal_inr ? 'Selected parts subtotal' : 'Partial selected parts subtotal'}</span><strong>{price(report.parts_subtotal_inr ?? report.selected_parts_subtotal_inr)}</strong></div>}{refreshable && <div className="refresh-controls"><p>New seller search may use paid analysis. Selected parts lose their old quotes; other parts stay saved. {2 - (job.refresh_count ?? 0)} of 2 refresh batches remain.</p><button className="nav-cta" disabled={!refreshIds.length || refreshIds.length > 10 || refreshing} onClick={() => void refresh()}>{refreshing ? 'Starting search…' : `Refresh ${refreshIds.length} selected ${refreshIds.length === 1 ? 'part' : 'parts'}`}</button>{refreshIds.length > 10 && <p>Select at most 10 parts per batch.</p>}{error && <p className="form-error" role="alert">{error}</p>}</div>}</>}<ImportCard key={JSON.stringify(report.lines.map(line => line.import_reference ?? null))} job={job} token={token} onJob={onJob} readOnly={readOnly} />{!readOnly && <Markets job={job} token={token} />}{cost != null && !readOnly && <p className="report-diagnostics">Estimated AI cost for this project: ${cost.toFixed(cost < 0.1 ? 4 : 2)} · estimated from token counts, not a charge{job.cost_estimate?.budget_reached ? ' · this run reached its AI budget' : ''}.</p>}<p className="result-disclaimer">Research is AI assessed from source quotes. Seller prices, stock and compatibility claims need your review before ordering. Selecting a quote does not purchase anything.</p></section>
}
