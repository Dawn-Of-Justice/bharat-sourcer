import {
  evidenceText,
  type BomItem,
  type Evidence,
  type EvidenceSource,
  type Job,
  type PartSpecs,
  type SpecEvidence,
} from './api'
import { kindLabel } from './sourceChips'
import { safeHref } from './safeUrl'

// Review-page details from multi-source intake (docs/contracts/multi-source-intake.md). All are rule or model outputs, not verified facts.
const sourceLabel: Record<EvidenceSource, string> = {
  video: 'Video',
  project_page: 'Page quote',
  code: 'Code',
  youtube_description: 'Video description',
}
const sourceOf = (entry: Evidence): EvidenceSource => entry.source ?? 'video'
// evidenceText() starts with the source label; the list shows that label as a chip, so drop it from the text.
const evidenceDetail = (entry: Evidence) => {
  const text = evidenceText(entry),
    label = sourceLabel[sourceOf(entry)]
  return text.startsWith(label + ' ') ? text.slice(label.length + 1) : text
}

// Evidence with a source label; code, page and description entries link to their url.
export function EvidenceList({ evidence }: { evidence: Evidence[] }) {
  if (!evidence.length) return null
  return (
    <div className="evidence-note">
      <strong>Evidence</strong>
      <ul className="evidence-list">
        {evidence.map((entry, index) => (
          <li key={index}>
            <span className={`evidence-kind evidence-${sourceOf(entry)}`}>{sourceLabel[sourceOf(entry)]}</span>{' '}
            {entry.url ? (
              <a href={safeHref(entry.url)} target="_blank" rel="noopener noreferrer">
                {evidenceDetail(entry)} <span aria-hidden="true">↗</span>
                <span className="visually-hidden"> (opens in a new tab)</span>
              </a>
            ) : (
              evidenceDetail(entry)
            )}
          </li>
        ))}
      </ul>
    </div>
  )
}

// Spec values the model decided from the project context are suggestions, never verified facts.
export const AI_DECIDED = 'AI decided from the project'
const specSource: Record<SpecEvidence['source'], string> = {
  part_name: 'part name',
  user: 'yours',
  seller_title: 'seller title',
  seller_property: 'seller property',
  seller_table: 'seller table',
  catalog: 'typical module value',
  ai_inferred: AI_DECIDED,
}
// One spec value's origin, with AI-decided values in muted text.
export function SpecSourceText({ source }: { source: SpecEvidence['source'] }) {
  return source === 'ai_inferred' ? (
    <span className="ai-decided">{AI_DECIDED}</span>
  ) : (
    <>{specSource[source] ?? String(source).replaceAll('_', ' ')}</>
  )
}

// Required values the source did not state, filled by the model (items[].ai_specs). Only used to fill gaps.
export function AiSpecs({ specs }: { specs?: PartSpecs | null }) {
  const rows = Object.entries(specs ?? {}).filter(([, value]) => value !== null && value !== undefined && value !== '')
  if (!rows.length) return null
  return (
    <div className="ai-specs">
      <strong>Values the source did not state</strong>
      <dl>
        {rows.map(([field, value]) => (
          <div key={field}>
            <dt>{field.replaceAll('_', ' ')}</dt>
            <dd>
              {String(value)} <span className="ai-decided">{AI_DECIDED}</span>
            </dd>
          </div>
        ))}
      </dl>
    </div>
  )
}

const confidence = {
  verified: { icon: '✓', label: 'Verified' },
  likely: { icon: '◐', label: 'Likely' },
  check: { icon: '⚠', label: 'Check' },
}
export function ConfidenceChip({ item }: { item: BomItem }) {
  if (!item.confidence) return null
  const chip = confidence[item.confidence]
  return (
    <span className={`confidence-chip confidence-${item.confidence}`} title={item.confidence_reason ?? undefined}>
      <span aria-hidden="true">{chip.icon}</span> {chip.label}
      <span className="visually-hidden">{item.confidence_reason ? `: ${item.confidence_reason}` : ''}</span>
    </span>
  )
}

