import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ref, watch } from 'vue'

import { createScreenshotPreview } from './screenshotPreview.js'

describe('memory screenshot preview', () => {
  let preview
  let fetchSnapshot
  let onChange
  let createUrl
  let revokeUrl
  let decode

  beforeEach(() => {
    vi.useFakeTimers()
    decode = vi.fn().mockResolvedValue()
    vi.stubGlobal(
      'Image',
      class {
        naturalWidth = 16
        naturalHeight = 9
        decode() {
          return decode(this.src)
        }
      }
    )
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
    vi.unstubAllGlobals()
  })

  it('polls without log messages and avoids retransmitting an unchanged image', async () => {
    preview.start()
    await vi.advanceTimersByTimeAsync(0)
    expect(onChange).toHaveBeenLastCalledWith('blob:frame', 16 / 9)
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

  it('restores a cached frame before its refresh reply and releases only component URLs on stop', async () => {
    let snapshot = { blob: new Blob(['cached']), etag: 'cached-etag', aspect: 4 / 3 }
    fetchSnapshot.mockImplementation(() => new Promise(() => {}))
    preview = createScreenshotPreview({
      fetchSnapshot,
      onChange,
      getCachedSnapshot: () => snapshot,
      cacheSnapshot: (value) => (snapshot = value)
    })
    expect(onChange).toHaveBeenLastCalledWith('blob:frame', 4 / 3)
    preview.start()
    expect(fetchSnapshot.mock.calls[0][0].headers).toEqual({ 'If-None-Match': 'cached-etag' })
    preview.stop()
    expect(fetchSnapshot.mock.calls[0][0].signal.aborted).toBe(true)
    expect(revokeUrl).toHaveBeenCalledWith('blob:frame')
    expect(snapshot.blob.size).toBe(6)
    createUrl.mockReturnValue('blob:restored')
    preview.start()
    expect(onChange).toHaveBeenLastCalledWith('blob:restored', 4 / 3)
  })

  it('forgets a cached frame after an empty response and keeps only the most recent image', async () => {
    let snapshot = { blob: new Blob(['old']), etag: 'old', aspect: 4 / 3 }
    preview = createScreenshotPreview({
      fetchSnapshot,
      onChange,
      getCachedSnapshot: () => snapshot,
      cacheSnapshot: (value) => (snapshot = value)
    })
    preview.start()
    await vi.advanceTimersByTimeAsync(0)
    expect(snapshot).toEqual({ blob: expect.any(Blob), etag: '"frame-1"', aspect: 16 / 9 })
    expect(await snapshot.blob.text()).toBe('jpeg')
    fetchSnapshot.mockResolvedValue({ status: 204, headers: {} })
    await vi.advanceTimersByTimeAsync(1000)
    expect(snapshot).toBeNull()
    expect(onChange).toHaveBeenLastCalledWith('')
    preview.stop()
    createUrl.mockClear()
    preview.start()
    expect(createUrl).not.toHaveBeenCalled()
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

  it('keeps the old URL live while Vue patches the new image source', async () => {
    const src = ref('')
    const atPatch = vi.fn()
    const unwatch = watch(
      src,
      (url, oldUrl) => {
        if (oldUrl && url) atPatch(revokeUrl.mock.calls.map(([revoked]) => revoked))
      },
      { flush: 'post' }
    )
    try {
      preview = createScreenshotPreview({
        fetchSnapshot,
        onChange: (url) => (src.value = url)
      })
      preview.start()
      await vi.advanceTimersByTimeAsync(0)
      createUrl.mockReturnValue('blob:next')
      await vi.advanceTimersByTimeAsync(1000)
      expect(atPatch).toHaveBeenCalledExactlyOnceWith([])
      expect(revokeUrl).toHaveBeenCalledExactlyOnceWith('blob:frame')
    } finally {
      unwatch()
    }
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

  it('publishes each frame only after its decode finishes', async () => {
    let completeDecode
    decode.mockImplementation(() => new Promise((resolve) => (completeDecode = resolve)))
    preview.start()
    await vi.advanceTimersByTimeAsync(1500)
    expect(fetchSnapshot).toHaveBeenCalledTimes(1)
    expect(onChange).not.toHaveBeenCalled()

    completeDecode()
    await vi.advanceTimersByTimeAsync(0)
    expect(onChange).toHaveBeenLastCalledWith('blob:frame', 16 / 9)

    createUrl.mockReturnValue('blob:next')
    await vi.advanceTimersByTimeAsync(1000)
    expect(onChange).toHaveBeenCalledTimes(1)
    expect(revokeUrl).not.toHaveBeenCalled()

    completeDecode()
    await vi.advanceTimersByTimeAsync(0)
    expect(onChange).toHaveBeenLastCalledWith('blob:next', 16 / 9)
    expect(decode.mock.calls).toEqual([['blob:frame'], ['blob:next']])
  })

  it('releases a pending first frame on stop without publishing a stale decode', async () => {
    let completeDecode
    decode.mockImplementationOnce(() => new Promise((resolve) => (completeDecode = resolve)))
    preview.start()
    await vi.advanceTimersByTimeAsync(0)
    preview.stop()
    expect(revokeUrl).toHaveBeenCalledExactlyOnceWith('blob:frame')

    createUrl.mockReturnValue('blob:next')
    preview.start()
    await vi.advanceTimersByTimeAsync(0)
    completeDecode()
    await vi.advanceTimersByTimeAsync(0)
    expect(onChange.mock.calls).toEqual([[''], ['blob:next', 16 / 9]])
    expect(revokeUrl).toHaveBeenCalledTimes(1)
  })

  it('discards an invalid first frame and retries without its etag', async () => {
    vi.spyOn(console, 'debug').mockImplementation(() => {})
    decode.mockRejectedValueOnce(new Error('invalid image'))
    preview.start()
    await vi.advanceTimersByTimeAsync(0)
    expect(revokeUrl).toHaveBeenCalledExactlyOnceWith('blob:frame')
    expect(onChange).not.toHaveBeenCalled()

    createUrl.mockReturnValue('blob:next')
    await vi.advanceTimersByTimeAsync(1000)
    expect(fetchSnapshot.mock.calls[1][0].headers).toEqual({})
    expect(onChange).toHaveBeenLastCalledWith('blob:next', 16 / 9)
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
