import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { readSkeletonShape, saveSkeletonShape } from './skeletonShape'

describe('skeleton shape', () => {
  let entries
  beforeEach(() => {
    entries = new Map()
    vi.stubGlobal('localStorage', {
      getItem: (key) => (entries.has(key) ? entries.get(key) : null),
      setItem: (key, value) => entries.set(key, String(value))
    })
  })
  afterEach(() => vi.unstubAllGlobals())

  it('uses the fallback until a page saves its loaded shape', () => {
    const fallback = { ok: true, groups: [['A', 8]] }
    expect(readSkeletonShape('depot', fallback)).toEqual(fallback)

    saveSkeletonShape('depot', { ok: false, groups: [] })
    expect(readSkeletonShape('depot', fallback)).toEqual({ ok: false, groups: [] })
  })

  it('keeps fallback fields the saved shape lacks and ignores damaged records', () => {
    saveSkeletonShape('report', { hasData: false })
    expect(readSkeletonShape('report', { hasData: true, rows: 6 })).toEqual({
      hasData: false,
      rows: 6
    })

    localStorage.setItem('mower_skeleton_shape:report', '{broken')
    expect(readSkeletonShape('report', { hasData: true })).toEqual({ hasData: true })
    localStorage.setItem('mower_skeleton_shape:report', '[1]')
    expect(readSkeletonShape('report', { hasData: true })).toEqual({ hasData: true })
  })
})
