import { useEffect, useRef, useState, type FormEvent } from 'react'
import { reportPartName } from './partName'
import {
  evidenceText,
  offersOf,
  reportOf,
  selectOffer,
  updateRequirements,
  type BuyableSpec,
  type Job,
  type ReportLine,
  type ResearchAssessment,
  type PartRequirement,
  type UnsourcedLine,
} from './api'
import Requirements, { requirementPayload, validRequirements } from './Requirements'
import { GradeChip, MatchChip, PackPrice, price, secureLink } from './ReportBits'
import { PlanCompare } from './OrderPlan'
import PartsList, { statusOf } from './PartsList'
import { SidePanel } from './ProjectFrame'
import { ExportButtons, ShareControl } from './ReportActions'
import { NeedsList, SummaryBand } from './ReportSummary'
import { orderNeeds } from './orderNeeds'
import SellerRetry from './SellerRetry'
import CodePatchView from './CodePatch'
import { SellerIdentity } from './SellerIdentity'
import { AiSpecs, SpecSourceText } from './ReviewDetails'
import { Spinner } from './Skeleton'
import { useToast } from './toastContext'

function Assessment({ value }: { value: ResearchAssessment }) {
  return (
    <div className="research-assessment">
      <strong>AI assessment · {value.status.replaceAll('_', ' ')}</strong>
      <p>{value.explanation}</p>
      {value.conditions.length > 0 && (
        <div className="research-assessment-list">
          <h5>Conditions to check</h5>
          <ul>
            {value.conditions.map((condition, index) => (
              <li key={index}>{condition}</li>
            ))}
          </ul>
        </div>
      )}
      {value.questions.length > 0 && (
        <div className="research-assessment-list">
          <h5>Questions to resolve</h5>
          <ul>
            {value.questions.map((question, index) => (
              <li key={index}>{question}</li>
            ))}
          </ul>
        </div>
      )}
      {value.checks?.length ? (
        <details className="research-facts">
          <summary>Requirement checks ({value.checks.length})</summary>
          <ul>
            {value.checks.map((check, index) => (
              <li key={index}>
                <strong>
                  {check.requirement.name}: {check.status.replaceAll('_', ' ')}
                </strong>{' '}
                · {check.reason}
              </li>
            ))}
          </ul>
        </details>
      ) : null}
    </div>
  )
}

