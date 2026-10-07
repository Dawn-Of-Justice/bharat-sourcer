import { useEffect, useRef, useState } from 'react'
import { getPartImages, reportFailedImages, type CostAmount, type CostBreakdown, type Job, type OfferCompatibility, type OfferMatch, type PartImages, type ReportLine, type ReportOffer, type SellerTrust, type ShippingPolicyRef } from './api'

// Shared report pieces: images, chips (text plus icon, never colour alone), cost summaries and seller policies.
const money = new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR' })
export const price = (value: string | number) => money.format(Number(value))
export const secureLink = (url?: string | null) => url && /^https:\/\/[^\s]+$/i.test(url) ? url : undefined
const words = (value: string) => value.replaceAll('_', ' ')

type DisplayImage = { url: string; label: string; kind?: string }

// line_image first (selected or recommended photo, reference, or labelled illustration), then seller photos and page references.
function lineImages(line: ReportLine, demo: boolean): DisplayImage[] {
  const images: DisplayImage[] = []
  if (line.line_image) images.push(line.line_image)
  for (const offer of line.offers ?? []) if (offer.image_url) images.push({ url: offer.image_url, label: 'Seller image · visual reference only' })
  for (const image of line.image_candidates ?? []) images.push({ url: image.url, label: image.label, kind: image.kind })
  const seen = new Set<string>()
  return images.filter(image => {
    const allowed = secureLink(image.url) || /^data:image\/svg\+xml,/i.test(image.url) || (demo && image.url === '/preview-part.svg')
    if (!allowed || seen.has(image.url)) return false
    seen.add(image.url)
    return true
  })
}

// readOnly (share page): no image endpoint calls, so no generation is ever requested.
export function ProductImage({ job, line, token, readOnly = false }: { job: Job; line: ReportLine; token: string; readOnly?: boolean }) {
  const [remote, setRemote] = useState<PartImages | null>(null)
  const [failed, setFailed] = useState<string[]>([])
  const requested = useRef(false)
  const local = lineImages(line, job.demo)
  const allowed = (url: string) => secureLink(url) || /^data:image\/(?:svg\+xml,|jpeg;base64,)/i.test(url)
  const candidates: DisplayImage[] = [...local, ...(remote?.candidates ?? []).filter(image => allowed(image.url))]
  const image = candidates.find(candidate => !failed.includes(candidate.url))
    ?? (remote?.fallback && !failed.includes(remote.fallback.url) && allowed(remote.fallback.url) ? remote.fallback : null)
  // The labelled line_image is enough; ask the image endpoint only when it is missing or failed to load.
  const needRemote = !line.line_image || failed.includes(line.line_image.url)

  useEffect(() => {
    if (job.demo || readOnly || !needRemote) return
    let active = true
    void getPartImages(job.job_id, token, line.item.line_id).then(value => {
      if (active) setRemote(value)
    }).catch(() => { /* Images are optional; preserve the sourcing result. */ })
    return () => { active = false }
  }, [job.job_id, job.demo, token, line.item.line_id, readOnly, needRemote])

  useEffect(() => {
    if (job.demo || readOnly || !remote || requested.current) return
    const remaining = [...local, ...remote.candidates].some(candidate => !failed.includes(candidate.url))
    if (remaining || (failed.length === 0 && remote.fallback.kind !== 'placeholder')) return
    requested.current = true
    void reportFailedImages(job.job_id, token, line.item.line_id, failed.filter(url => secureLink(url)).slice(0, 10)).then(setRemote).catch(() => { /* Keep the labelled fallback. */ })
  }, [job.job_id, job.demo, token, line.item.line_id, remote, failed, readOnly])

  function imageFailed() {
    if (image) setFailed(current => [...current, image.url])
  }
  const label = image && (image.kind === 'category' || image.kind === 'placeholder') && !/not a product photo/i.test(image.label) ? `${image.label} · not a product photo` : image?.label
  return <div className="part-image"><div className="product-image">{image ? <img key={image.url} src={image.url} alt={`${label} for ${line.item.raw_name}`} title={label ?? undefined} loading="lazy" referrerPolicy="no-referrer" onError={imageFailed} /> : <span>Image<br />unavailable</span>}</div>{label && <small>{label}</small>}</div>
}

const statusText = { known: '✓ Known', estimated: '≈ Estimated', unknown: '? Unknown' }
export function StatusChip({ amount }: { amount: CostAmount }) {
  const status = amount.status ?? 'unknown'
  return <span className={`cost-chip cost-${status}`}>{statusText[status]}</span>
}

