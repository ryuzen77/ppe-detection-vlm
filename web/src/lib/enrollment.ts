/**
 * Mode pendaftaran wajah (T75): selama modal foto terbuka gerbang jeda, supaya orang yang
 * difoto tidak langsung diperiksa (uji nyata 19-10: foto selalu ditolak `camera_busy`).
 */
import type { EnrollmentHoldResponse } from './api/types'
import { ENROLLMENT_HOLD } from './settings'

export interface EnrollmentClient {
  holdEnrollment: () => Promise<EnrollmentHoldResponse>
  releaseEnrollment: () => Promise<void>
}

/**
 * Mulai jeda lalu kirim denyut beberapa kali dalam satu batas waktu backend (`hold_s` dari
 * server, bukan angka salinan). Mengembalikan fungsi penutup (dipakai sebagai cleanup $effect).
 */
export function keepEnrollmentHold(client: EnrollmentClient, onError: () => void): () => void {
  let timer: ReturnType<typeof setInterval> | undefined
  let closed = false
  // Gagal melepas tidak berbahaya: tanpa denyut, backend mengakhiri jeda sendiri
  const release = () => client.releaseEnrollment().catch(() => {})
  client.holdEnrollment().then(
    (res) => {
      // Modal ditutup sebelum jeda pertama terjawab: lepas lagi supaya gerbang tidak tertahan
      if (closed) return void release()
      timer = setInterval(
        () => client.holdEnrollment().catch(onError),
        (res.hold_s * 1000) / ENROLLMENT_HOLD.beatsPerHold,
      )
    },
    onError,
  )
  return () => {
    closed = true
    clearInterval(timer)
    release()
  }
}
