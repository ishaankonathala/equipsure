export const API_BASE =
  import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

export function apiFetch(
  path: string,
  init: RequestInit = {},
  token?: string,
): Promise<Response> {
  const headers = new Headers(init.headers)

  if (typeof init.body === 'string') {
    headers.set('Content-Type', 'application/json')
  }
  if (token !== undefined) {
    headers.set('Authorization', `Bearer ${token}`)
  }

  return fetch(`${API_BASE}${path}`, { ...init, headers })
}