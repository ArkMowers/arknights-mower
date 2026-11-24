import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  BOOT_FRAME_FALLBACK,
  BOOT_LEAVE_DURATION,
  BOOT_PAGE_LIMIT,
  createBootScreen
} from './bootScreen'

function fakeElement() {
  const classes = new Set()
  const nodes = {
    '[data-boot-error]': { textContent: '' }
  }
  return {
    classes,
    nodes,
    attributes: {},
    removed: false,
    classList: { add: (name) => classes.add(name) },
    querySelector: (selector) => nodes[selector] ?? null,
    setAttribute(name, value) {
      this.attributes[name] = value
    },
    remove() {
      this.removed = true
    }
  }
}

function setup({ hidden = false } = {}) {
  const element = fakeElement()
  const frames = []
  const windowObject = { requestAnimationFrame: (callback) => frames.push(callback) }
  const documentObject = { hidden }
  const screen = createBootScreen({ element, windowObject, documentObject })
  const flushFrames = () => {
    while (frames.length) frames.shift()()
  }
  return { element, frames, flushFrames, screen }
}

describe('startup screen', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => vi.useRealTimers())

  it('is already revealed when the page has no startup screen', () => {
    const screen = createBootScreen({ element: null })
    expect(screen.active).toBe(false)
    expect(screen.revealed.value).toBe(true)
    screen.release('app')
    screen.fail('x')
    expect(screen.hold('log')).toBeTypeOf('function')
  })

  it('fades out one frame after the last part is ready, then removes itself', () => {
    const { element, frames, flushFrames, screen } = setup()
    const releaseLog = screen.hold('log')
    screen.release('app')
    expect(frames).toHaveLength(0)
    expect(screen.revealed.value).toBe(false)

    releaseLog()
    expect(screen.revealed.value).toBe(false)
    flushFrames()
    expect(screen.revealed.value).toBe(true)
    expect(element.classes.has('mower-boot--leaving')).toBe(true)
    expect(element.attributes['aria-busy']).toBe('false')
    expect(element.removed).toBe(false)
    vi.advanceTimersByTime(BOOT_LEAVE_DURATION + 60)
    expect(element.removed).toBe(true)
  })

  it('keeps waiting when a page takes a hold before the scheduled frame', () => {
    const { flushFrames, screen } = setup()
    screen.release('app')
    const releaseLog = screen.hold('log')
    flushFrames()
    expect(screen.revealed.value).toBe(false)
    releaseLog()
    flushFrames()
    expect(screen.revealed.value).toBe(true)
  })

  it('stops waiting for a page after the page limit but not for the configuration', () => {
    const { flushFrames, screen } = setup()
    screen.hold('log')
    vi.advanceTimersByTime(BOOT_PAGE_LIMIT)
    flushFrames()
    expect(screen.revealed.value).toBe(false)
    screen.release('app')
    flushFrames()
    expect(screen.revealed.value).toBe(true)
  })

  it('shows no notice while loading slowly and keeps a failure on screen', () => {
    const { element, flushFrames, screen } = setup()
    vi.advanceTimersByTime(30000)
    expect([...element.classes]).toEqual([])
    expect(screen.revealed.value).toBe(false)

    screen.fail('无法读取 Mower 配置')
    screen.release('app')
    flushFrames()
    vi.runAllTimers()
    expect(element.nodes['[data-boot-error]'].textContent).toBe('无法读取 Mower 配置')
    expect(element.classes.has('mower-boot--failed')).toBe(true)
    expect(screen.revealed.value).toBe(false)
  })

  it('still fades out when animation frames are paused', () => {
    const { frames, screen } = setup()
    screen.release('app')
    expect(frames).toHaveLength(1)
    vi.advanceTimersByTime(BOOT_FRAME_FALLBACK - 1)
    expect(screen.revealed.value).toBe(false)
    vi.advanceTimersByTime(1)
    expect(screen.revealed.value).toBe(true)
  })

  it('is removed at once while the window is hidden', () => {
    const { element, frames, screen } = setup({ hidden: true })
    screen.release('app')
    expect(frames).toHaveLength(0)
    expect(screen.revealed.value).toBe(true)
    expect(element.removed).toBe(true)
  })
})
