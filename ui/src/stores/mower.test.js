import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import ReconnectingWebSocket from 'reconnecting-websocket'
import axios from 'axios'
import { useMowerStore } from './mower'

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

describe('log WebSocket access', () => {
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
    expect(store.log_lines).toEqual(['first', 'second'])
    expect(store.log).toBe('first\nsecond')
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
