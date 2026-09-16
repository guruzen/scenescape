export type SceneScapeRuntimeConfig = {
  apiBaseUrl: string
  keycloakUrl: string
  keycloakRealm: string
  keycloakClientId: string
  legacyBaseUrl: string
  appTitle: string
}

declare global {
  interface Window { __SCENESCAPE_CONFIG__?: Partial<SceneScapeRuntimeConfig> }
}

const defaults: SceneScapeRuntimeConfig = {
  apiBaseUrl: '', keycloakUrl: '/auth', keycloakRealm: 'scenescape', keycloakClientId: 'scenescape-ui', legacyBaseUrl: '/legacy/', appTitle: 'SceneScape',
}

export const runtimeConfig: SceneScapeRuntimeConfig = { ...defaults, ...(window.__SCENESCAPE_CONFIG__ ?? {}) }
export const legacyUrl = (path = '') => `${runtimeConfig.legacyBaseUrl.replace(/\/?$/, '/')}${path.replace(/^\//, '')}`
