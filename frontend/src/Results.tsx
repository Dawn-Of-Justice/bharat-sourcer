import { useState, type FormEvent } from 'react'
import { evidenceText, offersOf, refreshOffers, reportOf, selectOffer, updateRequirements, type BuyableSpec, type Job, type ReportLine, type ResearchAssessment, type PartRequirement } from './api'
import Requirements, { requirementPayload, validRequirements } from './Requirements'
import { CostSummary, GradeChip, GstChip, MatchChip, PackPrice, ProductImage, price, secureLink } from './ReportBits'
import OrderPlanView from './OrderPlan'
import { ExportButtons, ShareControl } from './ReportActions'
import { NeedsYou, SummaryBand } from './ReportSummary'
import CodePatchView from './CodePatch'
import { SellerIdentity, sellerName } from './SellerIdentity'

function Assessment({ value }: { value: ResearchAssessment }) {
  return <div className="research-assessment">
    <strong>AI assessment · {value.status.replaceAll('_', ' ')}</strong>
    <p>{value.explanation}</p>
    {value.conditions.length > 0 && <div className="research-assessment-list"><h5>Conditions to check</h5><ul>{value.conditions.map((condition, index) => <li key={index}>{condition}</li>)}</ul></div>}
    {value.questions.length > 0 && <div className="research-assessment-list"><h5>Questions to resolve</h5><ul>{value.questions.map((question, index) => <li key={index}>{question}</li>)}</ul></div>}
    {value.checks?.length ? <details className="research-facts"><summary>Requirement checks ({value.checks.length})</summary><ul>{value.checks.map((check, index) => <li key={index}><strong>{check.requirement.name}: {check.status.replaceAll('_', ' ')}</strong> · {check.reason}</li>)}</ul></details> : null}
  </div>
}

function Research({ line }: { line: ReportLine }) {
  const research = line.research
  if (!research) return null
  if (research.status === 'skipped') return <details className="research-block research-skipped"><summary>Additional research <span>Not run</span></summary><p>{research.summary}</p><small>No separate AI research review ran for this part. Check the seller page and match details before ordering.</small></details>
  const candidates = research.candidates ?? []
  return <section className="research-block" aria-label={`Research for ${line.item.raw_name}`}>
    <div className="research-heading"><div><span className="section-kicker">SOURCE LEADS</span><h4>Source research</h4></div><span className="research-count">{candidates.length} {candidates.length === 1 ? 'lead' : 'leads'}</span></div>
    <p className="research-summary">{research.summary || `Research ${research.status.replaceAll('_', ' ')}.`}</p>
    {!!research.questions?.length && <div className="research-questions"><strong>Check before choosing a part</strong><ul>{research.questions.map((question, index) => <li key={index}>{question}</li>)}</ul></div>}
    {candidates.map((candidate, index) => <details className="research-candidate" key={`${candidate.url}-${index}`}><summary><span className="candidate-heading"><strong>{candidate.title}</strong><small>{candidate.kind} · {candidate.match} match</small></span><span className={`research-status research-status-${candidate.assessment.status}`}>{candidate.assessment.status.replaceAll('_', ' ')}</span></summary><div className="research-candidate-body"><p className="research-identity"><strong>Identity excerpt</strong> “{candidate.identity_quote}”</p><Assessment value={candidate.assessment} />{candidate.facts?.length ? <details className="research-facts"><summary>Source facts and quotes ({candidate.facts.length})</summary><ul>{candidate.facts.map((fact, i) => <li key={i}><strong>{fact.name}: {fact.value} {fact.unit ?? ''}</strong><br />“{fact.quote}”</li>)}</ul></details> : null}{secureLink(candidate.url) && <a className="research-source-link" href={candidate.url} target="_blank" rel="noopener noreferrer">Review source ↗</a>}</div></details>)}
    {research.sources?.length ? <details className="research-facts research-access"><summary>Source access and review status</summary><ul>{research.sources.map((source, index) => <li key={index}>{secureLink(source.url) ? <a href={source.url} target="_blank" rel="noopener noreferrer">{source.url}</a> : source.url} · {source.status === 'unavailable' ? `Unavailable: ${source.reason ?? 'not readable'}` : source.reviewed ? 'Read for assessment' : 'Discovered, not reviewed'}</li>)}</ul></details> : null}
    <small className="research-disclaimer">AI-reviewed quotes are leads for your own checks, not verified prices or safety certifications.</small>
  </section>
}