// Unknown amounts are never shown as zero; a partial sum reads "at least".
export function amountText(amount: CostAmount) {
  if (amount.status !== 'unknown' && amount.amount_inr != null) return price(amount.amount_inr)
  return amount.partial_inr ? `at least ${price(amount.partial_inr)} + unknown` : 'Unknown'
}

export function AmountRow({ label, amount }: { label: string; amount: CostAmount }) {
  return <div className="cost-row"><dt>{label}</dt><dd><strong>{amountText(amount)}</strong> <StatusChip amount={amount} /></dd></div>
}

export function SellerPolicy({ seller, gap, policy }: { seller: string; gap?: string | null; policy?: ShippingPolicyRef | null }) {
  return <div className="seller-policy">{gap && Number(gap) > 0 && <p className="free-gap">🚚 Add {price(gap)} at {seller} for free shipping</p>}{policy && <p>{policy.unverified ? <span className="cost-chip cost-unknown">? Unverified policy</span> : null} Shipping policy{policy.checked_on ? ` checked ${policy.checked_on}` : ''}{policy.free_above_inr ? ` · free ${policy.free_when === 'at_or_above' ? 'at or above' : 'above'} ${price(policy.free_above_inr)}` : ''}{policy.note ? ` · ${policy.note}` : ''} {secureLink(policy.source_url) && <a href={policy.source_url!} target="_blank" rel="noopener noreferrer">Policy source ↗</a>}</p>}</div>
}

// The costing footer: parts, GST, shipping and total, each with its status, assumptions as numbered notes.
export function CostSummary({ costing, title, lineNames }: { costing: CostBreakdown; title: string; lineNames?: Record<string, string> }) {
  const notes = [costing.parts, costing.gst, costing.shipping, costing.total].flatMap(amount => amount.assumptions ?? [])
  const unique = [...new Set(notes)]
  const unknown = ([['parts', costing.parts], ['GST', costing.gst], ['shipping', costing.shipping]] as const).filter(([, amount]) => amount.status === 'unknown').map(([name]) => name)
  const excluded = costing.excluded_line_ids ?? []
  return <section className="cost-summary" aria-label={title}><h3>{title}</h3><dl><AmountRow label="Parts" amount={costing.parts} /><AmountRow label="GST" amount={costing.gst} /><AmountRow label="Shipping" amount={costing.shipping} /><AmountRow label="Estimated total" amount={costing.total} /></dl>{costing.total.status === 'unknown' && unknown.length > 0 && <p className="cost-unknown-note">Unknown: {unknown.join(', ')}. The total is not complete.</p>}{excluded.length > 0 && <p className="cost-unknown-note">Not included (no selection): {excluded.map(id => lineNames?.[id] ?? id).join(', ')}.</p>}{costing.sellers?.length ? <ul className="cost-sellers">{costing.sellers.map(seller => <li key={seller.seller}><div><strong>{seller.seller}</strong><span>{amountText(seller.total)} <StatusChip amount={seller.total} /></span></div><SellerPolicy seller={seller.seller} gap={seller.free_shipping_gap_inr} policy={seller.policy} /></li>)}</ul> : null}{unique.length > 0 && <details className="cost-notes"><summary>Assumptions ({unique.length})</summary><ol>{unique.map(note => <li key={note}>{note}</li>)}</ol></details>}<p className="cost-disclaimer">{costing.disclaimer || 'Estimate from seller-published prices and dated assumptions; not a final payable total.'}{costing.rates_checked_on ? ` Rates checked ${costing.rates_checked_on}.` : ''}</p></section>
}

export function GstChip({ offer }: { offer: ReportOffer }) {
  const text = offer.tax_included === true ? '✓ GST included' : offer.tax_included === false ? '+ GST' : '? GST unclear'
  return <span className="report-chip" title={offer.tax_evidence ?? 'No GST declaration found on the seller page'}>{text}</span>
}

const matchText = { exact: '✓ Exact', compatible: '≈ Compatible', partial: '◐ Partial', mismatch: '⛔ Mismatch' }
export function MatchChip({ match }: { match?: OfferMatch | null }) {
  if (!match) return null
  const method = match.method === 'deterministic_shortcut' ? 'Spec match' : 'AI match'
  return <details className={`match-chip match-${match.status}`}><summary>{matchText[match.status]} · {method}</summary><div>{match.reasons?.length ? <ul>{match.reasons.map((reason, index) => <li key={index}>{reason}</li>)}</ul> : null}{match.claims?.length ? <ul className="match-claims">{match.claims.map((claim, index) => <li key={index}><strong>{claim.claim}</strong><br />Listing says: “{claim.quote}”</li>)}</ul> : null}{match.missing?.length ? <p>Not stated: {match.missing.map(words).join(', ')}</p> : null}{match.conflicts?.length ? <p>Conflicts: {match.conflicts.map(words).join(', ')}</p> : null}<small>{match.method === 'deterministic_shortcut' ? 'Every spec value was found in the listing’s structured data.' : 'AI judgement of the listing text; quotes were found in the listing. Check before ordering.'}</small></div></details>
}

