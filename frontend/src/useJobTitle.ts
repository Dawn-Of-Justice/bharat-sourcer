import { useEffect } from 'react'
import type { Job, JobStatus } from './api'

const labels: Record<JobStatus, string> = {
  queued: 'Queued',
  extracting: 'Reading your project…',
  awaiting_confirmation: '✓ Parts list ready to review',
  resolving: 'Preparing your parts…',
  sourcing: 'Finding sellers…',
  done: '✓ Results ready',
  failed: '⚠ Run needs attention',
  paused: 'Ⅱ Run paused',
}

export function jobTabTitle(job: Job | null, fatalError: string, connectionIssue: string): string {
  let label = job ? labels[job.status] : 'Loading project…'
  if (fatalError) label = '⚠ Project unavailable'
  else if (connectionIssue) label = '⚠ Updates interrupted'
  return `${label} — Bharat Sourcer`
}

export function useJobTitle(job: Job | null, fatalError: string, connectionIssue: string) {
  const statusTitle = jobTabTitle(job, fatalError, connectionIssue)
  const projectTitle = job?.project?.title
  useEffect(() => {
    const original = document.title
    const update = () => {
      document.title = document.hidden ? statusTitle : projectTitle ? `${projectTitle} — Bharat Sourcer` : statusTitle
    }
    update()
    document.addEventListener('visibilitychange', update)
    return () => {
      document.removeEventListener('visibilitychange', update)
      document.title = original
    }
  }, [statusTitle, projectTitle])
}
