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
  source?: 'video' | 'project_page'
  quote?: string | null
  url?: string | null
}

// Video evidence cites a timestamp; project-page evidence cites a server-checked quote.
export function evidenceText(entry: Evidence) {
  return entry.source === 'project_page' ? `Page quote “${entry.quote}” — ${entry.observation}` : `${entry.timestamp} — ${entry.observation}`
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
}

type JobEdit =
  | { op: 'update'; line_id: string; raw_name?: string; qty?: number; requirements?: PartRequirement[] }
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

// --- report v0.21 ---
// Report-side types (costing, order plan, recommendations, matching, trust, grades, markets, share, extras).
// The ReportLine and Job interfaces below merge into the ones above; offers and report are widened through ReportOffer and Report.
export interface CostAmount { amount_inr?: string | null; status?: 'known' | 'estimated' | 'unknown'; partial_inr?: string | null; assumptions?: string[] }
export interface ShippingPolicyRef { seller: string; free_above_inr?: string | null; free_when?: 'above' | 'at_or_above'; flat_fee_inr?: string | null; fee_plus_gst?: boolean; unverified?: boolean; source_url?: string | null; checked_on?: string | null; note?: string | null }
export interface SellerCost { seller: string; line_ids?: string[]; parts: CostAmount; gst: CostAmount; shipping: CostAmount; total: CostAmount; free_shipping_gap_inr?: string | null; policy?: ShippingPolicyRef | null }
export interface ImportBaseline { line_ids?: string[]; complete?: boolean; goods_usd: string; fx_usd_inr: string; goods_inr: CostAmount; courier_inr: CostAmount; duty_inr: CostAmount; landed_inr: CostAmount; formula: string; sources?: string[] }
export interface CostBreakdown { basis?: 'selected_offers' | 'plan'; complete?: boolean; sellers?: SellerCost[]; parts: CostAmount; gst: CostAmount; shipping: CostAmount; total: CostAmount; excluded_line_ids?: string[]; import_baseline?: ImportBaseline | null; savings_vs_import?: { amount_inr: string; status?: 'estimated'; assumptions?: string[] } | null; rates_checked_on?: string | null; disclaimer?: string }
export type PlanGrade = 'A' | 'B' | 'C' | 'D' | 'X'
export interface OrderPlanLine { line_id: string; name: string; offer_url: string; title?: string | null; qty: number; pack_qty?: number | null; packs: number; units: number; unit_price_inr: string; line_price_inr: string; selection_source?: 'recommended' | 'user' | null; selected?: boolean; grade?: PlanGrade | null; changes_required?: boolean; blocked_reason?: string | null }
export interface OrderPlanSeller { seller: string; lines?: OrderPlanLine[]; subtotal_inr: string; gst: CostAmount; shipping: CostAmount; total: CostAmount; free_shipping_gap_inr?: string | null; policy?: ShippingPolicyRef | null; product_links?: string[] }
export interface UnsourcedLine { line_id: string; name: string; reason: 'pending' | 'needs_value' | 'no_offers' | 'no_acceptable_offer' | 'needs_quantity' | 'cleared_by_user'; message: string; next_steps?: string[]; research_urls?: string[] }
export interface OrderPlan { sellers?: OrderPlanSeller[]; unsourced?: UnsourcedLine[]; seller_count?: number; costing: CostBreakdown; ready?: boolean; disclaimer?: string }
export interface LineImage { url: string; kind: 'selected_offer' | 'recommended_offer' | 'offer' | 'reference' | 'category' | 'placeholder'; label: string; source_url?: string | null }
export interface LineRecommendation { status: 'recommended' | 'unsourced'; offer_url?: string | null; seller?: string | null; score?: number | null; reasons?: string[]; blocked_reason?: string | null; unsourced_reason?: Exclude<UnsourcedLine['reason'], 'cleared_by_user'> | null; next_steps?: string[]; qty?: number | null; pack_qty?: number | null; packs?: number | null }
export interface OfferMatch { status: 'exact' | 'compatible' | 'partial' | 'mismatch'; score: number; matched?: string[]; missing?: string[]; conflicts?: string[]; reasons?: string[]; claims?: { claim: string; quote: string }[]; dropped_claims?: number; variant?: string | null; pack_qty?: number | null; method?: 'llm_judge' | 'deterministic_shortcut'; model?: string | null }
export interface SellerTrust { label: 'established' | 'verified_basics' | 'unverified'; new_seller?: boolean; reasons?: string[]; signals?: { domain?: string | null; gstin?: string | null; price_anomaly?: boolean; policies?: ('returns' | 'shipping' | 'contact')[]; domain_age_days?: number | null }; checked_at?: string }
export interface CompatFinding { rule: string; grade: PlanGrade; area: 'wiring' | 'code' | 'power' | 'safety' | 'verify'; message: string; change?: string | null; basis?: string[] }
export interface OfferCompatibility { status: string; grade?: PlanGrade | null; reasons?: string[]; changes?: string[]; missing_fields?: string[]; method?: 'declared_specs' | 'catalog_rules'; grade_label?: string | null; findings?: CompatFinding[]; what_changes?: { wiring?: string[]; code?: string[]; power?: string[]; safety?: string[]; verify?: string[] } | null }
export type ReportOffer = Omit<ReportLine['offers'][number], 'compatibility'> & { compatibility?: OfferCompatibility | null; match?: OfferMatch | null; pack_qty?: number | null; trust?: SellerTrust | null; tax_included?: boolean | null; tax_evidence?: string | null }
export interface CostEstimate { total_usd?: number; budget_reached?: boolean; calls?: number; prices_checked?: string | null }
export interface ReportLine { line_image?: LineImage | null; selection_source?: 'recommended' | 'user' | null; user_offer_url?: string | null; recommended_offer_url?: string | null; recommendation?: LineRecommendation | null; changes_accepted?: boolean; import_reference?: { price_usd: string; source?: 'user' | 'research_fact'; source_url?: string | null; quote?: string | null } | null; seller_search?: { queries?: string[]; candidate_urls?: string[]; sellers_checked?: number; blocked_sellers?: string[]; message?: string } | null }
export interface Job { cost_estimate?: CostEstimate | null }
export type Report = NonNullable<Job['report']> & { costing?: CostBreakdown | null; order_plan?: OrderPlan | null }
export const reportOf = (job: Job) => job.report as Report | null
export const offersOf = (line: ReportLine) => (line.offers ?? []) as ReportOffer[]

