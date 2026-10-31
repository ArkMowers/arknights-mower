import { describe, expect, it } from 'vitest'
import { createDeviceConnectionNavigation } from './deviceConnectionNavigation'

describe('device connection navigation', () => {
  it('creates a new request for every explicit action, including repeated actions', () => {
    const navigation = createDeviceConnectionNavigation()
    expect(navigation.request.value).toBe(null)
    expect(navigation.locked.value).toBe(false)
    const first = navigation.open('test')
    const second = navigation.open('test')
    expect(first).toEqual({ action: 'test' })
    expect(second).toEqual(first)
    expect(second).not.toBe(first)
    expect(navigation.request.value).toBe(second)
    for (const action of ['select', 'settings']) {
      expect(navigation.open(action)).toEqual({ action })
      expect(navigation.request.value.action).toBe(action)
    }
  })

  it('rejects unsupported actions without replacing the current request', () => {
    const navigation = createDeviceConnectionNavigation()
    const current = navigation.open('settings')
    for (const action of ['', 'connect', null, undefined, {}]) {
      expect(navigation.open(action)).toBe(null)
      expect(navigation.request.value).toBe(current)
    }
  })

  it('consumes only the current request and cannot consume it twice', () => {
    const navigation = createDeviceConnectionNavigation()
    const previous = navigation.open('test')
    const current = navigation.open('test')
    expect(navigation.consume(previous)).toBe(false)
    expect(navigation.consume({ action: 'test' })).toBe(false)
    expect(navigation.consume(null)).toBe(false)
    expect(navigation.request.value).toBe(current)
    expect(navigation.consume(current)).toBe(true)
    expect(navigation.request.value).toBe(null)
    expect(navigation.consume(current)).toBe(false)
    expect(navigation.consume(null)).toBe(false)
  })

  it('keeps independent navigation controllers isolated', () => {
    const first = createDeviceConnectionNavigation()
    const second = createDeviceConnectionNavigation()
    const firstRequest = first.open('test')
    const secondRequest = second.open('select')
    first.locked.value = true
    expect(second.locked.value).toBe(false)
    expect(second.consume(firstRequest)).toBe(false)
    expect(second.request.value).toBe(secondRequest)
    expect(first.consume(firstRequest)).toBe(true)
    expect(second.request.value).toBe(secondRequest)
  })
})
