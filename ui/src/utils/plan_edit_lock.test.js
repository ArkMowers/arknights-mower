import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { usePlanEditLock } from './plan_edit_lock'

function storage() {
  const state = new Map()
  return {
    getItem: (key) => state.get(key) ?? null,
    setItem: (key, value) => state.set(key, value),
    removeItem: (key) => state.delete(key)
  }
}

describe('manual plan edit lock', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => vi.useRealTimers())

  it('defaults to unlocked and permits mutations', () => {
    const guard = usePlanEditLock({ storage: storage() })
    expect(guard.locked.value).toBe(false)
    expect(guard.isEditable()).toBe(true)
  })

  it('blocks guarded mutations only when manually enabled', () => {
    const guard = usePlanEditLock({ storage: storage() })
    guard.lock()
    expect(guard.isEditable()).toBe(false)
    expect(guard.noteActivity()).toBe(false)
    guard.unlock()
    expect(guard.isEditable()).toBe(true)
  })

  it('persists explicit manual lock and unlock, not a first-visit lock', () => {
    const saved = storage()
    expect(usePlanEditLock({ storage: saved }).locked.value).toBe(false)
    const guard = usePlanEditLock({ storage: saved })
    guard.lock()
    expect(usePlanEditLock({ storage: saved }).locked.value).toBe(true)
    guard.unlock()
    expect(usePlanEditLock({ storage: saved }).locked.value).toBe(false)
  })

  it('has no idle timeout and dispose does not change the choice', () => {
    const saved = storage()
    const guard = usePlanEditLock({ storage: saved })
    vi.advanceTimersByTime(24 * 60 * 60 * 1000)
    expect(guard.isEditable()).toBe(true)
    expect(guard.noteActivity()).toBe(true)
    expect(vi.getTimerCount()).toBe(0)
    guard.lock()
    guard.dispose()
    expect(usePlanEditLock({ storage: saved }).locked.value).toBe(true)
  })

  it('falls back to safe in-memory behavior if storage is blocked', () => {
    const blocked = {
      getItem: () => {
        throw new Error('blocked')
      },
      setItem: () => {
        throw new Error('blocked')
      },
      removeItem: () => {
        throw new Error('blocked')
      }
    }
    const guard = usePlanEditLock({ storage: blocked })
    expect(guard.isEditable()).toBe(true)
    expect(() => guard.lock()).not.toThrow()
    expect(guard.isEditable()).toBe(false)
    expect(() => guard.unlock()).not.toThrow()
    expect(guard.isEditable()).toBe(true)
    expect(usePlanEditLock({ storage: null }).isEditable()).toBe(true)
  })
})
