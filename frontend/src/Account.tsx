import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from 'react'
import { ApiError, getAccountSettings, getCountries, saveAccountSettings, getUsage, getSession, startGuest, logoutSession, listProjects, claimProject, type Session, type Project, type UsageWindow } from './api'
import { auth, firebaseLogout, googleLogin, localPreview } from './auth'
import { CountryPicker, fallbackCountries, type CountryOption } from './CountryPicker'

type Identity = Session | 'legacy' | null
const AccountContext = createContext<{ identity: Identity; ready: boolean; revision: number; country: string; requireIdentity: () => boolean; open: () => void }>({ identity: null, ready: false, revision: 0, country: 'IN', requireIdentity: () => false, open: () => {} })
export const useAccount = () => useContext(AccountContext)

function resetTime(window: UsageWindow) {
  return window.resets_at ? new Date(window.resets_at * 1000).toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short' }) : 'the next reset'
}

function projectTitle(project: Project) {
  if (project.title) return project.title
  try { return new URL(project.url).hostname + ' project' } catch { return 'Saved project' }
}

export function AccountProvider({ children }: { children: ReactNode }) {
  const [identity, setIdentity] = useState<Identity>(null)
  const [ready, setReady] = useState(false)
  const [visible, setVisible] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [guestProjects, setGuestProjects] = useState<Project[]>([])
  const [checkingGuestProjects, setCheckingGuestProjects] = useState(false)
  const [guestCaptureDone, setGuestCaptureDone] = useState(false)
  const [guestCaptureError, setGuestCaptureError] = useState('')
  const [captureAttempt, setCaptureAttempt] = useState(0)
  const [revision, setRevision] = useState(0)
  const [usage, setUsage] = useState<Awaited<ReturnType<typeof getUsage>> | null>(null)
  // Delivery country: saved on the account by the backend, which also lists the supported countries.
  const [country, setCountry] = useState('IN')
  const [countryOptions, setCountryOptions] = useState<CountryOption[]>(fallbackCountries)
  const [countryStatus, setCountryStatus] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle')
  const isAccount = !!identity && identity !== 'legacy' && identity.kind === 'account'
  useEffect(() => {
    let active = true
    setCountryStatus('idle')
    if (!isAccount) { setCountry('IN'); return }
    getAccountSettings().then(settings => { if (active) setCountry(settings.country) }).catch(() => {})
    getCountries().then(list => { if (active && list.countries.length) setCountryOptions(list.countries) }).catch(() => {})
    return () => { active = false }
  }, [isAccount, revision])
  async function chooseCountry(code: string) {
    if (code === country) return
    const previous = country
    setCountry(code); setCountryStatus('saving')
    try { setCountry((await saveAccountSettings({ country: code })).country); setCountryStatus('saved') }
    catch { setCountry(previous); setCountryStatus('error') }
  }
  useEffect(() => {
    let active = true
    if (!visible || !identity || identity === 'legacy' || identity.kind !== 'guest') return
    setCheckingGuestProjects(true)
    setGuestCaptureDone(false)
    setGuestCaptureError('')
    async function capture() {
      const collected: Project[] = []; let cursor: string | undefined
      do { const page = await listProjects(cursor); collected.push(...page.projects); cursor = page.next_cursor ?? undefined } while (cursor)
      if (active) { setGuestProjects(collected); setGuestCaptureDone(true) }
    }
    capture().catch(cause => { if (active) setGuestCaptureError(cause instanceof Error ? cause.message : 'Could not load guest projects.') }).finally(() => { if (active) setCheckingGuestProjects(false) })
    return () => { active = false }
  }, [visible, identity, captureAttempt])
  useEffect(() => {
    let active = true
    setUsage(null)
    if (visible && identity && identity !== 'legacy') getUsage().then(value => { if (active) setUsage(value) }).catch(() => {})
    return () => { active = false }
  }, [visible, identity, revision])
  useEffect(() => {
    let active = true
    getSession().then(value => { if (active) setIdentity(value) }).catch(cause => {
      if (!active) return
      if (cause instanceof ApiError && cause.code === 'AUTH_DISABLED') setIdentity('legacy')
      else if (!(cause instanceof ApiError && cause.status === 401 && !auth?.currentUser)) {
        setError(cause instanceof ApiError && cause.status === 503 ? 'The account service is temporarily unavailable. Your project remains saved. Retry the session check.' : 'Your sign-in needs to be checked again. Please retry or sign in.')
        setVisible(true)
      }
    }).finally(() => { if (active) setReady(true) })
    const recover = () => { setIdentity(null); setRevision(n => n + 1); setError('Your session has ended. Sign in again to reopen your projects.'); setVisible(true) }
    window.addEventListener('bs-signin-required', recover)
    return () => { active = false; window.removeEventListener('bs-signin-required', recover) }
  }, [])
  async function act(action: 'google' | 'guest' | 'logout' | 'retry') {
    if (action === 'google' && (checkingGuestProjects || guestCaptureError || (identity && identity !== 'legacy' && identity.kind === 'guest' && !guestCaptureDone))) return
    setBusy(true); setError('')
    try {
      if (action === 'logout') { try { await logoutSession() } catch (cause) { if (!(cause instanceof ApiError && cause.status === 401)) throw cause } await firebaseLogout(); setIdentity(null); setGuestProjects([]); setRevision(n => n + 1); setVisible(false); return }
      if (action === 'google') {
        await googleLogin()
        setIdentity(null)
        setRevision(n => n + 1)
      }
      const session = action === 'guest' ? await startGuest() : await getSession()
      if (action === 'guest') { setGuestProjects([]); setGuestCaptureDone(false) }
      setIdentity(session); setRevision(n => n + 1); setVisible(false)
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 401) { setIdentity(null); setRevision(n => n + 1) }
      setError(cause instanceof ApiError && cause.code === 'AUTH_DISABLED' ? 'Account access is temporarily unavailable. Please retry later.' : cause instanceof ApiError && cause.status === 503 ? 'The account service is temporarily unavailable. Your project remains saved. Retry the session check.' : cause instanceof Error ? cause.message : 'Sign-in failed. Please try again.')
    }
    finally { setBusy(false) }
  }
  const value = { identity, ready, revision, country, requireIdentity: () => { if (ready && identity) return true; setVisible(true); return false }, open: () => { if (identity && identity !== 'legacy' && identity.kind === 'guest') setGuestCaptureDone(false); setVisible(true) } }
  return <AccountContext.Provider value={value}>{children}
    {guestProjects.length > 0 && identity && identity !== 'legacy' && identity.kind === 'account' && <section className="claim-panel container"><h2>Keep your guest projects</h2><p>Choose which projects to save to this account. The saved parts, research, offers, and conversation will come with them.</p>{guestProjects.map(project => <div className="claim-row" key={project.job_id}><span>{project.url}</span><button className="nav-cta" disabled={busy} onClick={async () => { setBusy(true); setError(''); try { await claimProject(project.job_id); setGuestProjects(rows => rows.filter(row => row.job_id !== project.job_id)); setRevision(n => n + 1) } catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not save project') } finally { setBusy(false) } }}>Save this project to my account</button></div>)}{error && <p role="alert">{error}</p>}</section>}
    {visible && <AccountDialog close={() => !busy && setVisible(false)}>
      <span className="section-kicker">YOUR BUILDS, IN ONE PLACE</span>
      <h2>{identity && identity !== 'legacy' ? identity.kind === 'guest' ? 'Make your projects yours.' : 'Your project account' : 'Keep building where you left off.'}</h2>
      <p>Sign in with Google to keep track of projects and return to your parts lists and conversations.</p>
      {localPreview && <p className="demo-alert">Local demo: sign-in is simulated. No Google or backend requests.</p>}
      {identity === 'legacy' && <p className="demo-alert">Account access is temporarily unavailable. Please try again later.</p>}
      {error && <p className="form-error" role="alert">{error}</p>}
      {guestCaptureError && <p className="form-error" role="alert">{guestCaptureError} Retry loading your guest projects before signing in so they can be saved to your account.</p>}
      {usage && <div className="usage-summary">
        <p>New projects: {usage.daily_projects.remaining} of {usage.daily_projects.limit} remaining. Resets {resetTime(usage.daily_projects)}.</p>
        <p>Actions today: {usage.daily_actions.remaining} of {usage.daily_actions.limit} remaining. Resets {resetTime(usage.daily_actions)}.</p>
        <p>Actions this minute: {usage.minute_actions.remaining} of {usage.minute_actions.limit} remaining. Resets {resetTime(usage.minute_actions)}. Saved projects remain readable at the limit.</p>
      </div>}
      {isAccount && <div className="country-setting">
        <span className="country-label" id="account-country">Country</span>
        <CountryPicker labelId="account-country" options={countryOptions} value={country} onChange={code => void chooseCountry(code)} disabled={countryStatus === 'saving'} />
        <p>New projects find sellers that deliver to this country.</p>
        {countryStatus !== 'idle' && <p className={countryStatus === 'error' ? 'form-error' : 'country-status'} role={countryStatus === 'error' ? 'alert' : 'status'}>{countryStatus === 'saving' ? 'Saving…' : countryStatus === 'saved' ? '✓ Saved to your account' : 'Could not save the country. Please try again.'}</p>}
      </div>}
      <div className="account-actions">
        <button className="primary-button" disabled={busy || !ready || checkingGuestProjects || !!guestCaptureError || !!(identity && identity !== 'legacy' && identity.kind === 'guest' && !guestCaptureDone)} onClick={() => void act('google')}>{busy || checkingGuestProjects || (identity && identity !== 'legacy' && identity.kind === 'guest' && !guestCaptureDone) ? 'Please wait…' : localPreview ? 'Try demo account' : identity && identity !== 'legacy' && identity.kind === 'account' ? 'Switch Google account' : 'Sign in with Google'}</button>
        {(!identity || identity === 'legacy') && <button className="nav-cta" disabled={busy || !ready} onClick={() => void act('guest')}>Continue as guest</button>}
        {identity && identity !== 'legacy' && <button className="nav-cta" disabled={busy} onClick={() => void act('logout')}>Logout</button>}
        {guestCaptureError && <button className="nav-cta" disabled={busy} onClick={() => setCaptureAttempt(n => n + 1)}>Retry loading guest projects</button>}
        {error && <button className="nav-cta" disabled={busy} onClick={() => void act('retry')}>Retry session check</button>}
      </div>
      <p className="account-footnote">Guest access is temporary and has lower usage limits. An account keeps your projects together across visits.</p>
    </AccountDialog>}
  </AccountContext.Provider>
}

function AccountDialog({ children, close }: { children: ReactNode; close: () => void }) {
  const [element, setElement] = useState<HTMLDialogElement | null>(null)
  useEffect(() => { if (element && !element.open) element.showModal(); return () => element?.close() }, [element])
  return <dialog ref={setElement} className="account-dialog" aria-label="Your Bharat Sourcer account" onCancel={event => { event.preventDefault(); close() }}><button className="dialog-close" onClick={close} aria-label="Close account panel">×</button>{children}</dialog>
}

export function Projects({ onOpen, onNew }: { onOpen: (id: string) => void; onNew: () => void }) {
  const { identity, ready, revision, open } = useAccount()
  const ownerKey = identity && identity !== 'legacy' ? identity.kind + ':' + revision : ''
  const currentOwner = useRef(ownerKey)
  currentOwner.current = ownerKey
  const [loadedOwner, setLoadedOwner] = useState('')
  const [projects, setProjects] = useState<Project[]>([])
  const [cursor, setCursor] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [moreBusy, setMoreBusy] = useState(false)
  const [error, setError] = useState('')
  const [moreError, setMoreError] = useState('')
  const [retry, setRetry] = useState(0)
  useEffect(() => {
    let active = true
    if (!ownerKey) { setLoadedOwner(''); setProjects([]); setCursor(null); return }
    setBusy(true); setError(''); setMoreError('')
    listProjects().then(page => {
      if (!active) return
      setProjects(page.projects); setCursor(page.next_cursor); setLoadedOwner(ownerKey)
    }).catch(cause => { if (active) setError(cause instanceof Error ? cause.message : 'Could not load projects.') })
      .finally(() => { if (active) setBusy(false) })
    return () => { active = false }
  }, [ownerKey, retry])
  async function loadMore() {
    if (!cursor || moreBusy) return
    setMoreBusy(true); setMoreError('')
    try {
      const page = await listProjects(cursor)
      if (currentOwner.current !== ownerKey) return
      setProjects(rows => { const seen = new Set(rows.map(row => row.job_id)); return [...rows, ...page.projects.filter(row => !seen.has(row.job_id))] })
      setCursor(page.next_cursor)
    } catch (cause) { setMoreError(cause instanceof Error ? cause.message : 'Could not load more projects.') }
    finally { setMoreBusy(false) }
  }
  return <main id="main" className="projects-page container"><div className="projects-heading"><div><span className="section-kicker">FROM SAVED IDEA TO FINISHED BUILD</span><h1>My projects<span>.</span></h1><p>Your parts lists, progress, and conversations. Ready when you are.</p></div><button className="primary-button" onClick={onNew}>+ New project</button></div>
    {localPreview && <div className="demo-alert">Sample projects · Local demo only · No verified prices or evidence</div>}
    {!ready || (ownerKey && (busy || loadedOwner !== ownerKey) && !error) ? <p role="status">Loading your projects…</p> : !identity || identity === 'legacy' ? <section className="projects-empty"><span className="empty-symbol">↗</span><h2>A home for your next build.</h2><p>{identity === 'legacy' ? 'Saved projects are temporarily unavailable. Please retry later.' : 'Create an account to save projects and pick up where you left off.'}</p><button className="primary-button" onClick={open}>Sign in / Create account</button></section> : <>
      {identity.kind === 'guest' && <div className="guest-banner"><p>You’re browsing as a guest. Sign in to keep your projects in an account.</p><button className="nav-cta" onClick={open}>Save my projects</button></div>}
      {error && <div role="alert"><p>{error}</p><button className="nav-cta" onClick={() => setRetry(n => n + 1)}>Retry</button></div>}
      {!error && loadedOwner === ownerKey && !projects.length && <section className="projects-empty"><span className="empty-symbol">+</span><h2>Your first build starts here.</h2><p>Bring a project link. Review the parts, ask questions, and return whenever you’re ready.</p><button className="primary-button" onClick={onNew}>Start a project</button></section>}
        {loadedOwner === ownerKey && <><div className="project-grid">{projects.map(project => <button className="project-card" key={project.job_id} onClick={() => onOpen(project.job_id)}><div className="project-card-top"><span className="project-icon">↗</span><span className="project-status">{project.status.replaceAll('_', ' ')}</span></div><h2>{projectTitle(project)}</h2><p className="project-source">{project.description || project.url}</p>{project.description && <small className="project-url">{project.url}</small>}<div className="project-meta"><span>{project.part_count} parts</span><span>Updated {new Date(project.updated_at).toLocaleDateString('en-IN')}</span></div><div className="project-open">Open project <span>→</span></div></button>)}</div>{cursor && <button className="nav-cta" disabled={moreBusy} onClick={() => void loadMore()}>{moreBusy ? 'Loading…' : 'Load more projects'}</button>}{moreError && <p role="alert">{moreError} <button className="nav-cta" onClick={() => void loadMore()}>Retry loading more</button></p>}<p className="account-footnote">Opening a saved project does not run analysis or refresh seller prices.</p></>}
    </>}
  </main>
}
