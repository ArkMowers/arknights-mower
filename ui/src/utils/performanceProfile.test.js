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

  it('keeps Android out of high performance for explicit and automatic modes', () => {
    expect(normalizePerformanceMode('high', false, 'android')).toBe('medium')
    expect(normalizePerformanceMode('xhigh', false, 'android')).toBe('medium')
    expect(performanceProfile('high', 'android')).toEqual(performanceProfile('medium', 'android'))
    expect(normalizePerformanceMode('high', false, 'darwin')).toBe('high')
  })

  it('migrates custom to its saved click strategy', () => {
    expect(normalizePerformanceMode('custom', false, 'darwin')).toBe('high')
    expect(normalizePerformanceMode('custom', true, 'darwin')).toBe('medium')
    expect(normalizePerformanceMode('custom', false, 'android')).toBe('medium')
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

  it('uses the Android medium profile as the visible auto baseline', () => {
    expect(performanceProfile('auto', 'android')).toMatchObject({
      screenshotInterval: 500,
      selectionPollInterval: 0.5,
      selectionTransitionTimeout: 2.5,
      runOrderDelay: 5,
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
