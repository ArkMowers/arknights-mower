export const performancePresets = Object.freeze({
  xhigh: Object.freeze({ lowFrameRateMode: false }),
  high: Object.freeze({ lowFrameRateMode: false }),
  medium: Object.freeze({ lowFrameRateMode: true }),
  low: Object.freeze({ lowFrameRateMode: true })
})

export function defaultPerformanceMode() {
  return 'auto'
}

export function normalizePerformanceMode(mode, legacyLowFrameRateMode, platform) {
  if (mode === 'ultra') mode = 'xhigh'
  if (['auto', 'xhigh', 'high', 'medium', 'low'].includes(mode)) {
    return platform === 'android' && ['xhigh', 'high'].includes(mode) ? 'medium' : mode
  }
  // Old custom profiles stored their click strategy separately. Keep all
  // numeric settings, but map that strategy to one of the remaining modes.
  if (mode === 'custom' && legacyLowFrameRateMode !== undefined)
    return legacyLowFrameRateMode || platform === 'android' ? 'medium' : 'high'
  return defaultPerformanceMode(platform)
}

export function performanceProfile(mode, platform) {
  const selected = platform === 'android' && ['xhigh', 'high'].includes(mode) ? 'medium' : mode
  return {
    screenshotInterval: 500,
    selectionPollInterval: platform === 'android' ? 0.5 : 0.1,
    selectionTransitionTimeout: 2.5,
    runOrderDelay: platform === 'android' ? 5 : 3,
    grandetBufferTime: 15,
    ...(performancePresets[selected] ||
      performancePresets[platform === 'android' ? 'medium' : 'xhigh'])
  }
}
