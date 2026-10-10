import { reportOf, type Job, type UnsourcedLine } from './api'
import { safetyNeeds, type Need } from './ReportSummary'

const unsourcedText: Partial<Record<UnsourcedLine['reason'], string>> = {
  needs_value: 'choose a value',
  no_offers: 'no seller found yet',
  no_acceptable_offer: 'no offer fits yet',
  needs_quantity: 'set a quantity',
}
// Everything that needs a decision, in one list: safety checks, parts without a seller,
// selections waiting for confirmation and chat suggestions waiting for approval.
export function orderNeeds({
  job,
  readOnly,
  onShowLine,
  onOpenChat,
}: {
  job: Job
  readOnly: boolean
  onShowLine: (lineId: string) => void
  onOpenChat?: () => void
}) {
  const report = reportOf(job)
  const names = Object.fromEntries(job.items.map(item => [item.line_id, item.raw_name]))
  const needs: Need[] = safetyNeeds(job, onShowLine)
  if (!readOnly && report) {
    const plan = report.order_plan
    const unsourced: { line_id: string; reason: UnsourcedLine['reason']; message?: string }[] =
      plan?.unsourced ??
      report.lines
        .filter(line => !line.item.user_has_it && ['no_verified_offers', 'failed'].includes(line.sourcing_status))
        .map(line => ({
          line_id: line.item.line_id,
          reason: 'no_offers' as const,
          message: line.sourcing_error?.message,
        }))
    for (const entry of unsourced) {
      const text = unsourcedText[entry.reason]
      if (text)
        needs.push({
          key: `unsourced-${entry.line_id}`,
          tone: 'input',
          title: `${names[entry.line_id] ?? entry.line_id}: ${text}`,
          detail: entry.message,
          action: { label: 'Open part', onClick: () => onShowLine(entry.line_id) },
        })
    }
    const pending = plan
      ? (plan.sellers ?? [])
          .flatMap(seller => seller.lines ?? [])
          .filter(line => line.selected === false)
          .map(line => ({ id: line.line_id, reason: line.blocked_reason }))
      : report.lines
          .filter(line => line.recommendation?.blocked_reason && !line.selected_offer_url)
          .map(line => ({ id: line.item.line_id, reason: line.recommendation?.blocked_reason }))
    for (const entry of pending) {
      const reason =
        entry.reason ?? report.lines.find(line => line.item.line_id === entry.id)?.recommendation?.blocked_reason
      needs.push({
        key: `pending-${entry.id}`,
        tone: 'input',
        title: `${names[entry.id] ?? entry.id}: confirm the seller`,
        detail: reason ?? undefined,
        action: { label: 'Open part', onClick: () => onShowLine(entry.id) },
      })
    }
    const suggestions = job.messages.filter(
      message =>
        message.proposal?.status === 'pending' ||
        message.refresh_proposal?.status === 'pending' ||
        message.spec_proposal?.status === 'pending',
    ).length
    if (suggestions && onOpenChat)
      needs.push({
        key: 'chat',
        tone: 'input',
        title:
          suggestions === 1
            ? 'A suggested change is waiting for your approval'
            : `${suggestions} suggested changes are waiting for your approval`,
        action: { label: 'Review in chat', onClick: onOpenChat },
      })
  }
  return needs
}
