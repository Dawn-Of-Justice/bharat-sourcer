import { useRef, useState } from 'react'
import type { Job } from './api'
import { sellerSearchOutcomes } from './sellerSearch'

export default function SellerSearchResults({
  job,
  onRetry,
  onContinue,
  onDetails,
}: {
  job: Job
  onRetry: (ids: string[]) => Promise<void>
  onContinue: () => void
  onDetails: (id: string) => void
}) {
  const outcomes = sellerSearchOutcomes(job)
  const retryable = outcomes.filter(row => row.kind === 'retry')
  const details = outcomes.filter(row => row.kind === 'details')
  const needed = outcomes.filter(row => row.kind !== 'owned')
  const found = outcomes.filter(row => row.kind === 'ready').length
  const [selected, setSelected] = useState(() => retryable.slice(0, 10).map(row => row.item.line_id))
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const submitting = useRef(false)
  const remaining = Math.max(0, 2 - (job.refresh_count ?? 0))
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

  return (
    <section className="job-panel pp-stage seller-retry">
      <header className="pp-stage-head">
        <div>
          <h2>Seller search complete</h2>
          <p role="status">
            Seller offers available for {found} of {needed.length} parts.
            {needed.length > found
              ? ` ${needed.length - found} still need attention.`
              : ' Your order plan is ready to review.'}
          </p>
        </div>
      </header>
      {!!retryable.length && (
        <fieldset className="seller-retry-options" disabled={!canRetry}>
          <legend>Try finding sellers again</legend>
          <p>Select the parts to search again. Successful parts stay saved.</p>
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
      )}
      {!!details.length && (
        <div className="seller-retry-details">
          <h3>Review these parts first</h3>
          <p>Missing details or compatibility questions need your review before another search.</p>
          {details.map(({ item, reason }) => (
            <div className="seller-retry-option" key={item.line_id}>
              <div>
                <strong>{item.raw_name}</strong>
                <p>{reason}</p>
              </div>
              <button type="button" className="nav-cta" disabled={busy} onClick={() => onDetails(item.line_id)}>
                {reason === 'Missing part details' ? 'Add missing details' : 'Review compatibility'}
              </button>
            </div>
          ))}
        </div>
      )}
      {!!retryable.length && (
        <p className="seller-retry-note">
          {job.demo
            ? 'Seller searches are unavailable for this demo project.'
            : remaining
              ? `${remaining} of 2 retry batches remaining. Select up to 10 parts. Searching again replaces their saved quotes and may use paid analysis.`
              : 'No retry batches remaining. You can continue with the available results.'}
        </p>
      )}
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
      <div className="seller-retry-actions">
        {!!retryable.length && !job.demo && remaining > 0 && (
          <button type="button" className="nav-cta" disabled={!canRetry || !ids.length} onClick={() => void retry()}>
            {busy ? 'Starting seller search…' : `Try again for ${ids.length} ${ids.length === 1 ? 'part' : 'parts'}`}
          </button>
        )}
        <button type="button" className="primary-button" disabled={busy} onClick={onContinue}>
          Continue to order plan
        </button>
      </div>
      <details className="pp-section">
        <summary>All search results</summary>
        <ul className="pp-rows">
          {outcomes.map(({ item, reason }) => (
            <li className="seller-retry-option" key={item.line_id}>
              <strong>{item.raw_name}</strong>
              <span>{reason}</span>
            </li>
          ))}
        </ul>
      </details>
    </section>
  )
}
