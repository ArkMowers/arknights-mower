import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { initializeManager, loadInstances } from './bridge.js'

describe('manager startup', () => {
  let target
  let getInstances

  beforeEach(() => {
    vi.useFakeTimers()
    target = new EventTarget()
    getInstances = vi.fn().mockResolvedValue([{ name: '测试实例', path: '/tmp/mower' }])
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  function injectBridge() {
    target.pywebview = { api: { get_instances: getInstances } }
    target.dispatchEvent(new Event('pywebviewready'))
  }

  it('loads when the bridge event fired before Vue mounted', async () => {
    injectBridge()
    await expect(loadInstances(target)).resolves.toEqual([{ name: '测试实例', path: '/tmp/mower' }])
    expect(getInstances).toHaveBeenCalledOnce()
  })

  it('waits for a callable API and loads only once after delayed injection', async () => {
    target.pywebview = { api: {} }
    const result = loadInstances(target)
    target.dispatchEvent(new Event('pywebviewready'))
    await vi.advanceTimersByTimeAsync(100)
    expect(getInstances).not.toHaveBeenCalled()
    injectBridge()
    injectBridge()
    await expect(result).resolves.toHaveLength(1)
    expect(getInstances).toHaveBeenCalledOnce()
  })

  it('reports a missing bridge and stops responding to late events', async () => {
    const result = loadInstances(target, 100)
    const failure = expect(result).rejects.toThrow('加载实例列表超时')
    await vi.advanceTimersByTimeAsync(100)
    await failure
    injectBridge()
    await vi.advanceTimersByTimeAsync(0)
    expect(getInstances).not.toHaveBeenCalled()
  })

  it('times out a stalled API call and allows a fresh retry', async () => {
    let finishOldCall
    getInstances.mockImplementationOnce(() => new Promise((resolve) => (finishOldCall = resolve)))
    injectBridge()
    const result = loadInstances(target, 100)
    const failure = expect(result).rejects.toThrow('加载实例列表超时')
    await vi.advanceTimersByTimeAsync(100)
    await failure
    await expect(loadInstances(target)).resolves.toHaveLength(1)
    finishOldCall([])
    await expect(result).rejects.toThrow('加载实例列表超时')
  })

  it('propagates API failures so the UI can offer retry', async () => {
    getInstances.mockRejectedValueOnce(new Error('读取失败'))
    injectBridge()
    await expect(loadInstances(target)).rejects.toThrow('读取失败')
    await expect(loadInstances(target)).resolves.toHaveLength(1)
  })

  it('handles synchronous bridge exceptions', async () => {
    getInstances.mockImplementationOnce(() => {
      throw new Error('桥接失败')
    })
    injectBridge()
    await expect(loadInstances(target)).rejects.toThrow('桥接失败')
  })

  it('accepts an empty instance list but rejects malformed responses', async () => {
    getInstances.mockResolvedValueOnce([]).mockResolvedValueOnce(null)
    injectBridge()
    await expect(loadInstances(target)).resolves.toEqual([])
    await expect(loadInstances(target)).rejects.toThrow('实例列表格式错误')
  })
})

describe('manager readiness notification', () => {
  it('notifies the backend after rendering, including a retry after 30 seconds', async () => {
    vi.useFakeTimers()
    const target = new EventTarget()
    const get_instances = vi
      .fn()
      .mockImplementationOnce(() => new Promise(() => {}))
      .mockResolvedValueOnce([{ name: '重试成功', path: 'instance' }])
    const mark_ready = vi.fn()
    target.pywebview = { api: { get_instances, mark_ready } }
    const render = vi.fn(async () => {
      expect(mark_ready).not.toHaveBeenCalled()
    })
    try {
      const failed = initializeManager(render, target)
      const rejection = expect(failed).rejects.toThrow('加载实例列表超时')
      await vi.advanceTimersByTimeAsync(35000)
      await rejection
      expect(mark_ready).not.toHaveBeenCalled()
      await initializeManager(render, target)
      expect(render).toHaveBeenCalledExactlyOnceWith([{ name: '重试成功', path: 'instance' }])
      expect(mark_ready).toHaveBeenCalledOnce()
    } finally {
      vi.useRealTimers()
    }
  })
})
