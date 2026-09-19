export const performancePresets = Object.freeze({
  high: Object.freeze({
    lowFrameRateMode: false,
    screenshotInterval: 500,
    selectionPollInterval: 0.1,
    selectionTransitionTimeout: 2.5,
    runOrderDelay: 3,
    grandetBufferTime: 15
  }),
  medium: Object.freeze({
    lowFrameRateMode: true,
    screenshotInterval: 500,
    selectionPollInterval: 0.5,
    selectionTransitionTimeout: 2.5,
    runOrderDelay: 5,
    grandetBufferTime: 15
  }),
  low: Object.freeze({
    lowFrameRateMode: true,
    screenshotInterval: 750,
    selectionPollInterval: 0.75,
    selectionTransitionTimeout: 6,
    runOrderDelay: 10,
    grandetBufferTime: 30
  })
})

export function defaultPerformanceMode(platform) {
  return platform === 'android' ? 'auto' : 'high'
}

export function normalizePerformanceMode(mode, legacyLowFrameRateMode, platform) {
  if (['auto', 'high', 'medium', 'low', 'custom'].includes(mode)) return mode
  if (legacyLowFrameRateMode !== undefined) return legacyLowFrameRateMode ? 'medium' : 'high'
  return defaultPerformanceMode(platform)
}

export function performanceProfile(mode, platform) {
  if (performancePresets[mode]) return performancePresets[mode]
  return performancePresets[platform === 'android' ? 'medium' : 'high']
}
