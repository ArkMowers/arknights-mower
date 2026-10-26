import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia } from 'pinia'
import axios from 'axios'
import {
  BASELINE_STORAGE_KEY,
  DEFAULT_BASELINE_CONFIG,
  DEFAULT_VIEW_PREFS,
  FAVORITES_STORAGE_KEY,
  VIEW_PREFS_STORAGE_KEY
} from '@/utils/depot_inventory'
import { useDepotPreferencesStore } from './depotPreferences'

vi.mock('axios', () => ({ default: { get: vi.fn(), put: vi.fn() } }))

const stores = []
const clone = (value) => JSON.parse(JSON.stringify(value))
const defaults = () => ({
  favorites: [],
  view: { ...DEFAULT_VIEW_PREFS },
  baseline: { ...DEFAULT_BASELINE_CONFIG }
})
let saved
let storage

function deferred() {
  let resolve, reject
  const promise = new Promise((done, fail) => {
    resolve = done
    reject = fail
  })
  return { promise, resolve, reject }
}

function createStore(pinia = createPinia()) {
  const store = useDepotPreferencesStore(pinia)
  stores.push(store)
  return store
}

beforeEach(() => {
  saved = defaults()
  storage = { getItem: vi.fn(() => null), setItem: vi.fn(), removeItem: vi.fn() }
  vi.stubGlobal('localStorage', storage)
  axios.get.mockImplementation(async () => ({ data: { depot: clone(saved) } }))
  axios.put.mockImplementation(async (_url, payload) => {
    saved = { ...saved, ...clone(payload.depot) }
    return { data: { depot: clone(saved) } }
  })
})

afterEach(() => {
  for (const store of stores.splice(0)) store.$dispose()
  vi.unstubAllGlobals()
  vi.resetAllMocks()
})

