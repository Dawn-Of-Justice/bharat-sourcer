import { useState, type ReactNode } from 'react'
import { getPlans, offersOf, reportOf, selectOffer, selectOffers, type CartPlans, type Job, type OrderPlanLine, type OrderPlanSeller, type ReportLine, type UnsourcedLine } from './api'
import { CostSummary, GradeChip, GstChip, MatchChip, ProductImage, TrustBadges, amountText, price, secureLink } from './ReportBits'

type Props = { job: Job; token: string; onJob: (job: Job) => void; readOnly: boolean; renderOffers: (line: ReportLine) => ReactNode; onShowLine: (lineId: string) => void }
const errorText = (cause: unknown, fallback: string) => cause instanceof Error ? cause.message : fallback

function PlanLine({ job, token, onJob, readOnly, renderOffers, plan, line }: Omit<Props, 'onShowLine'> & { plan: OrderPlanLine; line?: ReportLine }) {
  const [changing, setChanging] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const offer = line && offersOf(line).find(entry => entry.url === plan.offer_url)
  const pack = plan.pack_qty ? `${plan.packs} × pack of ${plan.pack_qty} = ${plan.units} units` : `${plan.units} ${plan.units === 1 ? 'unit' : 'units'}`
  const spare = plan.units - plan.qty
  async function acknowledge() {
    setBusy(true); setError('')
    try { onJob(await selectOffer(job.job_id, token, plan.line_id, plan.offer_url, true)) }
    catch (cause) { setError(errorText(cause, 'Could not save the acknowledgement.')) }
    finally { setBusy(false) }
  }
  return <li className="plan-line">
    <details className="plan-line-card">
      <summary className="plan-line-summary">
        {line && <ProductImage job={job} line={line} token={token} readOnly={readOnly} />}
        <div className="plan-line-identity">
          <strong>{plan.name}</strong>
          <span>Need {plan.qty} · {offer?.seller ?? 'Seller listing'}</span>
          {plan.selected === false && <small>Selection pending</small>}
          {plan.changes_required && <small>Changes to review</small>}
        </div>
        <div className="plan-line-price"><strong>{price(plan.line_price_inr)}</strong><small>{price(plan.unit_price_inr)} {plan.pack_qty ? `per pack of ${plan.pack_qty}` : 'each'}</small><b className="result-card-toggle">View details</b></div>
      </summary>
      <div className="plan-line-content">
        {plan.title && <p className="result-card-description">{plan.title}</p>}
        {offer?.match?.variant && <p className="plan-variant">Variant: {offer.match.variant}</p>}
        <p className="plan-qty">Need {plan.qty} · {pack}{spare > 0 ? ` (${spare} spare)` : ''}</p>
        <div className="plan-chips">
          <span className={`report-chip ${plan.selection_source === 'user' ? 'choice-user' : 'choice-recommended'}`}>{plan.selection_source === 'user' ? 'Your choice' : 'Recommended'}</span>
          {offer && <MatchChip match={offer.match} />}
          {offer ? <GradeChip compatibility={offer.compatibility} match={offer.match} /> : plan.grade ? <span className="report-chip">Grade {plan.grade}</span> : null}
          {offer && <GstChip offer={offer} />}
        </div>
        {plan.selection_source === 'user' && line?.recommendation?.offer_url && line.recommendation.offer_url !== plan.offer_url && <p className="plan-qty">Recommended alternative: {line.recommendation.seller ?? 'another listing'}</p>}
        {!!line?.recommendation?.reasons?.length && <details className="plan-reasons"><summary>Why this listing was recommended</summary><ul>{line.recommendation.reasons.map((reason, index) => <li key={index}>{reason}</li>)}</ul></details>}
        {plan.selected === false && plan.blocked_reason && <p className="plan-blocked">Selection pending: {plan.blocked_reason}</p>}
        {plan.changes_required && <div className="plan-changes"><p>Review required changes before ordering{offer?.compatibility?.changes?.length ? `: ${offer.compatibility.changes.join('; ')}` : '.'}</p>{!readOnly && !job.demo && <button type="button" className="nav-cta" disabled={busy} onClick={() => void acknowledge()}>{busy ? 'Saving…' : 'I reviewed the changes'}</button>}</div>}
        <div className="plan-line-actions">{secureLink(plan.offer_url) && <a href={plan.offer_url} target="_blank" rel="noopener noreferrer">Open seller page ↗</a>}{!readOnly && line && <button type="button" className="report-action" aria-expanded={changing} onClick={() => setChanging(open => !open)}>{changing ? 'Close seller options' : 'Change seller'}</button>}</div>
        {error && <p className="form-error" role="alert">{error}</p>}
        {changing && line && <div className="plan-change">{renderOffers(line)}</div>}
      </div>
    </details>
  </li>
}

