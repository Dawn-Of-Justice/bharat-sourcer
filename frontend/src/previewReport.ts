import { ApiError } from './api'
import type { CartPlans, CostAmount, CostBreakdown, Explanation, ExtrasStatus, Job, MarketsResult, OrderPlanLine, Report, ReportLine, ReportOffer, SharedProject } from './api'

// Dummy report fixtures for ?preview=1&stage=plan (order plan, costing, trust, grades, markets, share, extras).
// Every seller, price, grade and shop here is invented and labelled "dummy"; nothing is sent to a server.
const svg = (text: string) => 'data:image/svg+xml,' + encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 84 84"><rect width="84" height="84" rx="10" fill="#eaf4e9"/><text x="42" y="46" font-size="10" text-anchor="middle" fill="#28594f">${text}</text></svg>`)
const url = (path: string) => 'https://example.com/dummy/' + path
const now = () => new Date().toISOString()
const amount = (amount_inr: string | null, status: CostAmount['status'], assumptions: string[] = [], partial_inr: string | null = null): CostAmount => ({ amount_inr, status, assumptions, partial_inr })
const sellerA = 'sample-seller-a.example (dummy)'
const sellerB = 'sample-seller-b.example (dummy)'
const policyA = { seller: sellerA, free_above_inr: '999.00', free_when: 'above' as const, flat_fee_inr: '50.00', source_url: url('shipping-policy'), checked_on: '2026-10-06', unverified: false }

function offer(path: string, seller: string, title: string, price: string, extra: Partial<ReportOffer>): ReportOffer {
  return { url: url(path), seller, title, price_inr: price, stock: 'in_stock', checked_at: now(), image_url: null, compatibility: null, ...extra }
}
const established = { label: 'established' as const, reasons: ['Dummy reason: on the curated seller list (sample).'], checked_at: now() }