function Research({ line }: { line: ReportLine }) {
  const research = line.research
  if (!research) return null
  if (research.status === 'skipped')
    return (
      <details className="research-block research-skipped">
        <summary>
          Additional research <span>Not run</span>
        </summary>
        <p>{research.summary}</p>
        <small>
          No separate AI research review ran for this part. Check the seller page and match details before ordering.
        </small>
      </details>
    )
  const candidates = research.candidates ?? []
  return (
    <section className="research-block" aria-label={`Research for ${line.item.raw_name}`}>
      <div className="research-heading">
        <div>
          <span className="section-kicker">SOURCE LEADS</span>
          <h4>Source research</h4>
        </div>
        <span className="research-count">
          {candidates.length} {candidates.length === 1 ? 'lead' : 'leads'}
        </span>
      </div>
      <p className="research-summary">{research.summary || `Research ${research.status.replaceAll('_', ' ')}.`}</p>
      {!!research.questions?.length && (
        <div className="research-questions">
          <strong>Check before choosing a part</strong>
          <ul>
            {research.questions.map((question, index) => (
              <li key={index}>{question}</li>
            ))}
          </ul>
        </div>
      )}
      {candidates.map((candidate, index) => (
        <details className="research-candidate" key={`${candidate.url}-${index}`}>
          <summary>
            <span className="candidate-heading">
              <strong>{candidate.title}</strong>
              <small>
                {candidate.kind} · {candidate.match} match
              </small>
            </span>
            <span className={`research-status research-status-${candidate.assessment.status}`}>
              {candidate.assessment.status.replaceAll('_', ' ')}
            </span>
          </summary>
          <div className="research-candidate-body">
            <p className="research-identity">
              <strong>Identity excerpt</strong> “{candidate.identity_quote}”
            </p>
            <Assessment value={candidate.assessment} />
            {candidate.facts?.length ? (
              <details className="research-facts">
                <summary>Source facts and quotes ({candidate.facts.length})</summary>
                <ul>
                  {candidate.facts.map((fact, i) => (
                    <li key={i}>
                      <strong>
                        {fact.name}: {fact.value} {fact.unit ?? ''}
                      </strong>
                      <br />“{fact.quote}”
                    </li>
                  ))}
                </ul>
              </details>
            ) : null}
            {secureLink(candidate.url) && (
              <a className="research-source-link" href={candidate.url} target="_blank" rel="noopener noreferrer">
                Review source ↗
              </a>
            )}
          </div>
        </details>
      ))}
      {research.sources?.length ? (
        <details className="research-facts research-access">
          <summary>Source access and review status</summary>
          <ul>
            {research.sources.map((source, index) => (
              <li key={index}>
                {secureLink(source.url) ? (
                  <a href={source.url} target="_blank" rel="noopener noreferrer">
                    {source.url}
                  </a>
                ) : (
                  source.url
                )}{' '}
                ·{' '}
                {source.status === 'unavailable'
                  ? `Unavailable: ${source.reason ?? 'not readable'}`
                  : source.reviewed
                    ? 'Read for assessment'
                    : 'Discovered, not reviewed'}
              </li>
            ))}
          </ul>
        </details>
      ) : null}
      <small className="research-disclaimer">
        AI-reviewed quotes are leads for your own checks, not verified prices or safety certifications.
      </small>
    </section>
  )
}

// The report carries the exact buying spec used during sourcing, including specs written for older jobs.
function BuyingSpec({ spec, warning = true }: { spec?: BuyableSpec | null; warning?: boolean }) {
  if (!spec) return null
  const origin =
    spec.origin === 'user'
      ? 'Your saved spec'
      : spec.origin === 'ai_inferred'
        ? 'Suggested spec — check values'
        : 'From the part name and requirements'
  return (
    <div className="report-buying-spec">
      {warning && spec.needs_value && (
        <p className="needs-value">
          <strong>⚠ Needs a value</strong> ·{' '}
          {spec.needs_value_reason || 'The source did not state the value for this part.'} To improve matching, add the
          exact value to the part name before refreshing seller search.
        </p>
      )}
      <div>
        <p>
          {origin}
          {spec.part_name ? ` · ${spec.part_name}` : ''}
        </p>
        <dl>
          <div>
            <dt>Category</dt>
            <dd>{spec.category.replaceAll('_', ' ')}</dd>
          </div>
          <div>
            <dt>Mount</dt>
            <dd>
              {spec.mount === 'any' ? 'Any' : spec.mount.toUpperCase()}
              {spec.mount_reason ? ` · ${spec.mount_reason}` : ''}
            </dd>
          </div>
          {spec.params.map((param, index) => (
            <div key={index}>
              <dt>{param.name}</dt>
              <dd>
                {param.value}
                {param.operator === 'between' && param.value_max ? `–${param.value_max}` : ''}
                {param.reason ? ` · ${param.reason}` : ''}
              </dd>
            </div>
          ))}
        </dl>
      </div>
    </div>
  )
}

