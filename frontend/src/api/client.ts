/** Typed API client. Reads admin bearer access token from sessionStorage when present. */

const ADMIN_ACCESS_TOKEN_KEY = 'adminAccessToken'

const BASE = '/api'

function getHeaders(extra?: HeadersInit): Headers {
  const h = new Headers(extra)
  h.set('Content-Type', 'application/json')
  const token = sessionStorage.getItem(ADMIN_ACCESS_TOKEN_KEY)
  if (token) h.set('Authorization', `Bearer ${token}`)
  return h
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: getHeaders(init?.headers),
  })

  if (!res.ok) {
    let detail = res.statusText

    try {
      const body = await res.json()
      if (typeof body?.detail === 'string' && body.detail.trim()) {
        detail = body.detail
      }
    } catch {
      const text = await res.text().catch(() => '')
      if (text.trim()) {
        detail = text.trim()
      }
    }

    if (res.status === 401 && (!detail || detail === 'Unauthorized')) {
      detail = 'Unauthorized'
    }

    throw new Error(`${res.status}: ${detail}`)
  }

  return res.json() as Promise<T>
}

export const apiGet = <T>(path: string, headers?: HeadersInit) =>
  request<T>(path, { headers })

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
