import { api } from '../api/client'
import type { User, SetupRequest, LoginRequest } from '../api/types'

class SessionStore {
  authenticated = $state(false)
  setupRequired = $state(false)
  setupAllowed = $state(false)
  user = $state<User | null>(null)
  loaded = $state(false)
  expiresInS = $state<number | null>(null)

  private timer: ReturnType<typeof setInterval> | null = null

  async load() {
    try {
      const res = await api.session()
      this.authenticated = res.authenticated
      this.setupRequired = res.setup_required
      this.setupAllowed = res.setup_allowed
      this.user = res.user
      this.expiresInS = res.expires_in_s
      this.startCountdown()
    } catch {
      this.authenticated = false
    }
    this.loaded = true
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

  async login(req: LoginRequest) {
    const res = await api.login(req)
    this.authenticated = true
    this.user = res.user
    this.expiresInS = res.expires_in_s
    this.startCountdown()
  }

  async setup(req: SetupRequest) {
    const res = await api.setup(req)
    this.authenticated = true
    this.setupRequired = false
    this.user = res.user
    this.expiresInS = res.expires_in_s
    this.startCountdown()
  }

  async logout() {
    await api.logout()
    this.clear()
  }

  clear() {
    this.authenticated = false
    this.user = null
    this.expiresInS = null
    this.stopCountdown()
  }
}

export const session = new SessionStore()