export function PackPrice({ offer }: { offer: ReportOffer }) {
  const pack = offer.pack_qty ?? offer.match?.pack_qty
  return <>{price(offer.price_inr)}{pack ? ` · pack of ${pack}` : ' per piece'}</>
}

export function TrustBadges({ trust }: { trust?: SellerTrust | null }) {
  if (!trust) return <span className="trust-badge trust-none">? Trust not checked</span>
  const label = trust.label === 'established' ? '✓ Established' : trust.label === 'verified_basics' ? '◐ Verified basics' : '⚠ Unverified seller — check before paying'
  const fresh = trust.new_seller ? (trust.label === 'verified_basics' ? (trust.signals?.gstin ? 'New seller · GSTIN verified' : 'New seller · policies found') : 'New seller') : null
  return <span className="trust-badges"><span className={`trust-badge trust-${trust.label}`}>{label}</span>{trust.label === 'unverified' && <span className="trust-hint">Prefer cash on delivery</span>}{fresh && <span className="trust-badge trust-new">✦ {fresh}</span>}{trust.signals?.price_anomaly && <span className="trust-badge trust-cheap">⚠ Unusually cheap — check seller</span>}<details className="trust-why"><summary>Seller checks</summary><ul>{(trust.reasons ?? []).map((reason, index) => <li key={index}>{reason}</li>)}</ul><small>Rule-based label from public signals, not a guarantee. A GSTIN is checked for format and checksum only.{trust.checked_at ? ` Checked ${new Date(trust.checked_at).toLocaleString('en-IN')}.` : ''}</small></details></span>
}

const gradeText: Record<string, string> = { A: '✓ A · Works as is', B: '⇄ B · Small setting change', C: '⚠ C · Wiring or power changes', D: '◐ D · Different part, similar result', X: '⛔ X · Don’t use' }
const areas = [['safety', 'Safety'], ['wiring', 'Wiring'], ['code', 'Code'], ['power', 'Power'], ['verify', 'Verify on arrival']] as const
const basisText = (item: string) => item.endsWith(':catalog') ? `${words(item.slice(0, -':catalog'.length))} — typical module value, not stated by this seller` : words(item)

// Grade chip with the "what changes" drawer. A judge-confirmed offer without a grade shows its match chip instead.
export function GradeChip({ compatibility, match }: { compatibility?: OfferCompatibility | null; match?: OfferMatch | null }) {
  if (!compatibility) return null
  const grade = compatibility.grade
  if (!grade && (match?.status === 'exact' || match?.status === 'compatible')) return null
  const findings = [...(compatibility.findings ?? [])].sort((a, b) => Number(b.area === 'safety') - Number(a.area === 'safety'))
  const changes = compatibility.what_changes
  const method = compatibility.method === 'catalog_rules' ? 'Checked by rules against a curated catalogue (unverified reference data) and the seller’s declared specs. Not a verified result.' : 'Checked against the seller’s declared specs only. Not a verified result.'
  return <details className={`grade-chip grade-${grade ?? 'none'}`}><summary>{grade ? gradeText[grade] : '? Not enough information'}{grade ? ' · what changes' : ''}</summary><div>{!grade && compatibility.missing_fields?.length ? <p>The seller does not state: {compatibility.missing_fields.map(words).join(', ')}.</p> : null}{changes && areas.map(([key, name]) => changes[key]?.length ? <div key={key} className={key === 'safety' ? 'changes-safety' : undefined}><h5>{name}</h5><ul>{changes[key]!.map((item, index) => <li key={index}>{key === 'safety' ? <strong>{item}</strong> : item}</li>)}</ul></div> : null)}{!changes && compatibility.changes?.length ? <ul>{compatibility.changes.map((item, index) => <li key={index}>{item}</li>)}</ul> : null}{findings.length > 0 && <ul className="grade-findings">{findings.map((finding, index) => <li key={index} className={finding.area === 'safety' ? 'changes-safety' : undefined}><span className="report-chip">{gradeText[finding.grade]}</span> {finding.area === 'safety' ? <strong>{finding.message}</strong> : finding.message}{finding.change ? ` Change: ${finding.change}` : ''}{finding.basis?.length ? <small> Basis: {finding.basis.map(basisText).join('; ')}</small> : null}</li>)}</ul>}{compatibility.reasons?.length ? <p>{compatibility.reasons.join(' ')}</p> : null}<small>{method}</small></div></details>
}
