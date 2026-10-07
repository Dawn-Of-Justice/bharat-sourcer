import { identityToken } from './auth'
const API_BASE = '/api'

export type JobStatus = 'queued' | 'extracting' | 'awaiting_confirmation' | 'resolving' | 'sourcing' | 'done' | 'failed' | 'paused'

export type ChatEdit =
  | { op: 'add'; raw_name: string; qty: number; specs?: Record<string, string | number | boolean | null>; requirements?: PartRequirement[] }
  | { op: 'update'; line_id: string; raw_name?: string | null; qty?: number | null; specs?: Record<string, string | number | boolean | null> | null; requirements?: PartRequirement[] }
  | { op: 'remove'; line_id: string }
  | { op: 'have_it'; line_id: string; user_has_it?: boolean }

export interface ChatMessage {
  message_id: string
  role: 'user' | 'assistant'
  text: string
  created_at: string
  cited_line_ids: string[]
  proposal: { edits: ChatEdit[]; status: 'pending' | 'accepted' | 'rejected'; base_fingerprint: string } | null
  refresh_proposal?: { request: { line_ids: string[] }; status: 'pending' | 'accepted' | 'rejected'; base_fingerprint: string; refresh_count: number | null; result_message_id?: string | null } | null
  spec_proposal?: { request: { updates: SpecUpdate[] }; status: 'pending' | 'accepted' | 'rejected'; base_fingerprint: string } | null
  completes_message_id?: string | null
  refresh_results?: RefreshLineResult[]
  resistor_question?: { line_id: string; purpose: string; question: string } | null
}

// Same shape as one entry of POST /v1/jobs/{id}/specs. Specs merge; requirements replace the list.
export interface SpecUpdate { line_id: string; specs?: Record<string, string | number | boolean | null> | null; requirements?: PartRequirement[] | null }
// Snapshot written by the worker when an approved refresh batch ends. Prices are seller-published, not verified totals.
export interface RefreshLineResult { line_id: string; sourcing_status: ReportLine['sourcing_status']; offer_count?: number; lowest_listed_price_inr?: string | null; lowest_listed_stock?: 'in_stock' | 'out_of_stock' | 'preorder' | 'unknown' | null; price_source?: 'seller_published'; error_code?: string | null }
export interface ActionRecord { kind: 'edit' | 'refresh' | 'spec_update'; message_id: string; status: 'accepted' | 'rejected' | 'completed' | 'failed'; created_at?: string; line_ids?: string[]; summary?: string; refresh_count?: number | null; result_message_id?: string | null }

// origin defaults to 'user'; 'inferred' rows were pre-filled by the model from project context, with a reason.
export interface PartRequirement { name: string; value: string; unit?: string | null; operator: 'equals' | 'at_least' | 'at_most'; origin?: 'user' | 'inferred'; reason?: string | null }
// The extraction model's reading of the whole project. AI-inferred; the user should check it.
export interface ProjectUnderstanding { title?: string | null; title_source?: 'ai' | 'user' | null; description?: string | null; description_source?: 'ai' | 'user' | null; summary: string; power: string | null; controller: string | null; interfaces: string[]; assumptions: string[]; origin: 'ai_inferred' }
export interface ResearchAssessment { status: 'potential_match' | 'needs_information' | 'not_suitable' | 'stale'; explanation: string; conditions: string[]; questions: string[]; checks?: { requirement: PartRequirement; status: 'meets' | 'does_not_meet' | 'unknown'; reason: string }[] }
export interface ResearchCandidate { url: string; title: string; category: string; kind: 'seller' | 'manufacturer' | 'reference'; identity_quote: string; match: 'exact' | 'possible'; facts: { name: string; value: string; unit?: string | null; quote: string }[]; assessment: ResearchAssessment }
export interface Evidence {
  timestamp?: string | null
  observation: string
  // 'code': a GitHub file line (file, line, quote = the line's text, url = link to it). 'youtube_description': a checked quote from the video description.
  source?: 'video' | 'project_page' | 'code' | 'youtube_description'
  quote?: string | null
  url?: string | null
  file?: string | null
  line?: number | null
}

// Video evidence cites a timestamp; page, code and description evidence cite a server-checked quote.
export function evidenceText(entry: Evidence) {
  if (entry.source === 'project_page') return `Page quote “${entry.quote}” — ${entry.observation}`
  if (entry.source === 'code') return `Code ${entry.file ?? 'file'}${entry.line ? ':' + entry.line : ''}${entry.quote ? ` “${entry.quote}”` : ''} — ${entry.observation}`
  if (entry.source === 'youtube_description') return `Video description${entry.quote ? ` “${entry.quote}”` : ''} — ${entry.observation}`
  return entry.timestamp ? `${entry.timestamp} — ${entry.observation}` : `Video — ${entry.observation}`
}

