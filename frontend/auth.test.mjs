import assert from 'node:assert/strict'
import { test } from 'node:test'
import { readFileSync } from 'node:fs'
import ts from 'typescript'

// auth.ts loads the Firebase SDK as a separate chunk; run it against a stub SDK.
const { outputText } = ts.transpileModule(
  readFileSync(new URL('./src/auth.ts', import.meta.url), 'utf8').replaceAll('import.meta.env', '({DEV:false})'),
  { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } },
)

function loadAuth({ config, sdk }) {
  globalThis.location = { search: '' }
  globalThis.window = { location: globalThis.location, __BS_FIREBASE_CONFIG: config }
  const exports = {}
  new Function('require', 'exports', outputText)(name => {
    if (name !== './firebase') throw new Error('unexpected import ' + name)
    return sdk()
  }, exports)
  return exports
}

const signedIn = { getIdToken: async () => 'id-token' }
function stubSdk(log) {
  const auth = { currentUser: signedIn, authStateReady: async () => log.push('ready') }
  return {
    connect: config => {
      log.push('connect ' + config.projectId)
      return auth
    },
    GoogleAuthProvider: class {
      setCustomParameters(value) {
        log.push('provider ' + value.prompt)
      }
    },
    signInWithPopup: async target => log.push(target === auth ? 'popup' : 'popup on wrong auth'),
    signOut: async target => log.push(target === auth ? 'signOut' : 'signOut on wrong auth'),
  }
}
const config = { apiKey: 'k', authDomain: 'd', projectId: 'p', appId: 'a' }

test('the SDK loads once, in the background, and every token request waits for it', async () => {
  const log = []
  let imports = 0
  const auth = loadAuth({ config, sdk: () => (imports++, stubSdk(log)) })
  assert.equal(auth.currentAuth(), null)
  // Loading starts with the module, before anything asks for a token.
  await new Promise(resolve => setTimeout(resolve))
  assert.equal(imports, 1)
  const [first, second] = await Promise.all([auth.identityToken(), auth.identityToken()])
  assert.deepEqual([first, second], ['id-token', 'id-token'])
  assert.equal(imports, 1)
  assert.equal(auth.currentAuth().currentUser, signedIn)
  await auth.googleLogin()
  await auth.firebaseLogout()
  assert.deepEqual(log, ['connect p', 'ready', 'ready', 'provider select_account', 'popup', 'signOut'])
})

test('a failed SDK download is retried by the next caller', async () => {
  const log = []
  let imports = 0
  const auth = loadAuth({
    config,
    sdk: () => {
      if (++imports === 1) throw new Error('chunk download failed')
      return stubSdk(log)
    },
  })
  await assert.rejects(auth.identityToken(), /chunk download failed/)
  assert.equal(await auth.identityToken(), 'id-token')
  assert.equal(imports, 2)
})

test('without a Firebase configuration the SDK is never downloaded', async () => {
  const auth = loadAuth({
    config: undefined,
    sdk: () => {
      throw new Error('Firebase must not load without a configuration')
    },
  })
  assert.equal(await auth.identityToken(), null)
  assert.equal(await auth.loadAuth(), null)
  await auth.firebaseLogout()
  await assert.rejects(auth.googleLogin(), /not configured/)
})
