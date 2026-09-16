import { runtimeConfig } from '../config'

export type TokenSupplier = () => Promise<string | undefined>
let tokenSupplier: TokenSupplier = async () => undefined
export const setTokenSupplier = (supplier: TokenSupplier) => { tokenSupplier = supplier }

const resolveUrl = (path: string) => `${runtimeConfig.apiBaseUrl.replace(/\/$/, '')}${path.startsWith('/') ? path : `/${path}`}`

export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = await tokenSupplier()
  const headers = new Headers(init.headers)
  headers.set('Accept', 'application/json')
  if (token) headers.set('Authorization', `Bearer ${token}`)
  if (init.body && !(init.body instanceof FormData) && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json')
  const response = await fetch(resolveUrl(path), { ...init, headers, credentials: 'same-origin' })
  const contentType = response.headers.get('content-type') ?? ''
  const body = response.status === 204 ? null : contentType.includes('application/json') ? await response.json().catch(() => null) : await response.text().catch(() => '')
  if (!response.ok) throw new Error(typeof body === 'object' && body && 'detail' in body ? String((body as { detail: unknown }).detail) : `SceneScape API returned ${response.status}`)
  return body as T
}

export function normalizeList(payload: unknown): Record<string, unknown>[] {
  if (Array.isArray(payload)) return payload.filter((v): v is Record<string, unknown> => !!v && typeof v === 'object')
  if (payload && typeof payload === 'object') {
    const value = payload as Record<string, unknown>
    if (Array.isArray(value.results)) return normalizeList(value.results)
  }
  return []
}