export interface PartResearch { status: 'ready' | 'no_evidence' | 'failed' | 'stale'; summary: string; checked_at?: string; questions?: string[]; sources?: { url: string; status: 'read' | 'unavailable'; reason?: string | null; reviewed?: boolean }[]; candidates?: ResearchCandidate[] }

export interface BomItem {
  line_id: string
  raw_name: string
  qty: number | null
  // 'inferred' means the source gave no count and the model filled qty (see qty_reason); defaults to 'stated'.
  qty_source?: 'stated' | 'inferred' | 'user'
  qty_reason?: string | null
  user_has_it: boolean
  user_edited: boolean
  evidence: Evidence[]
  clarifications: { field: string; question: string }[]
  requirements?: PartRequirement[]
  lookalikes?: Lookalike[]
  conflicts?: ItemConflict[]
  // Deterministic rule over the evidence; null means not assessed (user-added or renamed lines).
  confidence?: 'verified' | 'likely' | 'check' | null
  confidence_reason?: string | null
  buyable_spec?: BuyableSpec | null
}

export type EvidenceSource = NonNullable<Evidence['source']>
export interface Lookalike { name: string; note?: string | null; origin: 'table' | 'ai' }
export interface ItemConflict { kind: 'identity_mismatch' | 'qty_mismatch'; message: string; values: { value: string; source: EvidenceSource; url?: string | null; locator?: string | null }[] }
// What to buy, stated the way sellers list parts. ai_inferred and seed specs are suggestions; user specs are the maker's own.
export interface SpecParam { name: string; value: string; operator: 'equals' | 'at_least' | 'at_most' | 'between'; value_max?: string | null; unit?: string | null; si_value?: number | null; si_value_max?: number | null; required?: boolean; origin?: 'stated' | 'inferred' | 'user'; reason?: string | null }
export interface BuyableSpec {
  origin: 'seed' | 'ai_inferred' | 'user'
  part_name?: string | null
  category: 'resistor' | 'capacitor_electrolytic' | 'capacitor_ceramic' | 'led' | 'ldr' | 'wire' | 'diode' | 'transistor' | 'ic' | 'module' | 'board' | 'sensor' | 'connector' | 'switch' | 'battery' | 'other'
  mount: 'tht' | 'smd' | 'any'
  mount_origin?: 'stated' | 'inferred' | 'user' | 'default'
  mount_reason?: string | null
  params: SpecParam[]
  must?: string[]
  prefer?: string[]
  exclude?: string[]
  synonyms?: string[]
  queries?: string[]
  needs_value?: boolean
  needs_value_reason?: string | null
  reasons?: string[]
}
// Deterministic rule checks (MAINS, LIPO, HIGH_CURRENT, LEVEL_SHIFT). Advice, not a safety review.
export interface SafetyFlag { code: 'MAINS' | 'LIPO' | 'HIGH_CURRENT' | 'LEVEL_SHIFT'; severity: 'danger' | 'warning' | 'caution'; title: string; message: string; guidance: string[]; line_ids: string[]; triggers?: { line_id?: string | null; field: string; matched: string }[]; method?: 'deterministic_rules'; rule_version?: string }
export interface SourceReport { url: string; kind: 'video' | 'instructables' | 'hackster' | 'github' | 'adafruit' | 'blog' | 'youtube_description'; role: 'primary' | 'additional'; status: 'read' | 'failed'; item_count: number; code_item_count?: number; error?: { code: string; message: string } | null; found_in?: 'youtube_description' | null }
export interface VideoMeta { video_id: string; title?: string | null; channel?: string | null; published_at?: string | null; fetched_at: string; links?: { url: string; kind: 'project_source' | 'video' | 'store' | 'other'; followed: boolean }[]; expired?: boolean }

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
    spec_conflicts?: { field: string; candidates: { field: string; value: string; source: 'part_name' | 'user' | 'seller_title' | 'seller_property' | 'seller_table'; locator: string }[] }[]
    compatibility: {
      status: string
      grade: string | null
      reasons: string[]
      changes: string[]
      missing_fields: string[]
    } | null
    research_assessment?: ResearchAssessment | null
  }[]
  subtotal_inr: string | null
  selected_offer_url?: string | null
  grade?: 'A' | 'B' | null
  research_accepted?: boolean
  research?: PartResearch | null
  image_candidates?: PartImage[]
}

export interface PartImage {
  url: string
  kind: 'seller' | 'source' | 'category' | 'generated' | 'placeholder'
  label: string
  source_url?: string | null
}

