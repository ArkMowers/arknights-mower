import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { effectScope } from 'vue'

import LogSchedule from './LogSchedule.vue'

const state = vi.hoisted(() => ({ client: null }))
vi.mock('vue', async (original) => ({
  ...(await original()),
  useSSRContext: () => ({ modules: new Set() }),
  inject: () => state.client,
  onMounted: vi.fn(),
  onUnmounted: vi.fn()
}))

const row = (summary, level = 'INFO') => ({
  time: '2026-10-10 12:00:00',
  message: `2026-10-10 12:00:00,123 utils/task.py:42 ${level} run: ${summary}`,
  screenshot: null
})
const event = {
  id: '123',
  time_ns: new Date('2026-10-10T12:00:00').getTime() * 1e6,
  message: '失败',
  screenshots: ['errors/123/123.jpg']
}
const deferred = () => {
  let resolve, reject
  const promise = new Promise((yes, no) => {
    resolve = yes
    reject = no
  })
  return { promise, resolve, reject }
}

describe('log schedule browsing', () => {
  let scope, page
  beforeEach(() => {
    vi.spyOn(Date, 'now').mockReturnValue(new Date('2026-10-11T00:00:00Z').getTime())
    state.client = { get: vi.fn(), post: vi.fn(), delete: vi.fn() }
    scope = effectScope()
    page = scope.run(() => LogSchedule.setup({}, { expose: vi.fn() }))
  })
  afterEach(() => {
    scope.stop()
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  it('parses the file formatter and filters CRITICAL without losing traceback details', () => {
    page.logs.value = [
      row('正常'),
      {
        ...row('失败', 'CRITICAL'),
        message: row('失败', 'CRITICAL').message + '\nTraceback\n  ValueError: bad'
      }
    ]
    expect(page.visibleLogs.value.map((item) => item.summary)).toEqual(['正常', '失败'])
    page.levelFilter.value = 'CRITICAL'
    expect(page.visibleLogs.value).toHaveLength(1)
    expect(page.visibleLogs.value[0].detail).toBe('Traceback\n  ValueError: bad')
  })

  it('browses ordinary screenshots even when no log row links to a frame', async () => {
    const center = new Date('2026-10-10T12:00:00').getTime()
    const shots = [-90, 2, 60].map(
      (seconds) => `20261010-12/${(center + seconds * 1000) * 1e6}.jpg`
    )
    state.client.get.mockResolvedValue({
      data: { logs: [row('运行')], screenshots: shots, truncated: true }
    })
    await page.loadWindow(center)
    expect(page.screenshots.value).toEqual(shots)
    expect(page.imageIndex.value).toBe(1)
    expect(page.imagePath.value).toBe(shots[1])
    expect(page.truncated.value).toBe(true)
    page.moveImage(1)
    expect(page.imagePath.value).toBe(shots[2])
    page.showScreenshot(shots[0])
    expect(page.imageIndex.value).toBe(0)
    expect(page.imageFailed.value).toBe(false)
  })

  it('moves contiguous windows from the loaded center and restores time browsing after an archive', async () => {
    const center = new Date('2026-10-10T12:00:00').getTime()
    state.client.get.mockResolvedValue({ data: { logs: [], screenshots: [] } })
    await page.loadWindow(center)
    page.queryAt.value = center - 3600000
    await page.moveWindow(-1)
    expect(page.loadedAt.value).toBe(center - 600000)
    expect(state.client.get.mock.calls.at(-1)[1].params.at).toBe(center - 600000)
    page.events.value = [event]
    await page.setBrowseMode('archives')
    expect(page.activeEventId.value).toBe(event.id)
    expect(page.screenshots.value).toEqual(event.screenshots)
    await page.setBrowseMode('time')
    expect(page.activeEventId.value).toBe('')
    expect(page.loadedAt.value).toBe(center - 600000)
    expect(page.screenshots.value).toEqual([])
  })

  it('uses the loaded center for export while the date picker has an unsubmitted edit', async () => {
    const center = 1791604800000
    state.client.get.mockResolvedValue({ data: { logs: [], screenshots: [] } })
    await page.loadWindow(center)
    page.queryAt.value = center - 86400000
    const link = { click: vi.fn(), remove: vi.fn() }
    vi.stubGlobal('document', { createElement: () => link, body: { appendChild: vi.fn() } })
    vi.stubGlobal('URL', { createObjectURL: () => 'blob:test', revokeObjectURL: vi.fn() })
    await page.exportWindow()
    expect(state.client.get.mock.calls.at(-1)).toEqual([
      '/diagnostics/export',
      { params: { at: center }, responseType: 'blob' }
    ])
    expect(link.click).toHaveBeenCalledOnce()
  })

  it('ignores a superseded archive response and its loading state', async () => {
    const archiveRequest = deferred(),
      windowRequest = deferred()
    state.client.get
      .mockReturnValueOnce(archiveRequest.promise)
      .mockReturnValueOnce(windowRequest.promise)
    page.events.value = [event]
    const older = page.selectEvent(event)
    const newer = page.loadWindow(1791604800000)
    archiveRequest.resolve({ data: { logs: [row('旧归档')] } })
    await older
    expect(page.logs.value).toEqual([])
    expect(page.logLoading.value).toBe(true)
    windowRequest.resolve({ data: { logs: [row('新窗口')], screenshots: ['new.jpg'] } })
    await newer
    expect(page.logs.value[0].message).toContain('新窗口')
    expect(page.imagePath.value).toBe('new.jpg')
    expect(page.activeEventId.value).toBe('')
  })

  it('clears old evidence on a failed source change and blocks export until a successful retry', async () => {
    state.client.get.mockResolvedValueOnce({
      data: { logs: [row('旧窗口')], screenshots: ['old.jpg'] }
    })
    await page.loadWindow(1791604800000)
    state.client.get.mockRejectedValueOnce(new Error('unavailable'))
    await page.selectEvent(event)
    expect(page.logs.value).toEqual([])
    expect(page.imagePath.value).toBe('')
    expect(page.logError.value).toBeTruthy()
    expect(page.canExport.value).toBe(false)
    state.client.get.mockResolvedValueOnce({ data: { logs: [row('恢复')] } })
    page.events.value = [event]
    await page.refreshLogs()
    expect(page.canExport.value).toBe(true)
    expect(page.logs.value[0].message).toContain('恢复')
  })

  it('invalidates pending time requests when opening an empty archive tab', async () => {
    const request = deferred()
    state.client.get.mockReturnValueOnce(request.promise)
    const pending = page.loadWindow(1791604800000)
    await page.setBrowseMode('archives')
    request.resolve({ data: { logs: [row('过期')], screenshots: ['old.jpg'] } })
    await pending
    expect(page.logs.value).toEqual([])
    expect(page.imagePath.value).toBe('')
    expect(page.logLoading.value).toBe(false)
    expect(page.canExport.value).toBe(false)
  })

  it('selects an archive when its list arrives after opening the archive tab', async () => {
    const request = deferred()
    state.client.get.mockReturnValueOnce(request.promise)
    const pending = page.loadEvents()
    await page.setBrowseMode('archives')
    state.client.get.mockResolvedValueOnce({ data: { logs: [row('归档日志')] } })
    request.resolve({ data: { events: [event] } })
    await pending
    await vi.waitFor(() => expect(page.logs.value).toHaveLength(1))
    expect(page.activeEventId.value).toBe(event.id)
    expect(page.screenshots.value).toEqual(event.screenshots)
  })

  it('clears evidence when refreshing a list whose selected archive has expired', async () => {
    page.events.value = [event]
    state.client.get.mockResolvedValueOnce({ data: { logs: [row('旧归档')] } })
    await page.selectEvent(event)
    state.client.get.mockResolvedValueOnce({ data: { events: [] } })
    await page.loadEvents()
    expect(page.logs.value).toEqual([])
    expect(page.imagePath.value).toBe('')
    expect(page.canExport.value).toBe(false)
  })

  it('deletes the final archive without exposing another source or late data', async () => {
    page.events.value = [event]
    state.client.get.mockResolvedValueOnce({ data: { logs: [row('已删除')] } })
    await page.selectEvent(event)
    page.confirmDelete(event)
    state.client.delete.mockResolvedValueOnce({})
    await page.deleteEvent()
    expect(page.events.value).toEqual([])
    expect(page.logs.value).toEqual([])
    expect(page.imagePath.value).toBe('')
    expect(page.browseMode.value).toBe('archives')
    expect(page.canExport.value).toBe(false)
  })
})

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
      expect.stringContaining('/diagnostics/errors/test/logs'),
      { params: undefined }
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
