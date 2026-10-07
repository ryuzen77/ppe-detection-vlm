export function extractApiError(e: unknown, fallback: string = 'Terjadi kesalahan'): string {
  if (typeof e === 'object' && e !== null && 'body' in e) {
    const body = (e as {body: unknown}).body
    if (typeof body === 'object' && body !== null && 'detail' in body) {
      const detail = (body as {detail: unknown}).detail
      if (typeof detail === 'object' && detail !== null && 'message' in detail) {
        return String((detail as {message: unknown}).message)
      }
      return String(detail)
    }
  }
  if (e instanceof Error) {
    return e.message
  }
  if (typeof e === 'string' && e.trim() !== '') {
    return e
  }
  return fallback
}
