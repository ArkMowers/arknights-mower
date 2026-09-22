export const LOG_MIN_HEIGHT = 120
export const RESIZER_HEIGHT = 8
export const PANE_MIN_HEIGHT = 90
export const SCREENSHOT_MAX_HEIGHT = 500
export const TASK_MAX_HEIGHT = 600

function clamp(value, minimum, maximum) {
  const max = Math.max(0, maximum)
  const min = Math.min(minimum, max)
  return Math.round(Math.max(min, Math.min(max, Number(value) || 0)))
}

export function clampScreenshotHeight(value, containerHeight, bottomReserve) {
  const maximum = Math.min(
    SCREENSHOT_MAX_HEIGHT,
    containerHeight * 0.55,
    containerHeight - bottomReserve - PANE_MIN_HEIGHT - RESIZER_HEIGHT
  )
  return clamp(value, PANE_MIN_HEIGHT, maximum)
}

export function clampTaskHeight(value, availableHeight, bottomReserve) {
  const maximum = Math.min(TASK_MAX_HEIGHT, availableHeight - bottomReserve)
  return clamp(value, PANE_MIN_HEIGHT, maximum)
}
