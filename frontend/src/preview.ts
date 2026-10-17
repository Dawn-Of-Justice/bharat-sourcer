import { ApiError } from './api'
import { reviewItems, reviewJobFields } from './previewReview'
import type { ChatMessage, Job, JobStatus, BomItem, ProjectUnderstanding } from './api'
import { planPreview, previewCities, previewReportRequest } from './previewReport'
import { sampleOverview, sampleOverviewState } from './previewOverview'
import { sampleBuildGuide } from './previewBuild'

const items: BomItem[] = ['Sample controller board', 'Sample sensor module', 'Jumper wires'].map((raw_name, index) => ({
  line_id: 'L0' + (index + 1),
  raw_name,
  qty: index === 2 ? 10 : 1,
  user_has_it: false,
  user_edited: false,
  evidence: [],
  clarifications: [],
}))
// Dummy AI-inferred states: a quantity the source did not state and pre-filled build details, each with a reason.
items[2] = {
  ...items[2],
  qty_source: 'inferred',
  qty_reason:
    'Dummy reason: the sample source shows wiring but no count; 10 covers the controller, one sensor and spares.',
}
items[0] = {
  ...items[0],
  requirements: [
    {
      name: 'logic voltage',
      value: '3.3',
      unit: 'V',
      operator: 'equals',
      origin: 'inferred',
      reason: 'Dummy reason: the sample project powers the sensor from a 3.3 V rail.',
    },
    {
      name: 'GPIO pins',
      value: '4',
      unit: null,
      operator: 'at_least',
      origin: 'inferred',
      reason: 'Dummy reason: the sample build leaves extra pins available for later additions.',
    },
  ],
}
items.splice(0, items.length, ...reviewItems(items))
const project: ProjectUnderstanding = {
  title: 'Demo: Sensor logger',
  title_source: 'ai',
  description: 'Dummy battery-powered sensor logger for UI preview.',
  description_source: 'ai',
  summary: 'Dummy preview project: a sample battery-powered sensor logger. Not extracted from a real source.',
  power: 'Sample 3.7 V Li-ion cell (dummy)',
  controller: 'Sample controller board (dummy)',
  interfaces: ['I2C', 'USB'],
  assumptions: [
    'Dummy assumption: the sensor may need level shifting with the 3.3 V controller.',
    'Dummy assumption: one sensor per build.',
  ],
  origin: 'ai_inferred',
}
const phase = new URLSearchParams(window.location.search).get('stage')
const status: JobStatus =
  phase === 'done' || phase === 'plan' || phase === 'search-results' || phase === 'build'
    ? 'done'
    : phase === 'sourcing'
      ? 'sourcing'
      : 'awaiting_confirmation'
const lines = items.map(item => ({
  item,
  sourcing_status: 'offers_found' as const,
  sourcing_error: null,
  subtotal_inr: '199',
  offers: [
    {
      url: '#demo-seller',
      seller: 'Sample seller (dummy)',
      title: item.raw_name,
      price_inr: '199',
      stock: 'sample_stock',
      checked_at: new Date().toISOString(),
      image_url: '/preview-part.svg',
      compatibility: null,
      spec_conflicts:
        item.line_id === 'L01'
          ? [
              {
                field: 'logic_v',
                candidates: [
                  { field: 'logic_v', value: '3.3 V', source: 'seller_title' as const, locator: 'dummy title' },
                  { field: 'logic_v', value: '5 V', source: 'seller_table' as const, locator: 'dummy table' },
                ],
              },
            ]
          : [],
    },
  ],
}))
let job: Job = {
  job_id: 'ui-preview',
  status,
  updated_at: new Date().toISOString(),
  demo: true,
  input: { url: 'https://example.com/dummy-video' },
  items,
  project,
  events: [],
  report:
    status === 'awaiting_confirmation'
      ? null
      : {
          summary: 'Dummy preview',
          lines: status === 'done' ? lines : [lines[2]],
          selected_parts_subtotal_inr: '0',
          parts_subtotal_inr: null,
          unselected_line_ids: [],
        },
  error: null,
  messages: [],
  chat_state: 'idle',
  chat_error: null,
  actions: [],
  ...reviewJobFields,
  overview:
    status === 'awaiting_confirmation'
      ? sampleOverviewState(new URLSearchParams(window.location.search).get('overview'))
      : null,
}
// A pending sample overview becomes ready a few seconds after it started, so the skeleton and polling can be seen.
let overviewReadyAt = job.overview?.status === 'pending' ? Date.now() + 6000 : 0
function settleOverview() {
  if (job.overview?.status === 'pending' && Date.now() >= overviewReadyAt) {
    job.overview = sampleOverview()
    job.updated_at = new Date().toISOString()
  }
}

