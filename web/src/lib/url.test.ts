import { describe, it, expect } from 'vitest'
import { getSetupUrl } from './url'
import { DEV_SERVER } from './settings'

describe('getSetupUrl', () => {
  it('points to the backend when opened via the Vite dev server', () => {
    expect(getSetupUrl(DEV_SERVER.vitePort)).toBe(DEV_SERVER.backendUrl)
    expect(getSetupUrl(Number(DEV_SERVER.vitePort))).toBe(DEV_SERVER.backendUrl)
  })
  it('returns same port otherwise', () => {
    expect(getSetupUrl('8001')).toBe('http://localhost:8001')
    expect(getSetupUrl(80)).toBe('http://localhost:80')
  })
})
