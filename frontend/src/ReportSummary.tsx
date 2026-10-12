import { useState, type ReactNode } from 'react'
import { offersOf, reportOf, type Job, type SafetyFlag } from './api'
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
  const covered = plan
    ? (plan.sellers ?? []).reduce((sum, seller) => sum + (seller.lines?.length ?? 0), 0)
    : selected.length
  const sellers = plan
    ? (plan.seller_count ?? plan.sellers?.length ?? 0)
    : new Set(selected.map(line => offersOf(line).find(offer => offer.url === line.selected_offer_url)?.seller)).size
  const checked = selected
    .flatMap(line =>
      offersOf(line)
        .filter(offer => offer.url === line.selected_offer_url)
        .map(offer => Date.parse(offer.checked_at)),
    )
    .filter(Number.isFinite)
  // Whole rupees read better in the headline; paise stay in the detailed rows.
  const amount = costing ? amountText(costing.parts).replace(/\.00(?!\d)/g, '') : null
  return (
    <section className="pp-band" aria-label="Order summary">
      <div className="pp-band-main">
        {covered > 0 && amount ? (
          <>
            <p className="pp-band-amount">{amount}</p>
            <p className="pp-band-scope">
              for {covered === needed.length ? `all ${covered}` : `${covered} of ${needed.length}`}{' '}
              {needed.length === 1 ? 'part' : 'parts'}, from {sellers} {sellers === 1 ? 'seller' : 'sellers'}
              {owned ? `. You already have ${owned}.` : ''}
            </p>
          </>
        ) : (
          <>
            <p className="pp-band-amount pp-band-amount-empty">No seller picked yet</p>
            <p className="pp-band-scope">
              None of your {needed.length} parts has a chosen offer. Open a part to pick one.
            </p>
          </>
        )}
        <p className="pp-band-note">
          Parts price only.
          {costing && costing.shipping.status !== 'unknown' && Number(costing.shipping.amount_inr) > 0
            ? ` Shipping ${costing.shipping.status === 'estimated' ? 'about ' : ''}${amountText(costing.shipping)}.`
            : ''}
          {checked.length ? ` Prices checked ${ago(Math.min(...checked))}.` : ''}
        </p>
      </div>
      {actions && <div className="pp-band-actions">{actions}</div>}
    </section>
  )
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

const flagOrder: SafetyFlag['code'][] = ['MAINS', 'LIPO', 'HIGH_CURRENT', 'LEVEL_SHIFT']

export type Need = {
  key: string
  tone: 'danger' | 'warning' | 'caution' | 'input'
  title: string
  detail?: string
  action?: { label: string; onClick: () => void }
  body?: ReactNode
}

export function safetyNeeds(job: Job, onShowLine: (lineId: string) => void): Need[] {
  const names = Object.fromEntries(job.items.map(item => [item.line_id, item.raw_name]))
  return [...(job.safety_flags ?? [])]
    .sort((a, b) => flagOrder.indexOf(a.code) - flagOrder.indexOf(b.code))
    .map(flag => ({
      key: `flag-${flag.code}`,
      tone: flag.severity,
      title: flag.title,
      body: (
        <div className="pp-need-body" role={flag.severity === 'danger' ? 'alert' : undefined}>
          <p>{flag.message}</p>
          {flag.guidance.length > 0 && (
            <ul>
              {flag.guidance.map((entry, index) => (
                <li key={index}>{entry}</li>
              ))}
            </ul>
          )}
          {flag.line_ids.length > 0 && (
            <p className="pp-need-parts">
              Parts involved:{' '}
              {flag.line_ids.map((id, index) => (
                <span key={id}>
                  {index > 0 && ', '}
                  <button type="button" className="pp-text-button" onClick={() => onShowLine(id)}>
                    {names[id] ?? id}
                  </button>
                </span>
              ))}
            </p>
          )}
          <small>Automatic check from the parts list, not a guarantee. Review before ordering.</small>
        </div>
      ),
    }))
}

// The list itself: one row per need, with one action or an expandable explanation.
export function NeedsList({
  needs,
  initiallyOpen = null,
  showHeading = true,
}: {
  needs: Need[]
  initiallyOpen?: string | null
  showHeading?: boolean
}) {
  const [open, setOpen] = useState<string | null>(initiallyOpen)
  if (!needs.length) return null
  return (
    <section
      className="pp-needs"
      aria-labelledby={showHeading ? 'pp-needs-title' : undefined}
      aria-label={showHeading ? undefined : 'Attention items'}
    >
      {showHeading && (
        <h2 id="pp-needs-title">
          Needs your attention <span>{needs.length}</span>
        </h2>
      )}
      <ul>
        {needs.map(need => {
          const expanded = open === need.key
          return (
            <li key={need.key} className={`pp-need pp-need-${need.tone}`}>
              <span className="pp-need-dot" aria-hidden="true" />
              <div className="pp-need-text">
                <strong>{need.title}</strong>
                {need.detail && <span>{need.detail}</span>}
              </div>
              {need.body ? (
                <button
                  type="button"
                  className="pp-need-action"
                  aria-expanded={expanded}
                  aria-controls={`${need.key}-body`}
                  onClick={() => setOpen(expanded ? null : need.key)}
                >
                  {expanded ? 'Hide' : 'Review'}
                </button>
              ) : (
                need.action && (
                  <button type="button" className="pp-need-action" onClick={need.action.onClick}>
                    {need.action.label}
                  </button>
                )
              )}
              {need.body && (
                <div id={`${need.key}-body`} className="pp-need-expand" hidden={!expanded}>
                  {need.body}
                </div>
              )}
            </li>
          )
        })}
      </ul>
    </section>
  )
}
