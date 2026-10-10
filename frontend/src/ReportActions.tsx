import { useEffect, useState } from 'react'
import { createShare, exportBlob, shareUrl, type Job } from './api'

const errorText = (cause: unknown, fallback: string) => (cause instanceof Error ? cause.message : fallback)

// The PDF is fetched through the proxy so credentials are attached, then saved locally.
export function ExportButtons({ base, token, name }: { base: string; token?: string; name: string }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  async function download() {
    setBusy(true)
    setError('')
    try {
      const url = URL.createObjectURL(await exportBlob(base + '/export.pdf', token))
      const link = document.createElement('a')
      link.href = url
      link.download = name + '.pdf'
      document.body.append(link)
      link.click()
      link.remove()
      setTimeout(() => URL.revokeObjectURL(url), 30000)
    } catch (cause) {
      setError(errorText(cause, 'Could not download the PDF.'))
    } finally {
      setBusy(false)
    }
  }
  return (
    <div className="report-export">
      <button type="button" className="report-action" disabled={busy} onClick={() => void download()}>
        {busy ? 'Preparing PDF…' : 'Download PDF'}
      </button>
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
    </div>
  )
}

export function ShareControl({ job, token }: { job: Job; token: string }) {
  const [link, setLink] = useState('')
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState('')
  const [noticeId, setNoticeId] = useState(0)
  const [error, setError] = useState('')
  useEffect(() => {
    if (!notice) return
    const timer = window.setTimeout(() => setNotice(''), 4200)
    return () => window.clearTimeout(timer)
  }, [notice])
  async function share() {
    setBusy(true)
    setNotice('')
    setError('')
    try {
      const url = link || shareUrl((await createShare(job.job_id, token)).share_token)
      setLink(url)
      await navigator.clipboard.writeText(url)
      setNotice('Link copied')
      setNoticeId(current => current + 1)
    } catch (cause) {
      setError(errorText(cause, 'Could not copy the link.'))
    } finally {
      setBusy(false)
    }
  }
  return (
    <div className="share-control">
      <button
        type="button"
        className={`report-action share-button${notice ? ' share-button-copied' : ''}`}
        disabled={busy}
        onClick={() => void share()}
      >
        <svg viewBox="0 0 20 20" fill="none" aria-hidden="true">
          <path
            d="M8 6.5h-1.5A3.5 3.5 0 0 0 3 10a3.5 3.5 0 0 0 3.5 3.5H9m2-7h2.5A3.5 3.5 0 0 1 17 10a3.5 3.5 0 0 1-3.5 3.5H11M7 10h6"
            stroke="currentColor"
            strokeWidth="1.7"
            strokeLinecap="round"
          />
        </svg>
        {busy ? 'Sharing…' : 'Share link'}
      </button>
      {notice && (
        <div key={noticeId} className="share-toast" role="status">
          <span className="share-toast-icon" aria-hidden="true">
            ✓
          </span>
          {notice}
        </div>
      )}
      {error && (
        <div className="share-toast share-toast-error" role="alert">
          {error}
          {link && (
            <input aria-label="Share link to copy" readOnly value={link} onFocus={event => event.target.select()} />
          )}
        </div>
      )}
    </div>
  )
}
