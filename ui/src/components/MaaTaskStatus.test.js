import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { effectScope, nextTick, reactive } from 'vue'
import Component from './MaaTaskStatus.vue'

const state = vi.hoisted(() => ({ client: null, flush: vi.fn() }))
vi.mock('vue', async (original) => ({
  ...(await original()),
  inject: () => state.client,
  onMounted: () => {},
  useSSRContext: () => ({ modules: new Set() })
}))
vi.mock('@/stores/config', () => ({ useConfigStore: () => ({ flush_config_saves: state.flush }) }))
let scope
let component
let props
beforeEach(() => {
  vi.useFakeTimers()
  state.flush.mockReset().mockResolvedValue()
  state.client = { get: vi.fn(async () => ({ data: { completed: false } })) }
  props = reactive({ kind: 'copilot', settings: { run_id: '' } })
  scope = effectScope()
  component = scope.run(() => Component.setup(props, { expose: () => {} }))
})
afterEach(() => {
  scope.stop()
  vi.useRealTimers()
})

describe('MAA task completion status', () => {
  it.each([
    [true, '已完成', 'success'],
    [false, '待执行', 'warning']
  ])('displays %s using the saved backend status', async (completed, text, type) => {
    state.client.get.mockResolvedValue({ data: { completed } })
    await component.refresh()
    expect(component.status_text.value).toBe(text)
    expect(component.status_type.value).toBe(type)
    expect(state.flush).toHaveBeenCalledBefore(state.client.get)
  })

  it.each(['copilot', 'paradox'])(
    'summarizes progress from the corresponding %s queue',
    async (kind) => {
      props.kind = kind
      const items = ['completed', 'failed', 'running']
      state.client.get.mockResolvedValue({ data: { completed: false, items } })
      await nextTick()
      await component.refresh()
      expect(state.client.get).toHaveBeenLastCalledWith(
        expect.stringContaining('maa-long-task-status?kind=' + kind),
        expect.anything()
      )
      expect(component.status_text.value).toBe('正在执行')
      expect(component.completedItems.value).toBe(1)
      state.client.get.mockResolvedValue({
        data: { completed: false, items: ['completed', 'failed'] }
      })
      await component.refresh()
      expect(component.status_text.value).toBe('需要核对')
    }
  )

  it('rejects an old response when settings change and returns to pending for the new round', async () => {
    let resolveOld
    state.client.get.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolveOld = resolve
        })
    )
    const old = component.refresh()
    await nextTick()
    props.settings.run_id = 'new-round'
    await nextTick()
    await nextTick()
    resolveOld({ data: { completed: true } })
    await old
    expect(component.status_text.value).toBe('待执行')
    expect(component.status_type.value).toBe('warning')
  })

  it('shows a read error without claiming completion or pending', async () => {
    state.client.get.mockRejectedValue(new Error('offline'))
    await component.refresh()
    expect(component.status_text.value).toBe('状态读取失败')
    expect(component.status_type.value).toBe('default')
  })

  it('refreshes while mounted and cancels timers when the component is disposed', async () => {
    await component.refresh()
    await vi.advanceTimersByTimeAsync(5000)
    expect(state.client.get).toHaveBeenCalledTimes(2)
    scope.stop()
    await vi.advanceTimersByTimeAsync(10000)
    expect(state.client.get).toHaveBeenCalledTimes(2)
  })
})

it('shows the last garrison error while waiting for the next eligible window', async () => {
  props.kind = 'garrison'
  state.client.get.mockResolvedValue({
    data: {
      garrison: { completed: false, failed: false, count: 2, total: 31, message: '棋子身份未确认' }
    }
  })
  await nextTick()
  await component.refresh()
  expect(component.status_text.value).toBe('待执行')
  expect(component.detail.value.count).toBe(2)
  expect(component.detail.value.message).toBe('棋子身份未确认')
  expect(component.failed.value).toBe(false)
})
