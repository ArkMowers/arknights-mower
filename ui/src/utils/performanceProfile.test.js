import { describe, expect, it } from 'vitest'
import {
  defaultPerformanceMode,
  normalizePerformanceMode,
  performanceProfile
} from './performanceProfile'

describe('performance profiles', () => {
  it.each([
    ['android', 'auto'],
    ['windows', 'auto'],
    ['darwin', 'auto'],
    ['linux', 'auto']
  ])('defaults %s to %s', (platform, expected) => {
    expect(defaultPerformanceMode(platform)).toBe(expected)
  })

  it('defaults old configurations without an explicit mode to auto', () => {
    expect(normalizePerformanceMode(undefined, false, 'android')).toBe('auto')
    expect(normalizePerformanceMode(undefined, true, 'linux')).toBe('auto')
  })

  it('preserves Android fast modes and their click strategy', () => {
    expect(normalizePerformanceMode('high', false, 'android')).toBe('high')
    expect(normalizePerformanceMode('xhigh', false, 'android')).toBe('xhigh')
    for (const mode of ['high', 'xhigh'])
      expect(performanceProfile(mode, 'android')).toMatchObject({ lowFrameRateMode: false })
    expect(normalizePerformanceMode('high', false, 'darwin')).toBe('high')
  })

  it('migrates custom to its saved click strategy', () => {
    expect(normalizePerformanceMode('custom', false, 'darwin')).toBe('high')
    expect(normalizePerformanceMode('custom', true, 'darwin')).toBe('medium')
    expect(normalizePerformanceMode('custom', false, 'android')).toBe('high')
  })

  it('migrates the old ultra value to xhigh', () => {
    expect(normalizePerformanceMode('ultra', false, 'darwin')).toBe('xhigh')
  })

  it('uses the same numeric defaults regardless of the selected mode', () => {
    const high = performanceProfile('high', 'darwin')
    const low = performanceProfile('low', 'darwin')
    const xhigh = performanceProfile('xhigh', 'darwin')
    expect({ ...high, lowFrameRateMode: null }).toEqual({ ...low, lowFrameRateMode: null })
    expect(xhigh).toEqual(high)
  })

  it('uses the same auto baseline on Android', () => {
    expect(performanceProfile('auto', 'android')).toMatchObject({
      lowFrameRateMode: false,
      screenshotInterval: 500,
      selectionPollInterval: 0.1,
      selectionTransitionTimeout: 2.5,
      runOrderDelay: 3,
      grandetBufferTime: 15
    })
  })

  it('uses the xhigh profile as the desktop auto baseline', () => {
    expect(performanceProfile('auto', 'darwin')).toEqual(performanceProfile('xhigh', 'darwin'))
    expect(performanceProfile('auto', 'darwin')).toMatchObject({
      lowFrameRateMode: false,
      screenshotInterval: 500,
      selectionPollInterval: 0.1,
      runOrderDelay: 3
    })
  })
})
