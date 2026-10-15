export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public data: Record<string, unknown> = {},
  ) {
    super(message)
  }
  get code() {
    return typeof this.data.code === 'string' ? this.data.code : undefined
  }
}

// Answers of these calls are about signing in; a 401 there is not an expired session.
const AUTH_PATHS = [
  '/auth/me',
  '/auth/telegram',
  '/auth/webapp',
  '/auth/login-requests',
  '/auth/bastion',
]

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const body = options.body
  const headers: HeadersInit =
    body === undefined || body instanceof FormData
      ? { ...options.headers }
      : { 'Content-Type': 'application/json', ...options.headers }
  let response: Response
  try {
    response = await fetch(`/api${path}`, { ...options, headers, credentials: 'same-origin' })
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error
    throw new ApiError('Нет соединения. Проверьте интернет и попробуйте снова', 0)
  }
  if (!response.ok) {
    const data = await response.json().catch(() => ({}))
    if (response.status === 401 && !AUTH_PATHS.some((prefix) => path.startsWith(prefix)))
      window.dispatchEvent(new Event('session-expired'))
    throw new ApiError(
      typeof data.detail === 'string'
        ? data.detail
        : response.status === 413
          ? 'Файл слишком большой'
          : response.status >= 500
            ? 'Сервер не отвечает. Попробуйте позже'
            : 'Не удалось выполнить действие. Попробуйте снова',
      response.status,
      data && typeof data === 'object' ? data : {},
    )
  }
  return response.status === 204 ? (undefined as T) : response.json()
}

export const json = (method: string, value: unknown): RequestInit => ({
  method,
  body: JSON.stringify(value),
})

export function query(values: Record<string, string | number | boolean | null | undefined>) {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(values))
    if (value !== undefined && value !== null && value !== '') params.set(key, String(value))
  const text = params.toString()
  return text ? `?${text}` : ''
}

/** URL of a stored photo: a WebP preview by default, the original file on request. */
/** `version` changes the address when the same photo may look different (body photos
 * before and after the photo code). */
export const mediaUrl = (id: number, size: 'preview' | 'original' = 'preview', version = '') => {
  // Raised once when browsers may hold a wrong picture for an id: until October 2026 the
  // id of a deleted photo could be given to a new one.
  const params = new URLSearchParams({ r: '2' })
  if (size === 'original') params.set('size', 'original')
  if (version) params.set('v', version)
  return `/api/media/${id}?${params}`
}