// The report carries the exact buying spec used during sourcing, including specs written for older jobs.
function BuyingSpec({ spec }: { spec?: BuyableSpec | null }) {
  if (!spec) return null
  const origin = spec.origin === 'user' ? 'Your saved spec' : spec.origin === 'ai_inferred' ? 'Suggested spec — check values' : 'From the part name and requirements'
  return <div className="report-buying-spec">{spec.needs_value && <p className="needs-value"><strong>⚠ Needs a value</strong> · {spec.needs_value_reason || 'The source did not state the value for this part.'} To improve matching, add the exact value to the part name before refreshing seller search.</p>}<details><summary>Buying spec used for seller search</summary><p>{origin}{spec.part_name ? ` · ${spec.part_name}` : ''}</p><dl><div><dt>Category</dt><dd>{spec.category.replaceAll('_', ' ')}</dd></div><div><dt>Mount</dt><dd>{spec.mount === 'any' ? 'Any' : spec.mount.toUpperCase()}{spec.mount_reason ? ` · ${spec.mount_reason}` : ''}</dd></div>{spec.params.map((param, index) => <div key={index}><dt>{param.name}</dt><dd>{param.value}{param.operator === 'between' && param.value_max ? `–${param.value_max}` : ''}{param.reason ? ` · ${param.reason}` : ''}</dd></div>)}</dl></details></div>
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
  const needsValue = (line.buyable_spec ?? line.item.buyable_spec)?.needs_value === true
  async function choose(url: string | null, changes = false, assessment = false) {
    setBusy(true); setError('')
    try { onJob(await selectOffer(job.job_id, token, line.item.line_id, url, changes, assessment)) }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not update the selection.') }
    finally { setBusy(false) }
  }
  const leads = line.seller_search?.candidate_urls ?? []
  if (!offers.length) return <><div className="offer-search-note" role="status"><strong>{line.sourcing_status === 'already_owned' ? 'Already owned' : 'No verified seller offer yet'}</strong><p>{line.sourcing_status === 'already_owned' ? 'No seller search needed for this part.' : line.sourcing_error?.message || (line.sourcing_status === 'no_verified_offers' ? 'No page passed the current offer checks. Research leads may still be useful.' : 'No verified offer is available yet.')}</p></div>{leads.length > 0 && <details className="result-evidence"><summary>Unverified seller leads ({leads.length})</summary><ul>{leads.map(url => <li key={url}>{secureLink(url) ? <a href={url} target="_blank" rel="noopener noreferrer">{url}</a> : url}</li>)}</ul><small>Search results that did not pass the offer checks. They are not offers; check price and stock yourself.</small></details>}</>
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
    return <article className="offer" key={offer.url}><div><SellerIdentity offer={offer} /><span className="offer-title">{offer.title}{offer.match?.variant ? ` · Variant: ${offer.match.variant}` : ''}</span><span><PackPrice offer={offer} /> · {offer.stock.replaceAll('_', ' ')} · checked {new Date(offer.checked_at).toLocaleString('en-IN')}</span><div className="plan-chips"><MatchChip match={offer.match} /><GradeChip compatibility={offer.compatibility} match={offer.match} /><GstChip offer={offer} />{recommended && <span className="report-chip choice-recommended">★ Recommended</span>}</div><small>Seller-reported quote · shipping depends on the seller’s policy</small>{offer.spec_conflicts?.length ? <details className="spec-conflicts"><summary>Sellers disagree on {offer.spec_conflicts.map(conflict => conflict.field).join(', ')} · values unknown</summary><ul>{offer.spec_conflicts.map(conflict => <li key={conflict.field}><strong>{conflict.field}: unknown</strong><ul>{conflict.candidates.map((candidate, index) => <li key={index}>{candidate.value} · {candidate.source.replaceAll('_', ' ')}{candidate.locator ? ` (${candidate.locator})` : ''}</li>)}</ul></li>)}</ul></details> : null}{changeNeeded && <p>Required changes: {offer.compatibility?.changes?.join('; ') || 'Review the report before accepting.'}</p>}{offer.research_assessment && <Assessment value={offer.research_assessment} />}{selected && <strong>{line.selection_source === 'user' ? line.copied_choice ? '⧉ Copied choice, made by the person who shared this project' : '✓ Your choice' : line.selection_source === 'recommended' ? '★ Recommended pick, applied automatically' : line.research_accepted ? 'Selected with your AI assessment acknowledgement' : 'Selected quote'}</strong>}{eligible && !selected && (changeNeeded || aiChoice || needsValue) && <label className="offer-ack"><input type="checkbox" checked={acknowledged} onChange={event => setAcknowledge(rows => ({ ...rows, [offer.url]: event.target.checked }))} /> I reviewed {needsValue ? 'the missing value and will verify this listing before ordering' : changeNeeded ? 'the required changes' : 'the AI assessment, conditions and unknowns'}</label>}{editable && selected && <button type="button" className="nav-cta" disabled={busy} onClick={() => void choose(null)}>Clear selection</button>}{editable && selected && changeNeeded && line.selection_source !== 'user' && !line.changes_accepted && <><label className="offer-ack"><input type="checkbox" checked={acknowledged} onChange={event => setAcknowledge(rows => ({ ...rows, [offer.url]: event.target.checked }))} /> I reviewed the required changes</label><button type="button" className="nav-cta" disabled={busy || !acknowledged} onClick={() => void choose(offer.url, true)}>Keep this offer</button></>}{eligible && !selected && <button type="button" className="nav-cta" disabled={busy || (changeNeeded || aiChoice || needsValue) && !acknowledged} onClick={() => void choose(offer.url, changeNeeded, aiChoice)}>Select quote</button>}{!eligible && editable && !selected && <small>{!fresh ? 'Quote is older than 24 hours; refresh before selection.' : grade === 'C' || grade === 'D' || grade === 'X' ? 'Grade C, D and X offers can’t be selected yet.' : 'Selection unavailable until stock and compatibility are resolved.'}</small>}</div>{secureLink(offer.url) && <a href={offer.url} target="_blank" rel="noopener noreferrer">Seller page ↗</a>}</article>
  })}{error && <p className="form-error" role="alert">{error}</p>}</div>
}

