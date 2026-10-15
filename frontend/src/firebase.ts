import { initializeApp, type FirebaseOptions } from 'firebase/app'
import { getAuth, GoogleAuthProvider, signInWithPopup, signOut } from 'firebase/auth'

// The Firebase SDK, loaded on its own by auth.ts so the first page does not wait for it.
export function connect(config: FirebaseOptions) {
  return getAuth(initializeApp(config))
}
export { GoogleAuthProvider, signInWithPopup, signOut }
