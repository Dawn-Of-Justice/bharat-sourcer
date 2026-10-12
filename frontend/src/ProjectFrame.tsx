import { useEffect, useRef, type MouseEvent, type ReactNode } from 'react'
import type { Job } from './api'
import { ChatIcon } from './LandingIcons'

// The project page's three-step journey: the same order the user goes through.
const steps = ['Review the parts', 'Find sellers', 'Order plan'] as const

export function stepOf(job: Job): number {
  if (['queued', 'extracting', 'awaiting_confirmation'].includes(job.status)) return 0
  if (['resolving', 'sourcing', 'paused'].includes(job.status)) return 1
  if (job.status === 'done') return 2
  return job.report ? 2 : job.items.length ? 1 : 0
}

function stageNote(job: Job, reading: string): string {
  if (job.status === 'queued') return 'Waiting to start'
  if (job.status === 'extracting') return reading
  if (job.status === 'awaiting_confirmation') return 'Ready for your review'
  if (job.status === 'resolving') return 'Preparing your parts'
  if (job.status === 'paused') return 'Paused'
  if (job.status === 'failed') return 'Stopped'
  if (job.status === 'sourcing') {
    const lines = new Map(job.report?.lines.map(line => [line.item.line_id, line]) ?? [])
    const done = job.items.filter(
      item => item.user_has_it || (lines.get(item.line_id)?.sourcing_status ?? 'not_run') !== 'not_run',
    ).length
    return `Checking sellers, ${done} of ${job.items.length} parts done`
  }
  return 'Ready'
}

// Reached steps are buttons: the user can look back at an earlier stage (`viewing`).
export function StageSteps({
  job,
  reading,
  viewing,
  onView,
  action,
}: {
  job: Job
  reading: string
  viewing: number
  onView: (step: number) => void
  action?: ReactNode
}) {
  const current = stepOf(job)
  const finished = job.status === 'done'
  const failed = job.status === 'failed'
  const working = ['queued', 'extracting', 'resolving', 'sourcing'].includes(job.status)
  return (
    <nav className="pp-steps" aria-label="Project progress">
      <ol>
        {steps.map((label, index) => {
          const state =
            index < current || (finished && index === current)
              ? 'done'
              : index === current
                ? failed
                  ? 'failed'
                  : 'current'
                : 'next'
          const node = (
            <span className="pp-step-node" aria-hidden="true">
              {state === 'done' ? '✓' : state === 'failed' ? '!' : index + 1}
            </span>
          )
          const text = (
            <span className="pp-step-text">
              <strong>{label}</strong>
              {index === current ? (
                <span role="status" aria-live="polite">
                  {working && <i className="pp-live" aria-hidden="true" />}
                  {stageNote(job, reading)}
                </span>
              ) : index < current && viewing !== index ? (
                <span>View</span>
              ) : null}
            </span>
          )
          return (
            <li
              key={label}
              className={`pp-step pp-step-${state}${viewing === index ? ' pp-step-viewing' : ''}`}
              aria-current={index === current ? 'step' : undefined}
            >
              {index <= current ? (
                <button
                  type="button"
                  className="pp-step-button"
                  aria-pressed={viewing === index}
                  onClick={() => onView(index)}
                >
                  {node}
                  {text}
                </button>
              ) : (
                <>
                  {node}
                  {text}
                </>
              )}
            </li>
          )
        })}
      </ol>
      {action && <div className="pp-steps-action">{action}</div>}
    </nav>
  )
}

// A panel on the right: docked beside the page on wide screens (the page makes room through
// .sheet-open), inset from the screen edges on small ones. It starts below the site header so the header stays
// usable, closes on Esc and returns focus to whatever opened it. Children stay mounted while
// closed, so drafts and scroll positions survive.
export function SidePanel({
  id,
  open,
  title,
  subtitle,
  onClose,
  onBodyClick,
  children,
}: {
  id: string
  open: boolean
  title: string
  subtitle?: ReactNode
  onClose: () => void
  onBodyClick?: (event: MouseEvent<HTMLElement>) => void
  children: ReactNode
}) {
  const panelRef = useRef<HTMLElement>(null)
  const closeRef = useRef<HTMLButtonElement>(null)
  const opener = useRef<HTMLElement | null>(null)

  useEffect(() => {
    if (!open) return
    opener.current = document.activeElement instanceof HTMLElement ? document.activeElement : null
    closeRef.current?.focus({ preventScroll: true })
    function onKey(event: KeyboardEvent) {
      if (event.key === 'Escape') onClose()
    }
    function place() {
      const bottom = document.querySelector('.site-header')?.getBoundingClientRect().bottom ?? 0
      panelRef.current?.style.setProperty('--pp-drawer-top', `${Math.max(0, Math.round(bottom))}px`)
    }
    place()
    window.addEventListener('keydown', onKey)
    window.addEventListener('scroll', place, { passive: true })
    window.addEventListener('resize', place)
    return () => {
      window.removeEventListener('keydown', onKey)
      window.removeEventListener('scroll', place)
      window.removeEventListener('resize', place)
      if (opener.current?.isConnected) opener.current.focus({ preventScroll: true })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- onClose is an inline prop; re-running would refocus the opener on every parent render
  }, [open])

  return (
    <section
      ref={panelRef}
      id={id}
      className={`pp-drawer ${open ? 'is-open' : ''}`}
      aria-label={title}
      inert={!open}
      onClick={onBodyClick}
    >
      <header className="pp-drawer-head">
        <div className="pp-drawer-title">
          <h2>{title}</h2>
          {subtitle && <p>{subtitle}</p>}
        </div>
        <button ref={closeRef} type="button" className="pp-icon-button" aria-label="Close" onClick={onClose}>
          ✕
        </button>
      </header>
      <div className="pp-drawer-body">{children}</div>
    </section>
  )
}

const pending = (job: Job) =>
  job.messages.filter(
    message =>
      message.proposal?.status === 'pending' ||
      message.refresh_proposal?.status === 'pending' ||
      message.spec_proposal?.status === 'pending',
  ).length

// Chat lives in a side panel so the page can use its full width.
export function ChatDrawer({
  job,
  open,
  onOpenChange,
  children,
}: {
  job: Job
  open: boolean
  onOpenChange: (open: boolean) => void
  children: ReactNode
}) {
  const waiting = pending(job)
  const thinking = job.chat_state === 'queued' || job.chat_state === 'thinking'
  return (
    <>
      <button
        type="button"
        className="pp-chat-launcher"
        aria-label="Ask about this build"
        aria-expanded={open}
        aria-controls="pp-chat"
        onClick={() => onOpenChange(!open)}
      >
        <ChatIcon /> <span className="pp-chat-launcher-label">Ask about this build</span>
        {waiting > 0 && (
          <b
            className="pp-chat-badge"
            aria-label={`${waiting} ${waiting === 1 ? 'suggestion' : 'suggestions'} waiting for you`}
          >
            {waiting}
          </b>
        )}
        {!waiting && thinking && <i className="pp-live" aria-hidden="true" />}
      </button>
      <SidePanel
        id="pp-chat"
        open={open}
        title="Ask about this build"
        onClose={() => onOpenChange(false)}
        onBodyClick={event => {
          if (
            (event.target as HTMLElement).closest('.citation-detail button') &&
            window.matchMedia('(max-width: 1099px)').matches
          )
            onOpenChange(false)
        }}
      >
        {children}
      </SidePanel>
    </>
  )
}
