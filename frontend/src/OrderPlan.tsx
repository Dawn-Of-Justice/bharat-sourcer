import { useState, type FormEvent, type ReactNode } from 'react'
import { getPlans, offersOf, reportOf, selectOffer, selectOffers, setImportReferences, type CartPlans, type Job, type OrderPlanLine, type OrderPlanSeller, type ReportLine, type UnsourcedLine } from './api'
import { AmountRow, CostSummary, GradeChip, GstChip, MatchChip, ProductImage, SellerPolicy, StatusChip, TrustBadges, amountText, price, secureLink } from './ReportBits'

type Props = { job: Job; token: string; onJob: (job: Job) => void; readOnly: boolean; renderOffers: (line: ReportLine) => ReactNode; onShowLine: (lineId: string) => void }
const errorText = (cause: unknown, fallback: string) => cause instanceof Error ? cause.message : fallback

// Selection state of one plan line: applied automatically, the user's own choice, or recommended but blocked.
function SelectionBadge({ line, plan }: { line?: ReportLine; plan: OrderPlanLine }) {
  const reasons = line?.recommendation?.reasons ?? []
  if (plan.selection_source === 'user') return <span className="selection-badges"><span className="report-chip choice-user">✓ Your choice</span>{line?.recommendation?.offer_url && line.recommendation.offer_url !== plan.offer_url && <small>Recommended: {line.recommendation.seller ?? 'another listing'}</small>}</span>
  return <span className="selection-badges"><details className="why-popover"><summary><span className="report-chip choice-recommended">★ Recommended</span> why?</summary><div role="note">{reasons.length ? <ul>{reasons.map((reason, index) => <li key={index}>{reason}</li>)}</ul> : <p>No reasons were recorded.</p>}{line?.recommendation?.score != null && <small>Score {line.recommendation.score.toFixed(2)} of 1 · deterministic rules, not an AI pick</small>}</div></details>{plan.selected === false && <span className="report-chip choice-blocked">⚠ Not selected yet</span>}</span>
}

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
  return <li className={`plan-line ${plan.selected === false ? 'plan-line-blocked' : ''}`}>{line ? <ProductImage job={job} line={line} token={token} readOnly={readOnly} /> : null}<div className="plan-line-body"><div className="plan-line-head"><div><strong>{plan.name}</strong>{plan.title && <span className="plan-line-title">{plan.title}</span>}{offer?.match?.variant && <span className="plan-variant">Variant: {offer.match.variant}</span>}</div><div className="plan-line-price"><strong>{price(plan.line_price_inr)}</strong><small>{price(plan.unit_price_inr)} {plan.pack_qty ? `per pack of ${plan.pack_qty}` : 'each'}</small></div></div><p className="plan-qty">Need {plan.qty} · {pack}{spare > 0 ? ` (${spare} spare)` : ''}</p><div className="plan-chips"><SelectionBadge line={line} plan={plan} />{offer && <MatchChip match={offer.match} />}{offer ? <GradeChip compatibility={offer.compatibility} match={offer.match} /> : plan.grade ? <span className="report-chip">Grade {plan.grade}</span> : null}{offer && <GstChip offer={offer} />}</div>{plan.selected === false && plan.blocked_reason && <p className="plan-blocked">Why it is not selected: {plan.blocked_reason}</p>}{plan.changes_required && <div className="plan-changes"><p>⇄ Acknowledge the listed changes before ordering{offer?.compatibility?.changes?.length ? `: ${offer.compatibility.changes.join('; ')}` : '.'}</p>{!readOnly && !job.demo && <button type="button" className="nav-cta" disabled={busy} onClick={() => void acknowledge()}>{busy ? 'Saving…' : 'I reviewed the changes'}</button>}</div>}<div className="plan-line-actions">{secureLink(plan.offer_url) && <a href={plan.offer_url} target="_blank" rel="noopener noreferrer">Product page ↗</a>}{!readOnly && line && <button type="button" className="remove-button" aria-expanded={changing} onClick={() => setChanging(open => !open)}>{changing ? 'Close offers' : 'Change'}</button>}</div>{error && <p className="form-error" role="alert">{error}</p>}{changing && line && <div className="plan-change">{renderOffers(line)}</div>}</div></li>
}

