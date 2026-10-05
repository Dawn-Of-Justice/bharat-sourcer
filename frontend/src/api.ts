import { identityToken } from './auth'
const API_BASE = (import.meta.env.PROD ? '/api' : (import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000')).replace(/\/$/, '')
const INTEGRATION_KEY = import.meta.env.DEV ? import.meta.env.VITE_INTEGRATION_KEY : undefined

export type JobStatus = 'queued' | 'extracting' | 'awaiting_confirmation' | 'resolving' | 'sourcing' | 'done' | 'failed' | 'paused'

export type ChatEdit =
  | { op: 'add'; raw_name: string; qty: number; specs?: Record<string, string | number | boolean | null> }
  | { op: 'update'; line_id: string; raw_name?: string | null; qty?: number | null; specs?: Record<string, string | number | boolean | null> | null }
  | { op: 'remove'; line_id: string }
  | { op: 'have_it'; line_id: string; user_has_it?: boolean }

export interface ChatMessage {
  message_id: string
  role: 'user' | 'assistant'
  text: string
  created_at: string
  cited_line_ids: string[]
  proposal: { edits: ChatEdit[]; status: 'pending' | 'accepted' | 'rejected'; base_fingerprint: string } | null
}

export interface BomItem {
  line_id: string
  raw_name: string
  qty: number | null
  user_has_it: boolean
  user_edited: boolean
  evidence: { timestamp: string; observation: string }[]
  clarifications: { field: string; question: string }[]
}

export interface ReportLine {
  item: BomItem
  sourcing_status: 'not_run' | 'already_owned' | 'offers_found' | 'no_verified_offers' | 'failed'
  sourcing_error: { code: string; message: string } | null
  offers: {
    url: string
    seller: string
    title: string
    image_url?: string | null
    price_inr: string
    stock: string
    checked_at: string
    compatibility: {
      status: string
      grade: string | null
      reasons: string[]
      changes: string[]
      missing_fields: string[]
    } | null
  }[]
  subtotal_inr: string | null
}

export interface Job {
  job_id: string
  status: JobStatus
  pause_requested?: boolean
  updated_at: string
  demo: boolean
  input: { url: string }
  items: BomItem[]
  events: { seq: number; status: JobStatus; message: string; timestamp: string }[]
  report: {
    summary: string
    lines: ReportLine[]
    selected_parts_subtotal_inr: string
    parts_subtotal_inr: string | null
    unselected_line_ids: string[]
  } | null
  error: { code: string; message: string } | null
  messages: ChatMessage[]
  chat_state: 'idle' | 'queued' | 'thinking' | 'failed'
  chat_error: { code: string; message: string } | null
}

type JobEdit =
  | { op: 'update'; line_id: string; raw_name?: string; qty?: number }
  | { op: 'have_it'; line_id: string; user_has_it: boolean }
  | { op: 'remove'; line_id: string }

export class ApiError extends Error {
  constructor(message: string, public status: number, public code?: string) {
    super(message)
    this.name = 'ApiError'
  }
}

async function request<T>(path: string, options: RequestInit = {}, token?: string): Promise<T> {
  if (import.meta.env.DEV && new URLSearchParams(window.location.search).get('preview') === '1') {
    const { previewRequest } = await import('./preview')
    return previewRequest(path, options) as T
  }
  const bearer = await identityToken()
  let response: Response
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...options,
      credentials: 'include',
      cache: 'no-store',
      headers: {
        'Content-Type': 'application/json',
        'X-Requested-With': 'BharatSourcer',
        ...(bearer ? { Authorization: 'Bearer ' + bearer } : {}),
        ...(INTEGRATION_KEY ? { 'X-Integration-Key': INTEGRATION_KEY } : {}),
        ...(token ? { 'X-Job-Token': token } : {}),
        ...options.headers,
      },
    })
  } catch {
    throw new Error('Could not reach the backend. Check the API URL and connection.')
  }

  if (!response.ok) {
    const data = await response.json().catch(() => null)
    if (path !== '/v1/session' && response.status === 401 && data?.error?.code === 'IDENTITY_REQUIRED') window.dispatchEvent(new Event('bs-signin-required'))
    const wait = Number(response.headers.get('Retry-After'))
    if (response.status === 429) throw new ApiError('Usage limit reached. Your saved projects remain available.' + (wait > 0 ? ' Try again after ' + new Date(Date.now() + wait * 1000).toLocaleString() + '.' : ' Please try again later.'), 429, data?.error?.code)
    throw new ApiError(data?.error?.message || `Request failed (${response.status}).`, response.status, data?.error?.code)
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

export function createJob(url: string, pin?: string) {
  return request<{ job_id: string; job_token: string; demo: boolean }>('/v1/jobs', {
    method: 'POST',
    body: JSON.stringify({ url, ...(pin ? { pin } : {}), lang: 'en' }),
  })
}

export async function getBackendMode() {
  const health = await request<{ mode: 'demo' | 'live' }>('/healthz')
  return health.mode
}

export function getJob(id: string, token: string) {
  return request<Job>(`/v1/jobs/${encodeURIComponent(id)}`, {}, token)
}

export function confirmJob(id: string, token: string, edits: JobEdit[]) {
  return request<{ status: 'resolving' }>(`/v1/jobs/${encodeURIComponent(id)}/confirm`, {
    method: 'POST',
    body: JSON.stringify({ edits }),
  }, token)
}

export function sendMessage(id: string, token: string, messageId: string, message: string) {
  return request<Job>(`/v1/jobs/${encodeURIComponent(id)}/messages`, {
    method: 'POST',
    body: JSON.stringify({ message_id: messageId, text: message }),
  }, token)
}

export function decideProposal(id: string, token: string, messageId: string, action: 'accept' | 'reject') {
  return request<Job>(`/v1/jobs/${encodeURIComponent(id)}/messages/${encodeURIComponent(messageId)}/decision`, {
    method: 'POST',
    body: JSON.stringify({ action }),
  }, token)
}

export interface Session { kind: 'account' | 'guest'; expires_at: number | null; daily_action_limit: number; part_limit: number }
export interface Project { job_id: string; url: string; status: string; created_at: string; updated_at: string; part_count: number }
export const getSession = () => request<Session>('/v1/session')
export const startGuest = () => request<Session>('/v1/session/guest', { method: 'POST' })
export const logoutSession = () => request<void>('/v1/session/logout', { method: 'POST' })
export const listProjects = (cursor?: string) => request<{ projects: Project[]; next_cursor: string | null }>('/v1/projects?limit=20' + (cursor ? '&cursor=' + encodeURIComponent(cursor) : ''))
export const claimProject = (id: string, token?: string) => request('/v1/projects/' + encodeURIComponent(id) + '/claim', { method: 'POST', body: JSON.stringify(token ? { job_token: token } : {}) })

export interface UsageWindow { limit: number; used: number; remaining: number; resets_at: number }
export const getUsage = () => request<{ daily_actions: UsageWindow; daily_projects: UsageWindow; minute_actions: UsageWindow }>('/v1/session/usage')
export const pauseJob = (id: string, token: string) => request('/v1/jobs/' + encodeURIComponent(id) + '/pause', { method: 'POST' }, token)
export const resumeJob = (id: string, token: string) => request('/v1/jobs/' + encodeURIComponent(id) + '/resume', { method: 'POST' }, token)
