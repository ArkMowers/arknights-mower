import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createSkeletonShape, skeletonCount, skeletonList } from './skeletonShape'

describe('skeleton shape', () => {
  const key = 'mower_skeleton_shape:test'
  const shape = createSkeletonShape('test', {
    visible: true,
    cards: skeletonCount(12, 6),
    rows: skeletonList(2, skeletonCount(5), [3])
  })
  let entries
  beforeEach(() => {
    entries = new Map()
    vi.stubGlobal('localStorage', {
      getItem: (key) => entries.get(key) ?? null,
      setItem: (key, value) => entries.set(key, value),
      removeItem: (key) => entries.delete(key)
    })
  })
  afterEach(() => vi.unstubAllGlobals())

  it('keeps a successful empty layout across reads', () => {
    expect(shape.read()).toEqual({ visible: true, cards: 6, rows: [3] })
    shape.save({ visible: false, cards: 0, rows: [] })
    expect(shape.read()).toEqual({ visible: false, cards: 0, rows: [] })
  })

  it.each(['{broken', '[1]', 'null', ' '.repeat(16385)])(
    'falls back for an unreadable record (%#)',
    (raw) => {
      entries.set(key, raw)
      expect(shape.read()).toEqual({ visible: true, cards: 6, rows: [3] })
    }
  )

  it('recovers fields independently and strips obsolete data on read and write', () => {
    entries.set(key, JSON.stringify({ visible: false, cards: -1, rows: {}, detail: 'obsolete' }))
    const current = { visible: false, cards: 6, rows: [3] }
    expect(shape.read()).toEqual(current)
    expect(JSON.parse(entries.get(key))).toEqual(current)
    shape.save({ visible: 'false', cards: 13, rows: [7, 0, 3], detail: 'obsolete' })
    expect(JSON.parse(entries.get(key))).toEqual({ visible: true, cards: 12, rows: [5, 0] })
    entries.set(key, '{"cards":3.5}')
    expect(shape.read().cards).toBe(6)
  })

  it('can render with blocked storage and with a read-only cache', () => {
    entries.set(key, '{"visible":false}')
    const deny = () => {
      throw new Error('storage unavailable')
    }
    localStorage.setItem = deny
    expect(shape.read().visible).toBe(false)
    localStorage.getItem = deny
    expect(shape.read().visible).toBe(true)
    expect(() => shape.save({})).not.toThrow()
  })
})
