import { Fragment, useState, type FormEvent } from 'react'
import { ApiError, getMarkets, type Job, type MarketsResult } from './api'
import { secureLink } from './ReportBits'

// Google Maps grounding terms: the text "Google Maps" is never altered, translated or broken across lines.
function MapsText({ text }: { text: string }) {
  const parts = text.split('Google Maps')
  return <>{parts.map((part, index) => <Fragment key={index}>{part}{index < parts.length - 1 && <span className="no-break">Google Maps</span>}</Fragment>)}</>
}

function marketsError(cause: unknown) {
  if (!(cause instanceof ApiError)) return cause instanceof Error ? cause.message : 'Could not look up nearby markets.'
  if (cause.code === 'INVALID_PIN') return 'Enter a 6-digit PIN code that does not start with 0.'
  if (cause.code === 'PIN_NOT_SUPPORTED') return `${cause.message} Try “Use my location” instead.`
  if (cause.code === 'LOCATION_OUTSIDE_INDIA') return 'Your location appears to be outside India. Enter an Indian PIN code instead.'
  if (cause.status === 429) return cause.code === 'FEATURE_QUOTA' ? 'Today’s nearby-market lookups are used up. Try again tomorrow.' : cause.message
  if (cause.status === 503) return 'Nearby markets are unavailable right now.'
  return cause.message
}

export default function Markets({ job, token }: { job: Job; token: string }) {
  const [pin, setPin] = useState('')
  const [result, setResult] = useState<MarketsResult | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  async function lookup(place: { pin: string } | { lat: number; lng: number }) {
    setBusy(true); setError('')
    try { setResult(await getMarkets(job.job_id, token, place)) }
    catch (cause) { setError(marketsError(cause)) }
    finally { setBusy(false) }
  }
  function submit(event: FormEvent) {
    event.preventDefault()
    if (!/^[1-9]\d{5}$/.test(pin)) { setError('Enter a 6-digit PIN code that does not start with 0.'); return }
    void lookup({ pin })
  }
  function locate() {
    if (!navigator.geolocation) { setError('Location is not available in this browser. Enter a PIN code instead.'); return }
    setBusy(true); setError('')
    // Rounded to about 1 km before it leaves the browser; the backend rounds again.
    navigator.geolocation.getCurrentPosition(position => void lookup({ lat: Math.round(position.coords.latitude * 100) / 100, lng: Math.round(position.coords.longitude * 100) / 100 }), () => { setBusy(false); setError('Location permission was not given. Enter a PIN code instead.') }, { maximumAge: 600000, timeout: 15000 })
  }
  return <section className="markets-card" aria-labelledby="markets-title"><span className="section-kicker">NEARBY</span><h3 id="markets-title">Pick it up today</h3><p>Find electronics markets and shops near you. Only part categories are sent, never part names or project details.</p><form className="markets-form" onSubmit={submit}><label>PIN code<input inputMode="numeric" maxLength={6} pattern="[1-9][0-9]{5}" value={pin} onChange={event => setPin(event.target.value.replace(/\D/g, ''))} disabled={busy} /></label><button type="submit" className="nav-cta" disabled={busy}>{busy ? 'Looking…' : 'Find shops'}</button><button type="button" className="remove-button" disabled={busy} onClick={locate}>Use my location</button></form>{error && <p className="form-error" role="alert">{error}</p>}{result && <div className="markets-result" aria-live="polite"><p className="markets-location">📍 {result.location.label}</p>{result.demo && <p className="demo-alert"><strong>Sample</strong> · Fictional demo shops, not real places. No map sources.</p>}{result.summary ? <>
    <p className="markets-label">{result.summary_label ?? 'Shops likely to carry these parts — call first; stock is not confirmed'}</p>
    <div className="markets-summary">{result.summary}</div>
    {result.places.length > 0 && <ul className="markets-places">{result.places.map((place, index) => <li key={index}>{secureLink(place.uri) ? <a href={place.uri!} target="_blank" rel="noopener noreferrer">{place.title} ↗</a> : <strong>{place.title}</strong>}{place.address && <small>{place.address}</small>}</li>)}</ul>}
    {!result.demo && result.attribution.sources.length > 0 && <ul className="maps-sources" aria-label="Sources">{result.attribution.sources.map((source, index) => <li key={index}><a href={source.uri} target="_blank" rel="noopener noreferrer"><MapsText text={source.title} /></a></li>)}</ul>}
  </> : <p className="markets-label"><MapsText text={result.label} /></p>}{result.summary && <small className="markets-meta"><MapsText text={result.label} />{result.cached ? ' · saved result from the last 7 days' : ''}</small>}</div>}</section>
}
