/**
 * Status koneksi untuk chip bilah atas (logika murni, teruji).
 * Sebelum pengguna masuk WebSocket memang belum dibuka, jadi kondisi itu
 * dibedakan dari server yang benar-benar terputus (temuan uji UI 14-10).
 */
import type { ConnectionStatus } from './api/telemetry'

export type ConnectionView = 'signed_out' | 'connected' | 'disconnected'

export function connectionView(authenticated: boolean, status: ConnectionStatus): ConnectionView {
  if (!authenticated) return 'signed_out'
  return status === 'connected' ? 'connected' : 'disconnected'
}
