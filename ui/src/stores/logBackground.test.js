import { createPinia, disposePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import axios from 'axios'
import { useLogBackgroundStore, MAX_BACKGROUND_BYTES } from './logBackground'

vi.mock('axios', () => ({ default: { get: vi.fn(), put: vi.fn(), delete: vi.fn() } }))

function deferred() {
  let resolve
  const promise = new Promise((done) => (resolve = done))
  return { promise, resolve }
}

const picture = () => new Blob(['webp'], { type: 'image/webp' })
const imageResponse = () => ({ status: 200, data: picture() })

describe('running log background', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    let serial = 0
    vi.spyOn(URL, 'createObjectURL').mockImplementation(() => `blob:background-${++serial}`)
    vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {})
    axios.get.mockResolvedValue({ status: 204 })
    axios.put.mockResolvedValue(imageResponse())
    axios.delete.mockResolvedValue({ status: 204 })
  })

  it('shares one initial read, blocks edits until it finishes and loads the saved image', async () => {
    const pinia = createPinia()
    const store = useLogBackgroundStore(pinia)
    const initial = deferred()
    axios.get.mockReturnValueOnce(initial.promise)
    const first = store.load()
    const second = useLogBackgroundStore(pinia).load()
    expect(await store.upload(picture())).toBe(false)
    expect(await store.reset()).toBe(false)
    expect(axios.get).toHaveBeenCalledOnce()
    expect(axios.put).not.toHaveBeenCalled()
    expect(store.url).toBe('/bg.webp')
    initial.resolve(imageResponse())
    expect(await first).toBe(true)
    expect(await second).toBe(true)
    expect(store.url).toBe('blob:background-1')
    expect(store.busy).toBe(false)
    await store.load()
    expect(axios.get).toHaveBeenCalledOnce()
    disposePinia(pinia)
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:background-1')
  })

  it('updates shared consumers after each upload and reset without refreshing', async () => {
    const pinia = createPinia()
    const settings = useLogBackgroundStore(pinia)
    const log = useLogBackgroundStore(pinia)
    await settings.load()
    expect(await settings.upload(picture())).toBe(true)
    expect(log.url).toBe('blob:background-1')
    expect(axios.put).toHaveBeenCalledWith(
      expect.stringMatching(/\/gui\/log-background$/),
      expect.any(Blob),
      { headers: { 'Content-Type': 'image/webp' }, responseType: 'blob', timeout: 30000 }
    )
    await settings.upload(picture())
    expect(log.url).toBe('blob:background-2')
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:background-1')
    expect(await settings.reset()).toBe(true)
    expect(log.url).toBe('/bg.webp')
    expect(settings.customUrl).toBe('')
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:background-2')
    expect(await settings.reset()).toBe(false)
    expect(axios.delete).toHaveBeenCalledOnce()
    disposePinia(pinia)
  })

  it('retains the displayed image on failed upload or reset and allows retry', async () => {
    const store = useLogBackgroundStore(createPinia())
    axios.get.mockResolvedValueOnce(imageResponse())
    await store.load()
    axios.put.mockRejectedValueOnce({
      response: { data: new Blob([JSON.stringify({ message: '图片像素不能超过 2400 万' })]) }
    })
    expect(await store.upload(picture())).toBe(false)
    expect(store.url).toBe('blob:background-1')
    expect(store.error).toContain('2400 万')
    axios.delete.mockRejectedValueOnce(new Error('offline'))
    expect(await store.reset()).toBe(false)
    expect(store.url).toBe('blob:background-1')
    expect(store.error).toContain('恢复默认失败')
    expect(await store.upload(picture())).toBe(true)
    expect(store.error).toBe('')
    expect(store.url).toBe('blob:background-2')
  })

  it('rejects unsupported or oversized uploads before sending them', async () => {
    const store = useLogBackgroundStore(createPinia())
    await store.load()
    expect(await store.upload(new Blob(['svg'], { type: 'image/svg+xml' }))).toBe(false)
    expect(await store.upload({ type: 'image/png', size: MAX_BACKGROUND_BYTES + 1 })).toBe(false)
    expect(store.error).toContain('8 MiB')
    expect(axios.put).not.toHaveBeenCalled()
    expect(store.url).toBe('/bg.webp')
  })

  it('can retry an initial failure and restore a persisted image in a new store', async () => {
    const first = useLogBackgroundStore(createPinia())
    axios.get.mockRejectedValueOnce(new Error('offline'))
    expect(await first.load()).toBe(false)
    expect(first.loaded).toBe(false)
    expect(first.error).toContain('读取失败')
    expect(await first.load()).toBe(true)
    await first.upload(picture())
    const second = useLogBackgroundStore(createPinia())
    axios.get.mockResolvedValueOnce(imageResponse())
    expect(await second.load()).toBe(true)
    expect(second.customUrl).toBe('blob:background-2')
    expect(second.error).toBe('')
  })

  it('keeps an existing URL when a save returns an unexpected response', async () => {
    const store = useLogBackgroundStore(createPinia())
    axios.get.mockResolvedValueOnce(imageResponse())
    await store.load()
    axios.put.mockResolvedValueOnce({ status: 200, data: {} })
    expect(await store.upload(picture())).toBe(false)
    expect(store.url).toBe('blob:background-1')
    axios.delete.mockResolvedValueOnce({ status: 200 })
    expect(await store.reset()).toBe(false)
    expect(store.url).toBe('blob:background-1')
    expect(URL.revokeObjectURL).not.toHaveBeenCalled()
  })

  it('does not allocate an object URL when a pending read finishes after disposal', async () => {
    const pinia = createPinia()
    const store = useLogBackgroundStore(pinia)
    const response = deferred()
    axios.get.mockReturnValueOnce(response.promise)
    const pending = store.load()
    disposePinia(pinia)
    response.resolve(imageResponse())
    await pending
    expect(URL.createObjectURL).not.toHaveBeenCalled()
  })
})
