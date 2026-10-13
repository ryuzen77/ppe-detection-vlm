export interface AuthState {
  authenticated: boolean
  setupRequired: boolean
  loaded?: boolean
}

export type ViewState = 'loading' | 'setup' | 'login' | 'dashboard'

export function getViewState(state: AuthState): ViewState {
  if (!state.loaded) return 'loading'
  if (state.authenticated) return 'dashboard'
  if (state.setupRequired) return 'setup'
  return 'login'
}

export function shouldLoadData(prevState: AuthState, nextState: AuthState): boolean {
  if (!prevState.authenticated && nextState.authenticated) return true
  if (!prevState.loaded && nextState.loaded && nextState.authenticated) return true
  return false
}

export function tickCountdown(currentWait: number | null, elapsedSecs = 1): number | null {
  if (currentWait === null || currentWait <= 0) return null
  const next = currentWait - elapsedSecs
  return next > 0 ? next : null
}

export function telemetryAction(state: AuthState): 'start' | 'stop' | 'wait' {
  if (state.loaded === false) return 'wait'
  if (state.authenticated) return 'start'
  return 'stop'
}
