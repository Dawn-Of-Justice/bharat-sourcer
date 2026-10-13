import { useState, type ReactNode } from 'react'
import {
  offersOf,
  reportOf,
  type Job,
  type OrderPlanLine,
  type OrderPlanSeller,
  type ReportLine,
  type UnsourcedLine,
} from './api'
import { PartThumb, amountText, price } from './ReportBits'
import { sellerName } from './SellerIdentity'
import { reportPartName } from './partName'

type Status = { label: string; tone: 'ok' | 'input' | 'muted' }
// Whole rupees in the list, matching the summary band; the part details keep paise.
const rupees = (value: string | number) => price(value).replace(/\.00(?!\d)/, '')

const unsourcedStatus: Record<UnsourcedLine['reason'], string> = {
  pending: 'Search pending',
  needs_value: 'Needs a value',
  no_offers: 'No seller yet',
  no_acceptable_offer: 'No offer fits',
  needs_quantity: 'Needs a quantity',
  cleared_by_user: 'Cleared by you',
}

// One status per row, the most important first: what the user has to do, then whose pick it is.
export function statusOf(line: ReportLine, plan?: OrderPlanLine, unsourced?: UnsourcedLine): Status {
  if (line.item.user_has_it) return { label: 'You have it', tone: 'muted' }
  if (line.sourcing_error?.code === 'SOURCING_LIMIT') return { label: 'Not searched: run limit', tone: 'input' }
  if (line.sourcing_status === 'failed') return { label: 'Search failed', tone: 'input' }
  if (unsourced)
    return {
      label: unsourcedStatus[unsourced.reason],
      tone: unsourced.reason === 'cleared_by_user' ? 'muted' : 'input',
    }
  if (plan?.selected === false || (!plan && line.recommendation?.blocked_reason && !line.selected_offer_url))
    return { label: 'Confirm seller', tone: 'input' }
  if (plan?.changes_required && !line.changes_accepted) return { label: 'Changes to review', tone: 'input' }
  if (!line.selected_offer_url)
    return { label: offersOf(line).length ? 'Pick a seller' : 'No seller yet', tone: 'input' }
  if (line.selection_source === 'user')
    return { label: line.copied_choice ? 'Copied choice' : 'Your choice', tone: 'ok' }
  return { label: 'Recommended', tone: 'ok' }
}

function Row({
  job,
  token,
  readOnly,
  line,
  plan,
  unsourced,
  showSeller,
  active,
  onOpen,
}: {
  job: Job
  token: string
  readOnly: boolean
  line: ReportLine
  plan?: OrderPlanLine
  unsourced?: UnsourcedLine
  showSeller: boolean
  active: boolean
  onOpen: (lineId: string) => void
}) {
  const offer = offersOf(line).find(entry => entry.url === (plan?.offer_url ?? line.selected_offer_url))
  const amount = plan ? rupees(plan.line_price_inr) : offer && !line.item.user_has_it ? rupees(offer.price_inr) : null
  const pack = plan?.pack_qty ? `${plan.packs} × pack of ${plan.pack_qty}` : null
  const secondary = [showSeller && offer && !line.item.user_has_it ? sellerName(offer) : null, pack]
    .filter(Boolean)
    .join(', ')
  const status = statusOf(line, plan, unsourced)
  return (
    <div id={`line-${line.item.line_id}`} className={`pp-row${active ? ' is-active' : ''}`}>
      <button
        type="button"
        className="pp-row-summary"
        aria-controls="pp-part"
        aria-expanded={active}
        onClick={() => onOpen(line.item.line_id)}
      >
        <PartThumb job={job} line={line} token={token} readOnly={readOnly} />
        <span className="pp-row-name">
          <strong>{reportPartName(line)}</strong>
          {secondary && <small>{secondary}</small>}
        </span>
        <span className="pp-row-qty" aria-label={`Quantity ${line.item.qty ?? 'unknown'}`}>
          ×{line.item.qty ?? '?'}
        </span>
        <span className="pp-row-price">{amount ?? ''}</span>
        <span className={`pp-row-status pp-status-${status.tone}`}>{status.label}</span>
        <span className="pp-row-chevron" aria-hidden="true" />
      </button>
    </div>
  )
}

function sellerTitle(seller: OrderPlanSeller, lines: Map<string, ReportLine>) {
  const offer = seller.lines
    ?.map(plan => {
      const line = lines.get(plan.line_id)
      return line && offersOf(line).find(entry => entry.url === plan.offer_url)
    })
    .find(Boolean)
  return offer && offer.seller_kind !== 'marketplace' ? sellerName(offer) : seller.seller
}

function shippingNote(seller: OrderPlanSeller) {
  if (seller.shipping.status === 'unknown' || !(Number(seller.shipping.amount_inr) > 0)) return undefined
  const shipping = `Shipping ${seller.shipping.status === 'estimated' ? 'about ' : ''}${amountText(seller.shipping)}`
  return seller.free_shipping_gap_inr && Number(seller.free_shipping_gap_inr) > 0
    ? `${shipping}. Add ${rupees(seller.free_shipping_gap_inr)} more for free shipping.`
    : `${shipping}.`
}

