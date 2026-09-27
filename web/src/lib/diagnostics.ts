import { CLOCK } from './settings'

export function formatLostSince(lastMessageAt: number | null, fallback: string, sincePrefix: (t: string) => string): string {
  if (!lastMessageAt) return fallback
  const d = new Date(lastMessageAt)
  return sincePrefix(d.toLocaleTimeString(CLOCK.locale, { hour12: false }))
}