function SellerCard(props: Omit<Props, 'onShowLine'> & { seller: OrderPlanSeller; lines: Map<string, ReportLine> }) {
  const { seller, lines } = props
  const firstOffer = seller.lines?.map(plan => lines.get(plan.line_id) && offersOf(lines.get(plan.line_id)!).find(offer => offer.url === plan.offer_url)).find(Boolean)
  const titles = new Map(seller.lines?.map(plan => [plan.offer_url, plan.name]))
  return <article className="seller-card" aria-label={`Order from ${seller.seller}`}><header className="seller-card-head"><div><span className="section-kicker">SELLER</span><h3>{seller.seller}</h3></div><TrustBadges trust={firstOffer ? firstOffer.trust : undefined} /></header><ul className="plan-lines">{seller.lines?.map(plan => <PlanLine key={plan.line_id} {...props} plan={plan} line={lines.get(plan.line_id)} />)}</ul><dl className="seller-totals"><div className="cost-row"><dt>Subtotal (listed prices)</dt><dd><strong>{price(seller.subtotal_inr)}</strong></dd></div><AmountRow label="GST" amount={seller.gst} /><AmountRow label="Shipping" amount={seller.shipping} /><AmountRow label="Seller estimate" amount={seller.total} /></dl><SellerPolicy seller={seller.seller} gap={seller.free_shipping_gap_inr} policy={seller.policy} />{seller.product_links?.length ? <div className="product-links"><strong>Product pages</strong> <small>Open in new tabs; sellers have no shared cart, so add each part on the seller’s site.</small><ul>{seller.product_links.map(url => secureLink(url) ? <li key={url}><a href={url} target="_blank" rel="noopener noreferrer">{titles.get(url) ?? new URL(url).hostname} ↗</a></li> : null)}</ul></div> : null}</article>
}

const unsourcedLabel: Record<UnsourcedLine['reason'], string> = { pending: '… Pending', needs_value: '? Needs a value', no_offers: '⚠ No verified listing', no_acceptable_offer: '⚠ No acceptable listing', needs_quantity: '? Needs a quantity', cleared_by_user: '✕ Cleared by you' }
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
  return <details className="plan-compare" onToggle={event => { if ((event.target as HTMLDetailsElement).open && !plans && !busy) void load() }}><summary>Compare other plans (cheapest, fewest sellers)</summary>{busy && !plans && <p role="status">Loading plans…</p>}{plans && <><div className="plan-toggle" role="group" aria-label="Plan">{(plans.plans ?? []).map(entry => <button key={entry.kind} type="button" className="nav-cta" aria-pressed={kind === entry.kind} onClick={() => { setKind(entry.kind); setAcknowledged(false) }}>{kind === entry.kind ? '● ' : '○ '}{planNames[entry.kind]}</button>)}</div>{plan ? <div className="plan-preview"><p>{plan.seller_count ?? 0} {plan.seller_count === 1 ? 'seller' : 'sellers'} · estimated total {amountText(plan.costing.total)} <StatusChip amount={plan.costing.total} />{plan.matches_selection ? ' · matches your current selection' : ''}</p><ul>{picks.map(pick => <li key={pick.line_id}>{names[pick.line_id] ?? pick.line_id}: {pick.seller} · {price(pick.price_inr)}{pick.packs && pick.packs > 1 ? ` × ${pick.packs}` : ''}{pick.grade ? ` · grade ${pick.grade}` : ''}{pick.changes_required ? ' · ⇄ changes required' : ''}</li>)}</ul>{plans.uncovered_line_ids?.length ? <p>No selectable listing for: {plans.uncovered_line_ids.map(id => names[id] ?? id).join(', ')}.</p> : null}{plan.kind !== 'recommended' && picks.length > 0 && <>{needsChanges && <label className="offer-ack"><input type="checkbox" checked={acknowledged} onChange={event => setAcknowledged(event.target.checked)} /> I reviewed the required changes for the ⇄ picks</label>}<p>Applying makes these picks your own choices; recommendations will not replace them.</p><button type="button" className="nav-cta" disabled={busy || needsChanges && !acknowledged} onClick={() => void apply()}>{busy ? 'Applying…' : `Apply ${planNames[plan.kind].toLowerCase()} plan`}</button></>}{plans.rules?.length ? <details><summary>How plans are built</summary><ul>{plans.rules.map((rule, index) => <li key={index}>{rule}</li>)}</ul></details> : null}</div> : <p>This plan is not available.</p>}</>}{error && <p className="form-error" role="alert">{error}</p>}</details>
}

