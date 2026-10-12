import { useEffect, useState } from 'react'
import { getPlans, selectOffers, type CartPlans, type Job } from './api'
import { amountText, price } from './ReportBits'

const errorText = (cause: unknown, fallback: string) => (cause instanceof Error ? cause.message : fallback)

const planNames = { recommended: 'Recommended', cheapest: 'Cheapest', fewest_sellers: 'Fewest sellers' }
// Plans preview picks and totals; only an explicit Apply posts them to /selections.
export function PlanCompare({
  job,
  token,
  onJob,
  names,
}: {
  job: Job
  token: string
  onJob: (job: Job) => void
  names: Record<string, string>
}) {
  const [loaded, setLoaded] = useState<{ job: Job; plans: CartPlans } | null>(null)
  const plans = loaded?.job === job ? loaded.plans : null
  const [kind, setKind] = useState<'recommended' | 'cheapest' | 'fewest_sellers'>('cheapest')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [acknowledged, setAcknowledged] = useState(false)
  useEffect(() => {
    let cancelled = false
    void getPlans(job.job_id, token)
      .then(result => {
        if (!cancelled) setLoaded({ job, plans: result })
      })
      .catch(() => {
        // Keep comparison hidden when available options cannot be confirmed.
        if (!cancelled) setLoaded(null)
      })
    return () => {
      cancelled = true
    }
  }, [job, token])
  const plan = plans?.plans?.find(entry => entry.kind === kind) ?? plans?.plans?.[0]
  const picks = plan?.picks ?? []
  const needsChanges = picks.some(pick => pick.changes_required)
  async function apply() {
    setBusy(true)
    setError('')
    try {
      onJob(
        await selectOffers(
          job.job_id,
          token,
          picks.map(pick => ({
            line_id: pick.line_id,
            offer_url: pick.offer_url,
            accept_changes: !!pick.changes_required,
          })),
        ),
      )
      setAcknowledged(false)
    } catch (cause) {
      setError(errorText(cause, 'Could not apply the plan.'))
    } finally {
      setBusy(false)
    }
  }
  if ((plans?.plans?.length ?? 0) < 2) return null
  return (
    <details className="plan-compare">
      <summary>
        Compare plans <span className="plan-compare-hint">Cheapest · Fewest sellers</span>
      </summary>
      {plans && (
        <>
          <div className="plan-toggle" role="group" aria-label="Plan">
            {(plans.plans ?? []).map(entry => (
              <button
                key={entry.kind}
                type="button"
                className="nav-cta"
                aria-pressed={plan?.kind === entry.kind}
                onClick={() => {
                  setKind(entry.kind)
                  setAcknowledged(false)
                }}
              >
                {planNames[entry.kind]}
              </button>
            ))}
          </div>
          {plan ? (
            <div className="plan-preview">
              <p>
                {plan.seller_count ?? 0} {plan.seller_count === 1 ? 'seller' : 'sellers'} · subtotal{' '}
                {amountText(plan.costing.parts)}
                {plan.matches_selection ? ' · matches your current selection' : ''}
              </p>
              <ul>
                {picks.map(pick => (
                  <li key={pick.line_id}>
                    {names[pick.line_id] ?? pick.line_id}: {pick.seller} · {price(pick.price_inr)}
                    {pick.packs && pick.packs > 1 ? ` × ${pick.packs}` : ''}
                    {pick.grade ? ` · grade ${pick.grade}` : ''}
                    {pick.changes_required ? ' · ⇄ changes required' : ''}
                  </li>
                ))}
              </ul>
              {plans.uncovered_line_ids?.length ? (
                <p>No selectable listing for: {plans.uncovered_line_ids.map(id => names[id] ?? id).join(', ')}.</p>
              ) : null}
              {plan.kind !== 'recommended' && picks.length > 0 && (
                <>
                  {needsChanges && (
                    <label className="offer-ack">
                      <input
                        type="checkbox"
                        checked={acknowledged}
                        onChange={event => setAcknowledged(event.target.checked)}
                      />{' '}
                      I reviewed the required changes for the ⇄ picks
                    </label>
                  )}
                  <p>Applying makes these picks your own choices; recommendations will not replace them.</p>
                  <button
                    type="button"
                    className="nav-cta"
                    disabled={busy || (needsChanges && !acknowledged)}
                    onClick={() => void apply()}
                  >
                    {busy ? 'Applying…' : `Apply ${planNames[plan.kind].toLowerCase()} plan`}
                  </button>
                </>
              )}
            </div>
          ) : (
            <p>This plan is not available.</p>
          )}
        </>
      )}
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
    </details>
  )
}