// The report after sourcing. `shareToken` renders the read-only public share view: no chat, edit, select, refresh or image generation.
export default function Results({ job, token, onJob, shareToken, onOpenChat }: { job: Job; token: string; onJob: (job: Job) => void; shareToken?: string; onOpenChat?: () => void }) {
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
    requestAnimationFrame(() => {
      const card = document.getElementById(`line-${lineId}`) as HTMLDetailsElement | null
      if (card) { card.open = true; card.scrollIntoView({ behavior: 'smooth', block: 'start' }) }
    })
  }
  const offerPicker = (line: ReportLine) => <OfferList job={job} line={line} token={token} onJob={onJob} readOnly={readOnly} />
  return (
    <section className="job-panel report-panel">
      <SummaryBand job={job} actions={<>
        <ExportButtons base={readOnly ? '/v1/shared/' + encodeURIComponent(shareToken!) : '/v1/jobs/' + encodeURIComponent(job.job_id)} token={readOnly ? undefined : token} name={(job.project?.title || 'bharat-sourcer-bom').replace(/[^\w-]+/g, '-').slice(0, 60)} />
        {!readOnly && <ShareControl key={job.job_id} job={job} token={token} />}
      </>} />
      <NeedsYou job={job} readOnly={readOnly} onShowLine={showLine} onOpenChat={onOpenChat} />
      {hasPlan && <div className="report-views" role="group" aria-label="Report view">
        <button type="button" className="nav-cta" aria-pressed={shown === 'plan'} onClick={() => setView('plan')}>Order plan</button>
        <button type="button" className="nav-cta" aria-pressed={shown === 'parts'} onClick={() => setView('parts')}>All parts</button>
      </div>}
      <div className="report-layout report-layout-single">
        <div className="report-main">
          {shown === 'plan'
            ? <OrderPlanView job={job} token={token} onJob={onJob} readOnly={readOnly} renderOffers={offerPicker} onShowLine={showLine} />
            : <>
              <div className="result-list">{report.lines.map((line, index) => {
                const offers = offersOf(line)
                const featured = offers.find(offer => offer.url === line.selected_offer_url)
                  ?? offers.find(offer => offer.url === line.recommendation?.offer_url)
                  ?? offers[0]
                return <details id={`line-${line.item.line_id}`} className="result-card" key={line.item.line_id}>
                  <summary className="result-card-summary">
                    <ProductImage job={job} line={line} token={token} readOnly={readOnly} />
                    <div className="result-card-identity">
                      <small>PART {index + 1} · QTY {line.item.qty ?? 'unknown'}</small>
                      <h3>{line.item.raw_name}</h3>
                      <span>{line.item.user_has_it ? 'Already owned' : featured ? `Seller: ${sellerName(featured)}` : 'No verified seller yet'}</span>
                      {(line.buyable_spec ?? line.item.buyable_spec)?.needs_value && <small className="result-card-note">Value to confirm</small>}
                    </div>
                    <div className="result-card-end">
                      {featured && <strong>{price(featured.price_inr)}</strong>}
                      <span>{featured ? line.selected_offer_url === featured.url ? 'Selected quote' : 'Seller quote' : 'Part details'}</span>
                      <b className="result-card-toggle">View details</b>
                    </div>
                  </summary>
                  <div className="result-card-content">
                    {featured?.title && <p className="result-card-description">{featured.title}</p>}
                    {line.recommendation?.blocked_reason && !line.selected_offer_url && <p className="plan-blocked">Selection pending: {line.recommendation.blocked_reason}</p>}
                    {offerPicker(line)}
                    {!job.demo && !readOnly && <CodePatchView job={job} line={line} token={token} onJob={onJob} />}
                    <div className="result-more">
                      {line.item.evidence.length > 0 && <details className="result-evidence"><summary>Source evidence</summary><ul>{line.item.evidence.map((entry, i) => <li key={i}>{evidenceText(entry)}</li>)}</ul><small>Reported by extraction; check the source.</small></details>}
                      <Research line={line} />
                      <BuyingSpec spec={line.buyable_spec ?? line.item.buyable_spec} />
                      {!job.demo && !readOnly && <RequirementReview key={JSON.stringify(line.item.requirements ?? [])} job={job} line={line} token={token} onJob={onJob} />}
                    </div>
                    {refreshable && !line.item.user_has_it && <label className="refresh-check"><input type="checkbox" checked={refreshIds.includes(line.item.line_id)} onChange={event => setRefreshIds(current => event.target.checked ? [...current, line.item.line_id] : current.filter(id => id !== line.item.line_id))} /> Include in new seller search</label>}
                  </div>
                </details>
              })}</div>
              {report.costing ? <CostSummary costing={report.costing} title={report.costing.complete ? 'Selected parts estimate' : 'Partial estimate (selected parts only)'} lineNames={names} /> : !job.demo && <div className="subtotal"><span>Selected parts subtotal</span><strong>{price(report.parts_subtotal_inr ?? report.selected_parts_subtotal_inr)}</strong></div>}
              {refreshable && <div className="refresh-controls"><p>New seller search may use paid analysis. Selected parts lose their old quotes; other parts stay saved. {2 - (job.refresh_count ?? 0)} of 2 refresh batches remain.</p><button className="nav-cta" disabled={!refreshIds.length || refreshIds.length > 10 || refreshing} onClick={() => void refresh()}>{refreshing ? 'Starting search…' : `Refresh ${refreshIds.length} selected ${refreshIds.length === 1 ? 'part' : 'parts'}`}</button>{refreshIds.length > 10 && <p>Select at most 10 parts per batch.</p>}{error && <p className="form-error" role="alert">{error}</p>}</div>}
            </>}
        </div>
      </div>
    </section>
  )
}