function RequirementReview({
  job,
  line,
  token,
  onJob,
}: {
  job: Job
  line: ReportLine
  token: string
  onJob: (job: Job) => void
}) {
  const [requirements, setRequirements] = useState<PartRequirement[]>(line.item.requirements ?? [])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const original = JSON.stringify(line.item.requirements ?? [])
  async function save(event: FormEvent) {
    event.preventDefault()
    if (!validRequirements(requirements)) {
      setError('Every requirement needs a property and value.')
      return
    }
    setBusy(true)
    setError('')
    try {
      onJob(await updateRequirements(job.job_id, token, line.item.line_id, requirementPayload(requirements)))
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not save requirements.')
    } finally {
      setBusy(false)
    }
  }
  return (
    <div className="requirements-after">
      <form onSubmit={save}>
        <Requirements value={requirements} onChange={setRequirements} disabled={busy} />
        <p>
          Changing requirements may make AI assessments stale and clear affected selections. Refresh is a separate
          action.
        </p>
        <button className="nav-cta" type="submit" disabled={busy || JSON.stringify(requirements) === original}>
          {busy ? 'Saving…' : 'Save requirements'}
        </button>
        {error && (
          <p className="form-error" role="alert">
            {error}
          </p>
        )}
      </form>
    </div>
  )
}

// The offer picker, also used by the order plan's Change action. Choosing posts /selections and makes it the user's choice.
type SelectionNotice = { title: string; message: string }

