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

function createGuard(saved = storage()) {
  const documentTarget = new EventTarget()
  const guard = usePlanEditLock({ storage: saved, documentTarget })
  guard.start()
  return { guard, documentTarget }
}

describe('plan edit lock', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => {
    vi.clearAllTimers()
    vi.useRealTimers()
  })

  it('defaults to unlocked and permits mutations', () => {
    const { guard } = createGuard()
    expect(guard.locked.value).toBe(false)
    expect(guard.isEditable()).toBe(true)
    guard.dispose()
  })

  it('persists manual lock and unlock', () => {
    const saved = storage()
    const { guard } = createGuard(saved)
    guard.lock()
    expect(guard.isEditable()).toBe(false)
    expect(guard.noteActivity()).toBe(false)
    expect(usePlanEditLock({ storage: saved }).locked.value).toBe(true)
    guard.unlock()
    expect(guard.isEditable()).toBe(true)
    expect(usePlanEditLock({ storage: saved }).locked.value).toBe(false)
    guard.dispose()
  })

  it('locks after three minutes without activity and remembers the lock', () => {
    const saved = storage()
    const { guard } = createGuard(saved)
    vi.advanceTimersByTime(3 * 60 * 1000 - 1)
    expect(guard.isEditable()).toBe(true)
    vi.advanceTimersByTime(1)
    expect(guard.isEditable()).toBe(false)
    expect(usePlanEditLock({ storage: saved }).locked.value).toBe(true)
    guard.dispose()
  })

  it('resets the idle period when the user interacts with the page', () => {
    const { guard, documentTarget } = createGuard()
    vi.advanceTimersByTime(2 * 60 * 1000)
    documentTarget.dispatchEvent(new Event('pointermove'))
    vi.advanceTimersByTime(3 * 60 * 1000 - 1)
    expect(guard.isEditable()).toBe(true)
    vi.advanceTimersByTime(1)
    expect(guard.isEditable()).toBe(false)
    guard.dispose()
  })

  it('does not lock immediately when the page goes into the background', () => {
    const { guard, documentTarget } = createGuard()
    documentTarget.dispatchEvent(new Event('visibilitychange'))
    expect(guard.isEditable()).toBe(true)
    guard.dispose()
  })

  it('removes the idle timer and activity listeners when leaving the page', () => {
    const { guard, documentTarget } = createGuard()
    guard.dispose()
    expect(vi.getTimerCount()).toBe(0)
    vi.advanceTimersByTime(24 * 60 * 60 * 1000)
    documentTarget.dispatchEvent(new Event('pointermove'))
    expect(guard.isEditable()).toBe(true)
    expect(vi.getTimerCount()).toBe(0)
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
    const { guard } = createGuard(blocked)
    expect(guard.isEditable()).toBe(true)
    expect(() => guard.lock()).not.toThrow()
    expect(guard.isEditable()).toBe(false)
    expect(() => guard.unlock()).not.toThrow()
    expect(guard.isEditable()).toBe(true)
    guard.dispose()
    expect(usePlanEditLock({ storage: null }).isEditable()).toBe(true)
  })
})
