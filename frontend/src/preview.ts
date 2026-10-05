import { ApiError } from './api'
import type { Job, JobStatus, BomItem } from './api'

const items: BomItem[] = ['Sample controller board', 'Sample sensor module', 'Jumper wires'].map((raw_name, index) => ({ line_id: 'L0' + (index + 1), raw_name, qty: index === 2 ? 10 : 1, user_has_it: false, user_edited: false, evidence: [], clarifications: [] }))
const phase = new URLSearchParams(window.location.search).get('stage')
const status: JobStatus = phase === 'done' ? 'done' : phase === 'sourcing' ? 'sourcing' : 'awaiting_confirmation'
const lines = items.map(item => ({ item, sourcing_status: 'offers_found' as const, sourcing_error: null, subtotal_inr: '199', offers: [{ url: '#demo-seller', seller: 'Sample seller (dummy)', title: item.raw_name, price_inr: '199', stock: 'sample_stock', checked_at: new Date().toISOString(), image_url: '/preview-part.svg', compatibility: null }] }))
let job: Job = { job_id: 'ui-preview', status, updated_at: new Date().toISOString(), demo: true, input: { url: 'https://example.com/dummy-video' }, items, events: [], report: status === 'awaiting_confirmation' ? null : { summary: 'Dummy preview', lines: status === 'done' ? lines : [lines[2]], selected_parts_subtotal_inr: '0', parts_subtotal_inr: null, unselected_line_ids: [] }, error: null, messages: [], chat_state: 'idle', chat_error: null }

export function previewRequest(path: string, options: RequestInit): unknown {
  if (path === '/v1/session/usage') return { daily_actions: { limit: 40, remaining: 36 }, daily_projects: { limit: 5, remaining: 4 }, minute_actions: { limit: 5, remaining: 5 } }
  if (path.endsWith('/pause')) { job.status = 'paused'; return {} }
  if (path.endsWith('/resume')) { job.status = 'sourcing'; return {} }
  if (path === '/v1/session/logout') { sessionStorage.removeItem('bs-preview-account'); return undefined }
  if (path === '/v1/session/guest') sessionStorage.setItem('bs-preview-account', 'guest')
  if (path === '/v1/session' || path === '/v1/session/guest') {
    const kind = sessionStorage.getItem('bs-preview-account')
    if (!kind) throw new ApiError('Sign in to continue.', 401, 'IDENTITY_REQUIRED')
    return { kind, expires_at: null, daily_action_limit: kind === 'guest' ? 5 : 40, part_limit: kind === 'guest' ? 3 : 10 }
  }
  if (path.startsWith('/v1/projects?')) return { projects: [{ job_id: job.job_id, url: job.input.url, status: job.status, created_at: job.updated_at, updated_at: job.updated_at, part_count: job.items.length }], next_cursor: null }
  if (path.endsWith('/claim')) return { job_id: job.job_id }
  if (path === '/healthz') return { mode: 'demo' }
  if (path === '/v1/jobs' && options.method === 'POST') return { job_id: job.job_id, job_token: 'dummy-token', demo: true }
  if (path.endsWith('/confirm')) {
    const edits = JSON.parse(String(options.body)).edits
    for (const edit of edits) {
      if (edit.op === 'remove') job.items = job.items.filter(item => item.line_id !== edit.line_id)
      else job.items = job.items.map(item => item.line_id !== edit.line_id ? item : { ...item, ...(edit.raw_name ? { raw_name: edit.raw_name } : {}), ...(edit.qty ? { qty: edit.qty } : {}), ...(edit.op === 'have_it' ? { user_has_it: edit.user_has_it } : {}) })
    }
    job = { ...job, status: 'sourcing', report: { summary: 'Dummy preview', lines: [], selected_parts_subtotal_inr: '0', parts_subtotal_inr: null, unselected_line_ids: [] } }
    return { status: 'resolving' }
  }
  if (path.endsWith('/messages') && options.method === 'POST') {
    const input = JSON.parse(String(options.body))
    job.messages.push({ message_id: input.message_id, role: 'user', text: input.text, created_at: new Date().toISOString(), cited_line_ids: [], proposal: null }, { message_id: crypto.randomUUID(), role: 'assistant', text: 'Dummy reply: this preview does not contact the backend. Use the preview controls to switch analysis stages.', created_at: new Date().toISOString(), cited_line_ids: [], proposal: null })
  }
  if (path === '/v1/jobs/ui-preview' || path.endsWith('/messages')) return structuredClone({ ...job, updated_at: new Date().toISOString() })
  throw new Error('This action is unavailable in the local preview. No API request was sent.')
}
