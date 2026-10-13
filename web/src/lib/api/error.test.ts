import { describe, it, expect } from 'vitest'
import { extractApiError, extractRetryAfter } from './error'

describe('extractApiError', () => {
  it('extracts from { body: { detail: { message: "msg" } } }', () => {
    expect(extractApiError({ body: { detail: { message: 'Api Error' } } })).toBe('Api Error')
  })
  it('extracts from { body: { detail: "string error" } }', () => {
    expect(extractApiError({ body: { detail: 'string error' } })).toBe('string error')
  })
  it('extracts from Error instance', () => {
    expect(extractApiError(new Error('JS Error'))).toBe('JS Error')
  })
  it('returns fallback for unknown', () => {
    expect(extractApiError(null, 'fallback')).toBe('fallback')
  })
})

describe('extractRetryAfter', () => {
  it('extracts number from body.retry_after_s', () => {
    expect(extractRetryAfter({ body: { retry_after_s: 30 } })).toBe(30)
  })
  it('converts string number from body.retry_after_s', () => {
    expect(extractRetryAfter({ body: { retry_after_s: '15' } })).toBe(15)
  })
  it('returns null if not present or invalid', () => {
    expect(extractRetryAfter({ body: { detail: 'error' } })).toBeNull()
    expect(extractRetryAfter(new Error('err'))).toBeNull()
    expect(extractRetryAfter(null)).toBeNull()
  })
})
