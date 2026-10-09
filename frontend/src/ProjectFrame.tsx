import { useEffect, useRef, useState, type ReactNode } from 'react'
import type { Job } from './api'
import { ChatIcon } from './LandingIcons'

// The project page's three-step journey: the same order the user goes through.
const steps = ['Review the parts', 'Find sellers', 'Order plan'] as const

function stepOf(job: Job): number {
  if (['queued', 'extracting', 'awaiting_confirmation'].includes(job.status)) return 0
  if (['resolving', 'sourcing', 'paused'].includes(job.status)) return 1
  if (job.status === 'done') return 2
  return job.report ? 2 : job.items.length ? 1 : 0
}

export function stageNote(job: Job, reading: string): string {
  if (job.status === 'queued') return 'Waiting to start'
  if (job.status === 'extracting') return reading
  if (job.status === 'awaiting_confirmation') return 'Waiting for you'
  if (job.status === 'resolving') return 'Preparing your parts'
  if (job.status === 'paused') return 'Paused'
  if (job.status === 'failed') return 'Stopped'
  if (job.status === 'sourcing') {
    const lines = new Map(job.report?.lines.map(line => [line.item.line_id, line]) ?? [])
    const done = job.items.filter(item => item.user_has_it || (lines.get(item.line_id)?.sourcing_status ?? 'not_run') !== 'not_run').length
    return `Checking sellers, ${done} of ${job.items.length} parts done`
  }
  return 'Ready'
}

export function StageSteps({ job, reading, action }: { job: Job; reading: string; action?: ReactNode }) {
  const current = stepOf(job)
  const finished = job.status === 'done'
  const failed = job.status === 'failed'
  const working = ['queued', 'extracting', 'resolving', 'sourcing'].includes(job.status)
  return <nav className="pp-steps" aria-label="Project progress">
    <ol>{steps.map((label, index) => {
      const state = index < current || (finished && index === current) ? 'done' : index === current ? failed ? 'failed' : 'current' : 'next'
      return <li key={label} className={`pp-step pp-step-${state}`} aria-current={index === current ? 'step' : undefined}>
        <span className="pp-step-node" aria-hidden="true">{state === 'done' ? '✓' : state === 'failed' ? '!' : index + 1}</span>
        <span className="pp-step-text"><strong>{label}</strong>{index === current && <span role="status" aria-live="polite">{working && <i className="pp-live" aria-hidden="true" />}{stageNote(job, reading)}</span>}</span>
      </li>
    })}</ol>
    {action && <div className="pp-steps-action">{action}</div>}
  </nav>
}

const pending = (job: Job) => job.messages.filter(message => message.proposal?.status === 'pending' || message.refresh_proposal?.status === 'pending' || message.spec_proposal?.status === 'pending').length

// Chat lives in a side panel so the page can use its full width. It stays mounted while
// closed, keeping the draft and scroll position.
export function ChatDrawer({ job, children }: { job: Job; children: ReactNode }) {
  const [open, setOpen] = useState(false)
  const closeRef = useRef<HTMLButtonElement>(null)
  const launcherRef = useRef<HTMLButtonElement>(null)
  const waiting = pending(job)
  const thinking = job.chat_state === 'queued' || job.chat_state === 'thinking'

  useEffect(() => {
    if (!open) return
    closeRef.current?.focus()
    function onKey(event: KeyboardEvent) { if (event.key === 'Escape') close() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open])

  function close() {
    setOpen(false)
    launcherRef.current?.focus()
  }

  return <>
    <button ref={launcherRef} type="button" className="pp-chat-launcher" aria-expanded={open} aria-controls="pp-chat" onClick={() => open ? close() : setOpen(true)}>
      <ChatIcon /> <span>Ask about this build</span>
      {waiting > 0 && <b className="pp-chat-badge" aria-label={`${waiting} ${waiting === 1 ? 'suggestion' : 'suggestions'} waiting for you`}>{waiting}</b>}
      {!waiting && thinking && <i className="pp-live" aria-hidden="true" />}
    </button>
    <section id="pp-chat" className={`pp-drawer ${open ? 'is-open' : ''}`} aria-label="Ask about this build" inert={!open}
      onClick={event => { if ((event.target as HTMLElement).closest('.citation-detail button') && window.matchMedia('(max-width: 760px)').matches) setOpen(false) }}>
      <header className="pp-drawer-head"><h2>Ask about this build</h2><button ref={closeRef} type="button" className="pp-icon-button" aria-label="Close" onClick={close}>✕</button></header>
      <div className="pp-drawer-body">{children}</div>
    </section>
  </>
}