// Dummy chat states for the results stage: a pending spec proposal and an approved refresh with its completion message.
if (status === 'done') {
  const at = (minutes: number) => new Date(Date.now() - minutes * 60000).toISOString()
  const messages: ChatMessage[] = [
    {
      message_id: 'preview-refresh',
      role: 'assistant',
      text: 'Dummy reply: I can re-check sellers for the sample sensor module. Approve below to start the search.',
      created_at: at(30),
      cited_line_ids: ['L02'],
      proposal: null,
      refresh_proposal: {
        request: { line_ids: ['L02'] },
        status: 'accepted',
        base_fingerprint: 'dummy',
        refresh_count: 1,
        result_message_id: 'preview-refresh-result',
      },
    },
    {
      message_id: 'preview-refresh-result',
      role: 'assistant',
      text: 'Dummy completion: the approved seller refresh has finished. Prices below are sample data, not real quotes.',
      created_at: at(25),
      cited_line_ids: ['L02'],
      proposal: null,
      completes_message_id: 'preview-refresh',
      refresh_results: [
        {
          line_id: 'L02',
          sourcing_status: 'offers_found',
          offer_count: 2,
          lowest_listed_price_inr: '199.00',
          lowest_listed_stock: 'in_stock',
          price_source: 'seller_published',
          error_code: null,
        },
      ],
    },
    {
      message_id: 'preview-spec',
      role: 'assistant',
      text: 'Dummy reply: you said the controller must run at 3.3 V logic. Approve below to save that spec.',
      created_at: at(5),
      cited_line_ids: ['L01'],
      proposal: null,
      spec_proposal: {
        request: {
          updates: [
            {
              line_id: 'L01',
              specs: { logic_v: 3.3 },
              requirements: [{ name: 'flash', value: '32', unit: 'KB', operator: 'at_least' }],
            },
          ],
        },
        status: 'pending',
        base_fingerprint: 'dummy',
      },
    },
  ]
  job.messages = messages
  job.actions = [
    {
      kind: 'refresh',
      message_id: 'preview-refresh',
      status: 'accepted',
      created_at: at(29),
      line_ids: ['L02'],
      summary: 'Dummy: seller refresh approved for 1 part.',
      refresh_count: 1,
      result_message_id: null,
    },
    {
      kind: 'refresh',
      message_id: 'preview-refresh',
      status: 'completed',
      created_at: at(25),
      line_ids: ['L02'],
      summary: 'Dummy: seller refresh finished for 1 part.',
      refresh_count: 1,
      result_message_id: 'preview-refresh-result',
    },
  ]
}
// Both completed stages use the current interactive report fixtures; preview requests stay local.
if (status === 'done') job = planPreview(job)
// stage=build opens on the build page with a ready sample guide, the sample wiring and a dummy video link for the
// step timestamps. The other finished stages start without a guide, so opening "Build it" shows it being written.
if (phase === 'build') {
  job.input = { ...job.input, url: 'https://www.youtube.com/watch?v=demo-video' }
  job.build_guide = sampleBuildGuide()
  job.build_received = ['L01']
  job.overview = sampleOverview()
} else if (status === 'done') {
  job.build_guide = null
  job.build_received = []
}
let buildGuideReadyAt = 0
function settleBuildGuide() {
  if (job.build_guide?.status === 'pending' && Date.now() >= buildGuideReadyAt) {
    job.build_guide = sampleBuildGuide()
    job.updated_at = new Date().toISOString()
  }
}