function planLines(): Record<string, Omit<Partial<ReportLine>, 'offers'> & { offers?: ReportOffer[] }> {
  return {
    L01: {
      line_image: { url: svg('Dummy photo'), kind: 'selected_offer', label: 'Dummy seller photo of the selected offer · visual reference only' },
      offers: [
        offer('controller-a', sellerA, 'Sample controller board (dummy listing)', '349.00', { tax_included: true, tax_evidence: 'Dummy: page says “Incl. GST”', trust: established, match: { status: 'exact', score: 0.95, method: 'llm_judge', reasons: ['Dummy reason: listing states 3.3 V logic and 4+ GPIO pins.'], claims: [{ claim: 'logic voltage 3.3 V', quote: 'Dummy quote: 3.3V logic level' }] }, compatibility: { status: 'compatible', grade: 'A', method: 'catalog_rules', reasons: ['Dummy: declared specs meet the requirements.'], findings: [], what_changes: { verify: ['Dummy: check the board revision on arrival.'] } } }),
        offer('controller-b', sellerB, 'Sample controller board, 5 V variant (dummy listing)', '299.00', { tax_included: false, tax_evidence: 'Dummy: page says “+ GST”', trust: { label: 'verified_basics', new_seller: true, reasons: ['Dummy reason: GSTIN passes checksum.', 'Dummy reason: domain registered 120 days ago.'], signals: { gstin: '29ABCDE1234F1Z5' }, checked_at: now() }, match: { status: 'compatible', score: 0.8, method: 'llm_judge', variant: '5 V logic (dummy)', reasons: ['Dummy reason: same board, 5 V logic variant.'] }, compatibility: { status: 'changes_required', grade: 'B', method: 'catalog_rules', changes: ['Dummy: set the logic jumper to 3.3 V.'], what_changes: { safety: ['Dummy: do not feed 5 V into the 3.3 V sensor.'], wiring: ['Dummy: move the jumper to 3V3.'], code: ['Dummy: no code change.'] }, findings: [{ rule: 'logic_level', grade: 'B', area: 'safety', message: 'Dummy: 5 V logic by default.', change: 'Set jumper to 3.3 V', basis: ['logic_v:catalog'] }] } }),
      ],
      selected_offer_url: url('controller-a'), selection_source: 'recommended', grade: 'A',
      recommendation: { status: 'recommended', offer_url: url('controller-a'), seller: sellerA, score: 0.91, reasons: ['Dummy: exact AI match with quotes.', 'Dummy: grade A, works as is.', 'Dummy: grouped with L03 from the same seller to save shipping.'], blocked_reason: null, qty: 1, packs: 1 },
    },
    L02: {
      line_image: { url: svg('Dummy photo'), kind: 'selected_offer', label: 'Dummy seller photo of your choice · visual reference only' },
      offers: [
        offer('sensor-b', sellerB, 'Sample sensor module (dummy listing)', '199.00', { tax_included: null, tax_evidence: null, trust: { label: 'verified_basics', reasons: ['Dummy reason: returns, shipping and contact pages found.'], checked_at: now() }, match: { status: 'exact', score: 1, method: 'deterministic_shortcut', reasons: ['Dummy: every spec value is in structured data.'] }, compatibility: { status: 'unknown', grade: null, missing_fields: ['supply_voltage'] } }),
        offer('sensor-c', 'cheap-parts.example (dummy)', 'Sample sensor module clone (dummy listing)', '59.00', { tax_included: null, trust: { label: 'unverified', reasons: ['Dummy reason: no policy pages found.', 'Check the seller before paying; prefer cash on delivery'], signals: { price_anomaly: true }, checked_at: now() }, match: { status: 'partial', score: 0.5, method: 'llm_judge', missing: ['interface'], reasons: ['Dummy: the listing does not state the interface.'] }, compatibility: { status: 'changes_required', grade: 'C', method: 'catalog_rules', what_changes: { power: ['Dummy: needs a 5 V supply.'] }, findings: [{ rule: 'supply', grade: 'C', area: 'power', message: 'Dummy: 5 V supply only.' }] } }),
      ],
      selected_offer_url: url('sensor-b'), selection_source: 'user', user_offer_url: url('sensor-b'), grade: null,
      recommendation: { status: 'recommended', offer_url: url('sensor-b'), seller: sellerB, score: 0.82, reasons: ['Dummy: exact spec match.'], qty: 1, packs: 1 },
    },
    L03: {
      line_image: { url: svg('Dummy art'), kind: 'category', label: 'Dummy category illustration' },
      offers: [offer('wires-a', sellerA, 'Sample part, pack of 40 (dummy listing)', '120.00', { pack_qty: 40, tax_included: true, trust: established, match: { status: 'partial', score: 0.55, method: 'llm_judge', pack_qty: 40, missing: ['length'], reasons: ['Dummy: a required value is not stated.'] }, compatibility: { status: 'unknown', grade: null, missing_fields: ['length', 'connector_type'] } })],
      selected_offer_url: null, selection_source: null,
      recommendation: { status: 'recommended', offer_url: url('wires-a'), seller: sellerA, score: 0.62, reasons: ['Dummy: only listing found; 1 pack of 40 covers 10 needed.'], blocked_reason: 'Dummy: the listing does not state a required value, so it was not selected automatically.', qty: 10, pack_qty: 40, packs: 1 },
    },
  }
}

function costing(basis: CostBreakdown['basis']): CostBreakdown {
  return {
    basis, complete: false, excluded_line_ids: basis === 'plan' ? [] : ['L03', 'L04'],
    sellers: [
      { seller: sellerA, line_ids: ['L01'], parts: amount('349.00', 'known'), gst: amount('0.00', 'known'), shipping: amount('50.00', 'estimated', ['Dummy: flat ₹50 below ₹999 per policy checked 2026-10-06']), total: amount('399.00', 'estimated'), free_shipping_gap_inr: '650.01', policy: policyA },
      { seller: sellerB, line_ids: ['L02'], parts: amount('199.00', 'known'), gst: amount(null, 'unknown', ['Dummy: the page does not say whether GST is included']), shipping: amount(null, 'unknown', ['Dummy: no shipping policy on file']), total: amount(null, 'unknown', [], '199.00'), policy: { seller: sellerB, unverified: true, note: 'Dummy: conflicting thresholds on the seller site' } },
    ],
    parts: amount('548.00', 'known', ['Dummy: listed seller prices at checked_at']), gst: amount(null, 'unknown', [], '0.00'), shipping: amount(null, 'unknown', [], '50.00'), total: amount(null, 'unknown', [], '598.00'),
    import_baseline: basis === 'plan' ? null : { line_ids: ['L01'], complete: false, goods_usd: '4.95', fx_usd_inr: '95.99', goods_inr: amount('475.15', 'estimated'), courier_inr: amount('2879.70', 'estimated', ['Dummy: $30 courier placeholder']), duty_inr: amount('1423.11', 'estimated'), landed_inr: amount('4777.96', 'estimated'), formula: 'Dummy formula: goods + courier + BCD 10% + SWS 10% of BCD + IGST 28%', sources: ['Dummy: duty rates as of 2026-10-06 (unverified)', 'Dummy: FX USD→INR 95.99 on 2026-10-01'] },
    rates_checked_on: '2026-10-06',
    disclaimer: 'Dummy preview estimate from invented prices and dated assumptions; not a final payable total.',
  }
}

