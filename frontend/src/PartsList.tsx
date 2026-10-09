import { useState, type ReactNode } from 'react'
import { offersOf, reportOf, type Job, type OrderPlanLine, type OrderPlanSeller, type ReportLine, type UnsourcedLine } from './api'
import { amountText, price } from './ReportBits'
import { sellerName } from './SellerIdentity'

type Status = { label: string; tone: 'ok' | 'input' | 'muted' }
// Whole rupees in the list, matching the summary band; the part details keep paise.
const rupees = (value: string | number) => price(value).replace(/\.00(?!\d)/, '')
export type RenderDetail = (line: ReportLine, unsourced?: UnsourcedLine) => ReactNode

const unsourcedStatus: Record<UnsourcedLine['reason'], string> = { pending: 'Search pending', needs_value: 'Needs a value', no_offers: 'No seller yet', no_acceptable_offer: 'No offer fits', needs_quantity: 'Needs a quantity', cleared_by_user: 'Cleared by you' }

// One status per row, the most important first: what the user has to do, then whose pick it is.
function statusOf(line: ReportLine, plan?: OrderPlanLine, unsourced?: UnsourcedLine): Status {
  if (line.item.user_has_it) return { label: 'You have it', tone: 'muted' }
  if (unsourced) return { label: unsourcedStatus[unsourced.reason], tone: unsourced.reason === 'cleared_by_user' ? 'muted' : 'input' }
  if (plan?.selected === false || (!plan && line.recommendation?.blocked_reason && !line.selected_offer_url)) return { label: 'Confirm seller', tone: 'input' }
  if (plan?.changes_required && !line.changes_accepted) return { label: 'Changes to review', tone: 'input' }
  if (!line.selected_offer_url) return { label: offersOf(line).length ? 'Pick a seller' : 'No seller yet', tone: 'input' }
  if (line.selection_source === 'user') return { label: line.copied_choice ? 'Copied choice' : 'Your choice', tone: 'ok' }
  return { label: 'Recommended', tone: 'ok' }
}

function Row({ line, plan, unsourced, showSeller, renderDetail }: { line: ReportLine; plan?: OrderPlanLine; unsourced?: UnsourcedLine; showSeller: boolean; renderDetail: RenderDetail }) {
  const [imageFailed, setImageFailed] = useState(false)
  const offer = offersOf(line).find(entry => entry.url === (plan?.offer_url ?? line.selected_offer_url))
  const amount = plan ? rupees(plan.line_price_inr) : offer && !line.item.user_has_it ? rupees(offer.price_inr) : null
  const pack = plan?.pack_qty ? `${plan.packs} × pack of ${plan.pack_qty}` : null
  const secondary = [showSeller && offer && !line.item.user_has_it ? sellerName(offer) : null, pack].filter(Boolean).join(', ')
  const status = statusOf(line, plan, unsourced)
  const image = line.line_image?.url
  return <details id={`line-${line.item.line_id}`} className="pp-row">
    <summary className="pp-row-summary">
      <span className="pp-row-thumb" aria-hidden="true">{image && !imageFailed ? <img src={image} alt="" loading="lazy" onError={() => setImageFailed(true)} /> : null}</span>
      <span className="pp-row-name"><strong>{line.item.raw_name}</strong>{secondary && <small>{secondary}</small>}</span>
      <span className="pp-row-qty" aria-label={`Quantity ${line.item.qty ?? 'unknown'}`}>×{line.item.qty ?? '?'}</span>
      <span className="pp-row-price">{amount ?? ''}</span>
      <span className={`pp-row-status pp-status-${status.tone}`}>{status.label}</span>
      <span className="pp-row-chevron" aria-hidden="true" />
    </summary>
    <div className="pp-row-detail">{renderDetail(line, unsourced)}</div>
  </details>
}

function sellerTitle(seller: OrderPlanSeller, lines: Map<string, ReportLine>) {
  const offer = seller.lines?.map(plan => { const line = lines.get(plan.line_id); return line && offersOf(line).find(entry => entry.url === plan.offer_url) }).find(Boolean)
  return offer && offer.seller_kind !== 'marketplace' ? sellerName(offer) : seller.seller
}

