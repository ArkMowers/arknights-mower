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
  expect(state.client.get).toHaveBeenCalledWith(expect.stringMatching(/\/stage\/event-rerun$/))
  expect(panel.event.value.key).toBe(live.event.key)
  expect(panel.progress.value['OS-1']).toBe('completed')
  expect(panel.progress.value['OS-10']).toBe('attempted')
  expect(panel.failureReasons.value).toEqual({})
})

it('saves and clears a completion for the displayed opening', async () => {
  await panel.refreshStatus()
  state.client.patch = vi
    .fn()
    .mockResolvedValueOnce({ data: { ...live, progress: {} } })
    .mockResolvedValueOnce({ data: live })
  await panel.setCompleted('OS-1', false)
  expect(panel.progress.value['OS-1']).toBeUndefined()
  await panel.setCompleted('OS-1', true)
  expect(panel.progress.value['OS-1']).toBe('completed')
  expect(state.client.patch.mock.calls.map(([, body]) => body)).toEqual([
    { event_key: live.event.key, stage: 'OS-1', expected: 'completed', completed: false },
    { event_key: live.event.key, stage: 'OS-1', expected: 'pending', completed: true }
  ])
})

it('refreshes conflicting edits and prevents changes during a battle', async () => {
  await panel.refreshStatus()
  state.client.patch = vi.fn().mockRejectedValue({ response: { data: { message: '状态已变更' } } })
  state.client.get.mockResolvedValue({ data: { ...live, progress: { 'OS-10': 'running' } } })
  await panel.setCompleted('OS-10', false)
  expect(panel.saveError.value).toBe('状态已变更')
  expect(panel.progress.value['OS-10']).toBe('running')
  await panel.setCompleted('OS-10', true)
  expect(state.client.patch).toHaveBeenCalledTimes(1)
})

it.each([false, true])(
  'keeps the failed state as the edit precondition and clears its reason (completed=%s)',
  async (completed) => {
    state.client.get.mockResolvedValueOnce({
      data: {
        ...live,
        progress: { 'OS-10': 'failed' },
        failure_reasons: { 'OS-10': '未能确认关卡详情' }
      }
    })
    await panel.refreshStatus()
    expect(panel.failureReasons.value['OS-10']).toBe('未能确认关卡详情')
    const progress = completed ? { 'OS-10': 'completed' } : {}
    state.client.patch = vi
      .fn()
      .mockResolvedValue({ data: { ...live, progress, failure_reasons: {} } })
    await panel.setCompleted('OS-10', completed)
    expect(state.client.patch).toHaveBeenCalledWith(expect.stringMatching(/event-rerun$/), {
      event_key: live.event.key,
      stage: 'OS-10',
      expected: 'failed',
      completed
    })
    expect(panel.progress.value).toEqual(progress)
    expect(panel.failureReasons.value).toEqual({})
  }
)

it('clears prior failure reasons on refresh when the event ends or a response lacks reasons', async () => {
  state.client.get
    .mockResolvedValueOnce({
      data: { ...live, progress: { 'OS-10': 'failed' }, failure_reasons: { 'OS-10': '未通过关卡' } }
    })
    .mockResolvedValueOnce({ data: { ...live, progress: { 'OS-10': 'failed' } } })
    .mockResolvedValueOnce({ data: { event: null, progress: {} } })
  await panel.refreshStatus()
  await panel.refreshStatus()
  expect(panel.progress.value['OS-10']).toBe('failed')
  expect(panel.failureReasons.value).toEqual({})
  await panel.refreshStatus()
  expect(panel.event.value).toBe(null)
})