// Import comparison: shown only with a baseline; the US reference price form is always available on live reports.
export function ImportCard({ job, token, onJob, readOnly }: { job: Job; token: string; onJob: (job: Job) => void; readOnly: boolean }) {
  const report = reportOf(job)
  const lines = (report?.lines ?? []).filter(line => !line.item.user_has_it)
  const initial = Object.fromEntries(lines.map(line => [line.item.line_id, { price: line.import_reference?.source === 'user' ? line.import_reference.price_usd : '', url: line.import_reference?.source === 'user' ? line.import_reference.source_url ?? '' : '' }]))
  const [values, setValues] = useState(initial)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const baseline = report?.costing?.import_baseline
  const savings = report?.costing?.savings_vs_import
  async function save(event: FormEvent) {
    event.preventDefault()
    const changed = lines.filter(line => values[line.item.line_id].price !== initial[line.item.line_id].price || values[line.item.line_id].url !== initial[line.item.line_id].url)
    if (changed.some(line => values[line.item.line_id].price && !(Number(values[line.item.line_id].price) > 0))) { setError('Enter a positive USD price, or leave it empty to clear.'); return }
    if (changed.some(line => values[line.item.line_id].url && !secureLink(values[line.item.line_id].url))) { setError('Source links must start with https://'); return }
    setBusy(true); setError('')
    try { onJob(await setImportReferences(job.job_id, token, changed.map(line => ({ line_id: line.item.line_id, price_usd: values[line.item.line_id].price || null, source_url: values[line.item.line_id].url || null })))) }
    catch (cause) { setError(errorText(cause, 'Could not save reference prices.')) }
    finally { setBusy(false) }
  }
  if (!report?.costing || (readOnly && !baseline)) return null
  return <section className="import-card" aria-label="Import comparison"><h3>Compared with importing</h3>{baseline ? <><dl><AmountRow label={`Goods ($${baseline.goods_usd} at ₹${baseline.fx_usd_inr}/USD)`} amount={baseline.goods_inr} /><AmountRow label="Courier" amount={baseline.courier_inr} /><AmountRow label="Customs duty and IGST" amount={baseline.duty_inr} /><AmountRow label="Estimated landed cost" amount={baseline.landed_inr} /></dl>{!baseline.complete && <p className="cost-unknown-note">Only some parts have a US reference price, so this covers part of the list.</p>}{savings && <p className="import-savings">{Number(savings.amount_inr) >= 0 ? `Buying in India is estimated ${price(savings.amount_inr)} cheaper.` : `Importing is estimated ${price(Math.abs(Number(savings.amount_inr)))} cheaper.`} <span className="cost-chip cost-estimated">≈ Estimated</span></p>}<details><summary>Formula and dated assumptions (unverified)</summary><pre className="import-formula">{baseline.formula}</pre>{baseline.sources?.length ? <ul>{baseline.sources.map((source, index) => <li key={index}>{source}</li>)}</ul> : null}<small>Duty rates, the exchange rate and the courier fee are dated assumptions, not verified figures or tax advice.</small></details></> : <p>Add a US reference price for some parts to estimate the landed cost of importing them.</p>}{!readOnly && !job.demo && lines.length > 0 && <details className="import-form"><summary>US reference prices</summary><form onSubmit={save}>{lines.map(line => <div className="import-row" key={line.item.line_id}><span>{line.item.raw_name}{line.import_reference?.source === 'research_fact' && <small> · from research: ${line.import_reference.price_usd}</small>}</span><label>USD each<input inputMode="decimal" value={values[line.item.line_id].price} onChange={event => setValues(rows => ({ ...rows, [line.item.line_id]: { ...rows[line.item.line_id], price: event.target.value } }))} /></label><label>Source link<input type="url" placeholder="https://" value={values[line.item.line_id].url} onChange={event => setValues(rows => ({ ...rows, [line.item.line_id]: { ...rows[line.item.line_id], url: event.target.value } }))} /></label></div>)}<p>Saving counts toward your action budget.</p><button className="nav-cta" type="submit" disabled={busy || JSON.stringify(values) === JSON.stringify(initial)}>{busy ? 'Saving…' : 'Save reference prices'}</button>{error && <p className="form-error" role="alert">{error}</p>}</form></details>}</section>
}

export default function OrderPlanView(props: Props) {
  const report = reportOf(props.job)
  const plan = report?.order_plan
  if (!report || !plan) return null
  const lines = new Map(report.lines.map(line => [line.item.line_id, line]))
  const names = Object.fromEntries(report.lines.map(line => [line.item.line_id, line.item.raw_name]))
  const live = !props.readOnly && !props.job.demo
  return <div className="order-plan"><div className="plan-header"><p><strong>{plan.seller_count ?? plan.sellers?.length ?? 0} {(plan.seller_count ?? 0) === 1 ? 'seller' : 'sellers'}</strong> · {plan.ready ? '✓ Every part you need is in a seller group' : '⚠ Some parts still need your input'}</p><p className="plan-disclaimer">{plan.disclaimer || 'Picks are recommendations from seller-published listings. Check each seller page before ordering.'}</p></div>{plan.sellers?.map(seller => <SellerCard key={seller.seller} {...props} seller={seller} lines={lines} />)}<Unsourced entries={plan.unsourced ?? []} onShowLine={props.onShowLine} /><CostSummary costing={plan.costing} title="Plan estimate" lineNames={names} />{live && <PlanCompare job={props.job} token={props.token} onJob={props.onJob} names={names} />}</div>
}
