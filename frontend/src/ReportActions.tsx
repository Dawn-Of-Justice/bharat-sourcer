import { useEffect, useState } from 'react'
import { createShare, explainAloud, exportBlob, getExtras, getShare, revokeShare, shareUrl, type Explanation, type ExtrasStatus, type Job, type ShareStatus } from './api'

const errorText = (cause: unknown, fallback: string) => cause instanceof Error ? cause.message : fallback

// Exports go through the proxy so credentials are attached; the blob is saved or opened locally.
// `base` is '/v1/jobs/{id}' for owners or '/v1/shared/{share_token}' on the public share page.
export function ExportButtons({ base, token, name }: { base: string; token?: string; name: string }) {
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  async function download() {
    setBusy('csv'); setError('')
    try {
      const url = URL.createObjectURL(await exportBlob(base + '/export.csv', token))
      const link = document.createElement('a')
      link.href = url; link.download = name + '.csv'
      document.body.append(link); link.click(); link.remove()
      setTimeout(() => URL.revokeObjectURL(url), 30000)
    } catch (cause) { setError(errorText(cause, 'Could not download the CSV.')) }
    finally { setBusy('') }
  }
  async function print() {
    // Open the tab during the click so popup blockers allow it, then point it at the fetched report.
    const tab = window.open('', '_blank')
    setBusy('html'); setError('')
    try {
      const url = URL.createObjectURL(await exportBlob(base + '/export.html', token))
      if (tab) tab.location.href = url
      else window.location.assign(url)
      setTimeout(() => URL.revokeObjectURL(url), 60000)
    } catch (cause) { tab?.close(); setError(errorText(cause, 'Could not open the printable report.')) }
    finally { setBusy('') }
  }
  return <div className="report-export"><button type="button" className="nav-cta" disabled={!!busy} onClick={() => void download()}>⬇ {busy === 'csv' ? 'Preparing…' : 'Download CSV'}</button><button type="button" className="nav-cta" disabled={!!busy} onClick={() => void print()}>🖨 {busy === 'html' ? 'Opening…' : 'Print / PDF'}</button>{error && <p className="form-error" role="alert">{error}</p>}</div>
}

export function ShareControl({ job, token }: { job: Job; token: string }) {
  const [status, setStatus] = useState<ShareStatus | null>(null)
  const [link, setLink] = useState('')
  const [copied, setCopied] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  useEffect(() => {
    let active = true
    void getShare(job.job_id, token).then(value => { if (active) setStatus(value) }).catch(() => { /* Share state is optional; the create button still works. */ })
    return () => { active = false }
  }, [job.job_id, token])
  async function create() {
    setBusy(true); setError(''); setCopied(false)
    try { const created = await createShare(job.job_id, token); setLink(shareUrl(created.share_token)); setStatus({ active: true, created_at: created.created_at }) }
    catch (cause) { setError(errorText(cause, 'Could not create a share link.')) }
    finally { setBusy(false) }
  }
  async function revoke() {
    setBusy(true); setError('')
    try { await revokeShare(job.job_id, token); setLink(''); setStatus({ active: false, created_at: null }) }
    catch (cause) { setError(errorText(cause, 'Could not revoke the share link.')) }
    finally { setBusy(false) }
  }
  async function copy() {
    try { await navigator.clipboard.writeText(link); setCopied(true) } catch { setError('Copy failed. Select the link and copy it manually.') }
  }
  return <details className="share-control"><summary>🔗 Share a read-only link{status?.active ? ' · active' : ''}</summary><p>{status?.active ? `A share link is active${status.created_at ? ` since ${new Date(status.created_at).toLocaleString('en-IN')}` : ''}. Anyone with it can view this report without signing in.` : 'No share link is active. Anyone with a link can view the parts list and offers, but not your chat or account.'}</p>{link && <div className="share-copy"><label>Share link (shown only once)<input readOnly value={link} onFocus={event => event.target.select()} /></label><button type="button" className="nav-cta" onClick={() => void copy()}>{copied ? '✓ Copied' : 'Copy'}</button></div>}<p className="share-warning">⚠ The link is shown only once. Creating a new link replaces the old one, which stops working.</p><div className="share-buttons"><button type="button" className="nav-cta" disabled={busy} onClick={() => void create()}>{busy ? 'Working…' : status?.active ? 'Create new link' : 'Create link'}</button>{status?.active && <button type="button" className="remove-button" disabled={busy} onClick={() => void revoke()}>Revoke link</button>}</div>{error && <p className="form-error" role="alert">{error}</p>}</details>
}

const languageNames: Record<string, string> = { en: 'English', hi: 'हिन्दी (Hindi)', ta: 'தமிழ் (Tamil)', ml: 'മലയാളം (Malayalam)', bn: 'বাংলা (Bengali)', te: 'తెలుగు (Telugu)', kn: 'ಕನ್ನಡ (Kannada)', mr: 'मराठी (Marathi)' }

// Hidden unless GET /extras reports explain as enabled. Calls can take tens of seconds.
export function ExplainAloud({ job, token }: { job: Job; token: string }) {
  const [extras, setExtras] = useState<ExtrasStatus | null>(null)
  const [language, setLanguage] = useState('en')
  const [result, setResult] = useState<Explanation | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  useEffect(() => {
    let active = true
    void getExtras(job.job_id, token).then(value => { if (active) setExtras(value) }).catch(() => { /* Extras stay hidden. */ })
    return () => { active = false }
  }, [job.job_id, token])
  if (!extras?.explain.enabled) return null
  async function explain() {
    setBusy(true); setError('')
    try { setResult(await explainAloud(job.job_id, token, language)); setExtras(current => current && { ...current, explain: { ...current.explain, remaining: Math.max(0, current.explain.remaining - 1) } }) }
    catch (cause) { setError(errorText(cause, 'Could not prepare the explanation.')) }
    finally { setBusy(false) }
  }
  return <section className="explain-aloud" aria-label="Explain aloud"><div className="explain-controls"><label>Language<select value={language} onChange={event => setLanguage(event.target.value)} disabled={busy}>{extras.languages.map(code => <option key={code} value={code}>{languageNames[code] ?? code}</option>)}</select></label><button type="button" className="nav-cta" disabled={busy || extras.explain.remaining < 1} onClick={() => void explain()}>🔊 {busy ? 'Preparing audio…' : 'Explain aloud'}</button><small>{extras.explain.remaining} of {extras.explain.daily_limit} left today</small></div>{busy && <p role="status"><span className="loading-indicator" /> This can take up to a minute.</p>}{error && <p className="form-error" role="alert">{error}</p>}{result && <div className="explain-result">{result.demo && <p className="demo-alert"><strong>Demo sample</strong> · Not generated for this project.</p>}<audio controls src={'data:audio/wav;base64,' + result.audio_base64} /><details><summary>Transcript · {result.label}</summary><p>{result.transcript}</p></details></div>}</section>
}