export interface Job {
  job_id: string
  status: JobStatus
  pause_requested?: boolean
  refresh_count?: number
  updated_at: string
  demo: boolean
  input: { url: string }
  items: BomItem[]
  project?: ProjectUnderstanding | null
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
  actions?: ActionRecord[]
  safety_flags?: SafetyFlag[]
  source_reports?: SourceReport[]
  video_meta?: VideoMeta | null
}

type JobEdit =
  | { op: 'update'; line_id: string; raw_name?: string; qty?: number; requirements?: PartRequirement[]; buyable_spec?: BuyableSpec }
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

// sources: up to 3 extra project URLs read alongside url (at most one video across all of them).
export function createJob(url: string, pin?: string, sources: string[] = []) {
  return request<{ job_id: string; job_token: string; demo: boolean }>('/v1/jobs', {
    method: 'POST',
    body: JSON.stringify({ url, ...(pin ? { pin } : {}), ...(sources.length ? { sources: sources.slice(0, 3) } : {}), lang: 'en' }),
  })
}

export async function getBackendMode() {
  const health = await request<{ mode: 'demo' | 'live' }>('/healthz')
  return health.mode
}

export function getJob(id: string, token: string) {
  return request<Job>(`/v1/jobs/${encodeURIComponent(id)}`, {}, token)
}

export function updateProject(id: string, token: string, changes: { title?: string; description?: string }) {
  return request<Job>(`/v1/jobs/${encodeURIComponent(id)}/project`, { method: 'POST', body: JSON.stringify(changes) }, token)
}

export interface PartImages { candidates: PartImage[]; fallback: PartImage; generation_status: 'not_needed' | 'not_requested' | 'ready' | 'pending' | 'unavailable' }
export function getPartImages(id: string, token: string, lineId: string) {
  return request<PartImages>(`/v1/jobs/${encodeURIComponent(id)}/parts/${encodeURIComponent(lineId)}/image`, {}, token)
}
export function reportFailedImages(id: string, token: string, lineId: string, failedUrls: string[]) {
  return request<PartImages>(`/v1/jobs/${encodeURIComponent(id)}/parts/${encodeURIComponent(lineId)}/image`, { method: 'POST', body: JSON.stringify({ failed_urls: failedUrls.slice(0, 10) }) }, token)
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
export interface Project { job_id: string; url: string; status: string; created_at: string; updated_at: string; part_count: number; title?: string | null; description?: string | null; summary?: string | null }
export const getSession = () => request<Session>('/v1/session')
export const startGuest = () => request<Session>('/v1/session/guest', { method: 'POST' })
export const logoutSession = () => request<void>('/v1/session/logout', { method: 'POST' })
export const listProjects = (cursor?: string) => request<{ projects: Project[]; next_cursor: string | null }>('/v1/projects?limit=20' + (cursor ? '&cursor=' + encodeURIComponent(cursor) : ''))
export const claimProject = (id: string, token?: string) => request('/v1/projects/' + encodeURIComponent(id) + '/claim', { method: 'POST', body: JSON.stringify(token ? { job_token: token } : {}) })

export interface UsageWindow { limit: number; used: number; remaining: number; resets_at: number }
export const getUsage = () => request<{ daily_actions: UsageWindow; daily_projects: UsageWindow; minute_actions: UsageWindow }>('/v1/session/usage')
export const pauseJob = (id: string, token: string) => request('/v1/jobs/' + encodeURIComponent(id) + '/pause', { method: 'POST' }, token)
export const resumeJob = (id: string, token: string) => request('/v1/jobs/' + encodeURIComponent(id) + '/resume', { method: 'POST' }, token)
export const selectOffer = (id: string, token: string, lineId: string, url: string | null, acceptChanges = false, acceptResearchAssessment = false) => request<Job>('/v1/jobs/' + encodeURIComponent(id) + '/selections', { method: 'POST', body: JSON.stringify({ selections: [{ line_id: lineId, offer_url: url, accept_changes: acceptChanges, accept_research_assessment: acceptResearchAssessment }] }) }, token)
export const refreshOffers = (id: string, token: string, lineIds: string[]) => request('/v1/jobs/' + encodeURIComponent(id) + '/refresh', { method: 'POST', body: JSON.stringify({ line_ids: lineIds }) }, token)
export const updateRequirements = (id: string, token: string, lineId: string, requirements: PartRequirement[]) => request<Job>('/v1/jobs/' + encodeURIComponent(id) + '/specs', { method: 'POST', body: JSON.stringify({ updates: [{ line_id: lineId, requirements }] }) }, token)
