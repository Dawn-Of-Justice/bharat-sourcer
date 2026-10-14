import { offersOf, reportOf, type BomItem, type Job } from './api'
import { madeToOrder } from './fabrication'

export type SellerSearchOutcome = {
  item: BomItem
  kind: 'ready' | 'retry' | 'details' | 'owned'
  reason: string
}

export function sellerSearchOutcomes(job: Job, now = Date.now()): SellerSearchOutcome[] {
  const report = reportOf(job)
  return job.items.map(item => {
    if (item.user_has_it) return { item, kind: 'owned', reason: 'You already have it' }
    const line = report?.lines.find(entry => entry.item.line_id === item.line_id)
    if (madeToOrder(line)) return { item, kind: 'ready', reason: 'Made to order' }
    const spec = line?.buyable_spec ?? item.buyable_spec
    const needsValue =
      spec?.needs_value ||
      line?.recommendation?.unsourced_reason === 'needs_value' ||
      report?.order_plan?.unsourced?.some(entry => entry.line_id === item.line_id && entry.reason === 'needs_value')
    if (needsValue) return { item, kind: 'details', reason: 'Missing part details' }
    const offers = line ? offersOf(line) : []
    if (!offers.length)
      return {
        item,
        kind: 'retry',
        reason: line?.sourcing_status === 'failed' ? 'Search failed' : 'No verified offers',
      }
    const fresh = offers.filter(offer => now - Date.parse(offer.checked_at) < 24 * 60 * 60 * 1000)
    if (!fresh.length) return { item, kind: 'retry', reason: 'Quotes expired' }
    const inStock = fresh.filter(offer => offer.stock === 'in_stock')
    if (!inStock.length)
      return {
        item,
        kind: 'retry',
        reason: fresh.every(offer => offer.stock === 'out_of_stock') ? 'Out of stock' : 'Stock unconfirmed',
      }
    const selectable = inStock.some(offer => {
      const grade = offer.compatibility?.grade
      return (
        grade === 'A' ||
        grade === 'B' ||
        (!grade &&
          (offer.match?.status === 'exact' ||
            offer.match?.status === 'compatible' ||
            offer.research_assessment?.status === 'potential_match'))
      )
    })
    return selectable
      ? { item, kind: 'ready', reason: 'Seller offers available' }
      : { item, kind: 'details', reason: 'Compatibility needs review' }
  })
}
