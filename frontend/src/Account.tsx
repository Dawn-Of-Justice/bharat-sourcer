import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { ApiError, getUsage, getSession, startGuest, logoutSession, listProjects, claimProject, type Session, type Project } from './api'
import { firebaseLogout, googleLogin, localPreview } from './auth'

type Identity = Session | 'legacy' | null
const AccountContext = createContext<{ identity: Identity; ready: boolean; revision: number; requireIdentity: () => boolean; open: () => void }>({ identity: null, ready: false, revision: 0, requireIdentity: () => false, open: () => {} })
export const useAccount = () => useContext(AccountContext)

export function AccountProvider({ children }: { children: ReactNode }) {
  const [identity, setIdentity] = useState<Identity>(null)
  const [ready, setReady] = useState(false)
  const [visible, setVisible] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [guestProjects, setGuestProjects] = useState<Project[]>([])
  const [revision, setRevision] = useState(0)
  const [usage, setUsage] = useState<Awaited<ReturnType<typeof getUsage>> | null>(null)
  useEffect(() => {
    let active = true
    setUsage(null)
    if (visible && identity && identity !== 'legacy') getUsage().then(value => { if (active) setUsage(value) }).catch(() => {})
    return () => { active = false }
  }, [visible, identity])
  useEffect(() => {
    let active = true
    getSession().then(value => { if (active) setIdentity(value) }).catch(cause => {
      if (!active) return
      if (cause instanceof ApiError && cause.code === 'AUTH_DISABLED') setIdentity('legacy')
      else if (!(cause instanceof ApiError && cause.status === 401)) setError('Could not check your session. Please retry before starting a project.')
    }).finally(() => { if (active) setReady(true) })
    const recover = () => { setIdentity(null); setError('Your session has ended. Sign in again to reopen your projects.'); setVisible(true) }
    window.addEventListener('bs-signin-required', recover)
    return () => { active = false; window.removeEventListener('bs-signin-required', recover) }
  }, [])
  async function act(action: 'google' | 'guest' | 'logout' | 'retry') {
    setBusy(true); setError('')
    try {
      if (action === 'logout') { try { await logoutSession() } finally { await firebaseLogout(); setIdentity(null); setGuestProjects([]); setRevision(n => n + 1) } setVisible(false); return }
      if (action === 'google') {
        // Capture every guest page before switching identities; claiming remains explicit.
        if (identity && identity !== 'legacy' && identity.kind === 'guest') {
          const collected: Project[] = []; let cursor: string | undefined
          do { const page = await listProjects(cursor); collected.push(...page.projects); cursor = page.next_cursor ?? undefined } while (cursor)
          setGuestProjects(collected)
        }
        await googleLogin()
      }
      const session = action === 'guest' ? await startGuest() : await getSession()
      setIdentity(session); setRevision(n => n + 1); setVisible(false)
    } catch (cause) { setError(cause instanceof ApiError && cause.code === 'AUTH_DISABLED' ? 'Accounts are not enabled on this backend yet. Your current project flow is still available.' : cause instanceof Error ? cause.message : 'Sign-in failed. Please try again.') }
    finally { setBusy(false) }
  }
  const value = { identity, ready, revision, requireIdentity: () => { if (ready && identity) return true; setVisible(true); return false }, open: () => setVisible(true) }
  return <AccountContext.Provider value={value}>{children}
    {guestProjects.length > 0 && identity && identity !== 'legacy' && identity.kind === 'account' && <section className="claim-panel container"><h2>Keep your guest projects</h2><p>Choose which projects to save to this account. This will not run analysis again.</p>{guestProjects.map(project => <div className="claim-row" key={project.job_id}><span>{project.url}</span><button className="nav-cta" disabled={busy} onClick={async () => { setBusy(true); setError(''); try { await claimProject(project.job_id); setGuestProjects(rows => rows.filter(row => row.job_id !== project.job_id)); setRevision(n => n + 1) } catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not save project') } finally { setBusy(false) } }}>Save to my account</button></div>)}{error && <p role="alert">{error}</p>}</section>}
    {visible && <AccountDialog close={() => !busy && setVisible(false)}><span className="section-kicker">YOUR BUILDS, IN ONE PLACE</span><h2>{identity && identity !== 'legacy' ? identity.kind === 'guest' ? 'Make your projects yours.' : 'Your project account' : 'Keep building where you left off.'}</h2><p>Sign in with Google to create your account, keep track of projects, and return to your parts lists and conversations.</p>{localPreview && <p className="demo-alert">Local demo: sign-in is simulated. No Google or backend requests.</p>}{identity === 'legacy' && <p className="demo-alert">Account saving is coming soon. This backend still uses browser-session project access.</p>}{error && <p className="form-error" role="alert">{error}</p>}{usage && <p className="usage-summary">Today: {usage.daily_projects.remaining} of {usage.daily_projects.limit} new projects and {usage.daily_actions.remaining} of {usage.daily_actions.limit} actions remaining. Saved projects stay readable at the limit.</p>}<div className="account-actions"><button className="primary-button" disabled={busy || !ready} onClick={() => void act('google')}>{busy ? 'Please wait…' : localPreview ? 'Try demo account' : 'Continue with Google'}</button>{(!identity || identity === 'legacy') && <button className="nav-cta" disabled={busy || !ready} onClick={() => void act('guest')}>Continue as guest</button>}{identity && identity !== 'legacy' && <button className="nav-cta" disabled={busy} onClick={() => void act('logout')}>Sign out</button>}{error && <button className="nav-cta" disabled={busy} onClick={() => void act('retry')}>Retry session check</button>}</div><p className="account-footnote">Guest access is temporary and has lower usage limits. An account keeps your projects together across visits.</p></AccountDialog>}
  </AccountContext.Provider>
}

function AccountDialog({ children, close }: { children: ReactNode; close: () => void }) {
  const [element, setElement] = useState<HTMLDialogElement | null>(null)
  useEffect(() => { if (element && !element.open) element.showModal(); return () => element?.close() }, [element])
  return <dialog ref={setElement} className="account-dialog" aria-label="Your Bharat Sourcer account" onCancel={event => { event.preventDefault(); close() }}><button className="dialog-close" onClick={close} aria-label="Close account panel">×</button>{children}</dialog>
}

export function Projects({ onOpen, onNew }: { onOpen: (id: string) => void; onNew: () => void }) {
  const { identity, ready, revision, open } = useAccount()
  const [projects, setProjects] = useState<Project[]>([])
  const [cursor, setCursor] = useState<string | null>(null)
  const [busy, setBusy] = useState(true)
  const [error, setError] = useState('')
  const [retry, setRetry] = useState(0)
  useEffect(() => {
    let active = true
    if (!identity || identity === 'legacy') { setBusy(false); return }
    setBusy(true); setError('')
    listProjects().then(page => { if (active) { setProjects(page.projects); setCursor(page.next_cursor) } }).catch(cause => { if (active) setError(cause.message) }).finally(() => { if (active) setBusy(false) })
    return () => { active = false }
  }, [identity, retry, revision])
  return <main id="main" className="projects-page container"><div className="projects-heading"><div><span className="section-kicker">FROM SAVED IDEA TO FINISHED BUILD</span><h1>My projects<span>.</span></h1><p>Your parts lists, progress, and conversations. Ready when you are.</p></div><button className="primary-button" onClick={onNew}>+ New project</button></div>
    {localPreview && <div className="demo-alert">Sample projects · Local demo only · No verified prices or evidence</div>}
    {!ready || busy ? <p role="status">Loading your projects…</p> : !identity || identity === 'legacy' ? <section className="projects-empty"><span className="empty-symbol">↗</span><h2>A home for your next build.</h2><p>{identity === 'legacy' ? 'Saved accounts are not enabled on this backend yet.' : 'Create an account to save projects and pick up where you left off.'}</p><button className="primary-button" onClick={open}>Sign in / Create account</button></section> : <>{identity.kind === 'guest' && <div className="guest-banner"><p>You’re browsing as a guest. Sign in to keep your projects in an account.</p><button className="nav-cta" onClick={open}>Save my projects</button></div>}{error && <div role="alert"><p>{error}</p><button className="nav-cta" onClick={() => setRetry(n => n + 1)}>Retry</button></div>}{!error && !projects.length && <section className="projects-empty"><span className="empty-symbol">+</span><h2>Your first build starts here.</h2><p>Bring a project link. Review the parts, ask questions, and return whenever you’re ready.</p><button className="primary-button" onClick={onNew}>Start a project</button></section>}<div className="project-grid">{projects.map(project => <button className="project-card" key={project.job_id} onClick={() => onOpen(project.job_id)}><div className="project-card-top"><span className="project-icon">↗</span><span className="project-status">{project.status.replaceAll('_', ' ')}</span></div><h2>{localPreview ? 'Sample maker project' : new URL(project.url).hostname + ' project'}</h2><p className="project-source">{project.url}</p><div className="project-meta"><span>{project.part_count} parts</span><span>Updated {new Date(project.updated_at).toLocaleDateString('en-IN')}</span></div><div className="project-open">Open project <span>→</span></div></button>)}</div>{cursor && <button className="nav-cta" disabled={busy} onClick={async () => { setBusy(true); try { const page = await listProjects(cursor); setProjects(rows => [...rows, ...page.projects]); setCursor(page.next_cursor) } catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not load more projects') } finally { setBusy(false) } }}>Load more projects</button>}<p className="account-footnote">Opening a saved project does not run analysis or refresh seller prices.</p></>}
  </main>
}
