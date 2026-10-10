import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import ReconnectingWebSocket from 'reconnecting-websocket'
import axios from 'axios'
import { useMowerStore } from './mower'

vi.mock('axios', () => ({ default: { get: vi.fn() } }))
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

  it.each([
    ['starting', true, '启动中'],
    ['recovering', true, '等待设备恢复'],
    ['working', true, '运行中'],
    ['sleeping', true, '休眠中'],
    ['stopped', false, '已停止']
  ])('maps %s to worker activity and display', async (value, running, label) => {
    status = value
    await store.get_running()
    expect(store.status).toBe(value)
    expect(store.running).toBe(running)
    expect(store.status_label).toBe(label)
    expect(axios.get.mock.calls.filter(([url]) => url.endsWith('/task'))).toHaveLength(
      running ? 1 : 0
    )
  })

  it('keeps task polling through startup and recovery and clears it only after exit', async () => {
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
    expect(store.get_task_id).toBe(0)
    expect(vi.getTimerCount()).toBe(0)
  })

  it('shows stopped immediately after Stop succeeds before the next status poll', async () => {
    status = 'recovering'
    await store.get_running()
    store.running = false
    expect(store.status_label).toBe('已停止')
  })
})

describe('log WebSocket access', () => {
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
