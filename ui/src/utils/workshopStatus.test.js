import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createWorkshopStatus } from './workshopStatus'

let documentState
const flush = async () => {
  await Promise.resolve()
  await Promise.resolve()
}
beforeEach(() => {
  vi.useFakeTimers()
  documentState = new EventTarget()
  documentState.hidden = false
  vi.stubGlobal('document', documentState)
})
afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

describe('workshop status requests', () => {
  it('rejects a late response even when configuration generation is unchanged', async () => {
    const pending = []
    const http = { get: vi.fn(() => new Promise((resolve) => pending.push(resolve))) }
    const model = createWorkshopStatus(http, '/workshop-status', () => false)
    const first = model.start()
    const next = model.refresh()
    pending[1]({ data: { generation: 3, execution: 'waiting' } })
    await next
    pending[0]({ data: { generation: 3, execution: 'ready' } })
    await first
    expect(model.data.value.execution).toBe('waiting')
    expect(http.get.mock.calls[0][1].signal.aborted).toBe(true)
    model.stop()
  })

  it('keeps the previous result marked stale after failure', async () => {
    const http = {
      get: vi
        .fn()
        .mockResolvedValueOnce({ data: { execution: 'ready' } })
        .mockRejectedValue(new Error())
    }
    const model = createWorkshopStatus(http, '/workshop-status', () => false)
    await model.start()
    await model.refresh()
    expect(model.data.value.execution).toBe('ready')
    expect(model.stale.value).toBe(true)
    model.stop()
  })

  it('polls after completion, pauses while hidden, and releases timers and requests', async () => {
    let finish
    const http = { get: vi.fn().mockResolvedValue({ data: { execution: 'queued' } }) }
    const model = createWorkshopStatus(http, '/workshop-status', () => true)
    await model.start()
    http.get.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          finish = resolve
        })
    )
    await vi.advanceTimersByTimeAsync(15000)
    expect(http.get).toHaveBeenCalledTimes(2)
    await vi.advanceTimersByTimeAsync(60000)
    expect(http.get).toHaveBeenCalledTimes(2)
    documentState.hidden = true
    documentState.dispatchEvent(new Event('visibilitychange'))
    finish({ data: { execution: 'running' } })
    await flush()
    expect(model.data.value.execution).toBe('queued')
    await vi.advanceTimersByTimeAsync(60000)
    expect(http.get).toHaveBeenCalledTimes(2)
    documentState.hidden = false
    documentState.dispatchEvent(new Event('visibilitychange'))
    await flush()
    expect(http.get).toHaveBeenCalledTimes(3)
    model.stop()
    await vi.advanceTimersByTimeAsync(60000)
    documentState.dispatchEvent(new Event('visibilitychange'))
    expect(http.get).toHaveBeenCalledTimes(3)
    expect(vi.getTimerCount()).toBe(0)
  })

  it('does not poll a stopped scheduler', async () => {
    const http = { get: vi.fn().mockResolvedValue({ data: { execution: 'stopped' } }) }
    const model = createWorkshopStatus(http, '/workshop-status', () => false)
    await model.start()
    await vi.advanceTimersByTimeAsync(60000)
    expect(http.get).toHaveBeenCalledTimes(1)
    model.stop()
  })
})
