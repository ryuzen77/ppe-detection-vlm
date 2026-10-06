export interface AuthState {
  authenticated: boolean
  authRequired: boolean
}

/** Menentukan apakah halaman Login harus ditampilkan. */
export function shouldShowLogin(state: AuthState): boolean {
  return state.authRequired && !state.authenticated
}

/** 
 * Menghitung hitung mundur berikutnya setelah interval tick (misal 1 detik).
 * Mengembalikan null jika hitung mundur selesai atau tidak aktif.
 */
export function tickCountdown(currentWait: number | null, elapsedSecs = 1): number | null {
  if (currentWait === null || currentWait <= 0) return null
  const next = currentWait - elapsedSecs
  return next > 0 ? next : null
}
