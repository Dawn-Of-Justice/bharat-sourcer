import { auth } from './auth'
import type { ErrorBody, Job } from './api'

interface WatchJobOptions {
  jobId: string
  token: string
  signal: AbortSignal
  onSnapshot: (job: Job) => void
  onError: (message: string, status?: number) => void
}

function pause(ms: number, signal: AbortSignal): Promise<void> {
  if (signal.aborted) return Promise.resolve()
  return new Promise(resolve => {
    const finish = () => {
      clearTimeout(timer)
      signal.removeEventListener('abort', finish)
      resolve()
    }
    const timer = setTimeout(finish, ms)
    signal.addEventListener('abort', finish, { once: true })
  })
}

// The backend sends complete saved jobs. A new connection always starts with a fresh snapshot.
export async function watchJob({ jobId, token, signal, onSnapshot, onError }: WatchJobOptions): Promise<void> {
  const url = `/api/v1/jobs/${encodeURIComponent(jobId)}/stream`
  let backoff = 1000

  while (!signal.aborted) {
    let reader: ReadableStreamDefaultReader<Uint8Array> | undefined
    try {
      if (auth) await auth.authStateReady()
      // Force a refresh on every connection, including recovery from an expired token.
      const bearer = await auth?.currentUser?.getIdToken(true)
      if (signal.aborted) return
      const response = await fetch(url, {
        headers: {
          Accept: 'text/event-stream',
          'X-Requested-With': 'BharatSourcer',
          ...(token ? { 'X-Job-Token': token } : {}),
          ...(bearer ? { Authorization: `Bearer ${bearer}` } : {}),
        },
        credentials: 'include',
        cache: 'no-store',
        signal,
      })

      if (!response.ok) {
        const detail = (await response.json().catch(() => null)) as ErrorBody | null
        if (response.status === 401) {
          onError('Sign in again to continue receiving updates.', 401)
          if (detail?.error?.code === 'IDENTITY_REQUIRED') window.dispatchEvent(new Event('bs-signin-required'))
          return
        }
        if (response.status === 404) {
          onError('This project is unavailable or belongs to another account.', 404)
          return
        }
        if (response.status === 429) {
          onError('Live update limit reached. Your saved project remains available.', 429)
          return
        }
        if (response.status >= 400 && response.status < 500) {
          onError(detail?.error?.message || `Live updates unavailable (${response.status}).`, response.status)
          return
        }
        onError(
          response.status === 503
            ? 'Live updates are temporarily unavailable. Reconnecting to your saved project…'
            : `Live updates unavailable (${response.status}). Reconnecting…`,
          response.status,
        )
      } else {
        if (!response.body) throw new Error('Streaming body unavailable')
        reader = response.body.getReader()
        const decoder = new TextDecoder()
        let pending = ''
        let event = 'message'
        let data: string[] = []

        function consume(chunk: string) {
          pending += chunk
          let newline: number
          while ((newline = pending.indexOf('\n')) !== -1) {
            const line = pending.slice(0, newline).replace(/\r$/, '')
            pending = pending.slice(newline + 1)
            if (!line) {
              if (event === 'snapshot' && data.length) {
                onSnapshot(JSON.parse(data.join('\n')) as Job)
                backoff = 1000
              } else if (event === 'stream_error') {
                onError('Live updates are temporarily unavailable. Reconnecting…')
              }
              event = 'message'
              data = []
            } else if (!line.startsWith(':')) {
              const colon = line.indexOf(':')
              const field = colon < 0 ? line : line.slice(0, colon)
              const value = colon < 0 ? '' : line.slice(colon + 1).replace(/^ /, '')
              if (field === 'event') event = value
              if (field === 'data') data.push(value)
            }
          }
        }

        while (!signal.aborted) {
          const next = await reader.read()
          if (next.done) {
            consume(decoder.decode())
            break
          }
          consume(decoder.decode(next.value, { stream: true }))
        }
      }
    } catch {
      if (signal.aborted) return
      onError('Connection interrupted. Reconnecting to your saved project…')
      backoff = Math.min(backoff * 2, 10000)
    } finally {
      if (reader) {
        await reader.cancel().catch(() => {})
        reader.releaseLock()
      }
    }
    await pause(backoff, signal)
  }
}
