import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { parse as parseHtml } from '@vue/compiler-dom'
import { createSSRApp, watch } from 'vue'
import { renderToString } from 'vue/server-renderer'
import ReconnectingWebSocket from 'reconnecting-websocket'
import axios from 'axios'
import { useMowerStore } from './mower'
import LogOutput from '@/components/LogOutput.vue'

vi.mock('axios', () => ({ default: { get: vi.fn(), put: vi.fn(), delete: vi.fn() } }))
vi.mock('reconnecting-websocket', () => ({
  default: vi.fn(function MockSocket() {
    this.send = vi.fn()
  })
}))

afterEach(() => {
  vi.clearAllTimers()
  vi.useRealTimers()
  vi.unstubAllGlobals()
  vi.unstubAllEnvs()
  vi.clearAllMocks()
})

describe('worker status', () => {
  let store
  let status

  beforeEach(() => {
    vi.useFakeTimers()
    setActivePinia(createPinia())
    store = useMowerStore()
    status = 'stopped'
    axios.get.mockImplementation(async (url) => ({
      data: url.endsWith('/status')
        ? { status, plan_condition: [], scheduled_start_at: null }
        : [{ time: '2026-10-01T12:00:00', plan: {} }]
    }))
  })

  afterEach(() => store.$dispose())

  it.each([
    ['starting', true, '启动中'],
    ['recovering', true, '等待设备恢复'],
    ['working', true, '运行中'],
    ['sleeping', true, '休眠中'],
    ['stopped', false, '已停止']
  ])('maps %s to worker activity and display', async (value, running, label) => {
    store.start_task_polling()
    status = value
    await store.get_running()
    expect(store.status).toBe(value)
    expect(store.running).toBe(running)
    expect(store.status_label).toBe(label)
    expect(axios.get.mock.calls.filter(([url]) => url.endsWith('/task'))).toHaveLength(
      running ? 1 : 0
    )
  })

  it('restores flash pause from status and clears it for older or stopped backends', async () => {
    const pause = { id: 'window', end: '2026-10-26T18:00:00+08:00' }
    axios.get.mockResolvedValueOnce({
      data: { status: 'sleeping', plan_condition: [], maintenance_pause: pause }
    })
    await store.get_running()
    expect(store.maintenance_pause).toEqual(pause)
    axios.get.mockResolvedValueOnce({ data: { status: 'sleeping', plan_condition: [] } })
    await store.get_running()
    expect(store.maintenance_pause).toBeNull()
    store.maintenance_pause = pause
    store.running = false
    expect(store.maintenance_pause).toBeNull()
  })

  it('cancels the captured flash pause and ignores an older status response', async () => {
    store.running = true
    store.maintenance_pause = { id: 'window', end: '2026-10-26T18:00:00+08:00' }
    let resolveStatus
    axios.get.mockImplementationOnce(() => new Promise((resolve) => (resolveStatus = resolve)))
    const request = store.get_running()
    axios.delete.mockResolvedValueOnce({ data: { maintenance_pause: null } })
    await store.cancel_maintenance_pause('window')
    expect(axios.delete).toHaveBeenCalledWith('/maintenance-pause', {
      data: { id: 'window' },
      timeout: 10000
    })
    expect(store.maintenance_pause).toBeNull()
    resolveStatus({
      data: { status: 'sleeping', plan_condition: [], maintenance_pause: { id: 'window' } }
    })
    await request
    expect(store.maintenance_pause).toBeNull()
    expect(store.running).toBe(true)
  })

  it('does not clear a newer flash window when an older cancel request finishes', async () => {
    store.running = true
    store.maintenance_pause = { id: 'next-window' }
    axios.delete.mockResolvedValueOnce({ data: { maintenance_pause: null } })
    await store.cancel_maintenance_pause('old-window')
    expect(store.maintenance_pause.id).toBe('next-window')
  })

  it.each([true, false, null, undefined])(
    'reads the assistant authorization snapshot %s without saving it',
    async (enabled) => {
      axios.get.mockResolvedValue({
        data: { status: 'stopped', plan_condition: [], ai_assistant_enabled: enabled }
      })
      await store.get_running()
      expect(store.ai_assistant_enabled).toBe(typeof enabled === 'boolean' ? enabled : null)
      expect(axios.get).toHaveBeenCalledOnce()
      expect(vi.getTimerCount()).toBe(0)
    }
  )

  it('starts with unknown deployment and reads actual source or release deployment from status', async () => {
    expect(store.deployment).toBeNull()
    for (const deployment of ['source', 'release']) {
      axios.get.mockResolvedValueOnce({
        data: { status: 'stopped', plan_condition: [], deployment }
      })
      await store.get_running()
      expect(store.deployment).toBe(deployment)
    }
    expect(axios.get).toHaveBeenCalledTimes(2)
    expect(vi.getTimerCount()).toBe(0)
  })

  it.each([null, '', 'nightly', 'Source', 'frozen', true, {}, 1])(
    'clears previous source deployment when the next status contains invalid deployment %j',
    async (deployment) => {
      axios.get
        .mockResolvedValueOnce({
          data: { status: 'stopped', plan_condition: [], deployment: 'source' }
        })
        .mockResolvedValueOnce({ data: { status: 'stopped', plan_condition: [], deployment } })
      await store.get_running()
      expect(store.deployment).toBe('source')
      await store.get_running()
      expect(store.deployment).toBeNull()
      expect(vi.getTimerCount()).toBe(0)
    }
  )

  it('clears previous deployment when an older backend omits it from a new status snapshot', async () => {
    axios.get
      .mockResolvedValueOnce({
        data: { status: 'stopped', plan_condition: [], deployment: 'source' }
      })
      .mockResolvedValueOnce({ data: { status: 'stopped', plan_condition: [] } })
    await store.get_running()
    expect(store.deployment).toBe('source')
    await store.get_running()
    expect(store.deployment).toBeNull()
    expect(axios.get).toHaveBeenCalledTimes(2)
  })

  it('keeps task polling through startup and recovery and clears it only after exit', async () => {
    store.start_task_polling()
    for (const value of ['starting', 'recovering', 'working', 'sleeping']) {
      status = value
      await store.get_running()
      expect(store.running).toBe(true)
      expect(store.task_list).toHaveLength(1)
      expect(vi.getTimerCount()).toBe(1)
    }
    expect(axios.get.mock.calls.filter(([url]) => url.endsWith('/task'))).toHaveLength(1)
    status = 'stopped'
    await store.get_running()
    expect(store.running).toBe(false)
    expect(store.task_list).toEqual([])
    expect(vi.getTimerCount()).toBe(0)
  })

  it('keeps one task poll when app status and repeated page refreshes overlap', async () => {
    status = 'working'
    await store.get_running()
    await Promise.all([store.start_task_polling(), store.start_task_polling()])

    expect(axios.get.mock.calls.filter(([url]) => url.endsWith('/task'))).toHaveLength(1)
    expect(vi.getTimerCount()).toBe(1)
    await vi.advanceTimersByTimeAsync(3000)
    expect(axios.get.mock.calls.filter(([url]) => url.endsWith('/task'))).toHaveLength(2)
    expect(vi.getTimerCount()).toBe(1)
  })

  it('shows stopped immediately after Stop succeeds before the next status poll', async () => {
    status = 'recovering'
    await store.get_running()
    store.running = false
    expect(store.status_label).toBe('已停止')
  })

  it('reads the pending round stop from backend status after opening the page', async () => {
    axios.get.mockResolvedValueOnce({
      data: { status: 'working', plan_condition: [], stop_after_round: true }
    })
    await store.get_running()
    expect(store.stop_after_round).toBe(true)
    axios.get.mockResolvedValueOnce({ data: { status: 'stopped', plan_condition: [] } })
    await store.get_running()
    expect(store.stop_after_round).toBe(false)
  })

  it('sets and cancels a round stop through the backend without stopping current work', async () => {
    status = 'working'
    await store.get_running()
    axios.put.mockResolvedValueOnce({ data: { stop_after_round: true } })
    await store.set_stop_after_round(true)
    expect(axios.put).toHaveBeenCalledExactlyOnceWith('/stop-after-round', null, { timeout: 10000 })
    expect(store.running).toBe(true)
    expect(store.stop_after_round).toBe(true)
    axios.delete.mockResolvedValueOnce({ data: { stop_after_round: false } })
    await store.set_stop_after_round(false)
    expect(axios.delete).toHaveBeenCalledExactlyOnceWith('/stop-after-round', { timeout: 10000 })
    expect(store.stop_after_round).toBe(false)
  })

  it('does not let an older status response undo a confirmed round stop', async () => {
    status = 'working'
    await store.get_running()
    let resolveStatus
    axios.get.mockImplementationOnce(() => new Promise((resolve) => (resolveStatus = resolve)))
    const request = store.get_running()
    axios.put.mockResolvedValueOnce({ data: { stop_after_round: true } })
    await store.set_stop_after_round(true)
    resolveStatus({ data: { status: 'working', plan_condition: [], stop_after_round: false } })
    await request
    expect(store.stop_after_round).toBe(true)
  })

  it('keeps immediate Stop effective while the round-stop request is pending', async () => {
    status = 'working'
    await store.get_running()
    let resolveStop
    axios.put.mockImplementationOnce(() => new Promise((resolve) => (resolveStop = resolve)))
    const request = store.set_stop_after_round(true)
    store.running = false
    resolveStop({ data: { stop_after_round: true } })
    await request
    expect(store.stop_after_round).toBe(false)
    expect(store.running).toBe(false)
  })

  it('retains the previous state when a round-stop request fails', async () => {
    status = 'working'
    await store.get_running()
    axios.put.mockRejectedValueOnce(new Error('request failed'))
    await expect(store.set_stop_after_round(true)).rejects.toThrow('request failed')
    expect(store.stop_after_round).toBe(false)
    expect(store.running).toBe(true)
  })

  it('does not undo a successful Stop when an older status response arrives', async () => {
    status = 'working'
    await store.get_running()
    await store.start_task_polling()
    let resolveStatus
    axios.get.mockImplementationOnce(() => new Promise((resolve) => (resolveStatus = resolve)))
    const request = store.get_running()

    store.running = false
    resolveStatus({ data: { status: 'working', plan_condition: [] } })
    await request

    expect(store.running).toBe(false)
    expect(store.status_label).toBe('已停止')
    expect(store.task_list).toEqual([])
    expect(vi.getTimerCount()).toBe(0)
  })

  it('does not read tasks without a visible task table subscription', async () => {
    status = 'working'
    await store.get_running()
    await store.get_tasks()
    expect(axios.get).toHaveBeenCalledOnce()
    expect(vi.getTimerCount()).toBe(0)

    await store.start_task_polling()
    store.stop_task_polling()
    status = 'recovering'
    await store.get_running()
    await store.get_tasks()
    expect(axios.get.mock.calls.filter(([url]) => url.endsWith('/task'))).toHaveLength(1)
    expect(vi.getTimerCount()).toBe(0)
  })

  it('shares an active task refresh and replaces the pending poll after a manual refresh', async () => {
    status = 'working'
    await store.get_running()
    await store.start_task_polling()
    let resolveTasks
    axios.get.mockImplementationOnce(() => new Promise((resolve) => (resolveTasks = resolve)))
    const first = store.get_tasks()
    const second = store.get_tasks()
    await vi.advanceTimersByTimeAsync(9000)
    expect(axios.get.mock.calls.filter(([url]) => url.endsWith('/task'))).toHaveLength(2)
    expect(vi.getTimerCount()).toBe(0)

    const tasks = [{ time: '2026-10-18T12:00:00', plan: {} }]
    resolveTasks({ data: tasks })
    await Promise.all([first, second])
    expect(store.task_list).toEqual(tasks)
    expect(vi.getTimerCount()).toBe(1)
    await vi.advanceTimersByTimeAsync(3000)
    expect(axios.get.mock.calls.filter(([url]) => url.endsWith('/task'))).toHaveLength(3)
    expect(vi.getTimerCount()).toBe(1)
  })

  it('clears stopped tasks and rejects a response from the previous worker run', async () => {
    status = 'working'
    await store.get_running()
    let resolveTasks
    axios.get.mockImplementationOnce(() => new Promise((resolve) => (resolveTasks = resolve)))
    const request = store.start_task_polling()
    const { signal } = axios.get.mock.lastCall[1]
    store.task_list = [{ time: 'old', plan: {} }]
    store.running = false
    expect(signal.aborted).toBe(true)
    expect(store.task_list).toEqual([])

    resolveTasks({ data: [{ time: 'late', plan: {} }] })
    await request
    expect(store.task_list).toEqual([])
    expect(vi.getTimerCount()).toBe(0)

    status = 'starting'
    await store.get_running()
    await store.get_tasks()
    expect(store.task_list).toHaveLength(1)
    expect(vi.getTimerCount()).toBe(1)
  })

  it('keeps a reentered task table independent of the previous pending response', async () => {
    status = 'working'
    await store.get_running()
    let resolveOld
    let resolveCurrent
    axios.get.mockImplementationOnce(() => new Promise((resolve) => (resolveOld = resolve)))
    const old = store.start_task_polling()
    const oldSignal = axios.get.mock.lastCall[1].signal
    store.stop_task_polling()
    expect(oldSignal.aborted).toBe(true)
    axios.get.mockImplementationOnce(() => new Promise((resolve) => (resolveCurrent = resolve)))
    const current = store.start_task_polling()
    resolveOld({ data: [{ time: 'old', plan: {} }] })
    await old
    expect(store.task_list).toEqual([])
    expect(vi.getTimerCount()).toBe(0)

    const tasks = [{ time: 'current', plan: {} }]
    resolveCurrent({ data: tasks })
    await current
    expect(store.task_list).toEqual(tasks)
    expect(vi.getTimerCount()).toBe(1)
    await vi.advanceTimersByTimeAsync(3000)
    expect(axios.get.mock.calls.filter(([url]) => url.endsWith('/task'))).toHaveLength(3)
    expect(vi.getTimerCount()).toBe(1)
  })

  it('releases pending task reads when the store is disposed', async () => {
    store.running = true
    let resolveTasks
    axios.get.mockImplementationOnce(() => new Promise((resolve) => (resolveTasks = resolve)))
    const request = store.start_task_polling()
    const { signal } = axios.get.mock.lastCall[1]
    store.$dispose()
    expect(signal.aborted).toBe(true)
    resolveTasks({ data: [{ time: 'late', plan: {} }] })
    await request
    expect(store.task_list).toEqual([])
    expect(vi.getTimerCount()).toBe(0)
  })

  it('retains the last task list and one bounded retry after a failed read', async () => {
    const errorLog = vi.spyOn(console, 'error').mockImplementation(() => {})
    try {
      store.running = true
      const previous = [{ time: 'previous', plan: {} }]
      store.task_list = previous
      axios.get.mockRejectedValueOnce(new Error('offline'))
      await store.start_task_polling()
      expect(axios.get.mock.lastCall[1].timeout).toBe(10000)
      expect(store.task_list).toEqual(previous)
      expect(vi.getTimerCount()).toBe(1)
      expect(errorLog).toHaveBeenCalledOnce()
      await vi.advanceTimersByTimeAsync(3000)
      expect(store.task_list[0].time).toBe('2026-10-01T12:00:00')
      expect(vi.getTimerCount()).toBe(1)
      store.stop_task_polling()
      await vi.advanceTimersByTimeAsync(6000)
      expect(axios.get).toHaveBeenCalledTimes(2)
    } finally {
      errorLog.mockRestore()
    }
  })

  it('shares concurrent status reads and releases the request after failure', async () => {
    let rejectStatus
    axios.get.mockImplementationOnce(() => new Promise((_, reject) => (rejectStatus = reject)))
    const requests = Promise.all([store.get_running(), store.get_running()])
    expect(axios.get).toHaveBeenCalledOnce()
    expect(axios.get.mock.lastCall[1].timeout).toBe(10000)
    rejectStatus(new Error('offline'))
    await expect(requests).rejects.toThrow('offline')

    status = 'recovering'
    await store.get_running()
    expect(store.status).toBe('recovering')
    expect(axios.get).toHaveBeenCalledTimes(2)
    expect(vi.getTimerCount()).toBe(0)
  })

  it.each([true, false, null, undefined, 'true', 1])(
    'reads update authorization %s without accepting non-booleans',
    async (enabled) => {
      axios.get.mockResolvedValue({
        data: { status: 'stopped', plan_condition: [], updates_enabled: enabled }
      })
      await store.get_running()
      expect(store.updates_enabled).toBe(typeof enabled === 'boolean' ? enabled : null)
    }
  )

  it('reads desktop startup ownership while stopped without starting tasks', async () => {
    axios.get.mockResolvedValue({
      data: {
        status: 'stopped',
        plan_condition: [],
        auto_start_handled: true,
        desktop_startup_handled: true
      }
    })
    for (let i = 0; i < 3; i++) {
      await store.get_running()
      expect(store.running).toBe(false)
      expect(store.auto_start_handled).toBe(true)
      expect(store.desktop_startup_handled).toBe(true)
    }
    expect(axios.get.mock.calls.every(([url]) => url.endsWith('/status'))).toBe(true)
    expect(vi.getTimerCount()).toBe(0)
  })
})