export function ConflictNotes({ item }: { item: BomItem }) {
  if (!item.conflicts?.length) return null
  return (
    <div className="line-conflicts">
      {item.conflicts.map((conflict, index) => (
        <div key={index} className="line-conflict">
          <strong>
            <span aria-hidden="true">⚠</span>{' '}
            {conflict.kind === 'qty_mismatch' ? 'Sources give different quantities' : 'Sources name different parts'}
          </strong>
          <p>{conflict.message}</p>
          <ul>
            {conflict.values.map((value, i) => (
              <li key={i}>
                <span className={`evidence-kind evidence-${value.source}`}>{sourceLabel[value.source]}</span>{' '}
                <b>{value.value}</b>
                {value.locator ? (
                  <>
                    {' '}
                    ·{' '}
                    {value.url ? (
                      <a href={safeHref(value.url)} target="_blank" rel="noopener noreferrer">
                        {value.locator} <span aria-hidden="true">↗</span>
                      </a>
                    ) : (
                      value.locator
                    )}
                  </>
                ) : value.url ? (
                  <>
                    {' '}
                    ·{' '}
                    <a href={safeHref(value.url)} target="_blank" rel="noopener noreferrer">
                      source <span aria-hidden="true">↗</span>
                    </a>
                  </>
                ) : null}
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  )
}

const linkKind = {
  project_source: 'Project page',
  video: 'Another video',
  store: 'Shop or affiliate link',
  other: 'Other link',
}

export function SourcesCard({ job }: { job: Job }) {
  const reports = job.source_reports ?? []
  const meta = job.video_meta
  if (!reports.length && !meta?.expired && !meta?.links?.length) return null
  return (
    <section className="sources-card" aria-label="Sources read">
      {reports.length > 0 && (
        <>
          <strong>Sources read</strong>
          <ul className="sources-list">
            {reports.map((report, index) => (
              <li key={index} className={`source-report source-${report.status}`}>
                <span className="source-status">
                  {report.status === 'read' ? (
                    <>
                      <span aria-hidden="true">✓</span> Read
                    </>
                  ) : (
                    <>
                      <span aria-hidden="true">✕</span> Skipped
                    </>
                  )}
                </span>
                <div>
                  <b>{kindLabel[report.kind]}</b> · {report.role === 'primary' ? 'Main source' : 'Extra source'}
                  {report.found_in === 'youtube_description' && (
                    <span className="inferred-tag">Found in the video description</span>
                  )}
                  <br />
                  <a href={safeHref(report.url)} target="_blank" rel="noopener noreferrer">
                    {report.url} <span aria-hidden="true">↗</span>
                  </a>
                  {report.status === 'read' ? (
                    <small>
                      {report.item_count} {report.item_count === 1 ? 'part' : 'parts'} found
                      {report.code_item_count ? ` · ${report.code_item_count} from code` : ''}
                    </small>
                  ) : (
                    <small className="source-error">
                      {report.error?.message || 'This source could not be read.'} It was skipped.
                    </small>
                  )}
                </div>
              </li>
            ))}
          </ul>
        </>
      )}
      {meta?.expired ? (
        <p className="video-links-expired">
          Video description data expired under YouTube’s 30-day policy, so description quotes and links are no longer
          shown.
        </p>
      ) : meta?.links?.length ? (
        <div className="video-links">
          <strong>Links in the video description</strong>
          <ul>
            {meta.links.map((link, index) => (
              <li key={index}>
                <span className={`link-kind link-${link.kind}`}>{linkKind[link.kind]}</span>{' '}
                <a href={safeHref(link.url)} target="_blank" rel="nofollow noopener noreferrer">
                  {link.url} <span aria-hidden="true">↗</span>
                </a>
                {link.kind === 'store' ? (
                  <small>Not a verified seller or price.</small>
                ) : link.followed ? (
                  <small>
                    <span aria-hidden="true">✓</span> Read as a source
                  </small>
                ) : (
                  <small>Not read</small>
                )}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  )
}
