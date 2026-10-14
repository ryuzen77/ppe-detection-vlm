import { DEV_SERVER } from './settings'

export function getSetupUrl(currentPort: string | number): string {
  const port = String(currentPort)
  if (port === DEV_SERVER.vitePort) {
    return DEV_SERVER.backendUrl
  }
  return `http://localhost:${port}`
}
