import { initializeApp } from 'firebase/app'
import { getAuth, GoogleAuthProvider, signInWithPopup, signOut } from 'firebase/auth'

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
export const auth =
  !localPreview && Boolean(config.apiKey && config.authDomain && config.projectId && config.appId)
    ? getAuth(initializeApp(config))
    : null
export async function identityToken() {
  if (!auth) return null
  await auth.authStateReady()
  return auth.currentUser?.getIdToken() ?? null
}
export async function googleLogin() {
  if (localPreview) {
    sessionStorage.setItem('bs-preview-account', 'account')
    return
  }
  if (!auth) throw new Error('Google sign-in is not configured yet. Please try again when accounts are enabled.')
  const provider = new GoogleAuthProvider()
  provider.setCustomParameters({ prompt: 'select_account' })
  await signInWithPopup(auth, provider)
}
export async function firebaseLogout() {
  if (localPreview) sessionStorage.removeItem('bs-preview-account')
  if (auth) await signOut(auth)
}
