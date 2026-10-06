import { api } from '../api/client'

class SessionStore {
  authenticated = $state(false)
  authRequired = $state(false)
  expiresInS = $state<number | null>(null)
  
  // Waktu polling
  private timer: ReturnType<typeof setInterval> | null = null

  async load() {
    try {
      const res = await api.session()
      this.authenticated = res.authenticated
      this.authRequired = res.auth_required
      this.expiresInS = res.expires_in_s
      this.startCountdown()
    } catch {
      this.authenticated = false
    }
  }

  private startCountdown() {
    this.stopCountdown()
    if (this.expiresInS !== null) {
      this.timer = setInterval(() => {
        if (this.expiresInS !== null && this.expiresInS > 0) {
          this.expiresInS--
        }
      }, 1000)
    }
  }

  private stopCountdown() {
    if (this.timer) clearInterval(this.timer)
    this.timer = null
  }

  async login(password: string) {
    const res = await api.login(password)
    this.authenticated = true
    this.expiresInS = res.expires_in_s
    this.startCountdown()
  }

  async logout() {
    await api.logout()
    this.authenticated = false
    this.expiresInS = null
    this.stopCountdown()
  }

  clear() {
    this.authenticated = false
    this.expiresInS = null
    this.stopCountdown()
  }
}

export const session = new SessionStore()
