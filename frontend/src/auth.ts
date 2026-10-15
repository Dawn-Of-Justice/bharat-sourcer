import type { Auth } from 'firebase/auth'

export const localPreview = import.meta.env.DEV && new URLSearchParams(location.search).get('preview') === '1'
const runtime = (
  window as Window & {
    __BS_FIREBASE_CONFIG?: { apiKey?: string; authDomain?: string; projectId?: string; appId?: string }
  }
).__BS_FIREBASE_CONFIG
const config = runtime ?? {
  apiKey: import.meta.env.VITE_FIREBASE_API_KEY,
  authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN,
  projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID,
  appId: import.meta.env.VITE_FIREBASE_APP_ID,
}
const configured = !localPreview && Boolean(config.apiKey && config.authDomain && config.projectId && config.appId)

// The Firebase SDK is about a third of the app's JavaScript, so it is a separate chunk: the
// page renders without waiting for it, and everything that needs sign-in state awaits it.
type Firebase = { sdk: typeof import('./firebase'); auth: Auth }
let firebase: Firebase | null = null
let pending: Promise<Firebase | null> | null = null
function loadFirebase(): Promise<Firebase | null> {
  if (!configured) return Promise.resolve(null)
  return (pending ??= import('./firebase').then(
    sdk => (firebase = { sdk, auth: sdk.connect(config) }),
    cause => {
      // A failed chunk download is retried by the next caller.
      pending = null
      throw cause
    },
  ))
}
// Start the download at once: the first API call needs the signed-in user.
if (configured) void loadFirebase().catch(() => undefined)

export const loadAuth = async () => (await loadFirebase())?.auth ?? null
// The Auth instance once loaded; null before then or when accounts are not configured.
export const currentAuth = () => firebase?.auth ?? null

export async function identityToken() {
  const auth = await loadAuth()
  if (!auth) return null
  await auth.authStateReady()
  return auth.currentUser?.getIdToken() ?? null
}
export async function googleLogin() {
  if (localPreview) {
    sessionStorage.setItem('bs-preview-account', 'account')
    return
  }
  // Already loaded at start-up, so the popup still opens directly from the click.
  const loaded = firebase ?? (configured ? await loadFirebase() : null)
  if (!loaded) throw new Error('Google sign-in is not configured yet. Please try again when accounts are enabled.')
  const provider = new loaded.sdk.GoogleAuthProvider()
  provider.setCustomParameters({ prompt: 'select_account' })
  await loaded.sdk.signInWithPopup(loaded.auth, provider)
}
export async function firebaseLogout() {
  if (localPreview) sessionStorage.removeItem('bs-preview-account')
  const loaded = await loadFirebase()
  if (loaded) await loaded.sdk.signOut(loaded.auth)
}
