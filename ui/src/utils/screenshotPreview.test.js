import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { createScreenshotPreview } from './screenshotPreview.js'

describe('memory screenshot preview', () => {
  let preview
  let fetchSnapshot
  let onChange
  let createUrl
  let revokeUrl

  beforeEach(() => {
    vi.useFakeTimers()
    createUrl = vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:frame')
    revokeUrl = vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {})
    fetchSnapshot = vi.fn().mockResolvedValue({
      status: 200,
      data: new Blob(['jpeg']),
      headers: { etag: '"frame-1"' }
    })
    onChange = vi.fn()
    preview = createScreenshotPreview({ fetchSnapshot, onChange })
  })

  afterEach(() => {
    preview.stop()
    vi.useRealTimers()
    vi.restoreAllMocks()
  })

  it('polls without log messages and avoids retransmitting an unchanged image', async () => {
    preview.start()
    await vi.advanceTimersByTimeAsync(0)
    expect(onChange).toHaveBeenLastCalledWith('blob:frame')
    fetchSnapshot.mockResolvedValue({ status: 304, headers: {} })
    await vi.advanceTimersByTimeAsync(1000)
    expect(fetchSnapshot.mock.calls[1][0].headers).toEqual({ 'If-None-Match': '"frame-1"' })
    expect(createUrl).toHaveBeenCalledTimes(1)
    expect(revokeUrl).not.toHaveBeenCalled()
  })

  it('does not overlap requests on a slow connection', async () => {
    fetchSnapshot.mockImplementation(() => new Promise(() => {}))
    preview.start()
    preview.start()
    await vi.advanceTimersByTimeAsync(30000)
    expect(fetchSnapshot).toHaveBeenCalledTimes(1)
    expect(fetchSnapshot.mock.calls[0][0].timeout).toBe(10000)
    const signal = fetchSnapshot.mock.calls[0][0].signal
    preview.stop()
    expect(signal.aborted).toBe(true)
  })

  it('releases replaced images and cancels polling when closed', async () => {
    preview.start()
    await vi.advanceTimersByTimeAsync(0)
    createUrl.mockReturnValue('blob:next')
    await vi.advanceTimersByTimeAsync(1000)
    expect(revokeUrl).toHaveBeenCalledWith('blob:frame')
    preview.stop()
    expect(revokeUrl).toHaveBeenCalledWith('blob:next')
    expect(onChange).toHaveBeenLastCalledWith('')
    await vi.advanceTimersByTimeAsync(5000)
    expect(fetchSnapshot).toHaveBeenCalledTimes(2)
  })

  it('ignores a stale response after stopping and restarting', async () => {
    let finishOldRequest
    fetchSnapshot.mockImplementationOnce(
      () => new Promise((resolve) => (finishOldRequest = resolve))
    )
    preview.start()
    const oldSignal = fetchSnapshot.mock.calls[0][0].signal
    preview.stop()
    preview.start()
    await vi.advanceTimersByTimeAsync(0)
    expect(oldSignal.aborted).toBe(true)
    finishOldRequest({ status: 200, data: new Blob(['old']), headers: {} })
    await vi.advanceTimersByTimeAsync(0)
    expect(createUrl).toHaveBeenCalledTimes(1)
    await vi.advanceTimersByTimeAsync(1000)
    expect(fetchSnapshot).toHaveBeenCalledTimes(3)
  })

  it('publishes the first frame with its decoded aspect and leaves later frames on the normal path', async () => {
    let completeDecode
    const getFirstFrameAspect = vi.fn(() => new Promise((resolve) => (completeDecode = resolve)))
    preview = createScreenshotPreview({ fetchSnapshot, onChange, getFirstFrameAspect })
    preview.start()
    await vi.advanceTimersByTimeAsync(1500)
    expect(fetchSnapshot).toHaveBeenCalledTimes(1)
    expect(onChange).not.toHaveBeenCalled()

    completeDecode(4 / 3)
    await vi.advanceTimersByTimeAsync(0)
    expect(onChange).toHaveBeenLastCalledWith('blob:frame', 4 / 3)

    createUrl.mockReturnValue('blob:next')
    await vi.advanceTimersByTimeAsync(1000)
    expect(onChange).toHaveBeenLastCalledWith('blob:next')
    expect(getFirstFrameAspect).toHaveBeenCalledExactlyOnceWith('blob:frame')
  })

  it('releases a pending first frame on stop without publishing a stale decode', async () => {
    let completeDecode
    const getFirstFrameAspect = vi
      .fn()
      .mockImplementationOnce(() => new Promise((resolve) => (completeDecode = resolve)))
      .mockResolvedValueOnce(16 / 9)
    preview = createScreenshotPreview({ fetchSnapshot, onChange, getFirstFrameAspect })
    preview.start()
    await vi.advanceTimersByTimeAsync(0)
    preview.stop()
    expect(revokeUrl).toHaveBeenCalledExactlyOnceWith('blob:frame')

    createUrl.mockReturnValue('blob:next')
    preview.start()
    await vi.advanceTimersByTimeAsync(0)
    completeDecode(4 / 3)
    await vi.advanceTimersByTimeAsync(0)
    expect(onChange.mock.calls).toEqual([[''], ['blob:next', 16 / 9]])
    expect(revokeUrl).toHaveBeenCalledTimes(1)
  })

  it('discards an invalid first frame and retries without its etag', async () => {
    vi.spyOn(console, 'debug').mockImplementation(() => {})
    const getFirstFrameAspect = vi
      .fn()
      .mockRejectedValueOnce(new Error('invalid image'))
      .mockResolvedValueOnce(4 / 3)
    preview = createScreenshotPreview({ fetchSnapshot, onChange, getFirstFrameAspect })
    preview.start()
    await vi.advanceTimersByTimeAsync(0)
    expect(revokeUrl).toHaveBeenCalledExactlyOnceWith('blob:frame')
    expect(onChange).not.toHaveBeenCalled()

    createUrl.mockReturnValue('blob:next')
    await vi.advanceTimersByTimeAsync(1000)
    expect(fetchSnapshot.mock.calls[1][0].headers).toEqual({})
    expect(onChange).toHaveBeenLastCalledWith('blob:next', 4 / 3)
  })

  it('keeps the last image on a network failure and retries', async () => {
    vi.spyOn(console, 'debug').mockImplementation(() => {})
    preview.start()
    await vi.advanceTimersByTimeAsync(0)
    fetchSnapshot.mockRejectedValueOnce(new Error('network unavailable'))
    await vi.advanceTimersByTimeAsync(1000)
    expect(revokeUrl).not.toHaveBeenCalled()
    await vi.advanceTimersByTimeAsync(1000)
    expect(fetchSnapshot).toHaveBeenCalledTimes(3)
  })

  it('clears an old image and etag when the backend restarts with no frame', async () => {
    preview.start()
    await vi.advanceTimersByTimeAsync(0)
    fetchSnapshot.mockResolvedValueOnce({ status: 204, headers: {} })
    await vi.advanceTimersByTimeAsync(1000)
    expect(revokeUrl).toHaveBeenCalledWith('blob:frame')
    expect(onChange).toHaveBeenLastCalledWith('')
    await vi.advanceTimersByTimeAsync(1000)
    expect(fetchSnapshot.mock.calls[2][0].headers).toEqual({})
  })
})
