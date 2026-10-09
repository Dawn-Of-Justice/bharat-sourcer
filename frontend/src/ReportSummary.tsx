import { useState, type ReactNode } from 'react'
import { offersOf, reportOf, type Job, type SafetyFlag, type UnsourcedLine } from './api'
import { amountText } from './ReportBits'

// The results stage's headline: what the plan costs, how many parts it covers, from how many
// sellers, and what is still unknown. Report actions (PDF, share) sit beside it.
export function SummaryBand({ job, actions }: { job: Job; actions?: ReactNode }) {
  const report = reportOf(job)
  if (!report) return null
  const plan = report.order_plan
  const costing = plan?.costing ?? report.costing
  const needed = job.items.filter(item => !item.user_has_it)
  const owned = job.items.length - needed.length
  const selected = report.lines.filter(line => line.selected_offer_url && !line.item.user_has_it)
  const covered = plan ? (plan.sellers ?? []).reduce((sum, seller) => sum + (seller.lines?.length ?? 0), 0) : selected.length
  const sellers = plan ? plan.seller_count ?? plan.sellers?.length ?? 0 : new Set(selected.map(line => offersOf(line).find(offer => offer.url === line.selected_offer_url)?.seller)).size
  const checked = selected.flatMap(line => offersOf(line).filter(offer => offer.url === line.selected_offer_url).map(offer => Date.parse(offer.checked_at))).filter(Number.isFinite)
  const unknown = [costing?.shipping.status === 'unknown' && 'shipping', costing?.gst.status === 'unknown' && 'GST'].filter(Boolean) as string[]
  // Whole rupees read better in the headline; paise stay in the detailed rows.
  const amount = costing ? amountText(costing.parts).replace(/\.00(?!\d)/g, '') : null
  return <section className="pp-band" aria-label="Order summary">
    <div className="pp-band-main">
      {covered > 0 && amount
        ? <><p className="pp-band-amount">{amount}</p>
          <p className="pp-band-scope">for {covered === needed.length ? `all ${covered}` : `${covered} of ${needed.length}`} {needed.length === 1 ? 'part' : 'parts'}, from {sellers} {sellers === 1 ? 'seller' : 'sellers'}{owned ? `. You already have ${owned}.` : ''}</p></>
        : <><p className="pp-band-amount pp-band-amount-empty">No seller picked yet</p><p className="pp-band-scope">None of your {needed.length} parts has a chosen offer. Open a part to pick one.</p></>}
      <p className="pp-band-note">{costing?.total.status === 'known' && costing.total.amount_inr ? `Total with shipping and GST: ${amountText(costing.total)}.` : unknown.length ? `${unknown.join(' and ')} not known yet, so this is the parts price only.`.replace(/^./, c => c.toUpperCase()) : 'Parts price only.'}{checked.length ? ` Prices checked ${ago(Math.min(...checked))}.` : ''}</p>
    </div>
    {actions && <div className="pp-band-actions">{actions}</div>}
  </section>
}

function ago(time: number) {
  const minutes = Math.max(0, Math.round((Date.now() - time) / 60000))
  if (minutes < 2) return 'just now'
  if (minutes < 60) return `${minutes} minutes ago`
  const hours = Math.round(minutes / 60)
  if (hours < 24) return `${hours} ${hours === 1 ? 'hour' : 'hours'} ago`
  const days = Math.round(hours / 24)
  return `${days} ${days === 1 ? 'day' : 'days'} ago`
}

const unsourcedText: Partial<Record<UnsourcedLine['reason'], string>> = {
  needs_value: 'choose a value',
  no_offers: 'no seller found yet',
  no_acceptable_offer: 'no offer fits yet',
  needs_quantity: 'set a quantity',
}
const flagOrder: SafetyFlag['code'][] = ['MAINS', 'LIPO', 'HIGH_CURRENT', 'LEVEL_SHIFT']

export type Need = { key: string; tone: 'danger' | 'warning' | 'caution' | 'input'; title: string; detail?: string; action?: { label: string; onClick: () => void }; body?: ReactNode }

export function safetyNeeds(job: Job, onShowLine: (lineId: string) => void): Need[] {
  const names = Object.fromEntries(job.items.map(item => [item.line_id, item.raw_name]))
  return [...(job.safety_flags ?? [])].sort((a, b) => flagOrder.indexOf(a.code) - flagOrder.indexOf(b.code)).map(flag => ({
    key: `flag-${flag.code}`, tone: flag.severity, title: flag.title,
    body: <div className="pp-need-body" role={flag.severity === 'danger' ? 'alert' : undefined}>
      <p>{flag.message}</p>
      {flag.guidance.length > 0 && <ul>{flag.guidance.map((entry, index) => <li key={index}>{entry}</li>)}</ul>}
      {flag.line_ids.length > 0 && <p className="pp-need-parts">Parts involved: {flag.line_ids.map((id, index) => <span key={id}>{index > 0 && ', '}<button type="button" className="pp-text-button" onClick={() => onShowLine(id)}>{names[id] ?? id}</button></span>)}</p>}
      <small>Automatic check from the parts list, not a guarantee. Review before ordering.</small>
    </div>,
  }))
}

