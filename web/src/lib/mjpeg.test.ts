import { describe, expect, it } from 'vitest'
import { releaseStream } from './mjpeg'

describe('releaseStream', () => {
  it('mengosongkan src saat elemen dilepas (koneksi MJPEG diputus)', () => {
    const img = { src: '/api/stream?t=1' }
    const action = releaseStream(img)
    expect(img.src).toBe('/api/stream?t=1')
    action.destroy()
    expect(img.src).toBe('')
  })
})