function OfferList({
  job,
  line,
  token,
  onJob,
  readOnly,
  onNotice,
}: {
  job: Job
  line: ReportLine
  token: string
  onJob: (job: Job) => void
  readOnly: boolean
  onNotice: (notice: SelectionNotice | null) => void
}) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [acknowledge, setAcknowledge] = useState<Record<string, boolean>>({})
  // Optimistic selection: the chosen card shows as selected while the server confirms; a failure rolls it back.
  const [optimistic, setOptimistic] = useState<{ url: string | null } | null>(null)
  const toast = useToast()
  const offers = offersOf(line)
  const editable = !job.demo && !readOnly
  const needsValue = (line.buyable_spec ?? line.item.buyable_spec)?.needs_value === true
  const selectedUrl = optimistic ? optimistic.url : line.selected_offer_url
  async function choose(url: string | null, changes = false, assessment = false) {
    setBusy(true)
    setError('')
    setOptimistic({ url })
    try {
      onJob(await selectOffer(job.job_id, token, line.item.line_id, url, changes, assessment))
    } catch (cause) {
      const message = cause instanceof Error ? cause.message : 'Could not update the selection.'
      setError(message)
      toast(message, 'error')
    } finally {
      setOptimistic(null)
      setBusy(false)
    }
  }
  const leads = line.seller_search?.candidate_urls ?? []
  if (!offers.length)
    return (
      <>
        <div className="offer-search-note" role="status">
          <strong>{line.sourcing_status === 'already_owned' ? 'Already owned' : 'No verified seller offer yet'}</strong>
          <p>
            {line.sourcing_status === 'already_owned'
              ? 'No seller search needed for this part.'
              : line.sourcing_error?.message ||
                (line.sourcing_status === 'no_verified_offers'
                  ? 'No page passed the current offer checks. Research leads may still be useful.'
                  : 'No verified offer is available yet.')}
          </p>
        </div>
        {leads.length > 0 && (
          <details className="result-evidence">
            <summary>Unverified seller leads ({leads.length})</summary>
            <ul>
              {leads.map(url => (
                <li key={url}>
                  {secureLink(url) ? (
                    <a href={url} target="_blank" rel="noopener noreferrer">
                      {url}
                    </a>
                  ) : (
                    url
                  )}
                </li>
              ))}
            </ul>
            <small>
              Search results that did not pass the offer checks. They are not offers; check price and stock yourself.
            </small>
          </details>
        )}
      </>
    )
  return (
    <div className="offers-list">
      <div className="offers-track snap-row" tabIndex={0} role="group" aria-label="Seller offers">
        {offers.map(offer => {
          const selected = selectedUrl === offer.url
          const grade = offer.compatibility?.grade
          const changeNeeded = grade === 'B'
          const judged = !grade && (offer.match?.status === 'exact' || offer.match?.status === 'compatible')
          const aiChoice = !grade && !judged && offer.research_assessment?.status === 'potential_match'
          // eslint-disable-next-line react-hooks/purity -- offer freshness is evaluated at render time by design
          const fresh = Date.now() - Date.parse(offer.checked_at) < 24 * 60 * 60 * 1000
          const eligible =
            editable && offer.stock === 'in_stock' && fresh && (grade === 'A' || changeNeeded || judged || aiChoice)
          const acknowledged = acknowledge[offer.url] ?? false
          const recommended = line.recommendation?.offer_url === offer.url
          const canToggle =
            editable && !busy && (selected || (eligible && (!(changeNeeded || aiChoice || needsValue) || acknowledged)))
          const toggleSelection = () => {
            if (!editable || busy) return
            if (canToggle) {
              onNotice(null)
              void (selected ? choose(null) : choose(offer.url, changeNeeded, aiChoice))
              return
            }
            onNotice({
              title: !fresh ? 'Quote expired' : 'Can’t select this offer',
              message: !fresh
                ? 'This quote is over 24 hours old. Refresh the quote to select this seller.'
                : offer.stock !== 'in_stock'
                  ? 'Stock is not confirmed for this offer. Please choose an in-stock option.'
                  : !eligible
                    ? 'Compatibility is unresolved. Review the research notes or choose another offer.'
                    : 'Please tick the review checkbox before selecting this offer.',
            })
          }
          return (
            <article
              className={`offer${selected ? ' is-selected' : ''}${editable && !busy ? ' is-interactive' : ''}`}
              key={offer.url}
              onClick={event => {
                const control = (event.target as Element).closest('a, button, input, label, select, textarea, details')
                if (control && event.currentTarget.contains(control)) return
                toggleSelection()
              }}
            >
              {editable && (
                <button
                  type="button"
                  className="offer-card-toggle"
                  aria-label={`Select offer from ${offer.seller_name || offer.seller}: ${offer.title}`}
                  aria-pressed={selected}
                  disabled={busy}
                  onClick={toggleSelection}
                />
              )}
              <div>
                {(recommended || selected) && (
                  <div className="offer-card-status">
                    {busy && selected ? <Spinner /> : <span aria-hidden="true">{selected ? '✓' : '★'}</span>}
                    {selected ? (recommended ? 'Selected · Recommended' : 'Selected') : 'Recommended'}
                  </div>
                )}
                <SellerIdentity offer={offer} compact />
                <span className="offer-title">
                  {offer.title}
                  {offer.match?.variant ? ` · Variant: ${offer.match.variant}` : ''}
                </span>
                <span>
                  <PackPrice offer={offer} />, {offer.stock.replaceAll('_', ' ')}, checked{' '}
                  {checkedAgo(offer.checked_at)}
                </span>
                <div className="plan-chips">
                  <GradeChip compatibility={offer.compatibility} match={offer.match} />
                </div>
                {offer.spec_conflicts?.length ? (
                  <details className="spec-conflicts">
                    <summary>
                      Sellers disagree on {offer.spec_conflicts.map(conflict => conflict.field).join(', ')} · values
                      unknown
                    </summary>
                    <ul>
                      {offer.spec_conflicts.map(conflict => (
                        <li key={conflict.field}>
                          <strong>{conflict.field}: unknown</strong>
                          <ul>
                            {conflict.candidates.map((candidate, index) => (
                              <li key={index}>
                                {candidate.value} · <SpecSourceText source={candidate.source} />
                                {candidate.locator ? ` (${candidate.locator})` : ''}
                              </li>
                            ))}
                          </ul>
                        </li>
                      ))}
                    </ul>
                  </details>
                ) : null}
                {changeNeeded && (
                  <p>
                    Required changes:{' '}
                    {offer.compatibility?.changes?.join('; ') || 'Review the report before accepting.'}
                  </p>
                )}
                {offer.research_assessment && <Assessment value={offer.research_assessment} />}
                {eligible && !selected && (changeNeeded || aiChoice || needsValue) && (
                  <label className="offer-ack">
                    <input
                      type="checkbox"
                      checked={acknowledged}
                      onChange={event => setAcknowledge(rows => ({ ...rows, [offer.url]: event.target.checked }))}
                    />{' '}
                    I reviewed{' '}
                    {needsValue
                      ? 'the missing value and will verify this listing before ordering'
                      : changeNeeded
                        ? 'the required changes'
                        : 'the AI assessment, conditions and unknowns'}
                  </label>
                )}
                {editable && selected && changeNeeded && line.selection_source !== 'user' && !line.changes_accepted && (
                  <>
                    <label className="offer-ack">
                      <input
                        type="checkbox"
                        checked={acknowledged}
                        onChange={event => setAcknowledge(rows => ({ ...rows, [offer.url]: event.target.checked }))}
                      />{' '}
                      I reviewed the required changes
                    </label>
                    <button
                      type="button"
                      className="nav-cta"
                      disabled={busy || !acknowledged}
                      onClick={() => void choose(offer.url, true)}
                    >
                      Keep this offer
                    </button>
                  </>
                )}
              </div>
              <footer className="offer-actions">
                {secureLink(offer.url) && (
                  <a href={offer.url} target="_blank" rel="noopener noreferrer">
                    Seller page ↗
                  </a>
                )}
              </footer>
            </article>
          )
        })}
      </div>
      <small className="offers-note">Prices are what each seller's page showed when checked.</small>
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
    </div>
  )
}

