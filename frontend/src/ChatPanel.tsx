import { useEffect, useRef, useState, type FormEvent } from 'react'
import { ApiError, decideProposal, evidenceText, getJob, sendMessage, type ActionRecord, type BomItem, type ChatEdit, type ChatMessage, type Job, type PartRequirement, type RefreshLineResult } from './api'
import { ChatIcon } from './LandingIcons'

function findLine(job: Job, lineId: string): BomItem | undefined {
  return job.items.find((item) => item.line_id === lineId)
    ?? job.report?.lines.find((line) => line.item.line_id === lineId)?.item
}

function partLabel(job: Job, lineId: string): string {
  const index = job.items.findIndex(item => item.line_id === lineId)
  return index < 0 ? 'Removed part' : `Part ${index + 1}`
}

function specChanges(specs: Record<string, string | number | boolean | null> | null | undefined) {
  if (!specs) return []
  return Object.entries(specs).map(([field, value]) => {
    const name = field.replaceAll('_', ' ')
    const unit = field.endsWith('_v') ? ' V' : field.endsWith('_mhz') ? ' MHz' : ''
    return value === null ? `clear ${name}` : `${name}: ${String(value)}${unit}`
  })
}

function describeEdit(edit: ChatEdit, job: Job) {
  if (edit.op === 'add') {
    return `Add “${edit.raw_name}” (quantity ${edit.qty})${specChanges(edit.specs).length ? `; ${specChanges(edit.specs).join('; ')}` : ''}.`
  }
  const line = findLine(job, edit.line_id)
  const target = line ? `“${line.raw_name}” (${partLabel(job, edit.line_id)})` : `${partLabel(job, edit.line_id)}`
  if (edit.op === 'remove') return `Remove ${target} from the draft.`
  if (edit.op === 'have_it') return `Mark ${target} as ${edit.user_has_it === false ? 'needed again' : 'already owned'}.`
  const changes: string[] = []
  if (edit.raw_name !== undefined) changes.push(edit.raw_name === null ? 'clear the name' : `rename to “${edit.raw_name}”`)
  if (edit.qty !== undefined) changes.push(edit.qty === null ? 'clear the quantity' : `set quantity to ${edit.qty}`)
  changes.push(...specChanges(edit.specs))
  return `Update ${target}: ${changes.join('; ') || 'review its details'}.`
}

const operatorText: Record<PartRequirement['operator'], string> = { equals: '=', at_least: '≥', at_most: '≤' }

function requirementText(requirement: PartRequirement) {
  return `${requirement.name} ${operatorText[requirement.operator] ?? '='} ${requirement.value}${requirement.unit ? ` ${requirement.unit}` : ''}`
}

function lineName(job: Job, lineId: string) {
  const line = findLine(job, lineId)
  return line ? `“${line.raw_name}” (${partLabel(job, lineId)})` : partLabel(job, lineId)
}

function messageTime(value: string | undefined) {
  return value ? new Date(value).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' }) : ''
}

