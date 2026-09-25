/**
 * Token admin di browser ini (sementara sampai login T30). Satu tempat untuk
 * status "sudah diisi" dan dialog isiannya, supaya bilah atas dan penolakan
 * 401 dari perintah mana pun membuka dialog yang sama.
 */
import { readAdminToken, writeAdminToken } from '../api/client'

export type TokenPrompt = 'manual' | 'rejected'

class AdminTokenStore {
  hasToken = $state(readAdminToken() !== '')
  dialogOpen = $state(false)
  /** Alasan dialog terbuka: dibuka sendiri, atau karena server menolak perintah */
  reason = $state<TokenPrompt>('manual')

  open(reason: TokenPrompt = 'manual'): void {
    this.reason = reason
    this.dialogOpen = true
  }

  close(): void {
    this.dialogOpen = false
  }

  save(token: string): void {
    writeAdminToken(token)
    this.hasToken = readAdminToken() !== ''
  }

  clear(): void {
    writeAdminToken('')
    this.hasToken = false
  }
}

export const adminToken = new AdminTokenStore()
