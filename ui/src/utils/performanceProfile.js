export const performancePresets = Object.freeze({
  xhigh: Object.freeze({ lowFrameRateMode: false }),
  high: Object.freeze({ lowFrameRateMode: false }),
  medium: Object.freeze({ lowFrameRateMode: true }),
  low: Object.freeze({ lowFrameRateMode: true })
})

export function defaultPerformanceMode() {
  return 'auto'
}

export function normalizePerformanceMode(mode, legacyLowFrameRateMode) {
  if (mode === 'ultra') mode = 'xhigh'
  if (['auto', 'xhigh', 'high', 'medium', 'low'].includes(mode)) {
    return mode
  }
  // Old custom profiles stored their click strategy separately. Keep all
  // numeric settings, but map that strategy to one of the remaining modes.
  if (mode === 'custom' && legacyLowFrameRateMode !== undefined)
    return legacyLowFrameRateMode ? 'medium' : 'high'
  return defaultPerformanceMode()
}

export function performanceProfile(mode) {
  return {
    screenshotInterval: 500,
    selectionPollInterval: 0.1,
    selectionTransitionTimeout: 2.5,
    runOrderDelay: 3,
    grandetBufferTime: 15,
    ...(performancePresets[mode] || performancePresets.xhigh)
  }
}
