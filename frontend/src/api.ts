const API_BASE = (import.meta.env.PROD ? '/api' : (import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000')).replace(/\/$/, '')
const INTEGRATION_KEY = import.meta.env.DEV ? import.meta.env.VITE_INTEGRATION_KEY : undefined

export type JobStatus = 'queued' | 'extracting' | 'awaiting_confirmation' | 'resolving' | 'sourcing' | 'done' | 'failed'

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
  let response: Response
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
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
    throw new ApiError(data?.error?.message || `Request failed (${response.status}).`, response.status, data?.error?.code)
  }
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