function checkedAgo(value: string) {
  const minutes = Math.max(0, Math.round((Date.now() - Date.parse(value)) / 60000))
  if (!Number.isFinite(minutes)) return 'at an unknown time'
  if (minutes < 2) return 'just now'
  if (minutes < 60) return `${minutes} minutes ago`
  const hours = Math.round(minutes / 60)
  return hours < 24 ? `${hours} ${hours === 1 ? 'hour' : 'hours'} ago` : new Date(value).toLocaleDateString('en-IN')
}

// One part's details, shown in the side panel: the chosen offer first, then everything else
// in sections that open on demand.
function PartDetail({
  job,
  line,
  token,
  onJob,
  readOnly,
  unsourced,
}: {
  job: Job
  line: ReportLine
  token: string
  onJob: (job: Job) => void
  readOnly: boolean
  unsourced?: UnsourcedLine
}) {
  const offers = offersOf(line)
  const chosen = offers.find(offer => offer.url === line.selected_offer_url)
  const spec = line.buyable_spec ?? line.item.buyable_spec
  const blocked =
    line.recommendation?.blocked_reason && !line.selected_offer_url ? line.recommendation.blocked_reason : null
  const [offersOpen, setOffersOpen] = useState(() => !chosen || !!blocked)
  const [notice, setNotice] = useState<SelectionNotice | null>(null)
  const [fadingNotice, setFadingNotice] = useState<SelectionNotice | null>(null)
  useEffect(() => {
    if (!notice) return
    const fadeTimer = window.setTimeout(() => setFadingNotice(notice), 5000)
    const dismissTimer = window.setTimeout(() => setNotice(null), 5300)
    return () => {
      window.clearTimeout(fadeTimer)
      window.clearTimeout(dismissTimer)
    }
  }, [notice])
  const live = !job.demo && !readOnly
  return (
    <div className="pp-part-layout">
      <div className="pp-part">
        {line.item.user_has_it ? (
          <div className="pp-part-callout">
            <strong>You already have this part.</strong>
            <p>It is not part of the order.</p>
          </div>
        ) : chosen ? (
          <div className="pp-part-pick">
            <p className="pp-part-price">
              {price(chosen.price_inr)}
              <small>
                {(chosen.pack_qty ?? chosen.match?.pack_qty)
                  ? `pack of ${chosen.pack_qty ?? chosen.match?.pack_qty}`
                  : 'each'}
              </small>
            </p>
            <SellerIdentity offer={chosen} compact />
            <p className="pp-part-title">{chosen.title}</p>
            <p className="pp-part-meta">
              {chosen.stock.replaceAll('_', ' ')}, checked {checkedAgo(chosen.checked_at)}
            </p>
            <div className="plan-chips">
              <GradeChip compatibility={chosen.compatibility} match={chosen.match} />
            </div>
            {secureLink(chosen.url) && (
              <a className="primary-button pp-part-open" href={chosen.url} target="_blank" rel="noopener noreferrer">
                Open seller page ↗
              </a>
            )}
          </div>
        ) : (
          (unsourced || !(blocked || spec?.needs_value)) && (
            <div className="pp-part-callout">
              {unsourced ? (
                <>
                  <strong>{unsourced.message}</strong>
                  {!!unsourced.next_steps?.length && (
                    <ul>
                      {unsourced.next_steps.map((step, index) => (
                        <li key={index}>{step}</li>
                      ))}
                    </ul>
                  )}
                </>
              ) : (
                <>
                  <strong>{offers.length ? 'Pick a seller below.' : 'No verified seller offer yet.'}</strong>
                  {line.sourcing_error?.message && <p>{line.sourcing_error.message}</p>}
                </>
              )}
            </div>
          )
        )}
        {line.buyer?.value && (
          <div className="pp-part-callout">
            <strong>Value decided by AI: {line.buyer.value.replace(/^[a-z_]+:\s*/i, '')}</strong>
            <p>
              {line.buyer.value_reason}
              {line.buyer.value_confidence ? ` (${line.buyer.value_confidence} confidence)` : ''} The video does not
              state it; change it under Specs and requirements if you know better.
            </p>
          </div>
        )}
        {line.buyer?.fit && chosen && line.buyer.offer_url === chosen.url && (
          <div className="pp-part-callout">
            <strong>
              {line.buyer.fit === 'substitute'
                ? 'AI-suggested substitute'
                : line.buyer.fit === 'kit'
                  ? 'AI-suggested kit'
                  : 'Chosen by the AI buyer'}
            </strong>
            <p>{line.buyer.reason}</p>
            {!!line.buyer.changes?.length && (
              <ul>
                {line.buyer.changes.map((change, index) => (
                  <li key={index}>{change}</li>
                ))}
              </ul>
            )}
          </div>
        )}
        {blocked && (
          <div className="pp-part-callout pp-part-callout-input">
            <strong>Confirm the seller</strong>
            <p>{blocked}</p>
          </div>
        )}
        {spec?.needs_value && (
          <div className="pp-part-callout pp-part-callout-input">
            <strong>This part needs a value</strong>
            <p>
              {spec.needs_value_reason || 'The source did not state the value for this part.'} Add the exact value to
              the part name, then search sellers again.
            </p>
          </div>
        )}
        {!line.item.user_has_it && (
          <details className="pp-section" open={offersOpen} onToggle={event => setOffersOpen(event.currentTarget.open)}>
            <summary>
              Seller offers <span>{offers.length}</span>
            </summary>
            <div className="pp-section-body">
              <OfferList job={job} line={line} token={token} onJob={onJob} readOnly={readOnly} onNotice={setNotice} />
            </div>
          </details>
        )}
        {live && <CodePatchView job={job} line={line} token={token} onJob={onJob} />}
        {line.item.evidence.length > 0 && (
          <details className="pp-section">
            <summary>Why this part is in the list</summary>
            <div className="pp-section-body">
              <ul className="pp-evidence">
                {line.item.evidence.map((entry, i) => (
                  <li key={i}>{evidenceText(entry)}</li>
                ))}
              </ul>
              <small>Reported by reading the project source. Check it there.</small>
            </div>
          </details>
        )}
        <details className="pp-section">
          <summary>Specs and requirements</summary>
          <div className="pp-section-body">
            <BuyingSpec spec={spec} warning={false} />
            <AiSpecs specs={line.item.ai_specs} />
            {live && (
              <RequirementReview
                key={JSON.stringify(line.item.requirements ?? [])}
                job={job}
                line={line}
                token={token}
                onJob={onJob}
              />
            )}
          </div>
        </details>
        {(line.research ||
          offers.some(offer => offer.match) ||
          (!!line.recommendation?.reasons?.length && line.selected_offer_url === line.recommendation.offer_url)) && (
          <details className="pp-section">
            <summary>Research notes</summary>
            <div className="pp-section-body">
              {!!line.recommendation?.reasons?.length && line.selected_offer_url === line.recommendation.offer_url && (
                <div className="pp-pick-reasons">
                  <strong>Why this pick</strong>
                  <ul>
                    {line.recommendation.reasons.map((reason, index) => (
                      <li key={index}>{reason}</li>
                    ))}
                  </ul>
                </div>
              )}
              {offers
                .filter(offer => offer.match)
                .map(offer => (
                  <div className="pp-research-match" key={offer.url}>
                    <strong>
                      {offer.seller_name || offer.seller}
                      {offer.url === chosen?.url ? ' · Selected offer' : ''}
                    </strong>
                    <p>{offer.title}</p>
                    <MatchChip match={offer.match} showExplanation={false} />
                  </div>
                ))}
              <Research line={line} />
            </div>
          </details>
        )}
      </div>
      {notice && (
        <aside
          className={`offer-selection-notice${fadingNotice === notice ? ' is-fading' : ''}`}
          aria-label="Seller selection notice"
        >
          <span className="offer-notice-icon" aria-hidden="true">
            i
          </span>
          <div>
            <div role="status">
              <strong>{notice.title}</strong>
              <p>{notice.message}</p>
            </div>
          </div>
        </aside>
      )}
    </div>
  )
}

