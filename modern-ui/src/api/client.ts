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
  const ct = response.headers.get('content-type') ?? ''
  const body = response.status === 204 ? null : ct.includes('application/json') ? await response.json().catch(() => null) : await response.text().catch(() => '')
  if (!response.ok) throw new Error(typeof body === 'object' && body && 'detail' in body ? String((body as { detail: unknown }).detail) : `SceneScape API returned ${response.status}`)
  return body as T
}

export async function apiObjectUrl(path: string): Promise<string> {
  const token = await tokenSupplier()
  const headers = new Headers()
  if (token) headers.set('Authorization', `Bearer ${token}`)
  const response = await fetch(resolveUrl(path), { headers, credentials: 'same-origin' })
  if (!response.ok) throw new Error(`Media request returned ${response.status}`)
  return URL.createObjectURL(await response.blob())
}

export function normalizeList(payload: unknown): Record<string, unknown>[] {
  if (Array.isArray(payload)) return payload as Record<string, unknown>[]
  if (payload && typeof payload === 'object') {
    for (const value of Object.values(payload as Record<string, unknown>)) {
      if (Array.isArray(value)) return value as Record<string, unknown>[]
    }
  }
  return []
}


export async function apiJsonStream<T>(path: string, onData: (value: T) => void, signal: AbortSignal): Promise<void> {
  const token = await tokenSupplier()
  const headers = new Headers({ Accept: 'text/event-stream' })
  if (token) headers.set('Authorization', `Bearer ${token}`)
  const response = await fetch(resolveUrl(path), { headers, credentials: 'same-origin', signal })
  if (!response.ok) throw new Error(`SceneScape live stream returned ${response.status}`)
  if (!response.body) throw new Error('SceneScape live stream has no response body')
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  try {
    while (!signal.aborted) {
      const { value, done } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, '\n')
      let boundary = buffer.indexOf('\n\n')
      while (boundary >= 0) {
        const block = buffer.slice(0, boundary)
        buffer = buffer.slice(boundary + 2)
        const data = block.split('\n').filter((line) => line.startsWith('data:')).map((line) => line.slice(5).trim()).join('\n')
        if (data) onData(JSON.parse(data) as T)
        boundary = buffer.indexOf('\n\n')
      }
    }
  } finally {
    reader.releaseLock()
  }
}
