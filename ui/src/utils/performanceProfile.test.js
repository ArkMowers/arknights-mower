import { describe, expect, it } from 'vitest'
import {
  defaultPerformanceMode,
  normalizePerformanceMode,
  performanceProfile
} from './performanceProfile'

describe('performance profiles', () => {
  it.each([
    ['android', 'auto'],
    ['windows', 'high'],
    ['darwin', 'high'],
    ['linux', 'high']
  ])('defaults %s to %s', (platform, expected) => {
    expect(defaultPerformanceMode(platform)).toBe(expected)
  })

  it('migrates the former low-frame-rate boolean', () => {
    expect(normalizePerformanceMode(undefined, false, 'android')).toBe('high')
    expect(normalizePerformanceMode(undefined, true, 'linux')).toBe('medium')
  })

  it('uses the Android medium profile as the visible auto baseline', () => {
    expect(performanceProfile('auto', 'android')).toMatchObject({
      screenshotInterval: 500,
      selectionPollInterval: 0.5,
      selectionTransitionTimeout: 2.5,
      runOrderDelay: 5,
      grandetBufferTime: 15
    })
  })

  it('keeps other platforms on the high profile by default', () => {
    expect(performanceProfile('auto', 'darwin')).toMatchObject({
      lowFrameRateMode: false,
      screenshotInterval: 500,
      selectionPollInterval: 0.1,
      runOrderDelay: 3
    })
  })
})