export interface PlanPick { line_id: string; offer_url: string; seller: string; price_inr: string; grade: 'A' | 'B' | 'C' | 'D' | null; changes_required?: boolean; qty?: number | null; packs?: number | null }
export interface CartPlan { kind: 'cheapest' | 'fewest_sellers' | 'recommended'; picks?: PlanPick[]; seller_count?: number; costing: CostBreakdown; matches_selection?: boolean }
export interface CartPlans { plans?: CartPlan[]; method?: 'exhaustive' | 'greedy' | 'none'; uncovered_line_ids?: string[]; rules?: string[]; seller_penalty_inr?: string | null }
export interface SelectionInput { line_id: string; offer_url: string | null; accept_changes?: boolean; accept_research_assessment?: boolean }
const jobPath = (id: string, rest: string) => '/v1/jobs/' + encodeURIComponent(id) + rest
export const getPlans = (id: string, token: string) => request<CartPlans>(jobPath(id, '/plans'), {}, token)
export const selectOffers = (id: string, token: string, selections: SelectionInput[]) => request<Job>(jobPath(id, '/selections'), { method: 'POST', body: JSON.stringify({ selections }) }, token)
export const setImportReferences = (id: string, token: string, references: { line_id: string; price_usd: string | null; source_url?: string | null }[]) => request<Job>(jobPath(id, '/import-references'), { method: 'POST', body: JSON.stringify({ references }) }, token)

