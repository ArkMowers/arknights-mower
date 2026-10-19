import { nextTick } from 'vue'
import { describe, expect, it, vi } from 'vitest'
import { collectWindowHitRegions, createWindowHitRegionSync } from './hit-regions.js'

function makeElement({ x = 0, y = 0, width = 200, height = 36, edge = null } = {}) {
  return {
    getAttribute: () => edge,
    getBoundingClientRect: vi.fn(() => ({ left: x, top: y, width, height }))
  }
}

function makeWindow(elements = []) {
  const windowObject = new EventTarget()
  windowObject.document = {
    documentElement: { clientWidth: 300, clientHeight: 200 },
    querySelectorAll: vi.fn(() => elements)
  }
  windowObject.ResizeObserver = class {
    constructor(callback) {
      this.callback = callback
      this.observe = vi.fn()
      this.unobserve = vi.fn()
      this.disconnect = vi.fn()
      windowObject.observer = this
    }
  }
  return windowObject
}

async function flushLayout() {
  await nextTick()
  await Promise.resolve()
}

describe('native window hit regions', () => {
  it('clips regions to the viewport and gives resize corners priority over edges and dragging', () => {
    const windowObject = makeWindow([
      makeElement({ x: -10, width: 310 }),
      makeElement({ x: -5, width: 310, height: 6, edge: 'top' }),
      makeElement({ width: 10, height: 10, edge: 'top-left' })
    ])
    const { payload } = collectWindowHitRegions(windowObject)

    expect(payload.width).toBe(300)
    expect(payload.height).toBe(200)
    expect(payload.regions[0]).toEqual({
      kind: 'resize',
      edge: 'top-left',
      x: 0,
      y: 0,
      width: 10,
      height: 10
    })
    expect(payload.regions[1]).toEqual({
      kind: 'resize',
      edge: 'top',
      x: 10,
      y: 0,
      width: 290,
      height: 6
    })
    for (const [index, region] of payload.regions.entries()) {
      expect(region.x).toBeGreaterThanOrEqual(0)
      expect(region.y).toBeGreaterThanOrEqual(0)
      expect(region.x + region.width).toBeLessThanOrEqual(payload.width)
      expect(region.y + region.height).toBeLessThanOrEqual(payload.height)
      for (const other of payload.regions.slice(index + 1)) {
        const intersects =
          region.x < other.x + other.width &&
          other.x < region.x + region.width &&
          region.y < other.y + other.height &&
          other.y < region.y + region.height
        expect(intersects).toBe(false)
      }
    }
    expect(payload.regions.reduce((total, region) => total + region.width * region.height, 0)).toBe(
      300 * 36
    )
  })

  it('ignores hidden, invalid and offscreen rectangles and bounds the payload size', () => {
    const windowObject = makeWindow([
      makeElement({ width: 0 }),
      makeElement({ x: Number.NaN }),
      makeElement({ y: 300 }),
      makeElement({ edge: 'unknown' })
    ])
    expect(collectWindowHitRegions(windowObject).payload.regions).toEqual([])

    windowObject.document.querySelectorAll.mockReturnValue(
      Array.from({ length: 200 }, (_, x) => makeElement({ x, width: 1, height: 1 }))
    )
    expect(collectWindowHitRegions(windowObject).payload.regions).toHaveLength(128)
  })

  it('measures after layout and observes changes without repeatedly sending unchanged geometry', async () => {
    const element = makeElement()
    const windowObject = makeWindow([element])
    const send = vi.fn(async () => true)
    const sync = createWindowHitRegionSync({ windowObject, send })

    sync.setEnabled(true)
    expect(send).not.toHaveBeenCalled()
    await flushLayout()
    expect(send).toHaveBeenCalledOnce()
    expect(windowObject.observer.observe).toHaveBeenCalledWith(element)

    windowObject.observer.callback()
    windowObject.dispatchEvent(new Event('resize'))
    await flushLayout()
    expect(send).toHaveBeenCalledOnce()

    element.getBoundingClientRect.mockReturnValue({ left: 25, top: 0, width: 100, height: 36 })
    windowObject.observer.callback()
    await flushLayout()
    expect(send).toHaveBeenCalledTimes(2)
    expect(send.mock.lastCall[0].regions[0].x).toBe(25)

    windowObject.document.querySelectorAll.mockReturnValue([])
    sync.schedule()
    await flushLayout()
    expect(windowObject.observer.unobserve).toHaveBeenCalledWith(element)
    expect(send.mock.lastCall[0].regions).toEqual([])
    sync.dispose()
  })

  it('serializes geometry updates and clears old regions when native decorations take over', async () => {
    const element = makeElement()
    const windowObject = makeWindow([element])
    let finishFirst
    const send = vi
      .fn()
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            finishFirst = resolve
          })
      )
      .mockResolvedValue(true)
    const sync = createWindowHitRegionSync({ windowObject, send })
    sync.setEnabled(true)
    await flushLayout()

    element.getBoundingClientRect.mockReturnValue({ left: 25, top: 0, width: 100, height: 36 })
    sync.schedule()
    await flushLayout()
    expect(send).toHaveBeenCalledOnce()

    sync.setEnabled(false)
    finishFirst(true)
    await flushLayout()
    expect(send).toHaveBeenCalledTimes(2)
    expect(send.mock.lastCall[0]).toEqual({ width: 300, height: 200, regions: [] })
    expect(windowObject.observer.disconnect).toHaveBeenCalledOnce()
    windowObject.dispatchEvent(new Event('resize'))
    await flushLayout()
    expect(send).toHaveBeenCalledTimes(2)
    sync.dispose()
  })

  it('retries a refused update only after a new relevant layout observation', async () => {
    const windowObject = makeWindow([makeElement()])
    const send = vi.fn().mockResolvedValueOnce(false).mockResolvedValue(true)
    const sync = createWindowHitRegionSync({ windowObject, send })
    sync.setEnabled(true)
    await flushLayout()
    expect(send).toHaveBeenCalledOnce()
    await flushLayout()
    expect(send).toHaveBeenCalledOnce()

    windowObject.observer.callback()
    await flushLayout()
    expect(send).toHaveBeenCalledTimes(2)
    sync.dispose()
  })

  it('releases observers and cancels queued measurements on disposal', async () => {
    const windowObject = makeWindow([makeElement()])
    const send = vi.fn(async () => true)
    const sync = createWindowHitRegionSync({ windowObject, send })
    sync.setEnabled(true)
    const observer = windowObject.observer
    sync.dispose()
    windowObject.dispatchEvent(new Event('resize'))
    observer.callback()
    await flushLayout()

    expect(send).not.toHaveBeenCalled()
    expect(observer.disconnect).toHaveBeenCalledOnce()
  })
})
