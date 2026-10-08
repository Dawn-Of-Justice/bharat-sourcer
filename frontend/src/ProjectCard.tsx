import { useState, type ReactNode } from 'react'
import { deleteProject, type Project } from './api'

type Source = { kind: 'youtube' | 'github' | 'article' | 'link'; label: string }

function sourceOf(url: string): Source {
  let host = ''
  try { host = new URL(url).hostname.replace(/^www\./, '') } catch { return { kind: 'link', label: 'Saved link' } }
  if (['youtube.com', 'm.youtube.com', 'youtu.be'].includes(host)) return { kind: 'youtube', label: 'YouTube video' }
  if (host === 'github.com') return { kind: 'github', label: 'GitHub repository' }
  if (host === 'instructables.com') return { kind: 'article', label: 'Instructables' }
  if (host === 'learn.adafruit.com') return { kind: 'article', label: 'Adafruit Learn' }
  return { kind: 'article', label: host }
}

// Stroke icons on a 24px grid; they follow the tile's text colour.
const stroke = { fill: 'none', stroke: 'currentColor', strokeWidth: 1.8, strokeLinecap: 'round', strokeLinejoin: 'round' } as const
const sourceIcons: Record<Source['kind'], ReactNode> = {
  youtube: <svg viewBox="0 0 24 24" aria-hidden="true"><rect x="2" y="5" width="20" height="14" rx="4" fill="currentColor" /><path d="m10 9 6 3-6 3V9Z" fill="#fff" /></svg>,
  github: <svg viewBox="0 0 24 24" aria-hidden="true" {...stroke}><path d="m8 8-4 4 4 4" /><path d="m16 8 4 4-4 4" /><path d="m13.5 5-3 14" /></svg>,
  article: <svg viewBox="0 0 24 24" aria-hidden="true" {...stroke}><rect x="4" y="3" width="16" height="18" rx="2" /><path d="M8 8h8" /><path d="M8 12h8" /><path d="M8 16h5" /></svg>,
  link: <svg viewBox="0 0 24 24" aria-hidden="true" {...stroke}><path d="M10 13a5 5 0 0 0 7.07 0l3-3a5 5 0 0 0-7.07-7.07l-1.5 1.5" /><path d="M14 11a5 5 0 0 0-7.07 0l-3 3a5 5 0 0 0 7.07 7.07l1.5-1.5" /></svg>,
}

type Tone = 'working' | 'action' | 'ready' | 'muted' | 'error'
const statusIcons: Record<Tone, ReactNode> = {
  working: <svg viewBox="0 0 24 24" aria-hidden="true" {...stroke}><circle cx="12" cy="12" r="8" /><path d="M12 8v4l2.5 2" /></svg>,
  action: <svg viewBox="0 0 24 24" aria-hidden="true" {...stroke}><path d="M12 20h8" /><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z" /></svg>,
  ready: <svg viewBox="0 0 24 24" aria-hidden="true" {...stroke}><circle cx="12" cy="12" r="8" /><path d="m8.5 12 2.5 2.5 4.5-5" /></svg>,
  muted: <svg viewBox="0 0 24 24" aria-hidden="true" {...stroke}><circle cx="12" cy="12" r="8" /><path d="M10 9v6" /><path d="M14 9v6" /></svg>,
  error: <svg viewBox="0 0 24 24" aria-hidden="true" {...stroke}><circle cx="12" cy="12" r="8" /><path d="M12 8v5" /><path d="M12 16h.01" /></svg>,
}
const statuses: Record<string, [string, Tone]> = {
  queued: ['Reading the source', 'working'],
  extracting: ['Reading the source', 'working'],
  awaiting_confirmation: ['Review the parts', 'action'],
  resolving: ['Finding sellers', 'working'],
  sourcing: ['Finding sellers', 'working'],
  paused: ['Paused', 'muted'],
  done: ['Order plan ready', 'ready'],
  failed: ['Needs attention', 'error'],
}

const trashIcon = <svg viewBox="0 0 24 24" aria-hidden="true" {...stroke}><path d="M4 7h16" /><path d="M10 11v6" /><path d="M14 11v6" /><path d="M6 7l1 13h10l1-13" /><path d="M9 7V4h6v3" /></svg>

export function projectTitle(project: Project) {
  if (project.title) return project.title
  try { return new URL(project.url).hostname + ' project' } catch { return 'Saved project' }
}

export default function ProjectCard({ project, onOpen, onDeleted }: { project: Project; onOpen: () => void; onDeleted: () => void }) {
  const [confirming, setConfirming] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const source = sourceOf(project.url)
  const [statusLabel, tone] = statuses[project.status] ?? [project.status.replaceAll('_', ' '), 'muted' as Tone]
  const title = projectTitle(project)
  const updated = new Date(project.updated_at).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })
  async function remove() {
    setBusy(true); setError('')
    try {
      await deleteProject(project.job_id)
      try { sessionStorage.removeItem(`bharat-sourcer:job:${project.job_id}`) } catch { /* nothing saved */ }
      onDeleted()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not delete the project. Please try again.')
      setBusy(false)
    }
  }
  return <article className={`project-card source-${source.kind}`} aria-busy={busy}>
    <div className="project-card-top">
      <span className="project-icon" title={source.label}>{sourceIcons[source.kind]}</span>
      <span className={`project-status status-${tone}`}>{statusIcons[tone]}{statusLabel}</span>
    </div>
    <h2><button type="button" className="project-open-link" onClick={onOpen}>{title}</button></h2>
    {project.description && <p className="project-source">{project.description}</p>}
    <p className="project-origin">{source.label}</p>
    <div className="project-meta"><span>{project.part_count} {project.part_count === 1 ? 'part' : 'parts'}</span><span>Updated {updated}</span></div>
    {confirming ? <div className="project-confirm" role="group" aria-label={`Delete ${title}`}>
      <p><strong>Delete this project?</strong> Its parts list, seller offers, conversation and share link are removed for good.</p>
      {error && <p className="form-error" role="alert">{error}</p>}
      <div><button type="button" className="nav-cta" disabled={busy} onClick={() => { setConfirming(false); setError('') }}>Cancel</button><button type="button" className="danger-button" disabled={busy} onClick={() => void remove()}>{busy ? 'Deleting…' : 'Delete project'}</button></div>
    </div> : <div className="project-actions">
      <span className="project-open" aria-hidden="true">Open project <span>→</span></span>
      <button type="button" className="project-delete" aria-label={`Delete ${title}`} title="Delete project" onClick={() => setConfirming(true)}>{trashIcon}</button>
    </div>}
  </article>
}
