export function getSetupUrl(currentPort: string | number): string {
  const port = String(currentPort)
  if (port === '5173') {
    return 'http://localhost:8000'
  }
  return `http://localhost:${port}`
}
