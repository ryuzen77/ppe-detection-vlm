import { describe, it, expect } from 'vitest'
import { getSetupUrl } from './url'

describe('getSetupUrl', () => {
  it('returns 8000 if port is 5173', () => {
    expect(getSetupUrl('5173')).toBe('http://localhost:8000')
    expect(getSetupUrl(5173)).toBe('http://localhost:8000')
  })
  it('returns same port otherwise', () => {
    expect(getSetupUrl('8001')).toBe('http://localhost:8001')
    expect(getSetupUrl(80)).toBe('http://localhost:80')
  })
})
