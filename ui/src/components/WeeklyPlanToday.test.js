import { createRenderer, h, KeepAlive, nextTick, reactive, ref, ssrContextKey } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import MaaWeekly from './MaaWeekly.vue'
import MaaWeeklyTable from './MaaWeeklyTable.vue'
import { WEEKDAYS } from '@/utils/maa_weekly_plan'

const state = vi.hoisted(() => ({ config: {}, resource: null }))
vi.mock('@/stores/config', () => ({ useConfigStore: () => ({}) }))
vi.mock('@/stores/resourceVersion', () => ({ useResourceVersionStore: () => state.resource }))
vi.mock('pinia', () => ({ storeToRefs: () => state.config }))
vi.mock('axios', () => ({ default: { get: vi.fn(async () => ({ data: [] })) } }))

let app

function mountEditor(component, cached = false) {
  const node = () => ({ children: [], parent: null })
  const renderer = createRenderer({
    createElement: node,
    createText: node,
    createComment: node,
    setText() {},
    setElementText() {},
    patchProp() {},
    parentNode: (child) => child.parent,
    nextSibling: () => null,
    insert(child, parent, anchor) {
      if (child.parent) child.parent.children.splice(child.parent.children.indexOf(child), 1)
      child.parent = parent
      const index = anchor ? parent.children.indexOf(anchor) : -1
      parent.children.splice(index < 0 ? parent.children.length : index, 0, child)
    },
    remove(child) {
      child.parent?.children.splice(child.parent.children.indexOf(child), 1)
      child.parent = null
    }
  })
  const shown = ref(true)
  const editor = { ...component, render: () => h('div') }
  app = renderer.createApp({
    setup: () => () =>
      cached ? h(KeepAlive, null, { default: () => (shown.value ? h(editor) : null) }) : h(editor)
  })
  app.provide(ssrContextKey, { modules: new Set() })
  app.provide('mobile', false)
  app.mount(node())
  const instance = cached
    ? app._instance.subTree.component.subTree.component
    : app._instance.subTree.component
  return { shown, instance, today: () => WEEKDAYS.filter(instance.setupState.isToday) }
}

beforeEach(() => {
  vi.useFakeTimers()
  vi.setSystemTime(new Date('2026-11-08T19:59:59.000Z'))
  const window = new EventTarget()
  window.localStorage = { getItem: () => null, setItem: vi.fn() }
  vi.stubGlobal('window', window)
  const document = new EventTarget()
  document.visibilityState = 'visible'
  vi.stubGlobal('document', document)
  state.resource = reactive({ info: { current_version: 'old' } })
  state.config = { maa_weekly_plan: ref([{ weekday: '周一', stage: ['1-7'] }]) }
})

afterEach(() => {
  app?.unmount()
  app = undefined
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

describe.each([
  ['列表计划', MaaWeekly],
  ['表格计划', MaaWeeklyTable]
])('%s 的今天高亮', (_, component) => {
  it('缓存页面跨过换日后返回，更新日期并保留计划和组件', async () => {
    const { shown, instance, today } = mountEditor(component, true)
    const plan = state.config.maa_weekly_plan.value
    expect(today()).toEqual(['周日'])
    shown.value = false
    await nextTick()
    expect(vi.getTimerCount()).toBe(0)
    vi.setSystemTime(new Date('2026-11-08T20:00:00.000Z'))
    window.dispatchEvent(new Event('focus'))
    document.dispatchEvent(new Event('visibilitychange'))
    expect(vi.getTimerCount()).toBe(0)
    expect(today()).toEqual(['周日'])
    shown.value = true
    await nextTick()
    expect(app._instance.subTree.component.subTree.component).toBe(instance)
    expect(today()).toEqual(['周一'])
    expect(state.config.maa_weekly_plan.value).toBe(plan)
    expect(plan).toEqual([{ weekday: '周一', stage: ['1-7'] }])
  })

  it('页面保持打开时在北京时间四点更新，午夜仍属于前一个游戏日', async () => {
    vi.setSystemTime(new Date('2026-11-08T15:59:59.000Z'))
    const { today } = mountEditor(component)
    expect(today()).toEqual(['周日'])
    await vi.advanceTimersByTimeAsync(1000)
    expect(today()).toEqual(['周日'])
    await vi.advanceTimersByTimeAsync(4 * 60 * 60 * 1000)
    expect(today()).toEqual(['周一'])
    expect(vi.getTimerCount()).toBe(1)
    await vi.advanceTimersByTimeAsync(24 * 60 * 60 * 1000)
    expect(today()).toEqual(['周二'])
    expect(vi.getTimerCount()).toBe(1)
    app.unmount()
    app = undefined
    expect(vi.getTimerCount()).toBe(0)
  })

  it.each(['focus', 'visibilitychange'])('后台恢复通过 %s 校正日期并清理监听', async (event) => {
    const target = event === 'focus' ? window : document
    const remove = vi.spyOn(target, 'removeEventListener')
    const { today } = mountEditor(component)
    expect(today()).toEqual(['周日'])
    vi.setSystemTime(new Date('2026-11-08T20:00:00.000Z'))
    target.dispatchEvent(new Event(event))
    await nextTick()
    expect(today()).toEqual(['周一'])
    expect(vi.getTimerCount()).toBe(1)
    app.unmount()
    app = undefined
    expect(remove).toHaveBeenCalledWith(event, expect.any(Function))
    expect(vi.getTimerCount()).toBe(0)
  })
})
