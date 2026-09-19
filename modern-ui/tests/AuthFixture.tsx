// Browser-test fixture ONLY. Not imported by src/main.tsx or the production build.
import { setTokenSupplier } from '../src/api/client'
let token: Promise<string> | undefined
setTokenSupplier(() => {
  token ??= fetch('/api/v1/auth', { method: 'POST', body: new URLSearchParams({ username: 'browser-fixture', password: 'fixture-only' }) })
    .then(async (response) => {
      if (!response.ok) throw new Error('The isolated browser-test API was not started')
      return (await response.json()).token as string
    })
  return token
})
export function useAuth() {
  return { ready: true, authenticated: true, displayName: 'Synthetic test operator', email: '', roles: ['scenescape-admin'], isAdmin: true,
    login: async () => {}, logout: async () => {} }
}