type Group = {
  key: string
  title: string
  note?: string
  amount?: string
  lines: ReportLine[]
  seller?: OrderPlanSeller
}

// Add a seller's order to its cart (backend carts.py). Shopify shops take the whole order in one link; WooCommerce
// shops take one part per link; other shops have no add-to-cart link, so their product pages are the way in.
function CartLinks({ seller, names }: { seller: OrderPlanSeller; names: Map<string, ReportLine> }) {
  const entries = seller.lines ?? []
  const added = new Set(seller.cart_line_ids ?? [])
  const name = (id: string) => names.get(id)?.item.raw_name ?? id
  if (seller.cart_url) {
    const rest = entries.filter(entry => !added.has(entry.line_id))
    return (
      <div className="pp-cart">
        <a className="primary-button" href={seller.cart_url} target="_blank" rel="noopener noreferrer">
          Add {added.size} {added.size === 1 ? 'item' : 'items'} to cart <span aria-hidden="true">↗</span>
        </a>
        <p>
          Opens the shop's cart with these quantities, replacing anything already in it.
          {rest.length > 0 && ` Add ${rest.map(entry => name(entry.line_id)).join(', ')} from the product page.`}
        </p>
      </div>
    )
  }
  const single = entries.filter(entry => entry.cart_url)
  if (!single.length) return null
  return (
    <div className="pp-cart">
      <p>This shop adds one part at a time. Each link adds that part with its quantity:</p>
      <ul>
        {single.map(entry => (
          <li key={entry.line_id}>
            <a className="nav-cta" href={entry.cart_url!} target="_blank" rel="noopener noreferrer">
              Add {name(entry.line_id)} ×{entry.packs} <span aria-hidden="true">↗</span>
            </a>
          </li>
        ))}
      </ul>
    </div>
  )
}

// The parts list: grouped by seller (how the user will order) or in parts-list order.
export default function PartsList({
  job,
  token,
  readOnly,
  openLine,
  onOpen,
  attention,
}: {
  job: Job
  token: string
  readOnly: boolean
  openLine: string | null
  onOpen: (lineId: string) => void
  attention?: ReactNode
}) {
  const report = reportOf(job)
  const [grouping, setGrouping] = useState<'seller' | 'part'>('seller')
  if (!report) return null
  const plan = report.order_plan
  const lines = new Map(report.lines.map(line => [line.item.line_id, line]))
  const planLines = new Map(
    (plan?.sellers ?? []).flatMap(seller => (seller.lines ?? []).map(entry => [entry.line_id, entry] as const)),
  )
  const unsourced = new Map((plan?.unsourced ?? []).map(entry => [entry.line_id, entry]))
  const row = (line: ReportLine, showSeller: boolean) => (
    <li key={line.item.line_id}>
      <Row
        job={job}
        token={token}
        readOnly={readOnly}
        line={line}
        plan={planLines.get(line.item.line_id)}
        unsourced={unsourced.get(line.item.line_id)}
        showSeller={showSeller}
        active={openLine === line.item.line_id}
        onOpen={onOpen}
      />
    </li>
  )

  const groups: Group[] = []
  if (grouping === 'seller') {
    if (plan) {
      for (const seller of plan.sellers ?? [])
        groups.push({
          key: seller.seller,
          title: sellerTitle(seller, lines),
          note: shippingNote(seller),
          amount: rupees(seller.subtotal_inr),
          seller,
          lines: (seller.lines ?? [])
            .map(entry => lines.get(entry.line_id))
            .filter((line): line is ReportLine => !!line),
        })
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
    if (waiting.length)
      groups.push({
        key: 'waiting',
        title: 'Not bought yet',
        note: 'These parts are not in the order yet. Open one to see why.',
        lines: waiting,
      })
    if (owned.length) groups.push({ key: 'owned', title: 'You already have', lines: owned })
  }

  return (
    <section className="pp-parts" aria-labelledby="pp-parts-title">
      <header className="pp-parts-head">
        <div className="pp-parts-heading">
          <h2 id="pp-parts-title">
            Your parts <span>{report.lines.length}</span>
          </h2>
          {attention}
        </div>
        <div className="pp-switch" role="group" aria-label="Group parts">
          <button type="button" aria-pressed={grouping === 'seller'} onClick={() => setGrouping('seller')}>
            By seller
          </button>
          <button type="button" aria-pressed={grouping === 'part'} onClick={() => setGrouping('part')}>
            By part
          </button>
        </div>
      </header>
      {grouping === 'part' ? (
        <ul className="pp-rows">{report.lines.map(line => row(line, true))}</ul>
      ) : (
        <div className="pp-groups snap-row" tabIndex={0} role="group" aria-label="Order by seller">
          {groups.map(group => (
            <section key={group.key} className="pp-group" aria-label={group.title}>
              <header className="pp-group-head">
                <div>
                  <h3>{group.title}</h3>
                  {group.note && <p>{group.note}</p>}
                </div>
                {group.amount && <strong>{group.amount}</strong>}
              </header>
              {group.seller && !readOnly && <CartLinks seller={group.seller} names={lines} />}
              <ul className="pp-rows">{group.lines.map(line => row(line, false))}</ul>
            </section>
          ))}
        </div>
      )}
    </section>
  )
}
