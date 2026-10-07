import { useEffect, useState } from 'react'
import { ApiError, getShared, type Job, type SharedProject } from './api'
import Results from './Results'

// Public, read-only report at /shared/<token>. No sign-in, chat, edit, select, refresh or image-generation controls.
function asJob(shared: SharedProject): Job {
  return { job_id: '', status: shared.status, updated_at: shared.updated_at, demo: shared.demo, input: { url: shared.source_url }, items: shared.items, project: shared.project ?? null, events: [], report: shared.report ?? null, error: null, messages: [], chat_state: 'idle', chat_error: null }
}

export default function SharedReport({ shareToken }: { shareToken: string }) {
  const [shared, setShared] = useState<SharedProject | null>(null)
  const [error, setError] = useState('')
  useEffect(() => {
    let active = true
    void getShared(shareToken).then(value => { if (active) setShared(value) }).catch(cause => {
      if (!active) return
      setError(cause instanceof ApiError && cause.status === 404 ? 'This share link was revoked or replaced by a newer link. Ask the owner for a new one.' : cause instanceof ApiError && cause.status === 429 ? 'Too many views of shared reports from this connection. Please try again later.' : cause instanceof Error ? cause.message : 'Could not load the shared report.')
    })
    return () => { active = false }
  }, [shareToken])
  const job = shared && asJob(shared)
  return <main id="main" className="job-page"><div className="container job-container">
    <div className="job-hero"><div className="eyebrow"><span className="eyebrow-line" /> SHARED BUILD PLAN</div><h1>{shared?.project?.title || 'Shared parts list'}</h1>{shared?.project?.description && <p>{shared.project.description}{shared.project.description_source === 'ai' ? ' (AI-written)' : ''}</p>}</div>
    {error ? <section className="job-panel"><h2>We couldn’t open this link</h2><p role="alert">{error}</p></section> : !shared || !job ? <section className="job-panel loading-panel" role="status"><span className="loading-indicator" /> Loading the shared report…</section> : <>
      <div className="share-notice" role="note"><strong>Read-only shared report</strong> · {shared.notice}</div>
      {shared.demo && <div className="demo-alert"><strong>Demo data</strong> · Fixed sample. Extraction, seller checks, prices and compatibility were not verified.</div>}
      {shared.project?.summary && <p className="job-panel-intro">AI understanding of the project: {shared.project.summary}</p>}
      {secureSource(shared.source_url) && <p className="job-panel-intro">Source: <a href={shared.source_url} target="_blank" rel="noopener noreferrer">{shared.source_url} ↗</a></p>}
      {job.report ? <Results job={job} token="" onJob={() => undefined} shareToken={shareToken} /> : <section className="job-panel"><h2>No report yet</h2><p>The owner has not finished sourcing this project. Status: {shared.status.replaceAll('_', ' ')}.</p></section>}
    </>}
  </div></main>
}

const secureSource = (url: string) => /^https:\/\/[^\s]+$/i.test(url)