// Preview callers always send a JSON string body; JSON.parse coerces its argument to a string itself.
function jsonBody<T>(options: RequestInit): T {
  return JSON.parse(options.body as string) as T
}

export function previewRequest(path: string, options: RequestInit): unknown {
  settleOverview()
  settleBuildGuide()
  // The extra dummy project cards open the one sample project.
  path = path.replace(/^\/v1\/jobs\/ui-preview-[a-z]+(?=\/|$)/, '/v1/jobs/ui-preview')
  if (path === '/v1/countries')
    return {
      default: 'IN',
      countries: [{ code: 'IN', name: 'India', currency: 'INR', locale: 'en-IN', market_cities: previewCities }],
    }
  if (path === '/v1/account/settings') {
    if (options.method === 'POST') {
      const { country } = jsonBody<{ country: string }>(options)
      sessionStorage.setItem('bs-preview-country', country)
      return { country, updated_at: new Date().toISOString(), saved: true }
    }
    const country = sessionStorage.getItem('bs-preview-country')
    return { country: country ?? 'IN', updated_at: null, saved: !!country }
  }
  if (path === '/v1/session/usage')
    return {
      daily_actions: { limit: 40, remaining: 36 },
      daily_projects: { limit: 5, remaining: 4 },
      minute_actions: { limit: 5, remaining: 5 },
    }
  if (path.endsWith('/pause')) {
    job.status = 'paused'
    return {}
  }
  if (path.endsWith('/resume')) {
    job.status = 'sourcing'
    return {}
  }
  if (path === '/v1/account' && options.method === 'DELETE') {
    // `?preview=1&deleteError=429|401` shows the error states of the delete-my-data flow.
    const failure = new URLSearchParams(window.location.search).get('deleteError')
    if (failure === '429')
      throw new ApiError(
        'Usage limit reached. Your saved projects remain available. Try again after ' +
          new Date(Date.now() + 60000).toLocaleString() +
          '.',
        429,
        'USAGE_LIMIT',
      )
    if (failure === '401') throw new ApiError('Sign in to continue.', 401, 'IDENTITY_REQUIRED')
    const kind = sessionStorage.getItem('bs-preview-account')
    if (!kind) throw new ApiError('Sign in to continue.', 401, 'IDENTITY_REQUIRED')
    sessionStorage.removeItem('bs-preview-account')
    sessionStorage.removeItem('bs-preview-country')
    return {
      kind,
      projects_deleted: 4,
      share_links_revoked: 1,
      settings_deleted: kind === 'account',
      auth_user_deleted: kind === 'account' ? true : null,
    }
  }
  if (path === '/v1/session/logout') {
    sessionStorage.removeItem('bs-preview-account')
    return undefined
  }
  if (path === '/v1/session/guest') sessionStorage.setItem('bs-preview-account', 'guest')
  if (path === '/v1/session' || path === '/v1/session/guest') {
    const kind = sessionStorage.getItem('bs-preview-account')
    if (!kind) throw new ApiError('Sign in to continue.', 401, 'IDENTITY_REQUIRED')
    return {
      kind,
      expires_at: null,
      daily_action_limit: kind === 'guest' ? 5 : 40,
      part_limit: kind === 'guest' ? 3 : 10,
    }
  }
  if (path.startsWith('/v1/projects?')) {
    const deleted = JSON.parse(sessionStorage.getItem('bs-preview-deleted') ?? '[]') as string[]
    const at = (hours: number) => new Date(Date.now() - hours * 3600000).toISOString()
    const projects = [
      {
        job_id: job.job_id,
        url: job.input.url,
        status: job.status,
        created_at: job.updated_at,
        updated_at: job.updated_at,
        part_count: job.items.length,
        title: job.project?.title,
        description: job.project?.description,
        summary: job.project?.summary,
      },
      // Extra dummy cards so each source type and status is visible; they open the same sample project.
      {
        job_id: 'ui-preview-github',
        url: 'https://github.com/example/dummy-weather-station',
        status: 'done',
        created_at: at(30),
        updated_at: at(26),
        part_count: 8,
        title: 'Dummy weather station (preview)',
        description: 'Sample GitHub project for the preview list.',
        summary: null,
      },
      {
        job_id: 'ui-preview-blog',
        url: 'https://www.instructables.com/Dummy-Plant-Watering/',
        status: 'sourcing',
        created_at: at(3),
        updated_at: at(1),
        part_count: 5,
        title: 'Dummy plant watering (preview)',
        description: 'Sample article project for the preview list.',
        summary: null,
      },
      {
        job_id: 'ui-preview-failed',
        url: 'https://example.com/dummy-broken-link',
        status: 'failed',
        created_at: at(80),
        updated_at: at(79),
        part_count: 0,
        title: null,
        description: null,
        summary: null,
      },
    ].filter(project => !deleted.includes(project.job_id))
    return { projects, next_cursor: null }
  }
  if (path.startsWith('/v1/projects/') && options.method === 'DELETE') {
    const deleted = JSON.parse(sessionStorage.getItem('bs-preview-deleted') ?? '[]') as string[]
    sessionStorage.setItem('bs-preview-deleted', JSON.stringify([...deleted, decodeURIComponent(path.split('/')[3])]))
    return undefined
  }
  if (path.endsWith('/claim')) return { job_id: job.job_id }
  if (path === '/healthz') return { mode: 'demo' }
  if (path === '/v1/jobs' && options.method === 'POST')
    return { job_id: job.job_id, job_token: 'dummy-token', demo: true }
  if (path === '/v1/jobs/ui-preview/project' && options.method === 'POST') {
    const changes = jsonBody<{ title?: string; description?: string }>(options)
    job.project = {
      ...job.project!,
      ...changes,
      ...(changes.title ? { title_source: 'user' } : {}),
      ...(changes.description ? { description_source: 'user' } : {}),
    }
    return structuredClone({ ...job, updated_at: new Date().toISOString() })
  }
  if (path === '/v1/jobs/ui-preview/specs' && options.method === 'POST') {
    const { updates } = jsonBody<{
      updates: {
        line_id: string
        requirements?: BomItem['requirements']
      }[]
    }>(options)
    for (const update of updates) {
      const item = job.items.find(item => item.line_id === update.line_id)
      if (item && update.requirements) item.requirements = update.requirements
      const line = job.report?.lines.find(line => line.item.line_id === update.line_id)
      if (line && update.requirements) line.item.requirements = update.requirements
    }
    return structuredClone({ ...job, updated_at: new Date().toISOString() })
  }
  if (/^\/v1\/jobs\/ui-preview\/parts\/L0[1-3]\/image$/.test(path))
    return {
      candidates: [],
      fallback: { url: '/preview-part.svg', kind: 'category', label: 'Dummy illustration · not a product photo' },
      generation_status: 'not_needed',
    }
  if (path.endsWith('/confirm')) {
    const { edits } = jsonBody<{
      edits: ({ op: string; line_id: string; user_has_it: boolean } & Partial<
        Pick<BomItem, 'raw_name' | 'qty' | 'requirements' | 'buyable_spec'>
      >)[]
    }>(options)
    for (const edit of edits) {
      if (edit.op === 'remove') job.items = job.items.filter(item => item.line_id !== edit.line_id)
      else
        job.items = job.items.map(item =>
          item.line_id !== edit.line_id
            ? item
            : {
                ...item,
                ...(edit.raw_name ? { raw_name: edit.raw_name } : {}),
                ...(edit.qty ? { qty: edit.qty, qty_source: 'user' as const } : {}),
                ...(edit.requirements ? { requirements: edit.requirements } : {}),
                ...(edit.buyable_spec ? { buyable_spec: edit.buyable_spec } : {}),
                ...(edit.op === 'have_it' ? { user_has_it: edit.user_has_it } : {}),
              },
        )
    }
    job = {
      ...job,
      status: 'sourcing',
      report: {
        summary: 'Dummy preview',
        lines: [],
        selected_parts_subtotal_inr: '0',
        parts_subtotal_inr: null,
        unselected_line_ids: [],
      },
    }
    return { status: 'resolving' }
  }
  if (path.endsWith('/messages') && options.method === 'POST') {
    const input = jsonBody<{ message_id: string; text: string }>(options)
    job.messages.push(
      {
        message_id: input.message_id,
        role: 'user',
        text: input.text,
        created_at: new Date().toISOString(),
        cited_line_ids: [],
        proposal: null,
      },
      {
        message_id: crypto.randomUUID(),
        role: 'assistant',
        text: 'Dummy reply: this preview does not contact the backend. Use the preview controls to switch analysis stages.',
        created_at: new Date().toISOString(),
        cited_line_ids: [],
        proposal: null,
      },
    )
  }
  if (path.endsWith('/decision')) {
    const { action } = jsonBody<{ action: 'accept' | 'reject' }>(options)
    const message = job.messages.find(entry => path.includes('/messages/' + encodeURIComponent(entry.message_id) + '/'))
    const proposal = message?.spec_proposal ?? message?.proposal ?? message?.refresh_proposal
    if (!message || !proposal) throw new ApiError('Dummy preview: proposal not found.', 404, 'NOT_FOUND')
    if (proposal.status !== 'pending') {
      if (proposal.status !== (action === 'accept' ? 'accepted' : 'rejected'))
        throw new ApiError('Dummy preview: proposal already decided.', 409, 'PROPOSAL_DECIDED')
    } else {
      proposal.status = action === 'accept' ? 'accepted' : 'rejected'
      job.actions = [
        ...(job.actions ?? []),
        {
          kind: message.spec_proposal ? 'spec_update' : message.proposal ? 'edit' : 'refresh',
          message_id: message.message_id,
          status: action === 'accept' ? (message.refresh_proposal ? 'accepted' : 'completed') : 'rejected',
          created_at: new Date().toISOString(),
          line_ids: [],
          summary: 'Dummy preview decision; nothing was changed on a server.',
        },
      ]
    }
    return structuredClone({ ...job, updated_at: new Date().toISOString() })
  }
  if (path === '/v1/jobs/ui-preview/build-progress' || path === '/v1/jobs/ui-preview/build-guide') {
    if (job.status !== 'done') throw new ApiError('Dummy preview: the project is not finished.', 409, 'INVALID_STATE')
    if (path.endsWith('/build-progress')) {
      const { line_id, received } = jsonBody<{ line_id: string; received: boolean }>(options)
      if (!job.items.some(item => item.line_id === line_id))
        throw new ApiError('Dummy preview: no such line.', 422, 'INVALID_LINE')
      const rest = (job.build_received ?? []).filter(id => id !== line_id)
      job.build_received = received ? [...rest, line_id] : rest
      job.updated_at = new Date().toISOString()
      return structuredClone(job)
    }
    if (options.method === 'POST' && (!job.build_guide || ['failed', 'stale'].includes(job.build_guide.status))) {
      job.build_guide = { ...sampleBuildGuide(), status: 'pending', message: null, steps: [] }
      job.updated_at = new Date().toISOString()
      buildGuideReadyAt = Date.now() + 5000
    }
    if (!job.build_guide) throw new ApiError('Dummy preview: no build guide yet.', 404, 'BUILD_GUIDE_NOT_FOUND')
    return structuredClone(job.build_guide)
  }
  if (path === '/v1/jobs/ui-preview/overview') {
    if (
      options.method === 'POST' &&
      (!job.overview || job.overview.status === 'failed' || job.overview.status === 'stale')
    ) {
      job.overview = sampleOverviewState('pending')
      overviewReadyAt = Date.now() + 4000
    }
    return structuredClone(job.overview)
  }
  const reportReply = previewReportRequest(path, options, job)
  if (reportReply !== undefined || (path === '/v1/jobs/ui-preview/share' && options.method === 'DELETE'))
    return reportReply
  if (path === '/v1/jobs/ui-preview' || path.endsWith('/messages'))
    return structuredClone({ ...job, updated_at: new Date().toISOString() })
  throw new Error('This action is unavailable in the local preview. No API request was sent.')
}