function shippingNote(seller: OrderPlanSeller) {
  const shipping = seller.shipping.status === 'unknown' ? 'Shipping not known' : `Shipping ${seller.shipping.status === 'estimated' ? 'about ' : ''}${amountText(seller.shipping)}`
  return seller.free_shipping_gap_inr ? `${shipping}. Add ${rupees(seller.free_shipping_gap_inr)} more for free shipping.` : `${shipping}.`
}

type Group = { key: string; title: string; note?: string; amount?: string; lines: ReportLine[] }

// The parts list: grouped by seller (how the user will order) or in parts-list order.
export default function PartsList({ job, renderDetail }: { job: Job; renderDetail: RenderDetail }) {
  const report = reportOf(job)
  const [grouping, setGrouping] = useState<'seller' | 'part'>('seller')
  if (!report) return null
  const plan = report.order_plan
  const lines = new Map(report.lines.map(line => [line.item.line_id, line]))
  const planLines = new Map((plan?.sellers ?? []).flatMap(seller => (seller.lines ?? []).map(entry => [entry.line_id, entry] as const)))
  const unsourced = new Map((plan?.unsourced ?? []).map(entry => [entry.line_id, entry]))
  const row = (line: ReportLine, showSeller: boolean) => <li key={line.item.line_id}><Row line={line} plan={planLines.get(line.item.line_id)} unsourced={unsourced.get(line.item.line_id)} showSeller={showSeller} renderDetail={renderDetail} /></li>

  const groups: Group[] = []
  if (grouping === 'seller') {
    if (plan) {
      for (const seller of plan.sellers ?? []) groups.push({ key: seller.seller, title: sellerTitle(seller, lines), note: shippingNote(seller), amount: rupees(seller.subtotal_inr), lines: (seller.lines ?? []).map(entry => lines.get(entry.line_id)).filter((line): line is ReportLine => !!line) })
    } else {
      const bySeller = new Map<string, ReportLine[]>()
      for (const line of report.lines) {
        const offer = !line.item.user_has_it && offersOf(line).find(entry => entry.url === line.selected_offer_url)
        if (offer) bySeller.set(sellerName(offer), [...(bySeller.get(sellerName(offer)) ?? []), line])
      }
      for (const [title, entries] of bySeller) groups.push({ key: title, title, lines: entries })
    }
    const placed = new Set(groups.flatMap(group => group.lines.map(line => line.item.line_id)))
    const waiting = report.lines.filter(line => !placed.has(line.item.line_id) && !line.item.user_has_it)
    const owned = report.lines.filter(line => line.item.user_has_it)
    if (waiting.length) groups.push({ key: 'waiting', title: 'Not bought yet', note: 'These parts are not in the order yet. Open one to see why.', lines: waiting })
    if (owned.length) groups.push({ key: 'owned', title: 'You already have', lines: owned })
  }

  return <section className="pp-parts" aria-labelledby="pp-parts-title">
    <header className="pp-parts-head">
      <h2 id="pp-parts-title">Your parts <span>{report.lines.length}</span></h2>
      <div className="pp-switch" role="group" aria-label="Group parts">
        <button type="button" aria-pressed={grouping === 'seller'} onClick={() => setGrouping('seller')}>By seller</button>
        <button type="button" aria-pressed={grouping === 'part'} onClick={() => setGrouping('part')}>By part</button>
      </div>
    </header>
    {grouping === 'part'
      ? <ul className="pp-rows">{report.lines.map(line => row(line, true))}</ul>
      : groups.map(group => <section key={group.key} className="pp-group" aria-label={group.title}>
        <header className="pp-group-head"><div><h3>{group.title}</h3>{group.note && <p>{group.note}</p>}</div>{group.amount && <strong>{group.amount}</strong>}</header>
        <ul className="pp-rows">{group.lines.map(line => row(line, false))}</ul>
      </section>)}
  </section>
}
