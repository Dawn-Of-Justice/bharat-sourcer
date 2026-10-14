import { useEffect, useRef, useState } from 'react'
import { flushSync } from 'react-dom'

// Hover/focus prefetching, lazy-chunk preloaders and small motion helpers shared across views.

// Data Saver (navigator.connection.saveData) turns all speculative prefetching off.
export function canPrefetch() {
  const connection = (navigator as Navigator & { connection?: { saveData?: boolean } }).connection
  return !connection?.saveData
}

// Lazy view chunks. Each loader is the same promise React.lazy uses, so preloading on hover makes opening instant.
const once = <T>(load: () => Promise<T>) => {
  let promise: Promise<T> | null = null
  return () =>
    (promise ??= load().catch(cause => {
      promise = null
      throw cause
    }))
}
export const loadResults = once(() => import('./Results'))
export const loadBuildPage = once(() => import('./BuildPage'))
export const loadSharedReport = once(() => import('./SharedReport'))
export const loadChatPanel = once(() => import('./ChatPanel'))
export const loadProjectOverview = once(() => import('./ProjectOverview'))

export function preload(load: () => Promise<unknown>) {
  if (canPrefetch()) void load().catch(() => undefined)
}

// Handlers that run `prefetch` once the pointer rests on (or focus reaches) an element for `delay` ms.
export function usePrefetch(prefetch: () => void, delay = 80) {
  const timer = useRef<number | undefined>(undefined)
  const latest = useRef(prefetch)
  useEffect(() => {
    latest.current = prefetch
  })
  useEffect(() => () => window.clearTimeout(timer.current), [])
  const start = () => {
    if (!canPrefetch()) return
    window.clearTimeout(timer.current)
    timer.current = window.setTimeout(() => latest.current(), delay)
  }
  const cancel = () => window.clearTimeout(timer.current)
  return { onPointerEnter: start, onPointerLeave: cancel, onFocus: start, onBlur: cancel }
}

export const reducedMotion = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches

// Runs a React state update inside a View Transition when the browser supports it and motion is allowed.
export function withViewTransition(update: () => void) {
  if (!('startViewTransition' in document) || reducedMotion() || document.visibilityState !== 'visible') {
    update()
    return
  }
  let applied = false
  const apply = () => {
    if (applied) return
    applied = true
    flushSync(update)
  }
  const transition = document.startViewTransition(apply)
  // A page that is visible but not painting (an occluded window, a hidden embedded browser) never reaches the
  // transition's update, so the click would only land on the next one. Apply it without the animation then.
  const fallback = window.setTimeout(() => {
    if (applied) return
    transition.skipTransition()
    apply()
  }, 250)
  // A skipped or aborted transition still applies the update; its animation promises then reject harmlessly.
  transition.updateCallbackDone.then(
    () => window.clearTimeout(fallback),
    () => window.clearTimeout(fallback),
  )
  transition.ready.catch(() => undefined)
  transition.finished.catch(() => undefined)
}

// A class name for ~400 ms after `value` changes (not on first render), to play a short pulse. It alternates between
// two names so rapid changes restart the animation without remounting the element (which would drop focus).
export function usePulse(value: unknown) {
  const [pulse, setPulse] = useState(0)
  const previous = useRef(value)
  useEffect(() => {
    if (Object.is(previous.current, value)) return
    previous.current = value
    setPulse(current => current + 1)
    const timer = window.setTimeout(() => setPulse(0), 400)
    return () => window.clearTimeout(timer)
  }, [value])
  return pulse ? (pulse % 2 ? 'is-pulse-a' : 'is-pulse-b') : ''
}