function SellerCard(props: Omit<Props, 'onShowLine'> & { seller: OrderPlanSeller; lines: Map<string, ReportLine> }) {
  const { seller, lines } = props
  const firstOffer = seller.lines?.map(plan => lines.get(plan.line_id) && offersOf(lines.get(plan.line_id)!).find(offer => offer.url === plan.offer_url)).find(Boolean)
  const titles = new Map(seller.lines?.map(plan => [plan.offer_url, plan.name]))
  return <article className="seller-card" aria-label={`Order from ${seller.seller}`}><header className="seller-card-head"><div><span className="section-kicker">SELLER</span><h3>{seller.seller}</h3></div><TrustBadges trust={firstOffer ? firstOffer.trust : undefined} /></header><ul className="plan-lines">{seller.lines?.map(plan => <PlanLine key={plan.line_id} {...props} plan={plan} line={lines.get(plan.line_id)} />)}</ul><dl className="seller-totals"><div className="cost-row"><dt>Subtotal</dt><dd><strong>{price(seller.subtotal_inr)}</strong></dd></div></dl>{seller.product_links?.length ? <div className="product-links"><strong>Product pages</strong> <small>Open each part on the seller’s site.</small><ul>{seller.product_links.map(url => secureLink(url) ? <li key={url}><a href={url} target="_blank" rel="noopener noreferrer">{titles.get(url) ?? new URL(url).hostname} ↗</a></li> : null)}</ul></div> : null}</article>
}

const unsourcedLabel: Record<UnsourcedLine['reason'], string> = { pending: 'Search pending', needs_value: 'Value needed', no_offers: 'No verified listing', no_acceptable_offer: 'No suitable listing', needs_quantity: 'Quantity needed', cleared_by_user: 'Cleared by you' }
function Unsourced({ entries, onShowLine }: { entries: UnsourcedLine[]; onShowLine: (lineId: string) => void }) {
  if (!entries.length) return null
  return <section className="unsourced-group" aria-label="Parts not in the order plan"><h3>Not in the plan yet ({entries.length})</h3><ul>{entries.map(entry => <li key={entry.line_id}><div className="unsourced-head"><strong>{entry.name}</strong><span className="report-chip">{unsourcedLabel[entry.reason]}</span></div><p>{entry.message}</p>{entry.next_steps?.length ? <ul className="next-steps">{entry.next_steps.map((step, index) => <li key={index}>{step}</li>)}</ul> : null}{entry.research_urls?.length ? <p className="research-links">Research candidates (unverified leads): {entry.research_urls.map(url => secureLink(url) ? <a key={url} href={url} target="_blank" rel="noopener noreferrer">{new URL(url).hostname} ↗</a> : null)}</p> : null}<button type="button" className="remove-button" onClick={() => onShowLine(entry.line_id)}>Show part details, requirements and refresh</button></li>)}</ul></section>
}

