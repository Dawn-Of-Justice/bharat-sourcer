import { useEffect, useState } from 'react'
import {
  acceptCodePatch,
  ApiError,
  createCodePatch,
  downloadCodePatch,
  getCompileBoards,
  getJob,
  offersOf,
  requestCompile,
  type CodePatch,
  type CompileBoards,
  type CompileCheck,
  type Job,
  type ReportLine,
} from './api'

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

const compileUnavailableText: Record<NonNullable<CompileCheck['reason']>, string> = {
  source_changed: 'The project source changed since this patch was made. Request a new patch.',
  source_unavailable: 'The project repository could not be downloaded for compiling.',
  sketch_not_found: 'No Arduino sketch (.ino) containing this change was found.',
  platformio_not_supported: 'PlatformIO projects are not compiled, because their build scripts run project code.',
  too_large: 'The project is too large to compile here.',
  launch_failed: 'The compile runner could not be started. Try again later.',
  runner_error: 'The compile runner failed.',
}

// A queued check past expires_at has stopped; the backend lets the owner request it again.
const isWaiting = (check?: CompileCheck | null) =>
  check?.status === 'queued' && Date.parse(check.expires_at) > Date.now()

function CompileResult({ patch }: { patch: CodePatch }) {
  const check = patch.compile
  if (!check) return null
  const round = check.repairs ? ` (AI repair round ${check.repairs})` : ''
  return (
    <div className={`compile-result compile-${check.status}`} role="status">
      {check.status === 'queued' &&
        (isWaiting(check) ? (
          <p>
            <strong>
              Compiling for {check.board}
              {round}…
            </strong>{' '}
            This usually takes 1–3 minutes.
          </p>
        ) : (
          <p>
            <strong>The compile check for {check.board} did not finish.</strong> Try again.
          </p>
        ))}
      {check.status === 'compiles' && (
        <>
          <p>
            <strong>Compiles for {check.board}</strong>
            {check.core ? ` with ${check.core}` : ''}. Compile only: not tested on hardware.
          </p>
          {check.size && <p className="compile-size">{check.size}</p>}
        </>
      )}
      {check.status === 'compile_failed' && (
        <>
          <p>
            <strong>Did not compile for {check.board}.</strong>
            {check.log ? ' Compiler output:' : ''}
          </p>
          {check.log && <pre className="compile-log">{check.log}</pre>}
        </>
      )}
      {check.status === 'timeout' && (
        <p>
          <strong>The compile check for {check.board} timed out.</strong> Try again.
        </p>
      )}
      {check.status === 'unavailable' && (
        <p>
          <strong>Could not compile.</strong>{' '}
          {check.detail || (check.reason ? compileUnavailableText[check.reason] : '')}
        </p>
      )}
      {patch.origin === 'ai_draft' && check.repairs > 0 && !patch.accepted && (
        <p>The AI revised this draft after compiler errors. Review the new diff and accept it again.</p>
      )}
    </div>
  )
}

function Diff({ diff }: { diff: string }) {
  return (
    <pre className="code-patch-diff">
      {diff.split('\n').map((line, index) => (
        <span
          key={index}
          className={
            line.startsWith('+') && !line.startsWith('+++')
              ? 'diff-add'
              : line.startsWith('-') && !line.startsWith('---')
                ? 'diff-remove'
                : line.startsWith('@@')
                  ? 'diff-hunk'
                  : ''
          }
        >
          {line}
          {'\n'}
        </span>
      ))}
    </pre>
  )
}