// The report after sourcing. `shareToken` renders the read-only public share view: no chat, edit, select, refresh or image generation.
export default function Results({
  job,
  token,
  onJob,
  shareToken,
  onOpenChat,
  openPart,
  onOpenPart,
  attentionOpen,
  onAttentionChange,
  onRetry,
}: {
  job: Job
  token: string
  onJob: (job: Job) => void
  shareToken?: string
  onOpenChat?: () => void
  openPart?: string | null
  onOpenPart?: (lineId: string | null) => void
  attentionOpen?: boolean
  onAttentionChange?: (open: boolean) => void
  // Search again for parts without a seller; absent on the shared page.
  onRetry?: (ids: string[]) => Promise<void>
}) {
  const report = reportOf(job)
  const readOnly = !!shareToken
  // The page (JobPage) owns which part is open so it can close the chat; the shared page does not.
  const [localPart, setLocalPart] = useState<string | null>(null)
  const [localAttention, setLocalAttention] = useState(false)
  const showingAttention = attentionOpen ?? localAttention
  const setAttention = onAttentionChange ?? setLocalAttention
  const openLine = onOpenPart ? (openPart ?? null) : localPart
  const updateOpenLine = onOpenPart ?? setLocalPart
  const setOpenLine = (lineId: string | null) => {
    if (lineId) setAttention(false)
    updateOpenLine(lineId)
  }
  const lastLine = useRef<ReportLine | null>(null)
  useEffect(() => {
    function show(event: Event) {
      const id = (event as CustomEvent<string>).detail
      if (reportOf(job)?.lines.some(line => line.item.line_id === id)) setOpenLine(id)
    }
    window.addEventListener('bharat-sourcer:show-line', show)
    return () => window.removeEventListener('bharat-sourcer:show-line', show)
  })
  if (!report) return null
  const names = Object.fromEntries(report.lines.map(line => [line.item.line_id, reportPartName(line)]))
  const showLine = (lineId: string) => setOpenLine(lineId)
  const needs = orderNeeds({
    job,
    readOnly,
    onShowLine: showLine,
    onOpenChat: onOpenChat
      ? () => {
          setAttention(false)
          onOpenChat()
        }
      : undefined,
  })
  const safetyChecks = needs.filter(need => need.tone === 'danger').length
  const plan = report.order_plan
  const planLines = new Map(
    (plan?.sellers ?? []).flatMap(seller => (seller.lines ?? []).map(entry => [entry.line_id, entry] as const)),
  )
  const unsourcedLines = new Map((plan?.unsourced ?? []).map(entry => [entry.line_id, entry]))
  const current = report.lines.find(line => line.item.line_id === openLine) ?? null
  // eslint-disable-next-line react-hooks/refs -- keeps the last opened part rendered while the side panel closes
  if (current) lastLine.current = current
  // eslint-disable-next-line react-hooks/refs -- keeps the last opened part rendered while the side panel closes
  const shown = current ?? lastLine.current
  const status = shown
    ? statusOf(shown, planLines.get(shown.item.line_id), unsourcedLines.get(shown.item.line_id))
    : null
  return (
    <section className="job-panel report-panel">
      <SummaryBand
        job={job}
        actions={
          <>
            <ExportButtons
              base={
                readOnly ? '/v1/shared/' + encodeURIComponent(shareToken) : '/v1/jobs/' + encodeURIComponent(job.job_id)
              }
              token={readOnly ? undefined : token}
              name={(job.project?.title || 'bharat-sourcer-bom').replace(/[^\w-]+/g, '-').slice(0, 60)}
            />
            {!readOnly && <ShareControl key={job.job_id} job={job} token={token} />}
          </>
        }
      />
      {report.order_plan && !readOnly && !job.demo && (
        <div className="pp-plan-tools">
          <PlanCompare job={job} token={token} onJob={onJob} names={names} />
        </div>
      )}
      <PartsList
        job={job}
        token={token}
        readOnly={readOnly}
        openLine={openLine}
        onOpen={id => setOpenLine(openLine === id ? null : id)}
        attention={
          needs.length > 0 && (
            <button
              type="button"
              className={`pp-attention-button${safetyChecks ? ' has-danger' : ''}`}
              aria-controls="pp-attention"
              aria-expanded={showingAttention}
              onClick={() => {
                setOpenLine(null)
                setAttention(!showingAttention)
              }}
            >
              <span className="pp-need-dot" aria-hidden="true" />
              Needs your attention <b>{needs.length}</b>
              {safetyChecks > 0 && (
                <small>
                  {safetyChecks} safety {safetyChecks === 1 ? 'check' : 'checks'}
                </small>
              )}
            </button>
          )
        }
      />
      {onRetry && !readOnly && <SellerRetry job={job} onRetry={onRetry} />}
      <SidePanel
        id="pp-attention"
        open={showingAttention}
        title="Needs your attention"
        onClose={() => setAttention(false)}
      >
        {needs.length ? (
          <NeedsList
            needs={needs}
            showHeading={false}
            initiallyOpen={job.safety_flags?.some(flag => flag.code === 'MAINS') ? 'flag-MAINS' : null}
          />
        ) : (
          <p>Nothing needs your attention right now.</p>
        )}
      </SidePanel>
      <SidePanel
        id="pp-part"
        open={!!current}
        title={shown ? reportPartName(shown) : 'Part'}
        subtitle={
          shown && status ? (
            <>
              <span>×{shown.item.qty ?? '?'}</span>
              <span className={`pp-row-status pp-status-${status.tone}`}>{status.label}</span>
            </>
          ) : undefined
        }
        onClose={() => setOpenLine(null)}
      >
        {shown && (
          <PartDetail
            key={shown.item.line_id}
            job={job}
            line={shown}
            token={token}
            onJob={onJob}
            readOnly={readOnly}
            unsourced={unsourcedLines.get(shown.item.line_id)}
          />
        )}
      </SidePanel>
    </section>
  )
}
