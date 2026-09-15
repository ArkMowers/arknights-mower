import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

import axios from 'axios'
import { useResourceVersionStore } from './resourceVersion.js'

vi.mock('axios', () => ({ default: { get: vi.fn(), post: vi.fn() } }))

const version = {
  current_version: 'v2026.09.03-aaaaaaa',
  remote_version: 'v2026.09.04-deadbee',
  update_available: true
}
const running = { id: 'resource-task', status: 'running', phase: 'downloading', progress: 20 }
const success = {
  ...running,
  status: 'success',
  phase: 'done',
  progress: 100,
  message: '资源包已安装，各实例在任务间歇加载，无需重启 Mower'
}
const response = (job) => ({ data: { ok: true, job } })

describe('resource version store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.resetAllMocks()
    vi.useFakeTimers()
  })
  afterEach(() => {
    vi.clearAllTimers()
    vi.useRealTimers()
  })

  it('tracks download and installation until success, then refreshes the version', async () => {
    axios.get
      .mockResolvedValueOnce({ data: version })
      .mockResolvedValueOnce(response({ ...running, phase: 'installing', progress: 96 }))
      .mockResolvedValueOnce(response(success))
      .mockResolvedValueOnce({
        data: { current_version: version.remote_version, update_available: false }
      })
    axios.post.mockResolvedValueOnce(response(running))
    const store = useResourceVersionStore()
    await store.loadResourceVersion()
    expect(store.canInstall).toBe(true)
    const installation = store.installResource()
    await vi.advanceTimersByTimeAsync(0)
    expect(store.job.progress).toBe(20)
    expect(store.installing).toBe(true)
    expect(store.canInstall).toBe(false)
    await expect(store.installResource()).resolves.toBe(false)
    expect(axios.post).toHaveBeenCalledOnce()
    expect(axios.post).toHaveBeenCalledWith(expect.stringContaining('/resource/install'), {
      background: true
    })
    await vi.advanceTimersByTimeAsync(800)
    expect(store.job.phase).toBe('installing')
    expect(store.job.progress).toBe(96)
    await vi.advanceTimersByTimeAsync(800)
    await expect(installation).resolves.toBe(true)
    expect(store.install_message).toBe(success.message)
    expect(store.installing).toBe(false)
    expect(store.info.current_version).toBe(version.remote_version)
  })

  it('restores an active update after refresh and retries a dropped progress connection', async () => {
    axios.get
      .mockResolvedValueOnce(response(running))
      .mockRejectedValueOnce(new Error('offline'))
      .mockResolvedValueOnce(response(success))
      .mockResolvedValueOnce({ data: version })
    const store = useResourceVersionStore()
    const recovered = store.loadResourceJob()
    await vi.advanceTimersByTimeAsync(0)
    expect(store.installing).toBe(true)
    await vi.advanceTimersByTimeAsync(800)
    expect(store.progress_error).toContain('正在重试')
    expect(store.installing).toBe(true)
    await vi.advanceTimersByTimeAsync(800)
    await expect(recovered).resolves.toBe(true)
    expect(store.job.status).toBe('success')
    expect(store.progress_error).toBe('')
    expect(axios.post).not.toHaveBeenCalled()
    expect(vi.getTimerCount()).toBe(0)
  })

  it('ignores a stale status response arriving after a new installation starts', async () => {
    let resolveStatus
    axios.get
      .mockResolvedValueOnce({ data: version })
      .mockImplementationOnce(() => new Promise((resolve) => (resolveStatus = resolve)))
      .mockResolvedValueOnce(response(success))
      .mockResolvedValueOnce({ data: version })
    axios.post.mockResolvedValueOnce(response(running))
    const store = useResourceVersionStore()
    await store.loadResourceVersion()
    const previous = store.loadResourceJob()
    const installation = store.installResource()
    await vi.advanceTimersByTimeAsync(0)
    resolveStatus(response({ id: 'old', status: 'success', progress: 100 }))
    await previous
    expect(store.job.id).toBe(running.id)
    expect(store.installing).toBe(true)
    await vi.advanceTimersByTimeAsync(800)
    await expect(installation).resolves.toBe(true)
  })

  it('stops polling on installation failure without claiming 100 percent', async () => {
    axios.get
      .mockResolvedValueOnce({ data: version })
      .mockResolvedValueOnce(response({ ...running, status: 'error', message: '安装失败' }))
    axios.post.mockResolvedValueOnce(response(running))
    const store = useResourceVersionStore()
    await store.loadResourceVersion()
    const installation = store.installResource()
    await vi.advanceTimersByTimeAsync(800)
    await expect(installation).resolves.toBe(false)
    expect(store.install_message).toBe('安装失败')
    expect(store.job.progress).toBeLessThan(100)
    expect(vi.getTimerCount()).toBe(0)
  })

  it('does not install before a check finds a new version', async () => {
    const store = useResourceVersionStore()
    await expect(store.installResource()).resolves.toBe(false)
    expect(axios.post).not.toHaveBeenCalled()
    expect(store.install_message).toBe('请先检查更新，发现新版本后再安装')
  })

  it('shares an in-flight version check between app entry and the settings card', async () => {
    let resolveCheck
    axios.get.mockImplementationOnce(() => new Promise((resolve) => (resolveCheck = resolve)))
    const store = useResourceVersionStore()
    const settingsCheck = store.loadResourceVersion()
    const automaticCheck = store.loadResourceVersion()
    expect(store.loading).toBe(true)
    resolveCheck({ data: version })
    expect((await settingsCheck).update_available).toBe(true)
    expect((await automaticCheck).update_available).toBe(true)
    expect(axios.get).toHaveBeenCalledOnce()
  })

  it('clears a stale update result when a forced check fails', async () => {
    axios.get.mockResolvedValueOnce({ data: version })
    const store = useResourceVersionStore()
    await store.loadResourceVersion()
    expect(store.canInstall).toBe(true)
    axios.get.mockRejectedValueOnce(new Error('network'))
    await store.loadResourceVersion(true)
    expect(store.canInstall).toBe(false)
    expect(store.info.update_available).toBeNull()
    expect(store.info.remote_version).toBe('')
  })

  it('refreshes after installation even if an older version request is still pending', async () => {
    let resolveCheck
    axios.get
      .mockImplementationOnce(() => new Promise((resolve) => (resolveCheck = resolve)))
      .mockResolvedValueOnce({
        data: { current_version: version.remote_version, update_available: false }
      })
    const store = useResourceVersionStore()
    const previous = store.loadResourceVersion()
    const refresh = store.loadResourceVersion(true)
    resolveCheck({ data: version })
    await previous
    await refresh
    expect(store.info.current_version).toBe(version.remote_version)
    expect(store.canInstall).toBe(false)
    expect(axios.get).toHaveBeenCalledTimes(2)
  })

  it('returns false when the checked install request fails', async () => {
    axios.get.mockResolvedValueOnce({ data: version })
    axios.post.mockRejectedValueOnce(new Error('network'))
    const store = useResourceVersionStore()
    await store.loadResourceVersion()
    await expect(store.installResource()).resolves.toBe(false)
    expect(store.install_message).toBe('安装失败：网络错误')
    expect(store.installing).toBe(false)
  })

  it('keeps the backend refusal reason', async () => {
    axios.get.mockResolvedValueOnce({ data: version })
    axios.post.mockResolvedValueOnce({ data: { ok: false, message: '任务正在运行' } })
    const store = useResourceVersionStore()
    await store.loadResourceVersion()
    await expect(store.installResource()).resolves.toBe(false)
    expect(store.install_message).toBe('任务正在运行')
  })
})
