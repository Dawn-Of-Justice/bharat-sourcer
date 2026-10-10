import { evidenceText, type BomItem, type Evidence, type EvidenceSource, type Job, type SourceReport } from './api'

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
              <a href={entry.url} target="_blank" rel="noopener noreferrer">
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
                      <a href={value.url} target="_blank" rel="noopener noreferrer">
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
                    <a href={value.url} target="_blank" rel="noopener noreferrer">
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

// Warnings only, never suggested substitutes.
export function LookalikeNotes({ item }: { item: BomItem }) {
  if (!item.lookalikes?.length) return null
  return (
    <div className="lookalike-note">
      <span aria-hidden="true">⇄</span>
      <div>
        {item.lookalikes.map((entry, index) => (
          <p key={index}>
            Often confused with <b>{entry.name}</b>
            {entry.origin === 'ai' && <span className="inferred-tag">AI-suggested</span>}
            {entry.note ? ` — ${entry.note}` : ''}
          </p>
        ))}
        <small>Check the exact part before ordering. These are warnings, not substitutes.</small>
      </div>
    </div>
  )
}

const kindLabel: Record<SourceReport['kind'], string> = {
  video: 'YouTube video',
  instructables: 'Instructables project',
  hackster: 'Hackster project',
  github: 'GitHub repository',
  adafruit: 'Adafruit Learn guide',
  blog: 'Tutorial blog',
  youtube_description: 'Video description',
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
  if (!reports.length && !meta) return null
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
                  <a href={report.url} target="_blank" rel="noopener noreferrer">
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
                <a href={link.url} target="_blank" rel="nofollow noopener noreferrer">
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
