import { describe, expect, it } from 'vitest'

import { clampScreenshotHeight, clampTaskHeight, RESIZER_HEIGHT } from './logLayout.js'

describe('log layout clamping', () => {
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