const planNames = { recommended: 'Recommended', cheapest: 'Cheapest', fewest_sellers: 'Fewest sellers' }
// Plans preview picks and totals; only an explicit Apply posts them to /selections.
function PlanCompare({ job, token, onJob, names }: { job: Job; token: string; onJob: (job: Job) => void; names: Record<string, string> }) {
  const [plans, setPlans] = useState<CartPlans | null>(null)
  const [kind, setKind] = useState<'recommended' | 'cheapest' | 'fewest_sellers'>('cheapest')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [acknowledged, setAcknowledged] = useState(false)
  async function load() {
    setBusy(true); setError('')
    try { setPlans(await getPlans(job.job_id, token)) }
    catch (cause) { setError(errorText(cause, 'Could not load plans.')) }
    finally { setBusy(false) }
  }
  const plan = plans?.plans?.find(entry => entry.kind === kind)
  const picks = plan?.picks ?? []
  const needsChanges = picks.some(pick => pick.changes_required)
  async function apply() {
    setBusy(true); setError('')
    try { onJob(await selectOffers(job.job_id, token, picks.map(pick => ({ line_id: pick.line_id, offer_url: pick.offer_url, accept_changes: !!pick.changes_required })))); setPlans(null); setAcknowledged(false) }
    catch (cause) { setError(errorText(cause, 'Could not apply the plan.')) }
    finally { setBusy(false) }
  }
  return <details className="plan-compare" onToggle={event => { if ((event.target as HTMLDetailsElement).open && !plans && !busy) void load() }}><summary>Compare other plans (cheapest, fewest sellers)</summary>{busy && !plans && <p role="status">Loading plans…</p>}{plans && <><div className="plan-toggle" role="group" aria-label="Plan">{(plans.plans ?? []).map(entry => <button key={entry.kind} type="button" className="nav-cta" aria-pressed={kind === entry.kind} onClick={() => { setKind(entry.kind); setAcknowledged(false) }}>{kind === entry.kind ? '● ' : '○ '}{planNames[entry.kind]}</button>)}</div>{plan ? <div className="plan-preview"><p>{plan.seller_count ?? 0} {plan.seller_count === 1 ? 'seller' : 'sellers'} · subtotal {amountText(plan.costing.parts)}{plan.matches_selection ? ' · matches your current selection' : ''}</p><ul>{picks.map(pick => <li key={pick.line_id}>{names[pick.line_id] ?? pick.line_id}: {pick.seller} · {price(pick.price_inr)}{pick.packs && pick.packs > 1 ? ` × ${pick.packs}` : ''}{pick.grade ? ` · grade ${pick.grade}` : ''}{pick.changes_required ? ' · ⇄ changes required' : ''}</li>)}</ul>{plans.uncovered_line_ids?.length ? <p>No selectable listing for: {plans.uncovered_line_ids.map(id => names[id] ?? id).join(', ')}.</p> : null}{plan.kind !== 'recommended' && picks.length > 0 && <>{needsChanges && <label className="offer-ack"><input type="checkbox" checked={acknowledged} onChange={event => setAcknowledged(event.target.checked)} /> I reviewed the required changes for the ⇄ picks</label>}<p>Applying makes these picks your own choices; recommendations will not replace them.</p><button type="button" className="nav-cta" disabled={busy || needsChanges && !acknowledged} onClick={() => void apply()}>{busy ? 'Applying…' : `Apply ${planNames[plan.kind].toLowerCase()} plan`}</button></>}{plans.rules?.length ? <details><summary>How plans are built</summary><ul>{plans.rules.map((rule, index) => <li key={index}>{rule}</li>)}</ul></details> : null}</div> : <p>This plan is not available.</p>}</>}{error && <p className="form-error" role="alert">{error}</p>}</details>
}

export default function OrderPlanView(props: Props) {
  const report = reportOf(props.job)
  const plan = report?.order_plan
  if (!report || !plan) return null
  const lines = new Map(report.lines.map(line => [line.item.line_id, line]))
  const names = Object.fromEntries(report.lines.map(line => [line.item.line_id, line.item.raw_name]))
  const live = !props.readOnly && !props.job.demo
  return <div className="order-plan">{plan.sellers?.map(seller => <SellerCard key={seller.seller} {...props} seller={seller} lines={lines} />)}<Unsourced entries={plan.unsourced ?? []} onShowLine={props.onShowLine} /><CostSummary costing={plan.costing} title="Plan subtotal" lineNames={names} />{live && <PlanCompare job={props.job} token={props.token} onJob={props.onJob} names={names} />}</div>
}
