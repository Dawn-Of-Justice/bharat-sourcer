import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from 'react'
import {
  ApiError,
  getAccountSettings,
  getCountries,
  saveAccountSettings,
  getSession,
  logoutSession,
  listProjects,
  cachedProjects,
  deleteProject,
  claimProject,
  clearApiCache,
  type Session,
  type Project,
} from './api'
import { currentAuth, firebaseLogout, googleLogin, localPreview } from './auth'
import ProjectCard from './ProjectCard'
import { ProjectsSkeleton } from './Skeleton'
import { useToast } from './toastContext'
import { CountryPicker, fallbackCountries, type CountryOption } from './CountryPicker'

type Identity = Session | 'legacy' | null
const AccountContext = createContext<{
  identity: Identity
  ready: boolean
  revision: number
  country: string
  requireIdentity: () => boolean
  open: () => void
}>({ identity: null, ready: false, revision: 0, country: 'IN', requireIdentity: () => false, open: () => {} })
export const useAccount = () => useContext(AccountContext)

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
  // Delivery country: saved on the account by the backend, which also lists the supported countries.
  const [country, setCountry] = useState('IN')
  const [countryOptions, setCountryOptions] = useState<CountryOption[]>(fallbackCountries)
  const [countryStatus, setCountryStatus] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle')
  const isAccount = !!identity && identity !== 'legacy' && identity.kind === 'account'
  const identityKey = identity && identity !== 'legacy' ? identity.kind + ':' + revision : String(identity)
  // Cached jobs and project lists belong to one identity; drop them whenever it changes.
  useEffect(() => clearApiCache(), [identityKey])
  useEffect(() => {
    let active = true
    // eslint-disable-next-line react-hooks/set-state-in-effect -- resets local state when the effect inputs change; restructuring would change render timing
    setCountryStatus('idle')
    if (!isAccount) {
      setCountry('IN')
      return
    }
    getAccountSettings()
      .then(settings => {
        if (active) setCountry(settings.country)
      })
      .catch(() => {})
    getCountries()
      .then(list => {
        if (active && list.countries.length) setCountryOptions(list.countries)
      })
      .catch(() => {})
    return () => {
      active = false
    }
  }, [isAccount, revision])
  async function chooseCountry(code: string) {
    if (code === country) return
    const previous = country
    setCountry(code)
    setCountryStatus('saving')
    try {
      setCountry((await saveAccountSettings({ country: code })).country)
      setCountryStatus('saved')
    } catch {
      setCountry(previous)
      setCountryStatus('error')
    }
  }
  useEffect(() => {
    let active = true
    if (!visible || !identity || identity === 'legacy' || identity.kind !== 'guest') return
    // eslint-disable-next-line react-hooks/set-state-in-effect -- resets local state when the effect inputs change; restructuring would change render timing
    setCheckingGuestProjects(true)
    setGuestCaptureDone(false)
    setGuestCaptureError('')
    async function capture() {
      const collected: Project[] = []
      let cursor: string | undefined
      do {
        const page = await listProjects(cursor)
        collected.push(...page.projects)
        cursor = page.next_cursor ?? undefined
      } while (cursor)
      if (active) {
        setGuestProjects(collected)
        setGuestCaptureDone(true)
      }
    }
    capture()
      .catch(cause => {
        if (active) setGuestCaptureError(cause instanceof Error ? cause.message : 'Could not load guest projects.')
      })
      .finally(() => {
        if (active) setCheckingGuestProjects(false)
      })
    return () => {
      active = false
    }
  }, [visible, identity, captureAttempt])
  useEffect(() => {
    let active = true
    getSession()
      .then(value => {
        if (active) setIdentity(value)
      })
      .catch(cause => {
        if (!active) return
        if (cause instanceof ApiError && cause.code === 'AUTH_DISABLED') setIdentity('legacy')
        else if (!(cause instanceof ApiError && cause.status === 401 && !currentAuth()?.currentUser)) {
          setError(
            cause instanceof ApiError && cause.status === 503
              ? 'The account service is temporarily unavailable. Your project remains saved. Please try signing in again later.'
              : 'Please sign in with Google to reconnect your account.',
          )
          // Session discovery is passive. Keep errors for the account panel,
          // but let visitors browse without opening a modal on every refresh.
        }
      })
      .finally(() => {
        if (active) setReady(true)
      })
    const recover = () => {
      setIdentity(null)
      setRevision(n => n + 1)
      setError('Your session has ended. Sign in again to reopen your projects.')
      setVisible(true)
    }
    window.addEventListener('bs-signin-required', recover)
    return () => {
      active = false
      window.removeEventListener('bs-signin-required', recover)
    }
  }, [])
  async function act(action: 'google' | 'logout') {
    if (
      action === 'google' &&
      (checkingGuestProjects ||
        guestCaptureError ||
        (identity && identity !== 'legacy' && identity.kind === 'guest' && !guestCaptureDone))
    )
      return
    setBusy(true)
    setError('')
    try {
      if (action === 'logout') {
        try {
          await logoutSession()
        } catch (cause) {
          if (!(cause instanceof ApiError && cause.status === 401)) throw cause
        }
        await firebaseLogout()
        setIdentity(null)
        setGuestProjects([])
        setRevision(n => n + 1)
        setVisible(false)
        return
      }
      if (action === 'google') {
        await googleLogin()
        setIdentity(null)
        setRevision(n => n + 1)
      }
      const session = await getSession()
      setIdentity(session)
      setRevision(n => n + 1)
      setVisible(false)
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 401) {
        setIdentity(null)
        setRevision(n => n + 1)
      }
      setError(
        cause instanceof ApiError && cause.code === 'AUTH_DISABLED'
          ? 'Account access is temporarily unavailable. Please retry later.'
          : cause instanceof ApiError && cause.status === 503
            ? 'The account service is temporarily unavailable. Your project remains saved. Please try signing in again later.'
            : cause instanceof Error
              ? cause.message
              : 'Sign-in failed. Please try again.',
      )
    } finally {
      setBusy(false)
    }
  }
  const value = {
    identity,
    ready,
    revision,
    country,
    requireIdentity: () => {
      if (ready && identity) return true
      setVisible(true)
      return false
    },
    open: () => {
      if (identity && identity !== 'legacy' && identity.kind === 'guest') setGuestCaptureDone(false)
      setVisible(true)
    },
  }
  return (
    <AccountContext.Provider value={value}>
      {children}
      {guestProjects.length > 0 && identity && identity !== 'legacy' && identity.kind === 'account' && (
        <section className="claim-panel container">
          <h2>Keep your guest projects</h2>
          <p>
            Choose which projects to save to this account. The saved parts, research, offers, and conversation will come
            with them.
          </p>
          {guestProjects.map(project => (
            <div className="claim-row" key={project.job_id}>
              <span>{project.url}</span>
              <button
                className="nav-cta"
                disabled={busy}
                onClick={async () => {
                  setBusy(true)
                  setError('')
                  try {
                    await claimProject(project.job_id)
                    setGuestProjects(rows => rows.filter(row => row.job_id !== project.job_id))
                    setRevision(n => n + 1)
                  } catch (cause) {
                    setError(cause instanceof Error ? cause.message : 'Could not save project')
                  } finally {
                    setBusy(false)
                  }
                }}
              >
                Save this project to my account
              </button>
            </div>
          ))}
          {error && <p role="alert">{error}</p>}
        </section>
      )}
      {visible && (
        <AccountDialog close={() => !busy && setVisible(false)}>
          <span className="section-kicker">YOUR BUILDS, IN ONE PLACE</span>
          <h2>
            {identity && identity !== 'legacy'
              ? identity.kind === 'guest'
                ? 'Make your projects yours.'
                : 'Your project account'
              : 'Keep building where you left off.'}
          </h2>
          <p>Sign in with Google to keep track of projects and return to your parts lists and conversations.</p>
          {localPreview && (
            <p className="demo-alert">Local demo: sign-in is simulated. No Google or backend requests.</p>
          )}
          {identity === 'legacy' && (
            <p className="demo-alert">Account access is temporarily unavailable. Please try again later.</p>
          )}
          {error && (
            <p className="form-error" role="alert">
              {error}
            </p>
          )}
          {guestCaptureError && (
            <p className="form-error" role="alert">
              {guestCaptureError} Retry loading your guest projects before signing in so they can be saved to your
              account.
            </p>
          )}
          {isAccount && (
            <div className="country-setting">
              <span className="country-label" id="account-country">
                Country
              </span>
              <CountryPicker
                labelId="account-country"
                options={countryOptions}
                value={country}
                onChange={code => void chooseCountry(code)}
                disabled={countryStatus === 'saving'}
              />
              <p>New projects find sellers that deliver to this country.</p>
              {countryStatus !== 'idle' && (
                <p
                  className={countryStatus === 'error' ? 'form-error' : 'country-status'}
                  role={countryStatus === 'error' ? 'alert' : 'status'}
                >
                  {countryStatus === 'saving'
                    ? 'Saving…'
                    : countryStatus === 'saved'
                      ? '✓ Saved to your account'
                      : 'Could not save the country. Please try again.'}
                </p>
              )}
            </div>
          )}
          <div className="account-actions">
            <button
              className="primary-button"
              disabled={
                busy ||
                !ready ||
                checkingGuestProjects ||
                !!guestCaptureError ||
                !!(identity && identity !== 'legacy' && identity.kind === 'guest' && !guestCaptureDone)
              }
              onClick={() => void act('google')}
            >
              {busy ||
              checkingGuestProjects ||
              (identity && identity !== 'legacy' && identity.kind === 'guest' && !guestCaptureDone)
                ? 'Please wait…'
                : localPreview
                  ? 'Try demo account'
                  : identity && identity !== 'legacy' && identity.kind === 'account'
                    ? 'Switch Google account'
                    : 'Sign in with Google'}
            </button>
            {identity && identity !== 'legacy' && (
              <button className="nav-cta" disabled={busy} onClick={() => void act('logout')}>
                Logout
              </button>
            )}
            {guestCaptureError && (
              <button className="nav-cta" disabled={busy} onClick={() => setCaptureAttempt(n => n + 1)}>
                Retry loading guest projects
              </button>
            )}
          </div>
          <p className="account-footnote">
            Your account keeps your projects, parts lists, and conversations together across visits.
          </p>
        </AccountDialog>
      )}
    </AccountContext.Provider>
  )
}

