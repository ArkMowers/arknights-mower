import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { effectScope } from 'vue'
import Component from './EventRerun.vue'

const state = vi.hoisted(() => ({
  client: null,
  mount: null,
  unmount: null
}))
vi.mock('vue', async (original) => ({
  ...(await original()),
  inject: (key) => (key === 'axios' ? state.client : false),
  onMounted: (callback) => (state.mount = callback),
  onUnmounted: (callback) => (state.unmount = callback),
  useSSRContext: () => ({ modules: new Set() })
}))
vi.mock('@/stores/resourceVersion', () => ({ useResourceVersionStore: () => ({ info: {} }) }))

const live = {
  event: {
    key: 'act46sre:100',
    name: '雪山降临1101',
    stages: [{ code: 'OS-1' }, { code: 'OS-10' }]
  },
  stage_seconds: 240,
  progress: { 'OS-1': 'completed', 'OS-10': 'attempted' }
}
let scope
let panel

beforeEach(() => {
  vi.useFakeTimers()
  state.client = { get: vi.fn().mockResolvedValue({ data: live }) }
  scope = effectScope()
  panel = scope.run(() => Component.setup({}, { expose: () => {} }))
})

afterEach(() => {
  state.unmount?.()
  scope.stop()
  vi.useRealTimers()
})

it('reads the current opening and displays each ordinary stage outcome', async () => {
  await panel.refreshStatus()
  expect(state.client.get).toHaveBeenCalledWith(
    expect.stringMatching(/\/maa-long-task-status\?kind=event_rerun$/)
  )
  expect(panel.event.value.key).toBe(live.event.key)
  expect(panel.statusLabel('OS-1')).toBe('已完成')
  expect(panel.statusLabel('OS-10')).toBe('已启动，结算待确认')
  expect(panel.statusLabel('OS-3')).toBe('待执行')
})
