import { useEffect, useState } from 'react'
import { getOverview, regenerateOverview, type Job, type ProjectOverview } from './api'
import { useToast } from './toastContext'

// The review step's project overview (docs/contracts/project-overview.md): the job's overview, polled while it is
// generated, plus the owner's Draw / Try again / Redraw action. All AI-inferred; never verified against the board.

// Changes whenever the backend's overview changes; a local reply is shown only until then.
const overviewKey = (overview: ProjectOverview | null | undefined) =>
  overview
    ? [
        overview.status,
        overview.stage,
        overview.generated_at,
        overview.items_hash,
        overview.parts.length,
        overview.wiring.length,
      ].join('|')
    : 'none'

export function useOverview(job: Job, token: string) {
  const key = overviewKey(job.overview)
  const [local, setLocal] = useState<{ overview: ProjectOverview; base: string } | null>(null)
  const overview = local && local.base === key ? local.overview : (job.overview ?? null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const pending = overview?.status === 'pending'
  const toast = useToast()

  // Poll while the drawing is generated (parts arrive a group at a time); the job stream may deliver them first.
  useEffect(() => {
    if (!pending) return
    let alive = true
    const timer = setInterval(() => {
      getOverview(job.job_id, token).then(
        next => {
          if (alive && next) setLocal({ overview: next, base: key })
        },
        () => undefined,
      )
    }, 1500)
    return () => {
      alive = false
      clearInterval(timer)
    }
  }, [pending, job.job_id, token, key])

  async function regenerate() {
    setBusy(true)
    setError('')
    try {
      setLocal({ overview: await regenerateOverview(job.job_id, token), base: key })
    } catch (cause) {
      const message = cause instanceof Error ? cause.message : 'Could not start the drawing.'
      setError(message)
      toast(message, 'error')
    } finally {
      setBusy(false)
    }
  }

  return { overview, pending, busy, error, regenerate }
}
