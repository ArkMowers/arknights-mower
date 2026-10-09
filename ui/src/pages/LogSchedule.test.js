import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { effectScope } from 'vue'

import LogSchedule from './LogSchedule.vue'

const state = vi.hoisted(() => ({ client: null }))

vi.mock('vue', async (original) => ({
  ...(await original()),
  useSSRContext: () => ({ modules: new Set() }),
  inject: () => state.client,
  onMounted: vi.fn()
}))

describe('diagnostic log timeline', () => {
  let scope, component

  beforeEach(() => {
    state.client = { get: vi.fn() }
    scope = effectScope()
    component = scope.run(() => LogSchedule.setup({}, { expose: vi.fn() }))
  })

  afterEach(() => scope.stop())

  it.each([
    [
      '2026-10-09 14:15:43,152',
      String.raw`_internal\arknights_mower\utils\device\device.py:661`,
      'DEBUG',
      'tap',
      'tap: (1589, 221)'
    ],
    [
      '2026-10-09 14:15:43',
      'arknights_mower/utils/device/device.py:661',
      'INFO',
      'tap',
      'tap: (1589, 221)'
    ],
    [
      '2026-10-09 14:15:43,483',
      String.raw`C:\Program Files\Mower\arknights_mower\solvers\base_schedule.py:1916`,
      'ERROR',
      'read_agent_mood',
      'MaaTouch 输入发送结果不明确，已停止本次动作'
    ]
  ])('parses %s %s %s log headers', async (timestamp, path, level, action, summary) => {
    const message = `${timestamp} ${path} ${level} ${action}: ${summary}`
    const row = { time: '2026-10-09 14:15:43', message, screenshot: 'errors/test/frame.jpg' }
    state.client.get.mockResolvedValueOnce({ data: { logs: [row] } })

    await component.loadWindow()

    expect(state.client.get).toHaveBeenCalledWith(
      expect.stringContaining('/diagnostics/timeline'),
      { params: { at: component.queryAt.value } }
    )
    expect(component.visibleLogs.value).toEqual([{ ...row, index: 0, level, summary, detail: '' }])
  })

  it('filters archived ERROR and DEBUG logs without losing traceback details', async () => {
    const detail =
      'Traceback (most recent call last):\n  File "session.py", line 166, in close\nValueError: 连接已关闭\n\nThe above exception was the direct cause of the following exception:\n\nTraceback (most recent call last):\n  File "session.py", line 168, in close\nRuntimeError: MaaTouch 进程异常退出：137'
    const logs = [
      {
        time: '2026-10-09 14:15:43',
        message: `2026-10-09 14:15:43,483 _internal/arknights_mower/solvers/base_schedule.py:1916 ERROR read_agent_mood: MaaTouch 输入发送结果不明确\n${detail}`
      },
      {
        time: '2026-10-09 14:15:43',
        message:
          '2026-10-09 14:15:43,406 _internal/arknights_mower/utils/device/maatouch/command.py:41 DEBUG publish: send operation: d 0 1589 221 100'
      }
    ]
    state.client.get.mockResolvedValueOnce({ data: { logs } })

    await component.selectEvent({ id: 'test', time_ns: 1791526543000000000, screenshots: [] })
    component.levelFilter.value = 'ERROR'
    component.searchText.value = 'runtimeerror'

    expect(state.client.get).toHaveBeenCalledWith(
      expect.stringContaining('/diagnostics/errors/test/logs')
    )
    expect(component.visibleLogs.value).toEqual([
      { ...logs[0], index: 0, level: 'ERROR', summary: 'MaaTouch 输入发送结果不明确', detail }
    ])

    component.levelFilter.value = 'DEBUG'
    component.searchText.value = ''
    expect(component.visibleLogs.value.map((row) => row.summary)).toEqual([
      'send operation: d 0 1589 221 100'
    ])
    expect(component.visibleLogs.value[0].level).toBe('DEBUG')
  })

  it('retains unformatted messages and their multiline details', async () => {
    state.client.get.mockResolvedValueOnce({
      data: { logs: [{ time: '2026-10-09 14:15:43', message: 'message\n  extra detail\n' }] }
    })

    await component.loadWindow()

    expect(component.visibleLogs.value[0]).toMatchObject({
      level: 'INFO',
      summary: 'message',
      detail: 'extra detail'
    })
  })
})