// The list itself: one row per need, with one action or an expandable explanation.
export function NeedsList({ needs, initiallyOpen = null }: { needs: Need[]; initiallyOpen?: string | null }) {
  const [open, setOpen] = useState<string | null>(initiallyOpen)
  if (!needs.length) return null
  return <section className="pp-needs" aria-labelledby="pp-needs-title">
    <h2 id="pp-needs-title">Needs you <span>{needs.length}</span></h2>
    <ul>{needs.map(need => {
      const expanded = open === need.key
      return <li key={need.key} className={`pp-need pp-need-${need.tone}`}>
        <span className="pp-need-dot" aria-hidden="true" />
        <div className="pp-need-text"><strong>{need.title}</strong>{need.detail && <span>{need.detail}</span>}</div>
        {need.body
          ? <button type="button" className="pp-need-action" aria-expanded={expanded} aria-controls={`${need.key}-body`} onClick={() => setOpen(expanded ? null : need.key)}>{expanded ? 'Hide' : 'Review'}</button>
          : need.action && <button type="button" className="pp-need-action" onClick={need.action.onClick}>{need.action.label}</button>}
        {need.body && <div id={`${need.key}-body`} className="pp-need-expand" hidden={!expanded}>{need.body}</div>}
      </li>
    })}</ul>
  </section>
}

// Everything that needs a decision, in one list: safety checks, parts without a seller,
// selections waiting for confirmation and chat suggestions waiting for approval.
export function NeedsYou({ job, readOnly, onShowLine, onOpenChat }: { job: Job; readOnly: boolean; onShowLine: (lineId: string) => void; onOpenChat?: () => void }) {
  const report = reportOf(job)
  const names = Object.fromEntries(job.items.map(item => [item.line_id, item.raw_name]))
  const needs: Need[] = safetyNeeds(job, onShowLine)
  if (!readOnly && report) {
    const plan = report.order_plan
    const unsourced: { line_id: string; reason: UnsourcedLine['reason']; message?: string }[] = plan?.unsourced
      ?? report.lines.filter(line => !line.item.user_has_it && ['no_verified_offers', 'failed'].includes(line.sourcing_status)).map(line => ({ line_id: line.item.line_id, reason: 'no_offers' as const, message: line.sourcing_error?.message }))
    for (const entry of unsourced) {
      const text = unsourcedText[entry.reason]
      if (text) needs.push({ key: `unsourced-${entry.line_id}`, tone: 'input', title: `${names[entry.line_id] ?? entry.line_id}: ${text}`, detail: entry.message, action: { label: 'Open part', onClick: () => onShowLine(entry.line_id) } })
    }
    const pending = plan
      ? (plan.sellers ?? []).flatMap(seller => seller.lines ?? []).filter(line => line.selected === false).map(line => ({ id: line.line_id, reason: line.blocked_reason }))
      : report.lines.filter(line => line.recommendation?.blocked_reason && !line.selected_offer_url).map(line => ({ id: line.item.line_id, reason: line.recommendation?.blocked_reason }))
    for (const entry of pending) {
      const reason = entry.reason ?? report.lines.find(line => line.item.line_id === entry.id)?.recommendation?.blocked_reason
      needs.push({ key: `pending-${entry.id}`, tone: 'input', title: `${names[entry.id] ?? entry.id}: confirm the seller`, detail: reason ?? undefined, action: { label: 'Open part', onClick: () => onShowLine(entry.id) } })
    }
    const suggestions = job.messages.filter(message => message.proposal?.status === 'pending' || message.refresh_proposal?.status === 'pending' || message.spec_proposal?.status === 'pending').length
    if (suggestions && onOpenChat) needs.push({ key: 'chat', tone: 'input', title: suggestions === 1 ? 'A suggested change is waiting for your approval' : `${suggestions} suggested changes are waiting for your approval`, action: { label: 'Review in chat', onClick: onOpenChat } })
  }
  return <NeedsList needs={needs} initiallyOpen={job.safety_flags?.some(flag => flag.code === 'MAINS') ? 'flag-MAINS' : null} />
}
