/**
 * Penyimpanan browser yang aman: bisa diblokir (mode privat, kebijakan situs),
 * jadi setiap akses dibungkus dan kegagalan tidak pernah menjatuhkan UI.
 */
type ReadStore = Pick<Storage, 'getItem'>
type WriteStore = Pick<Storage, 'setItem' | 'removeItem'>

const store = (): Storage | undefined => {
  try {
    return globalThis.localStorage
  } catch {
    return undefined
  }
}

export function readItem(key: string, s: ReadStore | undefined = store()): string | null {
  try {
    return s?.getItem(key) ?? null
  } catch {
    return null
  }
}

/** Nilai kosong/null menghapus kunci */
export function writeItem(key: string, value: string | null, s: WriteStore | undefined = store()): void {
  try {
    if (value) s?.setItem(key, value)
    else s?.removeItem(key)
  } catch {
    // Diblokir: nilai berlaku selama halaman terbuka saja
  }
}

export function readFlag(key: string, fallback: boolean): boolean {
  const v = readItem(key)
  return v === null ? fallback : v === 'true'
}

export function writeFlag(key: string, value: boolean): void {
  writeItem(key, String(value))
}
