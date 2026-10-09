import { useEffect, useState } from 'react'
import { useAccount } from './Account'
import { ApiError, copyShared, getShared, type Job, type SharedProject } from './api'
import Results from './Results'

// Public, read-only report at /shared/<token>. No chat, edit, select, refresh or image-generation
// controls; "Copy to my projects" (sign-in or guest session) makes an editable copy.
function asJob(shared: SharedProject): Job {
  return { job_id: '', status: shared.status, updated_at: shared.updated_at, demo: shared.demo, input: { url: shared.source_url }, items: shared.items, project: shared.project ?? null, events: [], report: shared.report ?? null, error: null, messages: [], chat_state: 'idle', chat_error: null }
}

function copyError(cause: unknown) {
  if (!(cause instanceof ApiError)) return cause instanceof Error ? cause.message : 'Could not copy this project. Please try again.'
  if (cause.code === 'PART_LIMIT') return cause.message + '. Guest projects are limited in size.'
  if (cause.code === 'SHARE_NOT_READY') return 'The owner is still preparing this project. Try again once it is ready.'
  if (cause.status === 404) return 'This share link was revoked or replaced, so it can no longer be copied.'
  if (cause.status === 429) return 'You have reached today’s limit for new projects. Try again tomorrow.'
  return cause.message
}

export default function SharedReport({ shareToken, onCopied }: { shareToken: string; onCopied: (jobId: string) => void }) {
  const account = useAccount()
  const [shared, setShared] = useState<SharedProject | null>(null)
  const [error, setError] = useState('')
  const [copying, setCopying] = useState(false)
  const [copyFailure, setCopyFailure] = useState('')
  async function copy() {
    if (!account.requireIdentity()) return
    setCopying(true); setCopyFailure('')
    try {
      const created = await copyShared(shareToken)
      try { sessionStorage.setItem(`bharat-sourcer:job:${created.job_id}`, created.job_token) } catch { /* signed-in access still works */ }
      onCopied(created.job_id)
    } catch (cause) { setCopyFailure(copyError(cause)); setCopying(false) }
  }
  useEffect(() => {
    let active = true
    void getShared(shareToken).then(value => { if (active) setShared(value) }).catch(cause => {
      if (!active) return
      setError(cause instanceof ApiError && cause.status === 404 ? 'This share link was revoked or replaced by a newer link. Ask the owner for a new one.' : cause instanceof ApiError && cause.status === 429 ? 'Too many views of shared reports from this connection. Please try again later.' : cause instanceof Error ? cause.message : 'Could not load the shared report.')
    })
    return () => { active = false }
  }, [shareToken])
  const job = shared && asJob(shared)
  return <main id="main" className="job-page project-page"><div className="container job-container pp-container">
    <p className="pp-demo-tag pp-shared-tag">Shared build plan, read only</p><section className="project-heading"><div className="editable-project-field"><h1>{shared?.project?.title || 'Shared parts list'}</h1></div>{shared?.project?.description && <div className="editable-project-field"><p>{shared.project.description}</p></div>}{shared && secureSource(shared.source_url) && <a className="project-source-link" href={shared.source_url} target="_blank" rel="noopener noreferrer">Open original project source ↗</a>}</section>
    {error ? <section className="job-panel"><h2>We couldn’t open this link</h2><p role="alert">{error}</p></section> : !shared || !job ? <section className="job-panel loading-panel" role="status"><span className="loading-indicator" /> Loading the shared report…</section> : <>
      <div className="share-notice" role="note"><strong>Read-only shared report</strong> · {shared.notice}</div>
      <section className="copy-shared" aria-labelledby="copy-shared-title"><div><h2 id="copy-shared-title">Want to build this too?</h2><p>Copy it to your projects to edit the parts, refresh prices and plan your own order. The owner’s project is not changed.</p></div><button type="button" className="primary-button" disabled={copying} onClick={() => void copy()}>{copying ? 'Copying…' : 'Copy to my projects'}</button>{copyFailure && <p className="form-error" role="alert">{copyFailure}</p>}</section>
      {shared.demo && <div className="demo-alert"><strong>Demo data</strong> · Fixed sample. Extraction, seller checks, prices and compatibility were not verified.</div>}
      
      {job.report ? <Results job={job} token="" onJob={() => undefined} shareToken={shareToken} /> : <section className="job-panel"><h2>No report yet</h2><p>The owner has not finished sourcing this project. Status: {shared.status.replaceAll('_', ' ')}.</p></section>}
    </>}
  </div></main>
}

const secureSource = (url: string) => /^https:\/\/[^\s]+$/i.test(url)
