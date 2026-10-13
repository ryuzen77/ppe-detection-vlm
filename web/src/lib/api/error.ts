import type { LoginErrorBody } from './types'

function isObject(val: unknown): val is Record<string, unknown> {
  return typeof val === 'object' && val !== null
}

export function extractApiError(e: unknown, fallback: string = 'Terjadi kesalahan'): string {
  if (isObject(e) && 'body' in e) {
    const body = e.body
    if (isObject(body) && 'detail' in body) {
      const detail = (body as LoginErrorBody).detail
      if (isObject(detail) && 'message' in detail) {
        return detail.message ? String(detail.message) : fallback
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

export function extractRetryAfter(e: unknown): number | null {
  if (isObject(e) && 'body' in e) {
    const body = e.body
    if (isObject(body) && 'retry_after_s' in body) {
      const val = (body as LoginErrorBody).retry_after_s
      if (val !== undefined && val !== null) {
        const n = Number(val)
        return Number.isFinite(n) ? n : null
      }
    }
  }
  return null
}
