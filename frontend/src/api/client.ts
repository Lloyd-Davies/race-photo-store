/** Typed API client. Reads X-Admin-Token from sessionStorage when present. */

const BASE = '/api'

function getHeaders(extra?: HeadersInit): Headers {
  const h = new Headers(extra)
  h.set('Content-Type', 'application/json')
  const token = sessionStorage.getItem('adminToken')
  if (token) h.set('X-Admin-Token', token)
  return h
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: getHeaders(init?.headers),
  })
  if (!res.ok) {
    const msg = await res.text().catch(() => res.statusText)
    throw new Error(`${res.status}: ${msg}`)
  }
  return res.json() as Promise<T>
}

export const apiGet = <T>(path: string) => request<T>(path)

export const apiPost = <T>(path: string, body?: unknown) =>
  request<T>(path, {
    method: 'POST',
    body: JSON.stringify(body),
  })

export const apiPatch = <T>(path: string, body?: unknown) =>
  request<T>(path, {
    method: 'PATCH',
    body: JSON.stringify(body),
  })

export const apiDelete = <T>(path: string) =>
  request<T>(path, { method: 'DELETE' })
