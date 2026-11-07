export const LOG_MIN_HEIGHT = 120
export const LOG_MIN_SHARE = 1 / 3
export const RESIZER_HEIGHT = 8
export const PANE_MIN_HEIGHT = 90
export const SCREENSHOT_MAX_HEIGHT = 500
export const TASK_MAX_HEIGHT = 600
export const RAIL_GAP = 24
export const RAIL_MIN_WIDTH = 320
export const RAIL_MAX_WIDTH = 720
export const RAIL_LOG_MIN_WIDTH = 440
export const RAIL_LAYOUT_MIN_WIDTH = 900

export function logLayoutZoom(element) {
  const zoom = Number(element.ownerDocument?.documentElement.style.zoom)
  return Number.isFinite(zoom) && zoom > 0 ? zoom : 1
}

function clamp(value, minimum, maximum) {
  const max = Math.max(0, maximum)
  const min = Math.min(minimum, max)
  return Math.round(Math.max(min, Math.min(max, Number(value) || 0)))
}

export function clampScreenshotHeight(value, containerHeight, bottomReserve, stackedFit) {
  const widthFit = Number.isFinite(stackedFit) ? stackedFit : Infinity
  const maximum = Math.min(
    SCREENSHOT_MAX_HEIGHT,
    containerHeight * 0.55,
    containerHeight - bottomReserve - PANE_MIN_HEIGHT - RESIZER_HEIGHT,
    widthFit
  )
  return clamp(value, PANE_MIN_HEIGHT, maximum)
}

export function clampTaskHeight(value, availableHeight, bottomReserve) {
  const maximum = Math.min(TASK_MAX_HEIGHT, availableHeight - bottomReserve)
  return clamp(value, PANE_MIN_HEIGHT, maximum)
}

export function logMinHeight(containerHeight) {
  return Math.max(LOG_MIN_HEIGHT, Math.round(containerHeight * LOG_MIN_SHARE))
}

// 右侧栏宽度：用户拖过纵向分隔条后用保存的 rail_width，
// 否则按截图高度和画面比例推导默认宽度，再按最终栏宽等比计算截图高度。
export function fitRailLayout(
  railWidth,
  screenshotHeight,
  containerWidth,
  containerHeight,
  aspect
) {
  const logRailMinWidth = Math.max(RAIL_LOG_MIN_WIDTH, Math.round(containerWidth * 0.4))
  const maxRailWidth = Math.min(RAIL_MAX_WIDTH, containerWidth - logRailMinWidth - RAIL_GAP)
  const width = clamp(railWidth ?? screenshotHeight * aspect, RAIL_MIN_WIDTH, maxRailWidth)
  const logRailBottom = logMinHeight(containerHeight) + RESIZER_HEIGHT
  const maxRailHeight = Math.min(SCREENSHOT_MAX_HEIGHT, containerHeight - logRailBottom)
  const height = clamp(width / aspect, PANE_MIN_HEIGHT, maxRailHeight)
  return { width, height }
}
