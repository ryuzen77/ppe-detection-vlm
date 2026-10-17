import type { CameraDevice } from './api/types'
import { CAMERA_PICKER, modeLabel } from './messages'

export function formatServerDate(dateStr: string | null): string {
  if (!dateStr) return '-'
  const d = new Date(dateStr)
  if (Number.isNaN(d.getTime())) return dateStr
  return d.toLocaleString('id-ID')
}

/** Format metadata kamera yang ramah operator (mis. "Kamera 1 · kemampuan belum dipindai") */
export function formatDeviceMeta(dev: CameraDevice): string {
  const parts = [CAMERA_PICKER.cameraNumber(dev.index)]
  parts.push(
    dev.selected_mode
      ? modeLabel(dev.selected_mode)
      : dev.scanned === false
        ? CAMERA_PICKER.capabilityNotScanned
        : CAMERA_PICKER.unavailable
  )
  return parts.join(' · ')
}

