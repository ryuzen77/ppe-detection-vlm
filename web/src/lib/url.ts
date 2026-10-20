import { DEV_SERVER } from './settings'

export function getSetupUrl(currentPort: string | number): string {
  const port = String(currentPort)
  if (port === DEV_SERVER.vitePort) {
    return DEV_SERVER.backendUrl
  }
  return `http://localhost:${port}`
}

/** Path + query string dari parameter yang terisi (undefined / null / '' dilewati). */
export function withQuery(path: string, params: object): string {
  const q = new URLSearchParams()
  for (const [key, value] of Object.entries(params) as [string, unknown][]) {
    if (value !== undefined && value !== null && value !== '') q.set(key, String(value))
  }
  const qs = q.toString()
  return qs ? `${path}?${qs}` : path
}
