import { describe, it, expect } from 'vitest'
import { connectionView } from './connection'

describe('connectionView', () => {
  it('is signed_out before login regardless of socket state', () => {
    expect(connectionView(false, 'disconnected')).toBe('signed_out')
    expect(connectionView(false, 'connecting')).toBe('signed_out')
    expect(connectionView(false, 'connected')).toBe('signed_out')
  })
  it('is connected only when the socket is connected after login', () => {
    expect(connectionView(true, 'connected')).toBe('connected')
  })
  it('is disconnected after login when the socket is not connected', () => {
    expect(connectionView(true, 'disconnected')).toBe('disconnected')
    expect(connectionView(true, 'connecting')).toBe('disconnected')
  })
})
