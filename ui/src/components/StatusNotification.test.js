import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { effectScope, nextTick, reactive } from 'vue'
import StatusNotification from './StatusNotification.vue'

const state = vi.hoisted(() => ({ create: vi.fn(), slots: {}, updated: [] }))
vi.mock('naive-ui', () => ({ useNotification: () => ({ create: state.create }) }))
vi.mock('vue', async (original) => ({
  ...(await original()),
  useSSRContext: () => ({ modules: new Set() }),
  useSlots: () => state.slots,
  onUpdated: (callback) => state.updated.push(callback)
}))

let scope
let props
let emit
beforeEach(() => {
  state.create.mockReset().mockImplementation((options) => ({ ...options, destroy: vi.fn() }))
  state.slots = {}
  state.updated = []
  emit = vi.fn()
  props = reactive({
    show: false,
    title: '正在自动恢复',
    type: 'info',
    content: '正在重新读取设备'
  })
  scope = effectScope()
  scope.run(() => StatusNotification.setup(props, { emit, expose: () => {} }))
})
afterEach(() => scope.stop())

function latest() {
  return state.create.mock.results.at(-1).value
}

it('updates one notification during repeated progress and removes it when recovery ends', async () => {
  expect(state.create).not.toHaveBeenCalled()
  props.show = true
  await nextTick()
  const entry = latest()
  expect(entry).toMatchObject({ title: '正在自动恢复', duration: 0 })
  props.content = '已读取设备，正在读取驻员和心情'
  await nextTick()
  expect(state.create).toHaveBeenCalledOnce()
  expect(entry.content).toBe('已读取设备，正在读取驻员和心情')
  props.show = false
  await nextTick()
  expect(entry.destroy).toHaveBeenCalledOnce()
})

it('keeps a dismissed recovery hidden until a later independent recovery begins', async () => {
  props.show = true
  await nextTick()
  const entry = latest()
  entry.onClose()
  expect(emit).toHaveBeenCalledWith('close')
  entry.onAfterLeave()
  props.content = '稍后自动重试'
  await nextTick()
  expect(state.create).toHaveBeenCalledOnce()
  props.show = false
  await nextTick()
  props.show = true
  await nextTick()
  expect(state.create).toHaveBeenCalledTimes(2)
})

it('ignores an old leave callback after a later recovery begins', async () => {
  props.show = true
  await nextTick()
  const previous = latest()
  props.show = false
  await nextTick()
  props.show = true
  await nextTick()
  const current = latest()
  previous.onAfterLeave()
  props.content = '新一轮恢复正在读取设备'
  await nextTick()
  expect(state.create).toHaveBeenCalledTimes(2)
  expect(current.content).toBe('新一轮恢复正在读取设备')
})

it('preserves rich content and retry actions when slot availability changes', async () => {
  state.slots.default = () => ['服务暂时不可用，恢复状态稍后自动刷新']
  props.show = true
  await nextTick()
  const entry = latest()
  expect(entry.content().children).toContain('服务暂时不可用，恢复状态稍后自动刷新')
  const retry = vi.fn()
  state.slots.action = () => [{ type: 'button', props: { onClick: retry } }]
  state.updated.forEach((callback) => callback())
  entry.action().children[0].props.onClick()
  expect(retry).toHaveBeenCalledOnce()
  expect(state.create).toHaveBeenCalledOnce()
})

it('destroys its notification when its page unmounts', async () => {
  props.show = true
  await nextTick()
  const entry = latest()
  scope.stop()
  expect(entry.destroy).toHaveBeenCalledOnce()
})