const planLine = (line_id: string, name: string, offer_url: string, title: string, price: string, extra: Partial<OrderPlanLine> = {}): OrderPlanLine => ({ line_id, name, offer_url, title, qty: 1, packs: 1, units: 1, unit_price_inr: price, line_price_inr: price, selection_source: 'recommended', selected: true, grade: null, changes_required: false, blocked_reason: null, ...extra })

export function planPreview(job: Job): Job {
  const extras = planLines()
  const items = [...job.items, { line_id: 'L04', raw_name: 'Resistor (dummy, value missing)', qty: 3, user_has_it: false, user_edited: false, evidence: [], clarifications: [] }]
  const name = (id: string) => items.find(item => item.line_id === id)?.raw_name ?? id
  const lines: ReportLine[] = items.map(item => ({ item, sourcing_status: 'offers_found', sourcing_error: null, subtotal_inr: null, offers: [], ...(extras[item.line_id] ?? {}) }) as unknown as ReportLine)
  lines[3] = { ...lines[3], sourcing_status: 'no_verified_offers', sourcing_error: { code: 'NO_VERIFIED_OFFERS', message: 'Dummy: searched 6 sellers; 1 blocked automated access (sample-blocked.example). No listing passed the checks.' }, seller_search: { candidate_urls: [url('resistor-lead')], sellers_checked: 6 }, line_image: { url: svg('Dummy art'), kind: 'placeholder', label: 'Dummy generic illustration' }, recommendation: { status: 'unsourced', unsourced_reason: 'needs_value', next_steps: ['Which resistor value do you need?'] } }
  const report: Report = {
    summary: 'Dummy preview order plan', lines, selected_parts_subtotal_inr: '548.00', parts_subtotal_inr: null, unselected_line_ids: ['L03', 'L04'],
    costing: costing('selected_offers'),
    order_plan: {
      sellers: [
        { seller: sellerA, lines: [planLine('L01', name('L01'), url('controller-a'), 'Sample controller board (dummy listing)', '349.00', { grade: 'A' }), planLine('L03', name('L03'), url('wires-a'), 'Sample part, pack of 40 (dummy listing)', '120.00', { qty: 10, pack_qty: 40, units: 40, selected: false, blocked_reason: 'Dummy: the listing does not state a required value, so it was not selected automatically.' })], subtotal_inr: '469.00', gst: amount('0.00', 'known'), shipping: amount('50.00', 'estimated', ['Dummy: flat ₹50 below ₹999']), total: amount('519.00', 'estimated'), free_shipping_gap_inr: '530.01', policy: policyA, product_links: [url('controller-a'), url('wires-a')] },
        { seller: sellerB, lines: [planLine('L02', name('L02'), url('sensor-b'), 'Sample sensor module (dummy listing)', '199.00', { selection_source: 'user' })], subtotal_inr: '199.00', gst: amount(null, 'unknown'), shipping: amount(null, 'unknown'), total: amount(null, 'unknown', [], '199.00'), policy: { seller: sellerB, unverified: true }, product_links: [url('sensor-b')] },
      ],
      unsourced: [{ line_id: 'L04', name: 'Resistor (dummy, value missing)', reason: 'needs_value', message: 'Dummy: needs a value — choose the resistance for this resistor.', next_steps: ['Which resistor value do you need?', 'Then refresh this part.'], research_urls: [url('resistor-research')] }],
      seller_count: 2, costing: costing('plan'), ready: false,
      disclaimer: 'Dummy preview plan: invented sellers and prices. Picks are recommendations; check each seller page before ordering.',
    },
  }
  return { ...job, demo: false, items, report, cost_estimate: { total_usd: 0.0123, calls: 9 } }
}

