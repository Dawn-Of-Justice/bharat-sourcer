import { useEffect, useState } from 'react'
import { acceptCodePatch, ApiError, createCodePatch, downloadCodePatch, getJob, offersOf, type CodePatch, type Job, type ReportLine } from './api'

const unavailableText: Record<NonNullable<CodePatch['reason']>, string> = {
  no_code: 'No project code was available to adapt.',
  file_not_read: 'The project code could not be read right now.',
  no_substitute: 'This offer is not a catalogue substitute.',
  recipe_not_applicable: 'No code recipe applies to this substitute and source file.',
  no_code_change_needed: 'This substitute needs no code edit. Review the notes below.',
  ai_failed_validation: 'The AI draft did not pass the scope and safety checks.',
  out_of_scope_mcu: 'Moving to a different microcontroller needs a separate port.',
  budget: 'The AI draft budget has been used up.',
  source_changed: 'The project source changed. Request a new patch.',
}

function Diff({ diff }: { diff: string }) {
  return <pre className="code-patch-diff">{diff.split('\n').map((line, index) => <span key={index} className={line.startsWith('+') && !line.startsWith('+++') ? 'diff-add' : line.startsWith('-') && !line.startsWith('---') ? 'diff-remove' : line.startsWith('@@') ? 'diff-hunk' : ''}>{line}{'\n'}</span>)}</pre>
}

export default function CodePatchView({ job, line, token, onJob }: { job: Job; line: ReportLine; token: string; onJob: (job: Job) => void }) {
  const selectedOffer = offersOf(line).find(offer => offer.url === line.selected_offer_url)
  const compatibility = selectedOffer?.compatibility
  const isSubstitute = !!compatibility?.required_catalog_id && !!compatibility.offered_catalog_id && compatibility.required_catalog_id !== compatibility.offered_catalog_id
  const [open, setOpen] = useState(false)
  const [patch, setPatch] = useState<CodePatch | null>(line.code_patch ?? null)
  const [busy, setBusy] = useState<'generate' | 'accept' | 'download' | null>(null)
  const [error, setError] = useState('')
  const preview = import.meta.env.DEV && new URLSearchParams(window.location.search).get('preview') === '1'

  useEffect(() => { setPatch(line.code_patch ?? null) }, [line.code_patch?.created_at, line.code_patch?.accepted])
  if (!isSubstitute || !line.selected_offer_url) return null
  const currentPatch = patch?.offer_url === line.selected_offer_url ? patch : null
  const ready = currentPatch?.status === 'ready'

  async function syncJob() {
    try { onJob(await getJob(job.job_id, token)) } catch { /* The patch response remains visible; the job stream will retry. */ }
  }

  async function generate() {
    setBusy('generate'); setError(''); setOpen(true)
    try {
      setPatch(await createCodePatch(job.job_id, token, line.item.line_id, line.selected_offer_url!))
      void syncJob()
    } catch (cause) {
      setError(cause instanceof ApiError && cause.code === 'PROPOSAL_STALE' ? 'The saved offer changed. Reload this project and request a new patch.' : cause instanceof Error ? cause.message : 'Could not prepare code changes.')
    } finally { setBusy(null) }
  }

  async function accept() {
    setBusy('accept'); setError('')
    try { setPatch(await acceptCodePatch(job.job_id, token, line.item.line_id)); void syncJob() }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not accept this draft.') }
    finally { setBusy(null) }
  }

  async function download() {
    setBusy('download'); setError('')
    try {
      const url = URL.createObjectURL(await downloadCodePatch(job.job_id, token, line.item.line_id))
      const link = document.createElement('a')
      link.href = url
      link.download = `code-patch-${line.item.line_id}.zip`
      document.body.append(link)
      link.click()
      link.remove()
      window.setTimeout(() => URL.revokeObjectURL(url), 30000)
    } catch (cause) {
      setError(cause instanceof ApiError && cause.code === 'SOURCE_CHANGED' ? 'The source files changed. Request a new patch before downloading.' : cause instanceof ApiError && cause.code === 'PATCH_NOT_ACCEPTED' ? 'Review and accept the AI draft before downloading.' : cause instanceof Error ? cause.message : 'Could not download the code patch.')
    } finally { setBusy(null) }
  }

  return <section className="code-patch" aria-label={`Code changes for ${line.item.raw_name}`}>
    <button type="button" className="nav-cta" aria-expanded={open} onClick={() => setOpen(value => !value)}>Code changes {currentPatch?.status === 'ready' ? 'available' : ''}</button>
    {open && <div className="code-patch-body">
      <div className="code-patch-heading"><h4>Code changes for this substitute</h4><span className="code-patch-label">Not compiled</span>{ready && <span className="code-patch-label">{currentPatch.origin === 'ai_draft' ? 'AI draft' : 'Curated recipe'}</span>}</div>
      <p>Review the diff and the wiring, power and verification notes before using this substitute.</p>
      {!currentPatch && <p>No patch has been requested for this selected offer.</p>}
      {currentPatch?.status === 'unavailable' && <p role="status"><strong>No code patch available.</strong> {currentPatch.detail || (currentPatch.reason ? unavailableText[currentPatch.reason] : '')}</p>}
      {ready && <>
        {currentPatch.files.map(file => <details className="code-patch-file" key={file.path} open={currentPatch.files.length === 1}><summary>{file.path}</summary><Diff diff={file.diff} /></details>)}
        {!!currentPatch.applied.length && <div className="code-patch-notes"><strong>Applied edits</strong><ul>{currentPatch.applied.map((step, index) => <li key={index}>{step}</li>)}</ul></div>}
        {!!currentPatch.assumptions.length && <div className="code-patch-notes"><strong>Assumptions to check</strong><ul>{currentPatch.assumptions.map((note, index) => <li key={index}>{note}</li>)}</ul></div>}
      </>}
      {!!currentPatch?.skipped.length && <div className="code-patch-notes"><strong>Edits not applied</strong><ul>{currentPatch.skipped.map((step, index) => <li key={index}>{step}</li>)}</ul></div>}
      {!!currentPatch?.notes.length && <div className="code-patch-notes"><strong>Wiring, power and verification</strong><ul>{currentPatch.notes.map((note, index) => <li key={index}>{note}</li>)}</ul></div>}
      {preview && <p className="result-card-note">Dummy preview · sample code only. Actions need a live project.</p>}
      {!preview && <div className="code-patch-actions">
        <button type="button" className="nav-cta" disabled={!!busy} onClick={() => void generate()}>{busy === 'generate' ? 'Preparing…' : currentPatch ? 'Request new patch' : 'Generate code changes'}</button>
        {ready && currentPatch.origin === 'ai_draft' && !currentPatch.accepted && <button type="button" className="nav-cta" disabled={!!busy} onClick={() => void accept()}>{busy === 'accept' ? 'Accepting…' : 'Accept AI draft'}</button>}
        {ready && currentPatch.accepted && <button type="button" className="nav-cta" disabled={!!busy} onClick={() => void download()}>{busy === 'download' ? 'Downloading…' : 'Download ZIP'}</button>}
      </div>}
      {error && <p className="form-error" role="alert">{error}</p>}
    </div>}
  </section>
}
