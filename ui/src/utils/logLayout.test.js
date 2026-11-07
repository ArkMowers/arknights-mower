import { describe, expect, it } from 'vitest'

import {
  clampScreenshotHeight,
  clampTaskHeight,
  fitRailLayout,
  RESIZER_HEIGHT
} from './logLayout.js'

describe('log layout clamping', () => {
  it('derives screenshot height from the saved rail width and actual frame aspect', () => {
    expect(fitRailLayout(640, 180, 1400, 900, 16 / 9)).toEqual({ width: 640, height: 360 })
    expect(fitRailLayout(640, 180, 1400, 900, 4 / 3)).toEqual({ width: 640, height: 480 })
    expect(fitRailLayout(320, 500, 1400, 900, 16 / 9)).toEqual({ width: 320, height: 180 })
  })

  it('keeps task space when a full-width screenshot would exceed the available height', () => {
    expect(fitRailLayout(720, 180, 1500, 400, 16 / 9)).toEqual({ width: 720, height: 259 })
  })

  it('shrinks restored large panes so log and actions remain available', () => {
    const containerHeight = 500
    const bottomReserve = 180
    const screenshot = clampScreenshotHeight(500, containerHeight, bottomReserve)
    const taskAvailable = containerHeight - screenshot - RESIZER_HEIGHT
    const task = clampTaskHeight(600, taskAvailable, bottomReserve)

    expect(screenshot + RESIZER_HEIGHT + task + bottomReserve).toBeLessThanOrEqual(containerHeight)
    expect(screenshot).toBeLessThan(500)
    expect(task).toBeLessThan(600)
  })

  it('reserves the taller mobile handles without covering screenshot, tasks or log', () => {
    const paneHeight = 400
    const handleHeight = 24
    const logHeight = 134
    const bottomReserve = logHeight + handleHeight
    const screenshot = clampScreenshotHeight(500, paneHeight, bottomReserve, 500, handleHeight)
    const task = clampTaskHeight(500, paneHeight - screenshot - handleHeight, bottomReserve)
    expect(screenshot + task + logHeight + 2 * handleHeight).toBeLessThanOrEqual(paneHeight)
    expect(task).toBeGreaterThanOrEqual(90)
  })

  it('reclamps saved sizes when a previously large container becomes smaller', () => {
    const bottomReserve = 180
    const largeScreenshot = clampScreenshotHeight(500, 1200, bottomReserve)
    const largeTask = clampTaskHeight(600, 1200 - largeScreenshot - RESIZER_HEIGHT, bottomReserve)
    const smallScreenshot = clampScreenshotHeight(500, 620, bottomReserve)
    const smallTask = clampTaskHeight(600, 620 - smallScreenshot - RESIZER_HEIGHT, bottomReserve)

    expect(largeScreenshot).toBeGreaterThan(smallScreenshot)
    expect(largeTask).toBeGreaterThan(smallTask)
    expect(smallScreenshot + RESIZER_HEIGHT + smallTask + bottomReserve).toBeLessThanOrEqual(620)
  })

  it('allows panes below the normal minimum only when the container is extremely small', () => {
    const bottomReserve = 180
    const screenshot = clampScreenshotHeight(500, 250, bottomReserve)
    const task = clampTaskHeight(600, 250 - screenshot - RESIZER_HEIGHT, bottomReserve)

    expect(screenshot + RESIZER_HEIGHT + task + bottomReserve).toBeLessThanOrEqual(250)
  })
})