// A short silent WAV so the audio control renders in the preview.
function silentWav() {
  const samples = 800, bytes = new Uint8Array(44 + samples * 2), view = new DataView(bytes.buffer)
  const text = (offset: number, value: string) => { for (let i = 0; i < value.length; i++) bytes[offset + i] = value.charCodeAt(i) }
  text(0, 'RIFF'); view.setUint32(4, 36 + samples * 2, true); text(8, 'WAVEfmt '); view.setUint32(16, 16, true); view.setUint16(20, 1, true); view.setUint16(22, 1, true); view.setUint32(24, 8000, true); view.setUint32(28, 16000, true); view.setUint16(32, 2, true); view.setUint16(34, 16, true); text(36, 'data'); view.setUint32(40, samples * 2, true)
  return btoa(String.fromCharCode(...bytes))
}

let shareActive = false
export function previewReportRequest(path: string, options: RequestInit, job: Job): unknown {
  const method = options.method ?? 'GET'
  const base = '/v1/jobs/ui-preview'
  if (path === base + '/share') {
    if (method === 'POST') { shareActive = true; return { share_token: 'ui-preview.dummy', path: '/shared/ui-preview.dummy', created_at: now() } }
    if (method === 'DELETE') { shareActive = false; return undefined }
    return { active: shareActive, created_at: shareActive ? now() : null }
  }
  if (path === '/v1/shared/ui-preview.dummy') {
    const source = job.report && (job.report as Report).order_plan ? job : planPreview(job)
    const shared: SharedProject = { shared: true, demo: false, status: 'done', source_url: source.input.url, project: source.project, created_at: source.updated_at, updated_at: now(), items: source.items, report: source.report as Report, notice: 'Dummy preview share link: invented sample data. Prices are seller snapshots and may have changed; this is not a verified or payable total.' }
    return structuredClone(shared)
  }
  if (path === base + '/extras') return { demo: true, explain: { enabled: true, daily_limit: 10, remaining: 9 }, zoom: { enabled: false, daily_limit: 10, remaining: 10 }, scan: { enabled: false, daily_limit: 5, remaining: 5 }, languages: ['en', 'hi', 'ta', 'ml'], zoom_line_ids: [], scan_max_bytes: 4000000, scan_mime_types: ['image/jpeg'] } satisfies ExtrasStatus
  if (path === base + '/explain') return { language: 'en', transcript: 'Dummy transcript: this preview plays a short silent sample. No speech was generated.', translated: false, audio_mime: 'audio/wav', audio_base64: silentWav(), duration_s: 0.1, cached: false, demo: true, label: 'Dummy sample · not generated for this project' } satisfies Explanation
  if (path.startsWith(base + '/markets?')) {
    const params = new URLSearchParams(path.split('?')[1])
    const pin = params.get('pin')
    if (pin && !/^[1-9]\d{5}$/.test(pin)) throw new ApiError('PIN must be 6 digits.', 422, 'INVALID_PIN')
    const location = { source: pin ? 'pin' as const : 'coordinates' as const, pin, city: 'Bengaluru', latitude: 12.97, longitude: 77.59, approximate: true, label: pin ? `Approximate: PIN ${pin} mapped to the centre of Bengaluru (dummy preview).` : 'Your location, rounded to about 1 km (dummy preview).' }
    // PIN 560001 shows a grounded layout with dummy sources; any other PIN shows the demo sample (no sources).
    if (pin === '560001') return { demo: false, location, categories: ['controller boards', 'sensors'], summary: '1. Dummy Electronics (preview) — SP Road\n2. Sample Components (preview) — SP Road', summary_label: 'Shops likely to carry these parts — call first; stock is not confirmed', places: [{ title: 'Dummy Electronics (preview)', uri: url('maps-place-1'), address: 'Dummy address, SP Road' }, { title: 'Sample Components (preview)', uri: url('maps-place-2'), address: null }], attribution: { provider: 'Google Maps', sources: [{ title: 'Dummy Electronics (preview) - Google Maps', uri: url('maps-place-1'), kind: 'place' }, { title: 'Review of Dummy Electronics (preview)', uri: url('maps-review-1'), kind: 'review' }] }, cached: false, label: 'AI summary grounded in Google Maps (dummy preview)' } satisfies MarketsResult
    return { demo: true, location, categories: ['controller boards', 'sensors'], summary: '1. Sample Market (demo) — fictional\n2. Example Parts Shop (demo) — fictional', summary_label: 'Shops likely to carry these parts — call first; stock is not confirmed', places: [{ title: 'Sample Market (demo)' }, { title: 'Example Parts Shop (demo)' }], attribution: { sources: [] }, cached: false, label: 'Demo sample · fictional shops' } satisfies MarketsResult
  }
  if (path === base + '/plans') return { method: 'exhaustive', uncovered_line_ids: ['L03', 'L04'], rules: ['Dummy rule: only offers that can be selected now (grade A or B, in stock, fresh).'], seller_penalty_inr: '60.00', plans: [
    { kind: 'cheapest', seller_count: 2, matches_selection: false, picks: [{ line_id: 'L01', offer_url: url('controller-b'), seller: sellerB, price_inr: '299.00', grade: 'B', changes_required: true }, { line_id: 'L02', offer_url: url('sensor-b'), seller: sellerB, price_inr: '199.00', grade: null }], costing: { ...costing('plan'), sellers: [], parts: amount('498.00', 'known'), total: amount(null, 'unknown', [], '498.00') } },
    { kind: 'fewest_sellers', seller_count: 1, matches_selection: false, picks: [{ line_id: 'L01', offer_url: url('controller-b'), seller: sellerB, price_inr: '299.00', grade: 'B', changes_required: true }, { line_id: 'L02', offer_url: url('sensor-b'), seller: sellerB, price_inr: '199.00', grade: null }], costing: { ...costing('plan'), sellers: [], parts: amount('498.00', 'known'), total: amount(null, 'unknown', [], '498.00') } },
    { kind: 'recommended', seller_count: 2, matches_selection: true, picks: [{ line_id: 'L01', offer_url: url('controller-a'), seller: sellerA, price_inr: '349.00', grade: 'A' }, { line_id: 'L02', offer_url: url('sensor-b'), seller: sellerB, price_inr: '199.00', grade: null }], costing: costing('plan') },
  ] } satisfies CartPlans
  if (path === base + '/selections' && method === 'POST') {
    const selections = JSON.parse(String(options.body)).selections as { line_id: string; offer_url: string | null }[]
    const report = job.report as Report
    for (const selection of selections) {
      const line = report.lines.find(entry => entry.item.line_id === selection.line_id)
      if (!line) continue
      Object.assign(line, { selected_offer_url: selection.offer_url, selection_source: 'user', user_offer_url: selection.offer_url })
      const chosen = (line.offers as ReportOffer[]).find(entry => entry.url === selection.offer_url)
      const plan = report.order_plan
      if (!plan) continue
      for (const seller of plan.sellers ?? []) { seller.lines = seller.lines?.filter(entry => entry.line_id !== selection.line_id); seller.product_links = seller.product_links?.filter(link => seller.lines?.some(entry => entry.offer_url === link)) }
      if (chosen) {
        let group = plan.sellers?.find(seller => seller.seller === chosen.seller)
        if (!group) { group = { seller: chosen.seller, lines: [], subtotal_inr: '0.00', gst: amount(null, 'unknown'), shipping: amount(null, 'unknown'), total: amount(null, 'unknown'), product_links: [] }; plan.sellers = [...(plan.sellers ?? []), group] }
        group.lines = [...(group.lines ?? []), planLine(selection.line_id, line.item.raw_name, chosen.url, chosen.title, chosen.price_inr, { selection_source: 'user', grade: chosen.compatibility?.grade ?? null, qty: line.item.qty ?? 1 })]
        group.product_links = [...new Set([...(group.product_links ?? []), chosen.url])]
      }
      plan.sellers = plan.sellers?.filter(seller => seller.lines?.length)
      plan.seller_count = plan.sellers?.length ?? 0
    }
    job.updated_at = now()
    return structuredClone(job)
  }
  if (path === base + '/import-references' && method === 'POST') {
    const references = JSON.parse(String(options.body)).references as { line_id: string; price_usd: string | null; source_url?: string | null }[]
    for (const reference of references) {
      const line = job.report?.lines.find(entry => entry.item.line_id === reference.line_id)
      if (line) line.import_reference = reference.price_usd ? { price_usd: reference.price_usd, source: 'user', source_url: reference.source_url ?? null } : null
    }
    job.updated_at = now()
    return structuredClone(job)
  }
  return undefined
}
