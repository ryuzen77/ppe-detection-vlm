import { describe, it, expect } from 'vitest'
import { extractApiError } from './error'

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