describe('instance depot preferences', () => {
  it('disables edits until loaded and shares reads and state across page visits', async () => {
    const read = deferred()
    axios.get.mockReturnValueOnce(read.promise)
    const pinia = createPinia()
    const store = createStore(pinia)
    expect(store.disabled).toBe(true)
    expect(await store.update({ favorites: ['龙门币'] })).toBe(false)
    const first = store.load()
    const second = store.load()
    expect(axios.get).toHaveBeenCalledOnce()
    read.resolve({ data: { depot: { ...defaults(), favorites: ['合成玉'] } } })
    expect(await Promise.all([first, second])).toEqual([true, true])
    expect(store.disabled).toBe(false)
    expect(useDepotPreferencesStore(pinia)).toBe(store)
    expect(await store.load()).toBe(true)
    expect(store.favorites).toEqual(['合成玉'])
    expect(axios.get).toHaveBeenCalledWith(expect.stringMatching(/\/gui\/depot$/), {
      timeout: 5000
    })
    expect(storage.getItem).not.toHaveBeenCalled()
    expect(axios.put).not.toHaveBeenCalled()
  })

  it('uses saved preferences without accessing browser storage even when access throws', async () => {
    const getStorage = vi.fn(() => {
      throw new Error('storage denied')
    })
    Object.defineProperty(globalThis, 'localStorage', { configurable: true, get: getStorage })
    saved.favorites = ['至纯源石']
    saved.view.stockFilter = 'favorite'
    saved.baseline = { ...DEFAULT_BASELINE_CONFIG, mode: 'snapshot', startKey: '100' }
    const store = createStore()
    expect(await store.load()).toBe(true)
    expect(store.favorites).toEqual(['至纯源石'])
    expect(store.view.stockFilter).toBe('favorite')
    expect(store.baseline.startKey).toBe('100')
    expect(getStorage).not.toHaveBeenCalled()
  })

  it('migrates all legacy preferences only when the instance has no saved depot settings', async () => {
    axios.get.mockResolvedValueOnce({ data: { depot: null } })
    const legacy = {
      [FAVORITES_STORAGE_KEY]: JSON.stringify(['龙门币', '龙门币', '合成玉']),
      [VIEW_PREFS_STORAGE_KEY]: JSON.stringify({ ...DEFAULT_VIEW_PREFS, sortMode: 'count-desc' }),
      [BASELINE_STORAGE_KEY]: JSON.stringify({ ...DEFAULT_BASELINE_CONFIG, preset: '7d' })
    }
    storage.getItem.mockImplementation((key) => legacy[key] ?? null)
    const store = createStore()
    expect(await store.load()).toBe(true)
    expect(axios.put).toHaveBeenCalledWith(
      expect.stringMatching(/\/gui\/depot$/),
      {
        depot: {
          favorites: ['龙门币', '合成玉'],
          view: { ...DEFAULT_VIEW_PREFS, sortMode: 'count-desc' },
          baseline: { ...DEFAULT_BASELINE_CONFIG, preset: '7d' }
        },
        migrate: true
      },
      { timeout: 5000 }
    )
    expect(store.favorites).toEqual(['龙门币', '合成玉'])
    expect(store.view.sortMode).toBe('count-desc')
    expect(store.baseline.preset).toBe('7d')
    expect(storage.setItem).not.toHaveBeenCalled()
    expect(storage.removeItem).not.toHaveBeenCalled()
  })

  it('migrates defaults if browser storage access is unavailable', async () => {
    axios.get.mockResolvedValueOnce({ data: { depot: null } })
    Object.defineProperty(globalThis, 'localStorage', {
      configurable: true,
      get() {
        throw new Error('storage denied')
      }
    })
    const store = createStore()
    expect(await store.load()).toBe(true)
    expect(axios.put.mock.calls[0][1]).toEqual({ depot: defaults(), migrate: true })
  })

  it('uses the backend winner when another client initializes during migration', async () => {
    axios.get.mockResolvedValueOnce({ data: { depot: null } })
    storage.getItem.mockReturnValue(JSON.stringify(['龙门币']))
    const winner = { ...defaults(), favorites: ['至纯源石'] }
    axios.put.mockResolvedValueOnce({ data: { depot: winner } })
    const store = createStore()
    expect(await store.load()).toBe(true)
    expect(store.favorites).toEqual(['至纯源石'])
    expect(storage.setItem).not.toHaveBeenCalled()
  })

  it('keeps edits disabled after a read failure and retries without overwriting server state', async () => {
    axios.get.mockRejectedValueOnce(new Error('offline'))
    const store = createStore()
    expect(await store.load()).toBe(false)
    expect(store.disabled).toBe(true)
    expect(store.error).toContain('读取失败')
    expect(await store.toggleFavorite('龙门币')).toBe(false)
    expect(axios.put).not.toHaveBeenCalled()
    expect(await store.retry()).toBe(true)
    expect(store.error).toBe('')
    expect(storage.getItem).not.toHaveBeenCalled()
  })

  it('keeps edits disabled after a failed migration and rereads the backend on retry', async () => {
    axios.get.mockResolvedValueOnce({ data: { depot: null } })
    axios.put.mockRejectedValueOnce(new Error('disk full'))
    const store = createStore()
    expect(await store.load()).toBe(false)
    expect(store.disabled).toBe(true)
    expect(store.error).toContain('迁移失败')
    saved.favorites = ['合成玉']
    expect(await store.retry()).toBe(true)
    expect(store.favorites).toEqual(['合成玉'])
    expect(axios.put).toHaveBeenCalledOnce()
  })

  it.each([undefined, {}, { depot: {} }, { depot: { ...defaults(), view: {} } }])(
    'rejects an incomplete response and keeps editing disabled: %j',
    async (data) => {
      axios.get.mockResolvedValueOnce({ data })
      const store = createStore()
      expect(await store.load()).toBe(false)
      expect(store.disabled).toBe(true)
      expect(axios.put).not.toHaveBeenCalled()
    }
  )

  it('saves edits through the instance endpoint without browser writes', async () => {
    const store = createStore()
    await store.load()
    expect(await store.toggleFavorite('龙门币')).toBe(true)
    expect(store.favorites).toEqual(['龙门币'])
    expect(axios.put.mock.calls[0][1]).toEqual({ depot: { favorites: ['龙门币'] } })
    expect(await store.toggleFavorite('龙门币')).toBe(true)
    expect(store.favorites).toEqual([])
    expect(storage.setItem).not.toHaveBeenCalled()
  })

  it('serializes saves, coalesces pending groups, and preserves newer local edits', async () => {
    const firstSave = deferred()
    const secondSave = deferred()
    axios.put.mockReturnValueOnce(firstSave.promise).mockReturnValueOnce(secondSave.promise)
    const store = createStore()
    await store.load()
    const request = store.update({ favorites: ['龙门币'] })
    store.update({ view: { ...store.view, sortMode: 'count-desc' } })
    store.update({ favorites: ['合成玉'] })
    store.update({ favorites: ['至纯源石'] })
    store.update({ baseline: { ...store.baseline, preset: '30d' } })
    expect(store.saving).toBe(true)
    expect(store.disabled).toBe(false)
    expect(axios.put).toHaveBeenCalledOnce()
    firstSave.resolve({ data: { depot: { ...defaults(), favorites: ['龙门币'] } } })
    await vi.waitFor(() => expect(axios.put).toHaveBeenCalledTimes(2))
    expect(store.favorites).toEqual(['至纯源石'])
    expect(store.view.sortMode).toBe('count-desc')
    expect(store.baseline.preset).toBe('30d')
    const pending = axios.put.mock.calls[1][1].depot
    expect(pending).toEqual({
      favorites: ['至纯源石'],
      view: { ...DEFAULT_VIEW_PREFS, sortMode: 'count-desc' },
      baseline: { ...DEFAULT_BASELINE_CONFIG, preset: '30d' }
    })
    secondSave.resolve({ data: { depot: clone(pending) } })
    expect(await request).toBe(true)
    expect(store.saving).toBe(false)
    expect(store.favorites).toEqual(['至纯源石'])
  })

  it('retains failed and newer edits until explicit retry without repeating requests', async () => {
    const failedSave = deferred()
    axios.put.mockReturnValueOnce(failedSave.promise)
    const store = createStore()
    await store.load()
    const request = store.update({ favorites: ['龙门币'] })
    store.update({ favorites: ['合成玉'] })
    store.update({ view: { ...store.view, stockFilter: 'favorite' } })
    failedSave.reject(new Error('offline'))
    expect(await request).toBe(false)
    expect(store.favorites).toEqual(['合成玉'])
    expect(store.error).toContain('保存失败')
    expect(store.disabled).toBe(false)
    expect(await store.update({ baseline: { ...store.baseline, preset: '7d' } })).toBe(false)
    expect(axios.put).toHaveBeenCalledOnce()
    expect(await store.retry()).toBe(true)
    expect(axios.put.mock.calls[1][1]).toEqual({
      depot: {
        favorites: ['合成玉'],
        view: { ...DEFAULT_VIEW_PREFS, stockFilter: 'favorite' },
        baseline: { ...DEFAULT_BASELINE_CONFIG, preset: '7d' }
      }
    })
    expect(store.error).toBe('')
    expect(store.saving).toBe(false)
  })

  it('retains local preferences when a save response is malformed', async () => {
    const store = createStore()
    await store.load()
    axios.put.mockResolvedValueOnce({ data: { depot: null } })
    expect(await store.toggleFavorite('龙门币')).toBe(false)
    expect(store.favorites).toEqual(['龙门币'])
    expect(store.error).toContain('保存失败')
  })
})