function scrollToMessage(messageId: string) {
  document.getElementById(`chat-msg-${messageId}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' })
}

// Shared 409 handling for report-level proposals: stale or already decided, then reload the job.
function decisionError(cause: unknown) {
  if (cause instanceof ApiError && cause.code === 'PROPOSAL_DECIDED') return 'This proposal was already decided. Showing the latest saved state.'
  if (cause instanceof ApiError && cause.status === 409) return 'This proposal is stale because the report changed. Review the latest report and ask for a new proposal.'
  return cause instanceof Error ? cause.message : 'Could not save this decision.'
}

function Citation({ job, lineId }: { job: Job; lineId: string }) {
  const line = findLine(job, lineId)
  return <details className="chat-citation"><summary>{line ? `${partLabel(job, lineId)} · ${line.raw_name}` : `Removed part · no longer in this BOM`}</summary><div className="citation-detail">{line?.evidence.length ? <><strong>Saved evidence</strong><ul>{line.evidence.map((entry, index) => <li key={index}>{evidenceText(entry)}</li>)}</ul><small>These observations were reported by the extraction model and need your review.</small></> : <p>No saved evidence is available for this line.</p>}{line ? <button type="button" onClick={() => { const target = document.getElementById(`line-${lineId}`); if (target instanceof HTMLDetailsElement) target.open = true; target?.scrollIntoView({ behavior: 'smooth', block: 'center' }) }}>View in BOM ↑</button> : null}</div></details>
}

function Proposal({ job, message, token, onJob }: { job: Job; message: ChatMessage; token: string; onJob: (job: Job) => void }) {
  const proposal = message.proposal
  const [busyAction, setBusyAction] = useState<'accept' | 'reject' | null>(null)
  const [error, setError] = useState('')
  const [stale, setStale] = useState(false)
  if (!proposal) return null

  async function decide(action: 'accept' | 'reject') {
    setBusyAction(action)
    setError('')
    try {
      onJob(await decideProposal(job.job_id, token, message.message_id, action))
    } catch (cause) {
      if (cause instanceof ApiError && (cause.status === 409 || cause.status === 422)) {
        setStale(true)
        setError('This proposal could not be applied to the current draft. Review the latest BOM and ask for a new proposal.')
        try {
          onJob(await getJob(job.job_id, token))
        } catch { /* The normal job watcher will retry. */ }
      } else {
        setError(cause instanceof Error ? cause.message : 'Could not save this decision. Try the same action again.')
      }
    } finally {
      setBusyAction(null)
    }
  }

  return <div className="chat-proposal"><div className="proposal-heading"><strong>Proposed BOM edits</strong><span className={`proposal-status ${proposal.status}`}>{proposal.status}</span></div><ul>{proposal.edits.map((edit, index) => <li key={`${edit.op}-${index}`}>{describeEdit(edit, job)}</li>)}</ul>{proposal.status === 'pending' ? <><p>Accepting updates the saved draft only. Any unsubmitted changes in the editor will reset. Use “Confirm BOM and find offers” separately when you are ready.</p><div className="proposal-actions"><button type="button" className="accept-button" disabled={busyAction !== null || job.status !== 'awaiting_confirmation' || stale} onClick={() => void decide('accept')}>{busyAction === 'accept' ? 'Applying…' : 'Accept edits'}</button><button type="button" className="reject-button" disabled={busyAction !== null} onClick={() => void decide('reject')}>{busyAction === 'reject' ? 'Rejecting…' : 'Reject'}</button></div>{job.status !== 'awaiting_confirmation' ? <small>Draft edits are available only before BOM confirmation.</small> : null}</> : <p>{proposal.status === 'accepted' ? 'Accepted. The saved draft now reflects these edits.' : 'Rejected. The draft was not changed.'}</p>}{error ? <p className="chat-action-error" role="alert">{error}</p> : null}</div>
}

function RefreshProposal({ job, message, token, onJob }: { job: Job; message: ChatMessage; token: string; onJob: (job: Job) => void }) {
  const proposal = message.refresh_proposal
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  if (!proposal) return null
  const names = proposal.request.line_ids.map(id => findLine(job, id)?.raw_name ?? id)
  async function decide(action: 'accept' | 'reject') {
    setBusy(true)
    setError('')
    try { onJob(await decideProposal(job.job_id, token, message.message_id, action)) }
    catch (cause) {
      setError(decisionError(cause))
      if (cause instanceof ApiError && cause.status === 409) {
        try { onJob(await getJob(job.job_id, token)) } catch { /* Polling will retry. */ }
      }
    } finally { setBusy(false) }
  }
  return <div className="chat-proposal"><div className="proposal-heading"><strong>Proposed seller refresh</strong><span className={`proposal-status ${proposal.status}`}>{proposal.status}</span></div><p>Parts: {names.join(', ')}.</p>{proposal.status === 'pending' ? <><p>Approving starts a new seller search, may use paid analysis, clears these parts’ old quotes and selections, and uses one of two refresh batches. It does not purchase anything.</p><div className="proposal-actions"><button className="accept-button" disabled={busy || job.status !== 'done'} onClick={() => void decide('accept')}>Approve search</button><button className="reject-button" disabled={busy} onClick={() => void decide('reject')}>Reject</button></div></> : <p>{proposal.status === 'accepted' ? (proposal.result_message_id ? 'Search approved; the batch has finished. Current quotes are in the report.' : 'Search approved and queued. Results appear in the report.') : 'Search rejected; saved offers were kept.'}</p>}{proposal.result_message_id ? <div className="citation-detail"><button type="button" onClick={() => scrollToMessage(proposal.result_message_id!)}>View refresh results ↓</button></div> : null}{error && <p className="chat-action-error" role="alert">{error}</p>}</div>
}

function SpecProposal({ job, message, token, onJob }: { job: Job; message: ChatMessage; token: string; onJob: (job: Job) => void }) {
  const proposal = message.spec_proposal
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  if (!proposal) return null
  async function decide(action: 'accept' | 'reject') {
    setBusy(true)
    setError('')
    try { onJob(await decideProposal(job.job_id, token, message.message_id, action)) }
    catch (cause) {
      setError(decisionError(cause))
      if (cause instanceof ApiError && cause.status === 409) {
        try { onJob(await getJob(job.job_id, token)) } catch { /* Polling will retry. */ }
      }
    } finally { setBusy(false) }
  }
  return <div className="chat-proposal"><div className="proposal-heading"><strong>Proposed spec changes</strong><span className={`proposal-status ${proposal.status}`}>{proposal.status}</span></div><ul>{proposal.request.updates.map(update => {
    const changes = specChanges(update.specs)
    if (update.requirements) changes.push(update.requirements.length ? `build details: ${update.requirements.map(requirementText).join('; ')}` : 'clear build details')
    return <li key={update.line_id}>{lineName(job, update.line_id)}: {changes.join('; ') || 'no changes'}.</li>
  })}</ul>{proposal.status === 'pending' ? <><p>Values come from what you said in chat. Approving saves them, re-checks saved quotes for these parts against the new specs, clears these parts’ selections and marks their AI research as stale. Nothing is searched or charged.</p><div className="proposal-actions"><button type="button" className="accept-button" disabled={busy || job.status !== 'done'} onClick={() => void decide('accept')}>Approve specs</button><button type="button" className="reject-button" disabled={busy} onClick={() => void decide('reject')}>Reject</button></div>{job.status !== 'done' ? <small>Spec changes can be approved once the report is complete.</small> : null}</> : <p>{proposal.status === 'accepted' ? 'Approved. Saved specs were updated and these parts’ quotes were re-checked; choose offers again in the report.' : 'Rejected. Specs and selections were not changed.'}</p>}{error && <p className="chat-action-error" role="alert">{error}</p>}</div>
}

const refreshStatusText: Record<RefreshLineResult['sourcing_status'], string> = { offers_found: 'offers found', no_verified_offers: 'no verified offers', failed: 'search failed', already_owned: 'already owned', not_run: 'not run' }
const inr = new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR' })

function RefreshResults({ job, message }: { job: Job; message: ChatMessage }) {
  const results = message.refresh_results ?? []
  if (!results.length) return null
  const origin = message.completes_message_id ? job.messages.find(entry => entry.message_id === message.completes_message_id) : undefined
  return <div className="chat-proposal"><div className="proposal-heading"><strong>Seller refresh results</strong><span className="proposal-status accepted">snapshot</span></div><ul>{results.map(result => <li key={result.line_id}>{lineName(job, result.line_id)}: {refreshStatusText[result.sourcing_status] ?? result.sourcing_status}{result.sourcing_status === 'offers_found' || result.offer_count ? ` · ${result.offer_count ?? 0} offer${result.offer_count === 1 ? '' : 's'}` : ''}{result.lowest_listed_price_inr ? ` · lowest ${inr.format(Number(result.lowest_listed_price_inr))} (seller-listed, not a verified total)${result.lowest_listed_stock ? `, stock: ${result.lowest_listed_stock.replaceAll('_', ' ')}` : ''}` : ''}{result.error_code ? ` · ${result.error_code}` : ''}</li>)}</ul><p>Snapshot when the approved batch ended. Tax, shipping and final payable totals are not known; select offers in the report.</p>{message.completes_message_id ? <div className="citation-detail">{origin ? <button type="button" onClick={() => scrollToMessage(origin.message_id)}>Completes the refresh proposal from {messageTime(origin.created_at)} ↑</button> : <small>Completes an earlier refresh proposal.</small>}</div> : null}</div>
}

const actionKindText: Record<ActionRecord['kind'], string> = { edit: 'BOM edit', refresh: 'Seller refresh', spec_update: 'Spec update' }

function ActionHistory({ actions }: { actions: ActionRecord[] }) {
  if (!actions.length) return null
  const newest = [...actions].reverse()
  return <details className="chat-citation chat-action-history"><summary>Action history ({actions.length})</summary><div className="citation-detail"><ul>{newest.map((action, index) => <li key={`${action.message_id}-${action.status}-${index}`}><strong>{actionKindText[action.kind] ?? action.kind}</strong> · {action.status}{action.created_at ? ` · ${new Date(action.created_at).toLocaleString('en-IN', { dateStyle: 'short', timeStyle: 'short' })}` : ''}{action.summary ? <><br />{action.summary}</> : null}</li>)}</ul><small>Decisions only; the report shows current quotes.</small></div></details>
}

export default function ChatPanel({ job, token, onJob }: { job: Job; token: string; onJob: (job: Job) => void }) {
  const historyRef = useRef<HTMLDivElement>(null)
  const openedRef = useRef(false)
  const [text, setText] = useState('')
  const [pendingSend, setPendingSend] = useState<{ id: string; text: string } | null>(null)
  const [sending, setSending] = useState(false)
  const [sendError, setSendError] = useState('')
  const busy = job.chat_state === 'queued' || job.chat_state === 'thinking'
  const turns = job.messages.filter((message) => message.role === 'user').length
  const latestMessage = job.messages.at(-1)

  useEffect(() => {
    const frame = requestAnimationFrame(() => {
      const history = historyRef.current
      const smooth = openedRef.current && !window.matchMedia('(prefers-reduced-motion: reduce)').matches
      history?.scrollTo({ top: history.scrollHeight, behavior: smooth ? 'smooth' : 'instant' })
      openedRef.current = true
    })
    return () => cancelAnimationFrame(frame)
  }, [latestMessage?.message_id, latestMessage?.text, busy])

  useEffect(() => {
    if (pendingSend && job.messages.some((message) => message.message_id === pendingSend.id)) {
      setPendingSend(null)
      setText((current) => current.trim() === pendingSend.text ? '' : current)
      setSendError('')
    }
  }, [job.messages, pendingSend])

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const content = text.trim()
    if (!content || busy || sending || turns >= 20) return
    const attempt = pendingSend?.text === content ? pendingSend : { id: crypto.randomUUID(), text: content }
    setPendingSend(attempt)
    setSending(true)
    setSendError('')
    try {
      onJob(await sendMessage(job.job_id, token, attempt.id, content))
      setText('')
      setPendingSend(null)
    } catch (cause) {
      setSendError(cause instanceof Error ? `${cause.message} Retry to reuse this message ID.` : 'Could not send. Retry to reuse this message ID.')
    } finally {
      setSending(false)
    }
  }

  return <aside className="chat-panel" aria-labelledby="chat-title"><div className="chat-heading"><div><span className="section-kicker">ASK ABOUT THIS BUILD</span><h2 id="chat-title">Build conversation</h2></div><span className="chat-icon"><ChatIcon /></span></div><p className="chat-intro">Ask about saved parts and evidence. Suggestions to change the BOM always need your approval.</p>{job.demo ? <div className="chat-demo">Demo conversation · replies use a fixed sample response.</div> : null}<div ref={historyRef} className="chat-history" role="log" aria-live="polite" aria-relevant="additions text">{!job.messages.length ? <div className="chat-empty"><span aria-hidden="true">✦</span><strong>A good place to ask “why?”</strong><p>Try “What does this board do?” or “Which parts still need checking?”</p></div> : job.messages.map((message) => <article id={`chat-msg-${message.message_id}`} className={`chat-message ${message.role}`} key={message.message_id}><div className="message-meta"><strong>{message.role === 'user' ? 'You' : 'Bharat Sourcer'}</strong><time>{new Date(message.created_at).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' })}</time></div><p>{message.text}</p>{message.cited_line_ids.length ? <div className="chat-citations"><span>Parts mentioned</span>{message.cited_line_ids.map((id) => <Citation key={id} job={job} lineId={id} />)}</div> : null}{message.proposal ? <Proposal job={job} message={message} token={token} onJob={onJob} /> : null}{message.refresh_proposal ? <RefreshProposal job={job} message={message} token={token} onJob={onJob} /> : null}{message.spec_proposal ? <SpecProposal job={job} message={message} token={token} onJob={onJob} /> : null}{message.refresh_results?.length ? <RefreshResults job={job} message={message} /> : null}{message.resistor_question ? <div className="chat-proposal"><strong>Design detail needed for {findLine(job, message.resistor_question.line_id)?.raw_name ?? partLabel(job, message.resistor_question.line_id)}</strong><p>{message.resistor_question.question}</p><small>This question is a model suggestion, not video evidence. Confirm circuit details before using any calculation.</small></div> : null}</article>)}{busy ? <div className="chat-waiting" role="status"><span className="loading-indicator" />{job.chat_state === 'queued' ? 'Question queued…' : 'Thinking through saved project details…'}</div> : null}</div><ActionHistory actions={job.actions ?? []} />{job.chat_state === 'failed' ? <p className="chat-failure" role="alert">{job.chat_error?.message || 'The reply failed. Send a new message to try again.'}</p> : null}<form className="chat-compose" onSubmit={submit}><label htmlFor="chat-message">Your question</label><textarea id="chat-message" rows={3} maxLength={4000} placeholder="Ask about a part, the evidence, or a possible change…" value={text} onChange={(event) => { setText(event.target.value); setPendingSend(null); setSendError('') }} disabled={turns >= 20} /><div className="chat-compose-bottom"><span>{turns}/20 questions</span><button type="submit" disabled={!text.trim() || busy || sending || turns >= 20}>{sending ? 'Sending…' : pendingSend ? 'Retry send' : 'Send question'} <span aria-hidden="true">↗</span></button></div>{turns >= 20 ? <p>Conversation limit reached for this job.</p> : null}{sendError ? <p className="chat-action-error" role="alert">{sendError}</p> : null}</form></aside>
}