export interface MarketsResult { demo: boolean; location: { source: 'pin' | 'coordinates'; pin?: string | null; city?: string | null; latitude: number; longitude: number; approximate: boolean; label: string }; categories: string[]; summary?: string | null; summary_label?: string; places: { title: string; uri?: string | null; address?: string | null; place_id?: string | null }[]; attribution: { provider?: 'Google Maps'; sources: { title: string; uri: string; kind: 'place' | 'review' | 'web' }[]; rules?: string }; cached: boolean; model?: string | null; label: string }
export const getMarkets = (id: string, token: string, place: { pin: string } | { lat: number; lng: number }) => request<MarketsResult>(jobPath(id, '/markets?' + new URLSearchParams('pin' in place ? { pin: place.pin } : { lat: String(place.lat), lng: String(place.lng) })), {}, token)

export interface ShareStatus { active: boolean; created_at?: string | null }
export interface ShareLink { share_token: string; path: string; created_at: string }
export interface SharedProject { shared?: true; demo: boolean; status: JobStatus; source_url: string; project?: ProjectUnderstanding | null; created_at: string; updated_at: string; items: BomItem[]; report?: Report | null; notice: string }
export const getShare = (id: string, token: string) => request<ShareStatus>(jobPath(id, '/share'), {}, token)
export const createShare = (id: string, token: string) => request<ShareLink>(jobPath(id, '/share'), { method: 'POST' }, token)
export const revokeShare = (id: string, token: string) => request<void>(jobPath(id, '/share'), { method: 'DELETE' }, token)
export const getShared = (shareToken: string) => request<SharedProject>('/v1/shared/' + encodeURIComponent(shareToken))
export const shareUrl = (shareToken: string) => window.location.origin + '/shared/' + encodeURIComponent(shareToken)

export interface FeatureStatus { enabled: boolean; daily_limit: number; remaining: number }
export interface ExtrasStatus { demo: boolean; explain: FeatureStatus; zoom: FeatureStatus; scan: FeatureStatus; languages: string[]; zoom_line_ids: string[]; scan_max_bytes: number; scan_mime_types: string[] }
export interface Explanation { language: string; transcript: string; translated: boolean; audio_mime?: 'audio/wav'; audio_base64: string; duration_s: number; cached: boolean; demo: boolean; label: string }
export const getExtras = (id: string, token: string) => request<ExtrasStatus>(jobPath(id, '/extras'), {}, token)
export const explainAloud = (id: string, token: string, language: string) => request<Explanation>(jobPath(id, '/explain'), { method: 'POST', body: JSON.stringify({ language }) }, token)

// CSV and printable HTML exports, fetched through the proxy so credentials are attached.
// `path` is '/v1/jobs/{id}/export.csv' style, or '/v1/shared/{share_token}/export.html' for share links.
export async function exportBlob(path: string, token?: string): Promise<Blob> {
  if (import.meta.env.DEV && new URLSearchParams(window.location.search).get('preview') === '1') {
    const csv = path.endsWith('.csv')
    return new Blob([csv ? '# DEMO JOB,Dummy preview export; no API request was sent\r\ndata_label,line_id,part_name\r\ndemo_sample,L01,Sample controller board\r\n' : '<!doctype html><meta charset="utf-8"><title>Dummy export</title><p><strong>DEMO JOB</strong> · Dummy preview export; no API request was sent.</p>'], { type: csv ? 'text/csv' : 'text/html' })
  }
  const bearer = await identityToken()
  let response: Response
  try {
    response = await fetch(`${API_BASE}${path}`, { credentials: 'include', cache: 'no-store', headers: { 'X-Requested-With': 'BharatSourcer', ...(bearer ? { Authorization: 'Bearer ' + bearer } : {}), ...(token ? { 'X-Job-Token': token } : {}) } })
  } catch {
    throw new Error('Could not reach the backend. Check the API URL and connection.')
  }
  if (!response.ok) {
    const data = await response.json().catch(() => null)
    throw new ApiError(response.status === 429 ? 'Usage limit reached. Please try again later.' : data?.error?.message || `Export failed (${response.status}).`, response.status, data?.error?.code)
  }
  return response.blob()
}