function AccountDialog({ children, close }: { children: ReactNode; close: () => void }) {
  const [element, setElement] = useState<HTMLDialogElement | null>(null)
  useEffect(() => {
    if (element && !element.open) element.showModal()
    return () => element?.close()
  }, [element])
  return (
    <dialog
      ref={setElement}
      className="account-dialog"
      aria-label="Your Bharat Sourcer account"
      onCancel={event => {
        event.preventDefault()
        close()
      }}
    >
      <button className="dialog-close" onClick={close} aria-label="Close account panel">
        ×
      </button>
      {children}
    </dialog>
  )
}

export function Projects({ onOpen, onNew }: { onOpen: (id: string) => void; onNew: () => void }) {
  const { identity, ready, revision, open } = useAccount()
  const ownerKey = identity && identity !== 'legacy' ? identity.kind + ':' + revision : ''
  const currentOwner = useRef(ownerKey)
  // eslint-disable-next-line react-hooks/refs -- latest owner key, read by loadMore after an await to drop stale pages
  currentOwner.current = ownerKey
  const [loadedOwner, setLoadedOwner] = useState('')
  const [projects, setProjects] = useState<Project[]>([])
  const [cursor, setCursor] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [moreBusy, setMoreBusy] = useState(false)
  const [error, setError] = useState('')
  const [moreError, setMoreError] = useState('')
  const [retry, setRetry] = useState(0)
  const toast = useToast()
  useEffect(() => {
    let active = true
    if (!ownerKey) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- resets local state when the effect inputs change; restructuring would change render timing
      setLoadedOwner('')
      setProjects([])
      setCursor(null)
      return
    }
    setError('')
    setMoreError('')
    // A list prefetched from the header paints at once; a fresh page replaces it when it arrives.
    const cached = retry ? null : cachedProjects()
    if (cached?.value) {
      setProjects(cached.value.projects)
      setCursor(cached.value.next_cursor)
      setLoadedOwner(ownerKey)
    } else setBusy(true)
    ;(cached && !cached.value ? cached.promise : listProjects())
      .then(page => {
        if (!active) return
        setProjects(page.projects)
        setCursor(page.next_cursor)
        setLoadedOwner(ownerKey)
      })
      .catch(cause => {
        if (active) setError(cause instanceof Error ? cause.message : 'Could not load projects.')
      })
      .finally(() => {
        if (active) setBusy(false)
      })
    return () => {
      active = false
    }
  }, [ownerKey, retry])
  // Optimistic delete: the card goes at once and comes back in place if the server refuses.
  async function remove(project: Project) {
    const index = projects.findIndex(row => row.job_id === project.job_id)
    setProjects(rows => rows.filter(row => row.job_id !== project.job_id))
    try {
      await deleteProject(project.job_id)
      try {
        sessionStorage.removeItem(`bharat-sourcer:job:${project.job_id}`)
      } catch {
        /* nothing saved */
      }
      toast('Project deleted')
    } catch (cause) {
      setProjects(rows =>
        rows.some(row => row.job_id === project.job_id)
          ? rows
          : [...rows.slice(0, Math.max(0, index)), project, ...rows.slice(Math.max(0, index))],
      )
      toast(cause instanceof Error ? cause.message : 'Could not delete the project. Please try again.', 'error')
    }
  }
  async function loadMore() {
    if (!cursor || moreBusy) return
    setMoreBusy(true)
    setMoreError('')
    try {
      const page = await listProjects(cursor)
      if (currentOwner.current !== ownerKey) return
      setProjects(rows => {
        const seen = new Set(rows.map(row => row.job_id))
        return [...rows, ...page.projects.filter(row => !seen.has(row.job_id))]
      })
      setCursor(page.next_cursor)
    } catch (cause) {
      setMoreError(cause instanceof Error ? cause.message : 'Could not load more projects.')
    } finally {
      setMoreBusy(false)
    }
  }
  return (
    <main id="main" className="projects-page container">
      <div className="projects-heading">
        <div>
          <span className="section-kicker">FROM SAVED IDEA TO FINISHED BUILD</span>
          <h1>
            My projects<span>.</span>
          </h1>
          <p>Your parts lists, progress, and conversations. Ready when you are.</p>
        </div>
        <button className="primary-button" onClick={onNew}>
          + New project
        </button>
      </div>
      {localPreview && (
        <div className="demo-alert">Sample projects · Local demo only · No verified prices or evidence</div>
      )}
      {!ready || (ownerKey && (busy || loadedOwner !== ownerKey) && !error) ? (
        <ProjectsSkeleton />
      ) : !identity || identity === 'legacy' ? (
        <section className="projects-empty">
          <span className="empty-symbol">↗</span>
          <h2>A home for your next build.</h2>
          <p>
            {identity === 'legacy'
              ? 'Saved projects are temporarily unavailable. Please retry later.'
              : 'Create an account to save projects and pick up where you left off.'}
          </p>
          <button className="primary-button" onClick={open}>
            Sign in / Create account
          </button>
        </section>
      ) : (
        <>
          {identity.kind === 'guest' && (
            <div className="guest-banner">
              <p>You’re browsing as a guest. Sign in to keep your projects in an account.</p>
              <button className="nav-cta" onClick={open}>
                Save my projects
              </button>
            </div>
          )}
          {error && (
            <div role="alert">
              <p>{error}</p>
              <button className="nav-cta" onClick={() => setRetry(n => n + 1)}>
                Retry
              </button>
            </div>
          )}
          {!error && loadedOwner === ownerKey && !projects.length && (
            <section className="projects-empty">
              <span className="empty-symbol">+</span>
              <h2>Your first build starts here.</h2>
              <p>Bring a project link. Review the parts, ask questions, and return whenever you’re ready.</p>
              <button className="primary-button" onClick={onNew}>
                Start a project
              </button>
            </section>
          )}
          {loadedOwner === ownerKey && (
            <>
              <div className="project-grid">
                {projects.map(project => (
                  <ProjectCard
                    key={project.job_id}
                    project={project}
                    onOpen={() => onOpen(project.job_id)}
                    onDelete={() => void remove(project)}
                  />
                ))}
              </div>
              {cursor && (
                <button className="nav-cta" disabled={moreBusy} onClick={() => void loadMore()}>
                  {moreBusy ? 'Loading…' : 'Load more projects'}
                </button>
              )}
              {moreError && (
                <p role="alert">
                  {moreError}{' '}
                  <button className="nav-cta" onClick={() => void loadMore()}>
                    Retry loading more
                  </button>
                </p>
              )}
              <p className="account-footnote">
                Opening a saved project does not run analysis or refresh seller prices.
              </p>
            </>
          )}
        </>
      )}
    </main>
  )
}
