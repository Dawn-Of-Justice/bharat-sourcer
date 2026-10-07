import { useEffect, useState } from 'react'
import { createShare, exportBlob, shareUrl, type Job } from './api'

const errorText = (cause: unknown, fallback: string) => cause instanceof Error ? cause.message : fallback

// Exports go through the proxy so credentials are attached; the blob is saved or opened locally.
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
  return <div className="report-export"><button type="button" className="report-action" disabled={!!busy} onClick={() => void download()}>{busy === 'csv' ? 'Preparing…' : 'Download CSV'}</button><button type="button" className="report-action" disabled={!!busy} onClick={() => void print()}>{busy === 'html' ? 'Opening…' : 'Print / PDF'}</button>{error && <p className="form-error" role="alert">{error}</p>}</div>
}

export function ShareControl({ job, token }: { job: Job; token: string }) {
  const [link, setLink] = useState('')
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState('')
  const [error, setError] = useState('')
  useEffect(() => {
    if (!notice) return
    const timer = window.setTimeout(() => setNotice(''), 2500)
    return () => window.clearTimeout(timer)
  }, [notice])
  async function share() {
    setBusy(true); setNotice(''); setError('')
    try {
      const url = link || shareUrl((await createShare(job.job_id, token)).share_token)
      setLink(url)
      await navigator.clipboard.writeText(url)
      setNotice('Link copied')
    } catch (cause) { setError(errorText(cause, 'Could not copy the link.')) }
    finally { setBusy(false) }
  }
  return <div className="share-control"><button type="button" className="report-action" disabled={busy} onClick={() => void share()}>{busy ? 'Sharing…' : 'Share link'}</button>{notice && <div className="share-toast" role="status">{notice}</div>}{error && <div className="share-toast share-toast-error" role="alert">{error}{link && <input aria-label="Share link to copy" readOnly value={link} onFocus={event => event.target.select()} />}</div>}</div>
}
