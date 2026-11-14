import { describe, expect, it, vi } from 'vitest'
import { createCrashRecovery } from './crashRecovery.js'

function setup() {
  const axios = {
    get: vi.fn(async () => ({
      data: { active: true, automatic: true, phase: 'observing', message: '正在重新观察设备' }
    })),
    post: vi.fn()
  }
  return { axios, recovery: createCrashRecovery({ axios, base: '/mower' }) }
}

describe('automatic crash recovery status', () => {
  it('displays backend progress without submitting a start or recovery action', async () => {
    const { axios, recovery } = setup()
    expect(await recovery.refresh()).toBe(true)
    expect(axios.get).toHaveBeenCalledWith('/mower/crash-recovery/status', { timeout: 3000 })
    expect(recovery.status.value.phase).toBe('observing')
    expect(axios.post).not.toHaveBeenCalled()
    axios.get.mockResolvedValueOnce({
      data: { active: true, phase: 'waiting', attempt: 2, message: '稍后自动重试' }
    })
    await recovery.refresh()
    expect(recovery.status.value.phase).toBe('waiting')
    expect(recovery.status.value.attempt).toBe(2)
    expect(axios.post).not.toHaveBeenCalled()
  })

  it('clears completed recovery but preserves an explicit stop without restarting it', async () => {
    const { axios, recovery } = setup()
    await recovery.refresh()
    axios.get.mockResolvedValueOnce({ data: { active: false, phase: 'resolved' } })
    await recovery.refresh()
    expect(recovery.status.value.active).toBe(false)
    axios.get.mockResolvedValueOnce({
      data: { active: true, automatic: false, phase: 'stopped' }
    })
    await recovery.refresh()
    expect(recovery.status.value.active).toBe(true)
    expect(recovery.status.value.automatic).toBe(false)
    expect(recovery.status.value.phase).toBe('stopped')
    expect(axios.post).not.toHaveBeenCalled()
  })

  it('keeps the last recovery notice during an outage and refreshes after service returns', async () => {
    const { axios, recovery } = setup()
    await recovery.refresh()
    axios.get.mockRejectedValueOnce(new Error('offline'))
    expect(await recovery.refresh()).toBe(false)
    expect(recovery.status.value.active).toBe(true)
    expect(recovery.unavailable.value).toBe(true)
    expect(recovery.error.value).toContain('稍后自动刷新')
    axios.get.mockResolvedValueOnce({ data: { active: false, phase: 'resolved' } })
    await recovery.refresh()
    expect(recovery.status.value.active).toBe(false)
    expect(recovery.error.value).toBe('')
  })

  it('does not hide active recovery when a response is malformed', async () => {
    const { axios, recovery } = setup()
    await recovery.refresh()
    axios.get.mockResolvedValueOnce({ data: {} })
    expect(await recovery.refresh()).toBe(false)
    expect(recovery.status.value.active).toBe(true)
    expect(recovery.unavailable.value).toBe(true)
  })

  it('keeps one pending poll and ignores responses after disposal', async () => {
    const { axios, recovery } = setup()
    let finish
    axios.get.mockImplementationOnce(() => new Promise((resolve) => (finish = resolve)))
    const pending = recovery.refresh()
    expect(await recovery.refresh()).toBe(false)
    expect(axios.get).toHaveBeenCalledOnce()
    recovery.dispose()
    finish({ data: { active: true, phase: 'observing' } })
    await pending
    expect(recovery.status.value.active).toBe(false)
    expect(await recovery.refresh()).toBe(false)
    expect(axios.get).toHaveBeenCalledOnce()
    expect(axios.post).not.toHaveBeenCalled()
  })
})