const logAt = (value) => Date.parse(value.replace(' ', 'T'))

describe('log WebSocket access', () => {
  it.each([
    [-8, 500, false],
    [8, 3000, true]
  ])(
    'times scene waits from the server instant with a %s-hour clock-text offset',
    async (offset, elapsed, waiting) => {
      vi.useFakeTimers()
      const now = Date.parse('2026-11-06T12:00:00Z')
      vi.setSystemTime(now)
      vi.stubGlobal('window', { location: { search: '' } })
      vi.stubGlobal('location', { origin: 'http://127.0.0.1:58000' })
      setActivePinia(createPinia())
      const store = useMowerStore()
      store.listen_ws()
      const differentZone = new Date(now + offset * 60 * 60 * 1000)
      const pad = (value) => String(value).padStart(2, '0')
      const t = `${differentZone.getFullYear()}-${pad(differentZone.getMonth() + 1)}-${pad(differentZone.getDate())} ${pad(differentZone.getHours())}:${pad(differentZone.getMinutes())}:${pad(differentZone.getSeconds())},000`
      store.ws.onmessage({
        data: JSON.stringify({
          type: 'log',
          records: [
            {
              t,
              at: now - elapsed,
              level: 'INFO',
              group: 'recognition',
              msg: 'Scene 9998: 场景跳转时的等待界面'
            }
          ]
        })
      })

      expect(store.log_lines[0].at).toBe(now - elapsed)
      expect(store.log_lines[0].text).toBe(`${t} INFO Scene 9998: 场景跳转时的等待界面`)
      const html = await renderToString(
        createSSRApp(LogOutput, { lines: store.log_lines, running: true })
      )
      expect(html.includes('class="log-wait-loader"')).toBe(waiting)
      store.$dispose()
    }
  )

  it.each([undefined, null, '1793966400000', true, {}, []])(
    'keeps the legacy timestamp fallback when the absolute instant is %j',
    (at) => {
      vi.stubGlobal('window', { location: { search: '' } })
      vi.stubGlobal('location', { origin: 'http://127.0.0.1:58000' })
      setActivePinia(createPinia())
      const store = useMowerStore()
      store.listen_ws()
      store.ws.onmessage({
        data: JSON.stringify({
          type: 'log',
          records: [{ t: '2026-11-06 12:00:00,125', at, level: 'INFO', msg: '旧式记录' }]
        })
      })
      expect(store.log_lines[0].at).toBe(Date.parse('2026-11-06T12:00:00.125'))
      store.$dispose()
    }
  )

  it('updates one facility summary from a live roster observation after history replay', async () => {
    vi.stubGlobal('window', { location: { search: '' } })
    vi.stubGlobal('location', { origin: 'http://127.0.0.1:58000' })
    setActivePinia(createPinia())
    const store = useMowerStore()
    store.listen_ws()
    const event = {
      type: 'facility-arrangement',
      id: 'wire-recycling-current',
      phase: 'started',
      anchor: true,
      room: 'recycle',
      label: '回收站',
      agents: ['行铃']
    }
    const parent = { type: event.type, id: event.id, room: event.room }
    const records = [
      { t: '2026-11-06 17:43:00', level: 'INFO', msg: '正在安排行铃进驻回收站', event },
      {
        t: '2026-11-06 17:43:02',
        level: 'INFO',
        msg: '正在安排行铃、旅骨进驻回收站',
        parent,
        event: { ...event, phase: 'updated', anchor: false, agents: ['行铃', '旅骨'] }
      }
    ]
    const walk = (node) => [node, ...(node.children ?? []).flatMap(walk)]
    const summaries = async () => {
      const html = await renderToString(
        createSSRApp(LogOutput, { lines: store.log_lines, running: true, concise: true })
      )
      return walk(parseHtml(html)).filter(
        (node) =>
          node.type === 1 &&
          node.props.some(
            (attribute) =>
              attribute.name === 'class' &&
              attribute.value?.content.split(/\s+/u).includes('log-arrangement')
          )
      )
    }
    const summaryText = (node) =>
      walk(node)
        .filter((entry) => entry.type === 2)
        .map((entry) => entry.content)
        .join('')
    store.ws.onmessage({ data: JSON.stringify({ type: 'log', records: records.slice(0, 1) }) })
    const first = await summaries()
    expect(first).toHaveLength(1)
    expect(summaryText(first[0])).toBe('正在安排行铃进驻回收站')
    store.ws.onmessage({ data: JSON.stringify({ type: 'log', records: records.slice(1) }) })
    const updated = await summaries()
    expect(updated).toHaveLength(1)
    expect(summaryText(updated[0])).toBe('正在安排行铃、旅骨进驻回收站')
    expect(
      updated[0].props.find((attribute) => attribute.name === 'data-log-source')?.value?.content
    ).toBe(store.log_lines[0].text)
    expect(store.log_lines.map((line) => line.event)).toEqual(records.map((record) => record.event))
    expect(store.log_lines[1].parent).toEqual(parent)
    store.$dispose()
  })

  it('replaces sequenced history and applies live evictions without duplicating old updates', () => {
    vi.stubGlobal('window', { location: { search: '' } })
    vi.stubGlobal('location', { origin: 'http://127.0.0.1:58000' })
    setActivePinia(createPinia())
    const store = useMowerStore()
    store.listen_ws()
    const send = (message) =>
      store.ws.onmessage({ data: JSON.stringify({ type: 'log', stream_id: 'run-a', ...message }) })
    const first = { seq: 1, msg: '开始' }
    const second = { seq: 2, msg: '原始详情' }
    const third = { seq: 3, msg: '完成' }
    send({ snapshot: true, records: [first, second] })
    const retainedId = store.log_lines[0].id
    store.clear_legacy_logs()
    expect(store.log_lines.map((line) => line.text)).toEqual(['开始', '原始详情'])
    send({ snapshot: false, records: [third], evicted: [2] })
    expect(store.log_lines.map((line) => line.text)).toEqual(['开始', '完成'])
    send({ snapshot: false, records: [second, third], evicted: [] })
    expect(store.log_lines.map((line) => line.text)).toEqual(['开始', '完成'])
    send({ snapshot: true, records: [first, third] })
    expect(store.log_lines.map((line) => line.text)).toEqual(['开始', '完成'])
    expect(store.log_lines[0].id).toBe(retainedId)
    send({ snapshot: false, records: [{ seq: 4, msg: '超过本次缓存预算' }], evicted: [4] })
    expect(store.log_lines.map((line) => line.text)).toEqual(['开始', '完成'])
    send({ snapshot: true, records: [first, third] })
    send({ snapshot: false, records: [{ seq: 4, msg: '已淘汰记录的迟到重放' }], evicted: [] })
    expect(store.log_lines.map((line) => line.text)).toEqual(['开始', '完成'])
    send({ stream_id: 'run-b', snapshot: true, records: [], data: '' })
    expect(store.log_lines).toEqual([])
    send({ stream_id: 'run-b', snapshot: false, records: [{ seq: 1, msg: '新运行' }] })
    expect(store.log_lines.map((line) => line.text)).toEqual(['新运行'])
    expect(store.log_lines[0].id).not.toBe(retainedId)
    const observed = []
    const stop = watch(
      () => store.log_lines,
      (lines) => observed.push(lines.map((line) => line.text)),
      {
        flush: 'sync'
      }
    )
    send({ stream_id: 'run-c', snapshot: false, records: [{ seq: 1, msg: '后端重新启动' }] })
    expect(observed).toEqual([['后端重新启动']])
    stop()
    store.$dispose()
  })

  it('keeps a facility summary through more than 100 details and restores the same replay', async () => {
    vi.stubGlobal('window', { location: { search: '' } })
    vi.stubGlobal('location', { origin: 'http://127.0.0.1:58000' })
    setActivePinia(createPinia())
    const store = useMowerStore()
    store.listen_ws()
    const event = {
      type: 'facility-arrangement',
      id: 'retained-roster',
      phase: 'started',
      anchor: true,
      room: 'recycle',
      label: '回收站',
      agents: ['行铃']
    }
    const parent = { type: event.type, id: event.id, room: event.room }
    const start = {
      seq: 1,
      t: '2026-11-06 17:43:00',
      level: 'INFO',
      group: 'base-scheduler',
      msg: '正在安排行铃进驻回收站',
      event
    }
    const details = Array.from({ length: 120 }, (_, index) => ({
      seq: index + 2,
      t: '2026-11-06 17:43:01',
      level: 'INFO',
      group: 'recognition',
      msg: `选人详情 ${index}`,
      parent
    }))
    const terminal = {
      seq: 122,
      t: '2026-11-06 17:43:02',
      level: 'INFO',
      group: 'base-scheduler',
      msg: '已安排行铃、旅骨进驻回收站',
      parent,
      event: { ...event, phase: 'completed', anchor: false, agents: ['行铃', '旅骨'] }
    }
    const lateUpdate = {
      ...terminal,
      seq: 123,
      msg: '迟到的进行中名单',
      event: { ...event, phase: 'updated', anchor: false }
    }
    const send = (message) =>
      store.ws.onmessage({
        data: JSON.stringify({
          type: 'log',
          stream_id: 'retained-run',
          ...message
        })
      })
    const render = () =>
      renderToString(
        createSSRApp(LogOutput, {
          lines: store.log_lines,
          running: true,
          concise: true
        })
      )
    send({ snapshot: true, records: [start] })
    for (const record of details) send({ snapshot: false, records: [record], evicted: [] })
    send({ snapshot: false, records: [terminal], evicted: details.slice(0, 70).map((r) => r.seq) })
    send({ snapshot: false, records: [lateUpdate], evicted: [] })
    const retained = [start, ...details.slice(70), terminal, lateUpdate]
    expect(store.log_lines.map((line) => line.text)).toEqual(
      retained.map((record) => `${record.t} ${record.level} ${record.msg}`)
    )
    expect(store.log_lines).toMatchObject(retained.map(({ t, level, msg }) => ({ t, level, msg })))
    const live = await render()
    const nodes = (node) => [node, ...(node.children ?? []).flatMap(nodes)]
    const summaries = nodes(parseHtml(live)).filter(
      (node) =>
        node.type === 1 &&
        node.props.some(
          (attribute) =>
            attribute.name === 'class' &&
            attribute.value?.content.split(/\s+/u).includes('log-arrangement')
        )
    )
    expect(summaries).toHaveLength(1)
    expect(
      nodes(summaries[0])
        .filter((node) => node.type === 2)
        .map((node) => node.content)
        .join('')
    ).toBe('已安排行铃、旅骨进驻回收站')
    send({ snapshot: true, records: retained })
    expect(await render()).toBe(live)
    const refreshed = useMowerStore(createPinia())
    refreshed.listen_ws()
    refreshed.ws.onmessage({
      data: JSON.stringify({
        type: 'log',
        stream_id: 'retained-run',
        snapshot: true,
        records: retained
      })
    })
    expect(
      await renderToString(
        createSSRApp(LogOutput, {
          lines: refreshed.log_lines,
          running: true,
          concise: true
        })
      )
    ).toBe(live)
    expect(store.log).toBe(
      retained.map((record) => `${record.t} ${record.level} ${record.msg}`).join('\n')
    )
    refreshed.$dispose()
    store.$dispose()
  })

  it('bounds legacy source records by count and serialized bytes', () => {
    vi.stubGlobal('window', { location: { search: '' } })
    vi.stubGlobal('location', { origin: 'http://127.0.0.1:58000' })
    setActivePinia(createPinia())
    const store = useMowerStore()
    store.listen_ws()
    const send = (records) => store.ws.onmessage({ data: JSON.stringify({ type: 'log', records }) })
    send(Array.from({ length: 2100 }, (_, index) => ({ msg: `旧版记录 ${index}` })))
    expect(store.log_lines).toHaveLength(2000)
    expect(store.log_lines[0].text).toBe('旧版记录 100')
    const t = '2026-11-01 00:00:00'
    const largeRecords = Array.from({ length: 150 }, () => ({
      t,
      level: 'INFO',
      msg: 'a'.repeat(16000)
    }))
    send(largeRecords)
    expect(store.log_lines.filter((line) => line.text.startsWith(t))).toHaveLength(
      largeRecords.length
    )
    send(Array.from({ length: 300 }, () => ({ msg: '汉'.repeat(16000) })))
    expect(
      new TextEncoder().encode(JSON.stringify(store.log_lines)).byteLength
    ).toBeLessThanOrEqual(4 * 1024 ** 2)
    expect(store.log_lines.at(-1).text).toBe('汉'.repeat(16000))
    send([{ msg: '汉'.repeat(2 * 1024 ** 2) }, { msg: '仍可接收后续日志' }])
    expect(store.log_lines.map((line) => line.text)).toEqual(['仍可接收后续日志'])
    store.$dispose()
  })

  it.each([
    ['text', (...messages) => ({ data: messages.join('\n') })],
    ['structured', (...messages) => ({ records: messages.map((msg) => ({ msg })) })]
  ])('replaces the legacy %s history when the socket reconnects', (_format, payload) => {
    vi.stubGlobal('window', { location: { search: '' } })
    vi.stubGlobal('location', { origin: 'http://127.0.0.1:58000' })
    const store = useMowerStore(createPinia())
    store.listen_ws()
    const send = (...messages) =>
      store.ws.onmessage({ data: JSON.stringify({ type: 'log', ...payload(...messages) }) })

    store.ws.onopen()
    send('旧记录', '重放记录')
    send('断开前记录')
    store.ws.onopen()
    send('重放记录', '断开前记录', '断开期间记录')
    send('重连后记录')
    expect(store.log_lines.map((line) => line.text)).toEqual([
      '重放记录',
      '断开前记录',
      '断开期间记录',
      '重连后记录'
    ])

    store.clear_legacy_logs()
    expect(store.log_lines).toEqual([])
    send('启动后记录')
    store.ws.onopen()
    send()
    expect(store.log_lines).toEqual([])
    store.$dispose()
  })

  it('measures the legacy byte budget only for newly received records', () => {
    vi.stubGlobal('window', { location: { search: '' } })
    vi.stubGlobal('location', { origin: 'http://127.0.0.1:58000' })
    const store = useMowerStore(createPinia())
    store.listen_ws()
    const send = (records) => store.ws.onmessage({ data: JSON.stringify({ type: 'log', records }) })

    send(Array.from({ length: 100 }, () => ({ msg: '汉'.repeat(5000) })))
    const encode = vi.spyOn(TextEncoder.prototype, 'encode')
    send([{ msg: '继续接收' }])
    const sizeChecks = encode.mock.calls.length
    encode.mockRestore()

    expect(sizeChecks).toBe(1)
    expect(store.log_lines).toHaveLength(101)
    store.$dispose()
  })

  it('renders scoped rescue details from real WebSocket records inside their parent block only', async () => {
    vi.stubGlobal('window', { location: { search: '' } })
    vi.stubGlobal('location', { origin: 'http://127.0.0.1:58000' })
    setActivePinia(createPinia())
    const store = useMowerStore()
    store.listen_ws()
    const rooms = [
      { room: 'meeting', label: '会客室', agents: ['Current', '阿米娅'], status: 'pending' }
    ]
    const event = {
      type: 'rescue-staffing',
      id: 'wire-rescue-task',
      phase: 'queued',
      anchor: true,
      rooms
    }
    const parent = {
      type: 'rescue-staffing',
      id: event.id,
      room: 'meeting',
      attempt: 'wire-facility-attempt'
    }
    const scopedError = '选人校验失败，保留此次原因'
    const unrelated = '独立调度信息不属于本次救急'
    store.ws.onmessage({
      data: JSON.stringify({
        type: 'log',
        records: [
          {
            t: '2026-11-05 22:00:00',
            level: 'INFO',
            msg: '已生成救急换班任务，等待执行\n会客室：Current、阿米娅',
            event,
            task: {
              title: '救急换班',
              header: '已生成救急换班任务，等待执行',
              rooms: [{ id: 'meeting', label: '会客室', agents: ['Current', '阿米娅'] }],
              actions: [],
              targets: [],
              backups: []
            }
          },
          {
            t: '2026-11-05 22:00:01',
            level: 'INFO',
            msg: '正在执行救急换班任务',
            event: {
              ...event,
              phase: 'started',
              anchor: false,
              rooms: rooms.map((room) => ({ ...room, status: 'active' }))
            }
          },
          {
            t: '2026-11-05 22:00:02',
            level: 'INFO',
            msg: '会客室',
            parent,
            event: {
              type: 'facility-arrangement',
              id: parent.attempt,
              phase: 'started',
              anchor: true,
              room: 'meeting',
              label: '会客室',
              agents: ['阿米娅']
            }
          },
          { t: '2026-11-05 22:00:03', level: 'ERROR', msg: scopedError, parent },
          { t: '2026-11-05 22:00:04', level: 'INFO', msg: unrelated }
        ]
      })
    })
    const html = await renderToString(
      createSSRApp(LogOutput, {
        lines: store.log_lines,
        operatorNames: ['阿米娅'],
        running: true,
        autoScroll: false
      })
    )
    const walk = (node) => [node, ...(node.children ?? []).flatMap(walk)]
    const blocks = walk(parseHtml(html)).filter(
      (node) =>
        node.type === 1 &&
        node.props.some(
          (attribute) =>
            attribute.name === 'class' &&
            attribute.value?.content.split(/\s+/u).includes('log-rescue-block')
        )
    )
    expect(blocks).toHaveLength(1)
    const blockText = walk(blocks[0])
      .filter((node) => node.type === 2)
      .map((node) => node.content)
      .join('')
    expect(blockText).toContain('正在执行救急换班任务')
    expect(blockText).toContain(scopedError)
    expect(blockText).not.toContain(unrelated)
    expect(store.log_lines[3].parent).toEqual(parent)
    expect(store.log_lines[3].text).toBe(`2026-11-05 22:00:03 ERROR ${scopedError}`)
    expect(store.log_lines[4]).not.toHaveProperty('parent')
    store.$dispose()
  })
  it('keeps rescue parent references from history and live records as separate wire snapshots', () => {
    vi.stubGlobal('window', { location: { search: '' } })
    vi.stubGlobal('location', { origin: 'http://127.0.0.1:58000' })
    setActivePinia(createPinia())
    const store = useMowerStore()
    store.listen_ws()
    const parent = { type: 'rescue-staffing', id: 'task-a', room: 'meeting', attempt: 'attempt-a' }
    const event = {
      type: 'facility-arrangement',
      id: 'attempt-a',
      phase: 'started',
      anchor: true,
      room: 'meeting',
      label: '会客室',
      agents: ['阿米娅']
    }
    const task = {
      title: '救急换班',
      header: '已生成救急换班任务，等待执行',
      rooms: [{ id: 'meeting', label: '会客室', agents: ['Current', '阿米娅'] }],
      targets: [],
      backups: [],
      actions: []
    }
    const record = { t: '2026-11-05 22:00:00', level: 'INFO', msg: '会客室', parent, event, task }
    store.ws.onmessage({
      data: JSON.stringify({ type: 'log', data: '旧式回退不应覆盖结构化记录', records: [record] })
    })
    expect(store.log_lines[0].parent).toEqual(parent)
    expect(store.log_lines[0].event).toEqual(event)
    expect(store.log_lines[0].task).toEqual(task)
    expect(store.log_lines[0].text).toBe('2026-11-05 22:00:00 INFO 会客室')
    parent.id = 'task-b'
    parent.attempt = 'attempt-b'
    event.id = 'attempt-b'
    task.rooms[0].agents[1] = '陈'
    store.ws.onmessage({
      data: JSON.stringify({
        type: 'log',
        records: [
          { ...record, msg: '再次进入会客室' },
          { msg: '救急任务尚未完成', parent: { type: 'rescue-staffing', id: 'task-b' } }
        ]
      })
    })
    expect(store.log_lines[0].parent).toEqual({
      type: 'rescue-staffing',
      id: 'task-a',
      room: 'meeting',
      attempt: 'attempt-a'
    })
    expect(store.log_lines[0].event.id).toBe('attempt-a')
    expect(store.log_lines[0].task.rooms[0].agents).toEqual(['Current', '阿米娅'])
    expect(store.log_lines[1].parent).toEqual(parent)
    expect(store.log_lines[2].parent).toEqual({ type: 'rescue-staffing', id: 'task-b' })
    expect(store.log).toBe(
      '2026-11-05 22:00:00 INFO 会客室\n2026-11-05 22:00:00 INFO 再次进入会客室\n救急任务尚未完成'
    )
    store.$dispose()
  })
  it('passes inventory and explicit reset events without replacing any source text', () => {
    vi.stubGlobal('window', { location: { search: '' } })
    vi.stubGlobal('location', { origin: 'http://127.0.0.1:58000' })
    setActivePinia(createPinia())
    const store = useMowerStore()
    store.listen_ws()
    const inventory = {
      items: [
        { name: '龙门币', count: 0 },
        { name: '固源岩', count: 2 }
      ]
    }
    const event = { type: 'operator-reset-idle' }
    const messages = [
      '仓库扫描：已识别2种物品\n龙门币：0\n固源岩：2',
      '重设 [[operator:砾]] 至空闲'
    ]
    store.ws.onmessage({
      data: JSON.stringify({
        type: 'log',
        records: [
          { msg: messages[0], inventory },
          { msg: messages[1], event, agents: ['砾'], room: 'dormitory_1' }
        ]
      })
    })
    expect(store.log_lines[0].inventory).toEqual(inventory)
    expect(store.log_lines[1].event).toEqual(event)
    expect(store.log_lines[1].agents).toEqual(['砾'])
    expect(store.log).toBe(messages.join('\n'))
    store.$dispose()
  })

  it.each([null, false, 'bad', 1, []])('ignores non-object display fields %j', (value) => {
    vi.stubGlobal('window', { location: { search: '' } })
    vi.stubGlobal('location', { origin: 'http://127.0.0.1:58000' })
    setActivePinia(createPinia())
    const store = useMowerStore()
    store.listen_ws()
    store.ws.onmessage({
      data: JSON.stringify({
        type: 'log',
        records: [{ msg: '原文保留', inventory: value, event: value, parent: value }]
      })
    })
    expect(store.log_lines[0]).not.toHaveProperty('inventory')
    expect(store.log_lines[0]).not.toHaveProperty('event')
    expect(store.log_lines[0]).not.toHaveProperty('parent')
    expect(store.log).toBe('原文保留')
    store.$dispose()
  })

  it('preserves complete backup names beside the unchanged message', () => {
    vi.stubGlobal('window', { location: { search: '' } })
    vi.stubGlobal('location', { origin: 'http://127.0.0.1:58000' })
    setActivePinia(createPinia())
    const store = useMowerStore()
    store.listen_ws()
    const backups = [{ name: '深海下班', active: true }]
    const msg = '已激活的副表：深海下班'
    store.ws.onmessage({ data: JSON.stringify({ type: 'log', records: [{ msg, backups }] }) })
    expect(store.log_lines[0].backups).toEqual(backups)
    expect(store.log).toBe(msg)
    store.$dispose()
  })

  it('passes optional recruitment metadata beside the unchanged copyable text', () => {
    vi.stubGlobal('window', { location: { search: '' } })
    vi.stubGlobal('location', { origin: 'http://127.0.0.1:58000' })
    setActivePinia(createPinia())
    const store = useMowerStore()
    store.listen_ws()
    const recruitment = { event: 'start', tags: ['治疗', '费用回复'], rarity: 4 }
    const msg = '1号招募位：开始招募，标签：治疗、费用回复，时长：9小时'

    store.ws.onmessage({
      data: JSON.stringify({
        type: 'log',
        records: [{ t: '2026-11-04 19:30:00', level: 'INFO', msg, recruitment }]
      })
    })

    expect(store.log_lines).toHaveLength(1)
    expect(store.log_lines[0].recruitment).toEqual(recruitment)
    expect(store.log_lines[0].text).toBe(`2026-11-04 19:30:00 INFO ${msg}`)
    expect(store.log).toBe(`2026-11-04 19:30:00 INFO ${msg}`)
    store.$dispose()
  })

  it.each([null, false, '治疗', 4, []])(
    'omits non-object recruitment metadata %j without changing text',
    (recruitment) => {
      vi.stubGlobal('window', { location: { search: '' } })
      vi.stubGlobal('location', { origin: 'http://127.0.0.1:58000' })
      setActivePinia(createPinia())
      const store = useMowerStore()
      store.listen_ws()

      store.ws.onmessage({
        data: JSON.stringify({
          type: 'log',
          records: [{ msg: '原有纯文本', recruitment }, { msg: '普通日志' }]
        })
      })

      expect(store.log_lines[0]).not.toHaveProperty('recruitment')
      expect(store.log_lines[1]).not.toHaveProperty('recruitment')
      expect(store.log).toBe('原有纯文本\n普通日志')
      store.$dispose()
    }
  )

  it('retains a complete task forecast as one record beside its copyable fallback', () => {
    vi.stubGlobal('window', { location: { search: '' } })
    vi.stubGlobal('location', { origin: 'http://127.0.0.1:58000' })
    setActivePinia(createPinia())
    const store = useMowerStore()
    store.listen_ws()
    const task = {
      header: '休息至 19:42:00，随后执行甲组上班',
      title: '甲组上班',
      rooms: [{ id: 'room_3_3', label: '发电站 B303', agents: ['Current', '阿米娅'] }],
      backups: [{ name: '夜班', active: true }],
      targets: []
    }
    store.ws.onmessage({
      data: JSON.stringify({
        type: 'log',
        records: [
          {
            t: '2026-11-04 18:30:02',
            level: 'INFO',
            msg: '完整纯文本预告\n发电站 B303：Current、阿米娅',
            task
          }
        ]
      })
    })
    expect(store.log_lines).toHaveLength(1)
    expect(store.log_lines[0].task).toEqual(task)
    expect(store.log).toBe('2026-11-04 18:30:02 INFO 完整纯文本预告\n发电站 B303：Current、阿米娅')
    store.$dispose()
  })
  it('appends log text when a message carries obsolete screenshot metadata', () => {
    vi.stubGlobal('window', { location: { search: '' } })
    vi.stubGlobal('location', { origin: 'http://127.0.0.1:58000' })
    setActivePinia(createPinia())
    const store = useMowerStore()
    store.listen_ws()

    expect(() =>
      store.ws.onmessage({
        data: JSON.stringify({ type: 'log', data: 'first\nsecond', screenshot: 'legacy-frame' })
      })
    ).not.toThrow()
    expect(store.log_lines).toEqual([
      { id: 1, at: null, text: 'first', group: null, room: null, agents: null },
      { id: 2, at: null, text: 'second', group: null, room: null, agents: null }
    ])
    expect(store.log).toBe('first\nsecond')
    store.$dispose()
  })

  it('appends structured records as text lines and keeps the legacy data.data fallback', () => {
    vi.stubGlobal('window', { location: { search: '' } })
    vi.stubGlobal('location', { origin: 'http://127.0.0.1:58000' })
    setActivePinia(createPinia())
    const store = useMowerStore()
    store.listen_ws()

    // 新式结构化记录：每条 record 的 msg 拼成 "t level msg" 文本行；
    // 历史中的旧式文本行以只有 msg 的记录送达，原样显示。
    store.ws.onmessage({
      data: JSON.stringify({
        type: 'log',
        data: '2026-11-01 00:00:00 INFO alpha\n2026-11-01 00:00:01 ERROR beta\nlegacy',
        records: [
          { t: '2026-11-01 00:00:00', level: 'INFO', msg: 'alpha' },
          { t: '2026-11-01 00:00:01', level: 'ERROR', msg: 'beta' },
          { msg: 'legacy' }
        ]
      })
    })
    expect(store.log_lines).toEqual([
      {
        id: 1,
        at: logAt('2026-11-01 00:00:00'),
        text: '2026-11-01 00:00:00 INFO alpha',
        group: null,
        room: null,
        agents: null
      },
      {
        id: 2,
        at: logAt('2026-11-01 00:00:01'),
        text: '2026-11-01 00:00:01 ERROR beta',
        group: null,
        room: null,
        agents: null
      },
      { id: 3, at: null, text: 'legacy', group: null, room: null, agents: null }
    ])

    // 缺少 records 时回退到旧式 data.data 文本；store 追加而非替换，保留已有行。
    store.ws.onmessage({
      data: JSON.stringify({ type: 'log', data: 'fallback\nsecond' })
    })
    expect(store.log_lines).toEqual([
      {
        id: 1,
        at: logAt('2026-11-01 00:00:00'),
        text: '2026-11-01 00:00:00 INFO alpha',
        group: null,
        room: null,
        agents: null
      },
      {
        id: 2,
        at: logAt('2026-11-01 00:00:01'),
        text: '2026-11-01 00:00:01 ERROR beta',
        group: null,
        room: null,
        agents: null
      },
      { id: 3, at: null, text: 'legacy', group: null, room: null, agents: null },
      { id: 4, at: null, text: 'fallback', group: null, room: null, agents: null },
      { id: 5, at: null, text: 'second', group: null, room: null, agents: null }
    ])
    store.$dispose()
  })

  it('parses and passes structured room and agents fields from records', () => {
    vi.stubGlobal('window', { location: { search: '' } })
    vi.stubGlobal('location', { origin: 'http://127.0.0.1:58000' })
    setActivePinia(createPinia())
    const store = useMowerStore()
    store.listen_ws()

    store.ws.onmessage({
      data: JSON.stringify({
        type: 'log',
        records: [
          {
            t: '2026-11-01 00:00:00',
            level: 'INFO',
            msg: '进驻设施',
            room: 'room_1_1',
            agents: ['但书', '巫恋']
          },
          { t: '2026-11-01 00:00:01', level: 'DEBUG', msg: '普通消息' }
        ]
      })
    })
    expect(store.log_lines).toEqual([
      {
        id: 1,
        at: logAt('2026-11-01 00:00:00'),
        text: '2026-11-01 00:00:00 INFO 进驻设施',
        group: null,
        room: 'room_1_1',
        agents: ['但书', '巫恋']
      },
      {
        id: 2,
        at: logAt('2026-11-01 00:00:01'),
        text: '2026-11-01 00:00:01 DEBUG 普通消息',
        group: null,
        room: null,
        agents: null
      }
    ])
    store.$dispose()
  })

  it('ignores log messages with neither records nor data.data', () => {
    vi.stubGlobal('window', { location: { search: '' } })
    vi.stubGlobal('location', { origin: 'http://127.0.0.1:58000' })
    setActivePinia(createPinia())
    const store = useMowerStore()
    store.listen_ws()

    expect(() => store.ws.onmessage({ data: JSON.stringify({ type: 'log' }) })).not.toThrow()
    expect(store.log_lines).toEqual([])
    store.$dispose()
  })

  it.each([
    ['http://mower.example:18000', 'ws://mower.example:18000/log'],
    ['https://mower.example', 'wss://mower.example/log'],
    ['https://mower.example:8443', 'wss://mower.example:8443/log'],
    ['https://[2001:db8::1]:8443', 'wss://[2001:db8::1]:8443/log']
  ])('preserves the public origin %s and authenticates each connection', (origin, url) => {
    vi.stubEnv('DEV', false)
    vi.stubGlobal('window', { location: { search: '?token=test%2Bsecret%26value' } })
    vi.stubGlobal('location', { origin })
    setActivePinia(createPinia())
    const store = useMowerStore()

    store.listen_ws()
    expect(ReconnectingWebSocket).toHaveBeenCalledWith(url)
    store.ws.onopen()
    store.ws.onopen()
    expect(store.ws.send).toHaveBeenCalledTimes(2)
    expect(store.ws.send).toHaveBeenLastCalledWith(JSON.stringify({ token: 'test+secret&value' }))
  })

  it.each([
    ['', null],
    ['?token=runtime-secret', 'runtime-secret']
  ])('connects with query %s', (search, token) => {
    vi.stubGlobal('window', { location: { search } })
    vi.stubGlobal('location', { origin: 'http://127.0.0.1:58000' })
    setActivePinia(createPinia())
    const store = useMowerStore()

    store.listen_ws()
    expect(ReconnectingWebSocket).toHaveBeenCalledWith('/log')
    store.ws.onopen()
    if (token) {
      expect(store.ws.send).toHaveBeenCalledWith(JSON.stringify({ token }))
    } else {
      expect(store.ws.send).not.toHaveBeenCalled()
    }
  })
})
