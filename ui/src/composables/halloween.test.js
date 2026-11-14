import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createRenderer, defineComponent, h, nextTick, ref } from 'vue'
import { provideHalloweenSeason, useHalloweenSeason } from './halloween'

const node = (tag) => ({ tag, text: '', children: [], parent: null })
const renderer = createRenderer({
  createElement: node,
  createText: (text) => ({ ...node('#text'), text }),
  createComment: () => node('#comment'),
  setText: (element, text) => (element.text = text),
  setElementText(element, text) {
    element.text = text
    element.children = []
  },
  patchProp() {},
  insert(element, parent, anchor) {
    const previousIndex = element.parent?.children.indexOf(element) ?? -1
    if (previousIndex >= 0) element.parent.children.splice(previousIndex, 1)
    element.parent = parent
    const index = anchor ? parent.children.indexOf(anchor) : -1
    if (index >= 0) parent.children.splice(index, 0, element)
    else parent.children.push(element)
  },
  remove(element) {
    const index = element.parent?.children.indexOf(element) ?? -1
    if (index >= 0) element.parent.children.splice(index, 1)
    element.parent = null
  },
  parentNode: (element) => element.parent,
  nextSibling: (element) => element.parent?.children[element.parent.children.indexOf(element) + 1]
})

let mounted
let documentTarget

function mountConsumers(withProvider = true, preference) {
  const consumers = []
  let provided
  const Consumer = defineComponent({
    setup() {
      const active = useHalloweenSeason()
      consumers.push(active)
      return () => h('span', String(active.value))
    }
  })
  const root = node('root')
  mounted = renderer.createApp({
    setup() {
      if (withProvider) provided = provideHalloweenSeason(preference)
      return () => h('div', [h(Consumer), h(Consumer), h(Consumer)])
    }
  })
  mounted.mount(root)
  return {
    provided,
    values: () => consumers.map((active) => active.value),
    rendered: () => root.children[0].children.map((element) => element.text)
  }
}

beforeEach(() => {
  vi.useFakeTimers()
  documentTarget = new EventTarget()
  documentTarget.visibilityState = 'visible'
  vi.stubGlobal('document', documentTarget)
})

afterEach(() => {
  mounted?.unmount()
  mounted = null
  vi.clearAllTimers()
  vi.restoreAllMocks()
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

describe('shared Halloween season', () => {
  it.each([
    ['outside the season', new Date(2026, 6, 1, 12), false],
    ['during the season', new Date(2026, 9, 31, 12), true]
  ])(
    'applies explicit choices immediately %s and restores automatic dates',
    async (_name, date, automatic) => {
      vi.setSystemTime(date)
      const preference = ref('auto')
      const state = mountConsumers(true, preference)
      expect(state.values()).toEqual([automatic, automatic, automatic])
      for (const [mode, expected] of [
        ['on', true],
        ['off', false],
        ['auto', automatic]
      ]) {
        preference.value = mode
        await nextTick()
        expect(state.values()).toEqual([expected, expected, expected])
        expect(state.rendered()).toEqual([String(expected), String(expected), String(expected)])
        expect(vi.getTimerCount()).toBe(1)
      }
    }
  )

  it.each([
    ['on', true],
    ['off', false]
  ])(
    'keeps %s across midnight and resynchronizes when returning to auto',
    async (mode, expected) => {
      vi.setSystemTime(new Date(2026, 10, 1, 23, 59, 59))
      const preference = ref(mode)
      const state = mountConsumers(true, preference)
      await vi.advanceTimersByTimeAsync(1000)
      expect(state.values()).toEqual([expected, expected, expected])
      preference.value = 'auto'
      await nextTick()
      expect(state.values()).toEqual([false, false, false])
    }
  )

  it.each([
    ['October 24', new Date(2026, 9, 23, 23, 59, 59), false, true],
    ['November 1', new Date(2026, 9, 31, 23, 59, 59), true, true],
    ['November 2', new Date(2026, 10, 1, 23, 59, 59), true, false]
  ])(
    'updates every consumer at local midnight on %s with one clock',
    async (_name, date, before, after) => {
      vi.setSystemTime(date)
      const state = mountConsumers()
      expect(state.provided.value).toBe(before)
      expect(state.values()).toEqual([before, before, before])
      expect(state.rendered()).toEqual([String(before), String(before), String(before)])
      expect(vi.getTimerCount()).toBe(1)

      await vi.advanceTimersByTimeAsync(1000)

      expect(state.provided.value).toBe(after)
      expect(state.values()).toEqual([after, after, after])
      expect(state.rendered()).toEqual([String(after), String(after), String(after)])
      expect(vi.getTimerCount()).toBe(1)
    }
  )

  it('resynchronizes a visible page after clock changes and removes its clock and listener on unmount', async () => {
    vi.setSystemTime(new Date(2026, 9, 30, 12))
    const addListener = vi.spyOn(documentTarget, 'addEventListener')
    const removeListener = vi.spyOn(documentTarget, 'removeEventListener')
    const state = mountConsumers()
    expect(state.values()).toEqual([true, true, true])
    expect(addListener).toHaveBeenCalledTimes(1)
    const listener = addListener.mock.calls[0][1]
    expect(addListener).toHaveBeenCalledWith('visibilitychange', listener)

    vi.setSystemTime(new Date(2026, 10, 2, 12))
    documentTarget.visibilityState = 'hidden'
    documentTarget.dispatchEvent(new Event('visibilitychange'))
    expect(state.values()).toEqual([true, true, true])
    documentTarget.visibilityState = 'visible'
    documentTarget.dispatchEvent(new Event('visibilitychange'))
    expect(state.values()).toEqual([false, false, false])
    expect(vi.getTimerCount()).toBe(1)

    vi.setSystemTime(new Date(2026, 9, 24, 12))
    documentTarget.dispatchEvent(new Event('visibilitychange'))
    expect(state.values()).toEqual([true, true, true])
    expect(vi.getTimerCount()).toBe(1)
    mounted.unmount()
    mounted = null
    expect(vi.getTimerCount()).toBe(0)
    expect(removeListener).toHaveBeenCalledWith('visibilitychange', listener)

    vi.setSystemTime(new Date(2026, 10, 2, 12))
    documentTarget.dispatchEvent(new Event('visibilitychange'))
    await vi.advanceTimersByTimeAsync(2 * 86400 * 1000)
    expect(state.provided.value).toBe(true)
    expect(state.values()).toEqual([true, true, true])
    expect(vi.getTimerCount()).toBe(0)
  })

  it('lets standalone consumers read the season without creating independent clocks or listeners', () => {
    vi.setSystemTime(new Date(2026, 9, 31, 12))
    const addListener = vi.spyOn(documentTarget, 'addEventListener')
    const state = mountConsumers(false)
    expect(state.values()).toEqual([true, true, true])
    expect(state.rendered()).toEqual(['true', 'true', 'true'])
    expect(vi.getTimerCount()).toBe(0)
    expect(addListener).not.toHaveBeenCalled()
  })
})
