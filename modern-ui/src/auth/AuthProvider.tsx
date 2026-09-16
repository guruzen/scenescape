import Keycloak, { type KeycloakTokenParsed } from 'keycloak-js'
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'
import type { PropsWithChildren } from 'react'
import { runtimeConfig } from '../config'
import { setTokenSupplier } from '../api/client'

type AuthState = {
  ready: boolean
  authenticated: boolean
  displayName: string
  email: string
  roles: string[]
  isAdmin: boolean
  login: () => Promise<void>
  logout: () => Promise<void>
}

const AuthContext = createContext<AuthState | undefined>(undefined)

const getRoles = (token?: KeycloakTokenParsed) => {
  const realm = token?.realm_access as { roles?: string[] } | undefined
  const client = (token?.resource_access as Record<string, { roles?: string[] }> | undefined)?.[runtimeConfig.keycloakClientId]
  return [...new Set([...(realm?.roles ?? []), ...(client?.roles ?? [])])]
}

export function AuthProvider({ children }: PropsWithChildren) {
  const keycloakRef = useRef<Keycloak | null>(null)
  const [ready, setReady] = useState(false)
  const [authenticated, setAuthenticated] = useState(false)
  const [, setRevision] = useState(0)

  useEffect(() => {
    let cancelled = false
    const keycloak = new Keycloak({ url: runtimeConfig.keycloakUrl, realm: runtimeConfig.keycloakRealm, clientId: runtimeConfig.keycloakClientId })
    keycloakRef.current = keycloak
    const refreshToken = async () => {
      if (!keycloak.authenticated) return undefined
      try { await keycloak.updateToken(30) } catch { await keycloak.login({ redirectUri: window.location.href }) }
      return keycloak.token
    }
    setTokenSupplier(refreshToken)
    keycloak.onTokenExpired = () => { void refreshToken() }
    keycloak.onAuthRefreshSuccess = () => setRevision((n) => n + 1)
    keycloak.onAuthLogout = () => setAuthenticated(false)
    void keycloak.init({ onLoad: 'login-required', pkceMethod: 'S256', checkLoginIframe: false, redirectUri: window.location.href })
      .then((ok) => { if (!cancelled) { setAuthenticated(ok); setReady(true); setRevision((n) => n + 1) } })
      .catch((error) => { console.error('Keycloak initialization failed', error); if (!cancelled) setReady(true) })
    return () => { cancelled = true; setTokenSupplier(async () => undefined) }
  }, [])

  const login = useCallback(async () => { await keycloakRef.current?.login({ redirectUri: window.location.href }) }, [])
  const logout = useCallback(async () => { await keycloakRef.current?.logout({ redirectUri: `${window.location.origin}/` }) }, [])
  const token = keycloakRef.current?.tokenParsed
  const roles = getRoles(token)
  const value = useMemo<AuthState>(() => ({
    ready,
    authenticated,
    displayName: String(token?.name ?? token?.preferred_username ?? 'SceneScape user'),
    email: String(token?.email ?? ''),
    roles,
    isAdmin: roles.includes('scenescape-admin'),
    login,
    logout,
  }), [ready, authenticated, token, roles.join('|'), login, logout])
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const value = useContext(AuthContext)
  if (!value) throw new Error('useAuth must be used inside AuthProvider')
  return value
}