export default function CodePatchView({
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
  const selectedOffer = offersOf(line).find(offer => offer.url === line.selected_offer_url)
  const compatibility = selectedOffer?.compatibility
  const isSubstitute =
    !!compatibility?.required_catalog_id &&
    !!compatibility.offered_catalog_id &&
    compatibility.required_catalog_id !== compatibility.offered_catalog_id
  const [open, setOpen] = useState(false)
  const [patch, setPatch] = useState<CodePatch | null>(line.code_patch ?? null)
  const [busy, setBusy] = useState<'generate' | 'accept' | 'download' | 'compile' | null>(null)
  const [error, setError] = useState('')
  const [boards, setBoards] = useState<CompileBoards | null>(null)
  const [fqbn, setFqbn] = useState(line.code_patch?.compile?.fqbn ?? '')
  const [needBoard, setNeedBoard] = useState(false)
  const preview = import.meta.env.DEV && new URLSearchParams(window.location.search).get('preview') === '1'
  const saved = line.code_patch
  const currentPatch = patch?.offer_url === line.selected_offer_url ? patch : null
  const ready = currentPatch?.status === 'ready'
  const waiting = isWaiting(currentPatch?.compile)

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- resyncs the local patch when the saved patch changes
    setPatch(line.code_patch ?? null)
    // eslint-disable-next-line react-hooks/exhaustive-deps -- resync only when these saved-patch fields change, not on every new line object
  }, [saved?.created_at, saved?.accepted, saved?.check, saved?.compile?.run_id, saved?.compile?.status])
  useEffect(() => {
    if (!open || preview || boards) return
    getCompileBoards()
      .then(setBoards)
      .catch(() => setBoards({ enabled: false, boards: [] }))
  }, [open, preview, boards])
  // The runner reports to the backend, not to this page: poll the job until the check settles.
  useEffect(() => {
    if (!waiting) return
    const timer = window.setInterval(() => void syncJob(), 8000)
    return () => window.clearInterval(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps -- syncJob is recreated every render; the interval restarts only for a new run
  }, [waiting, currentPatch?.compile?.run_id])
  if (!isSubstitute || !line.selected_offer_url) return null
  const compiled = ready && currentPatch.check === 'compiles'
  const failed = ready && currentPatch.check === 'compile_failed'
  const checkLabel = compiled
    ? `Compiles for ${currentPatch.compile?.board ?? 'the board'}`
    : failed
      ? 'Did not compile'
      : 'Not compiled'

  async function syncJob() {
    try {
      onJob(await getJob(job.job_id, token))
    } catch {
      /* The patch response remains visible; the job stream will retry. */
    }
  }

  async function generate() {
    setBusy('generate')
    setError('')
    setOpen(true)
    try {
      setPatch(await createCodePatch(job.job_id, token, line.item.line_id, line.selected_offer_url!))
      void syncJob()
    } catch (cause) {
      setError(
        cause instanceof ApiError && cause.code === 'PROPOSAL_STALE'
          ? 'The saved offer changed. Reload this project and request a new patch.'
          : cause instanceof Error
            ? cause.message
            : 'Could not prepare code changes.',
      )
    } finally {
      setBusy(null)
    }
  }

  async function accept() {
    setBusy('accept')
    setError('')
    try {
      setPatch(await acceptCodePatch(job.job_id, token, line.item.line_id))
      void syncJob()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not accept this draft.')
    } finally {
      setBusy(null)
    }
  }

  async function compile() {
    setBusy('compile')
    setError('')
    setNeedBoard(false)
    try {
      setPatch(await requestCompile(job.job_id, token, line.item.line_id, fqbn || undefined))
      void syncJob()
    } catch (cause) {
      const code = cause instanceof ApiError ? cause.code : undefined
      if (code === 'FQBN_REQUIRED') {
        setNeedBoard(true)
        setError('Choose the board this project uses, then check again.')
      } else if (code === 'COMPILE_IN_PROGRESS') {
        setError('A compile check is already running.')
        void syncJob()
      } else if (code === 'PROPOSAL_STALE') setError('The patch changed. Reload this project and try again.')
      else setError(cause instanceof Error ? cause.message : 'Could not start the compile check.')
    } finally {
      setBusy(null)
    }
  }

  async function download() {
    setBusy('download')
    setError('')
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
      setError(
        cause instanceof ApiError && cause.code === 'SOURCE_CHANGED'
          ? 'The source files changed. Request a new patch before downloading.'
          : cause instanceof ApiError && cause.code === 'PATCH_NOT_ACCEPTED'
            ? 'Review and accept the AI draft before downloading.'
            : cause instanceof Error
              ? cause.message
              : 'Could not download the code patch.',
      )
    } finally {
      setBusy(null)
    }
  }

  return (
    <section className="code-patch" aria-label={`Code changes for ${line.item.raw_name}`}>
      <button type="button" className="nav-cta" aria-expanded={open} onClick={() => setOpen(value => !value)}>
        Code changes {currentPatch?.status === 'ready' ? 'available' : ''}
      </button>
      {open && (
        <div className="code-patch-body">
          <div className="code-patch-heading">
            <h4>Code changes for this substitute</h4>
            <span className={`code-patch-label${compiled ? ' label-ok' : failed ? ' label-warn' : ''}`}>
              {checkLabel}
            </span>
            {ready && (
              <span className="code-patch-label">
                {currentPatch.origin === 'ai_draft' ? 'AI draft' : 'Curated recipe'}
              </span>
            )}
          </div>
          <p>Review the diff and the wiring, power and verification notes before using this substitute.</p>
          {!currentPatch && <p>No patch has been requested for this selected offer.</p>}
          {currentPatch?.status === 'unavailable' && (
            <p role="status">
              <strong>No code patch available.</strong>{' '}
              {currentPatch.detail || (currentPatch.reason ? unavailableText[currentPatch.reason] : '')}
            </p>
          )}
          {ready && (
            <>
              {currentPatch.files.map(file => (
                <details className="code-patch-file" key={file.path} open={currentPatch.files.length === 1}>
                  <summary>{file.path}</summary>
                  <Diff diff={file.diff} />
                </details>
              ))}
              {!!currentPatch.applied.length && (
                <div className="code-patch-notes">
                  <strong>Applied edits</strong>
                  <ul>
                    {currentPatch.applied.map((step, index) => (
                      <li key={index}>{step}</li>
                    ))}
                  </ul>
                </div>
              )}
              {!!currentPatch.assumptions.length && (
                <div className="code-patch-notes">
                  <strong>Assumptions to check</strong>
                  <ul>
                    {currentPatch.assumptions.map((note, index) => (
                      <li key={index}>{note}</li>
                    ))}
                  </ul>
                </div>
              )}
              <CompileResult patch={currentPatch} />
            </>
          )}
          {!!currentPatch?.skipped.length && (
            <div className="code-patch-notes">
              <strong>Edits not applied</strong>
              <ul>
                {currentPatch.skipped.map((step, index) => (
                  <li key={index}>{step}</li>
                ))}
              </ul>
            </div>
          )}
          {!!currentPatch?.notes.length && (
            <div className="code-patch-notes">
              <strong>Wiring, power and verification</strong>
              <ul>
                {currentPatch.notes.map((note, index) => (
                  <li key={index}>{note}</li>
                ))}
              </ul>
            </div>
          )}
          {preview && (
            <p className="result-card-note">Dummy preview · sample code only. Actions need a live project.</p>
          )}
          {!preview && (
            <div className="code-patch-actions">
              <button type="button" className="nav-cta" disabled={!!busy || waiting} onClick={() => void generate()}>
                {busy === 'generate' ? 'Preparing…' : currentPatch ? 'Request new patch' : 'Generate code changes'}
              </button>
              {ready && currentPatch.origin === 'ai_draft' && !currentPatch.accepted && (
                <button type="button" className="nav-cta" disabled={!!busy || waiting} onClick={() => void accept()}>
                  {busy === 'accept' ? 'Accepting…' : 'Accept AI draft'}
                </button>
              )}
              {ready && currentPatch.accepted && (
                <button type="button" className="nav-cta" disabled={!!busy} onClick={() => void download()}>
                  {busy === 'download' ? 'Downloading…' : 'Download ZIP'}
                </button>
              )}
            </div>
          )}
          {!preview && ready && boards?.enabled && (
            <div className="code-patch-actions compile-actions">
              <label className={needBoard ? 'compile-board needs-board' : 'compile-board'}>
                Board{' '}
                <select
                  value={fqbn}
                  disabled={!!busy || waiting}
                  aria-invalid={needBoard}
                  onChange={event => {
                    setFqbn(event.target.value)
                    setNeedBoard(false)
                  }}
                >
                  <option value="">From the parts list</option>
                  {boards.boards.map(board => (
                    <option key={board.fqbn} value={board.fqbn}>
                      {board.label}
                    </option>
                  ))}
                </select>
              </label>
              <button type="button" className="nav-cta" disabled={!!busy || waiting} onClick={() => void compile()}>
                {busy === 'compile'
                  ? 'Starting…'
                  : waiting
                    ? 'Compiling…'
                    : currentPatch.compile
                      ? 'Compile again'
                      : 'Check it compiles'}
              </button>
            </div>
          )}
          {error && (
            <p className="form-error" role="alert">
              {error}
            </p>
          )}
        </div>
      )}
    </section>
  )
}
