export function formatServerDate(dateStr: string | null): string {
  if (!dateStr) return '-'
  const d = new Date(dateStr)
  if (Number.isNaN(d.getTime())) return dateStr
  return d.toLocaleString('id-ID')
}
