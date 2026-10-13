import { useRef, useState } from 'react'
import type { Job } from './api'
import { sellerSearchOutcomes } from './sellerSearch'

// Parts without a usable seller offer, on the order plan: pick some and search again. Parts that need a missing
// value or a compatibility decision are listed under "Needs your attention" instead.
export default function SellerRetry({ job, onRetry }: { job: Job; onRetry: (ids: string[]) => Promise<void> }) {
  const retryable = sellerSearchOutcomes(job).filter(row => row.kind === 'retry')
  const [selected, setSelected] = useState(() => retryable.slice(0, 10).map(row => row.item.line_id))
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const submitting = useRef(false)
  const unlimited = job.refresh_limit === null
  const limit = job.refresh_limit ?? 2
  const remaining = unlimited ? Infinity : Math.max(0, limit - (job.refresh_count ?? 0))
  const ids = selected.filter(id => retryable.some(row => row.item.line_id === id))
  const canRetry = !job.demo && remaining > 0 && !busy

  async function retry() {
    if (!canRetry || !ids.length || ids.length > 10 || submitting.current) return
    submitting.current = true
    setBusy(true)
    setError('')
    try {
      await onRetry(ids)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not start the seller search. Please try again.')
    } finally {
      submitting.current = false
      setBusy(false)
    }
  }

  if (!retryable.length) return null
  return (
    <section className="seller-retry" aria-label="Search again">
      <fieldset className="seller-retry-options" disabled={!canRetry}>
        <legend>
          No seller yet for {retryable.length} {retryable.length === 1 ? 'part' : 'parts'}
        </legend>
        <p>Select the parts to search again. Parts with sellers stay saved.</p>
        <button
          type="button"
          className="nav-cta"
          onClick={() => setSelected(ids.length ? [] : retryable.slice(0, 10).map(row => row.item.line_id))}
        >
          {ids.length ? 'Clear selection' : retryable.length > 10 ? 'Select first 10' : 'Select all'}
        </button>
        {retryable.map(({ item, reason }) => (
          <label className="seller-retry-option" key={item.line_id}>
            <input
              type="checkbox"
              checked={ids.includes(item.line_id)}
              disabled={!canRetry || (ids.length >= 10 && !ids.includes(item.line_id))}
              onChange={event =>
                setSelected(previous =>
                  event.target.checked ? [...previous, item.line_id] : previous.filter(id => id !== item.line_id),
                )
              }
            />
            <strong>{item.raw_name}</strong>
            <span>{reason}</span>
          </label>
        ))}
      </fieldset>
      <p className="seller-retry-note">
        {job.demo
          ? 'Seller searches are unavailable for this demo project.'
          : unlimited
            ? 'Testing account: no seller retry batch limit. Select up to 10 parts. Daily usage and spending limits still apply.'
            : remaining
              ? `${remaining} of ${limit} retry batches remaining. Select up to 10 parts. Searching again replaces their saved quotes and may use paid analysis.`
              : 'No retry batches remaining. You can continue with the available results.'}
      </p>
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
      {!job.demo && remaining > 0 && (
        <div className="seller-retry-actions">
          <button type="button" className="nav-cta" disabled={!canRetry || !ids.length} onClick={() => void retry()}>
            {busy ? 'Starting seller search…' : `Search again for ${ids.length} ${ids.length === 1 ? 'part' : 'parts'}`}
          </button>
        </div>
      )}
    </section>
  )
}
