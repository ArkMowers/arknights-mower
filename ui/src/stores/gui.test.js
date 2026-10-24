import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia } from 'pinia'
import axios from 'axios'
import { useGuiStore } from './gui'

vi.mock('axios', () => ({ default: { get: vi.fn(), put: vi.fn() } }))

const stores = []

function deferred() {
  let resolve, reject
  const promise = new Promise((done, fail) => {
    resolve = done
    reject = fail
  })
  return { promise, resolve, reject }
}

function createStore() {
  const pinia = createPinia()
  const store = useGuiStore(pinia)
  stores.push(store)
  return { pinia, store }
}

beforeEach(() => {
  axios.get.mockResolvedValue({ data: { software_version_display: 'version' } })
  axios.put.mockImplementation(async (_url, data) => ({ data }))
})

afterEach(() => {
  for (const store of stores.splice(0)) store.$dispose()
  vi.resetAllMocks()
})

describe('shared GUI appearance preferences', () => {
  it('shares one version-default store and disables editing before the initial read', async () => {
    const { pinia, store } = createStore()
    expect(useGuiStore(pinia)).toBe(store)
    expect(store.softwareVersionDisplay).toBe('version')
    expect(store.softwareVersionLanguage).toBe('en')
    expect(store.loaded).toBe(false)
    expect(store.displayDisabled).toBe(true)
    expect(await store.setSoftwareVersionDisplay('channel')).toBe(false)
    expect(axios.put).not.toHaveBeenCalled()
    expect(store.softwareVersionDisplay).toBe('version')
  })

  it('merges concurrent reads and restores the saved mode from the appearance endpoint', async () => {
    const read = deferred()
    axios.get.mockReturnValueOnce(read.promise)
    const { pinia, store } = createStore()
    const first = store.load()
    const second = useGuiStore(pinia).load()
    expect(axios.get).toHaveBeenCalledOnce()
    expect(axios.get).toHaveBeenCalledWith(expect.stringMatching(/\/gui\/appearance$/), {
      timeout: 5000
    })
    expect(store.loading).toBe(true)
    expect(store.displayDisabled).toBe(true)
    expect(await store.setSoftwareVersionDisplay('channel')).toBe(false)

    read.resolve({ data: { software_version_display: 'channel' } })
    expect(await Promise.all([first, second])).toEqual([true, true])
    expect(store.softwareVersionDisplay).toBe('channel')
    expect(store.loaded).toBe(true)
    expect(store.loading).toBe(false)
    expect(store.displayDisabled).toBe(false)
    expect(await store.load()).toBe(true)
    expect(axios.get).toHaveBeenCalledOnce()
    expect(axios.put).not.toHaveBeenCalled()
  })

  it('keeps editing disabled after a read failure and lets retry load the saved preference', async () => {
    axios.get.mockRejectedValueOnce(new Error('unavailable'))
    const { store } = createStore()
    expect(await store.load()).toBe(false)
    expect(store.loaded).toBe(false)
    expect(store.loading).toBe(false)
    expect(store.displayDisabled).toBe(true)
    expect(store.error).toContain('读取失败')
    expect(await store.setSoftwareVersionDisplay('channel')).toBe(false)
    expect(axios.put).not.toHaveBeenCalled()

    axios.get.mockResolvedValueOnce({ data: { software_version_display: 'channel' } })
    expect(await store.retry()).toBe(true)
    expect(store.softwareVersionDisplay).toBe('channel')
    expect(store.displayDisabled).toBe(false)
    expect(store.error).toBe('')
    expect(axios.get).toHaveBeenCalledTimes(2)
  })

  it.each([undefined, {}, { software_version_display: 'other' }])(
    'does not enable editing after an invalid backend response %j',
    async (data) => {
      axios.get.mockResolvedValueOnce({ data })
      const { store } = createStore()
      expect(await store.load()).toBe(false)
      expect(store.softwareVersionDisplay).toBe('version')
      expect(store.displayDisabled).toBe(true)
      expect(store.error).toContain('读取失败')
      expect(axios.put).not.toHaveBeenCalled()
    }
  )

  it('updates shared state immediately and permits only one save while busy', async () => {
    const { pinia, store } = createStore()
    await store.load()
    const save = deferred()
    axios.put.mockReturnValueOnce(save.promise)
    const pending = store.setSoftwareVersionDisplay('channel')
    expect(useGuiStore(pinia).softwareVersionDisplay).toBe('channel')
    expect(store.saving).toBe(true)
    expect(store.displayDisabled).toBe(true)
    expect(axios.put).toHaveBeenCalledWith(
      expect.stringMatching(/\/gui\/appearance$/),
      { software_version_display: 'channel' },
      { timeout: 5000 }
    )
    expect(await store.setSoftwareVersionDisplay('version')).toBe(false)
    expect(await store.retry()).toBe(false)
    expect(axios.put).toHaveBeenCalledOnce()

    save.resolve({ data: { software_version_display: 'channel' } })
    expect(await pending).toBe(true)
    expect(store.softwareVersionDisplay).toBe('channel')
    expect(store.saving).toBe(false)
    expect(store.displayDisabled).toBe(false)
    expect(store.error).toBe('')
  })

  it.each(['request failure', 'unconfirmed response'])(
    'rolls back a %s and retries the requested mode rather than the restored mode',
    async (failure) => {
      const { store } = createStore()
      await store.load()
      if (failure === 'request failure') axios.put.mockRejectedValueOnce(new Error('offline'))
      else axios.put.mockResolvedValueOnce({ data: { software_version_display: 'version' } })
      expect(await store.setSoftwareVersionDisplay('channel')).toBe(false)
      expect(store.softwareVersionDisplay).toBe('version')
      expect(store.saving).toBe(false)
      expect(store.displayDisabled).toBe(false)
      expect(store.error).toContain('已恢复原来的显示')
      expect(axios.put).toHaveBeenCalledOnce()

      expect(await store.retry()).toBe(true)
      expect(axios.put.mock.calls.map(([, payload]) => payload)).toEqual([
        { software_version_display: 'channel' },
        { software_version_display: 'channel' }
      ])
      expect(store.softwareVersionDisplay).toBe('channel')
      expect(store.error).toBe('')
    }
  )

  it('avoids writes for invalid values and an unchanged saved mode', async () => {
    const { store } = createStore()
    await store.load()
    expect(await store.setSoftwareVersionDisplay('version')).toBe(true)
    expect(await store.setSoftwareVersionDisplay('source')).toBe(false)
    expect(await store.setSoftwareVersionDisplay(null)).toBe(false)
    expect(store.softwareVersionDisplay).toBe('version')
    expect(axios.put).not.toHaveBeenCalled()
  })

  it('restores the backend preference in a new application store after a reload', async () => {
    let saved = 'version'
    axios.get.mockImplementation(async () => ({ data: { software_version_display: saved } }))
    axios.put.mockImplementation(async (_url, payload) => {
      saved = payload.software_version_display
      return { data: { software_version_display: saved } }
    })
    const first = createStore().store
    await first.load()
    await first.setSoftwareVersionDisplay('channel')
    const reloaded = createStore().store
    expect(reloaded).not.toBe(first)
    expect(reloaded.softwareVersionDisplay).toBe('version')
    await reloaded.load()
    expect(reloaded.softwareVersionDisplay).toBe('channel')
    expect(reloaded.loaded).toBe(true)
    expect(axios.get).toHaveBeenCalledTimes(2)
    expect(axios.put).toHaveBeenCalledOnce()
  })

  it('loads the task layout with the shared initial read and supports older responses', async () => {
    const first = createStore().store
    expect(first.taskSettingsLayout).toBe('checklist')
    expect(first.layoutDisabled).toBe(true)
    expect(await first.setTaskSettingsLayout('waterfall')).toBe(false)
    axios.get.mockResolvedValueOnce({
      data: { software_version_display: 'channel', task_settings_layout: 'waterfall' }
    })
    await first.load()
    expect(first.taskSettingsLayout).toBe('waterfall')
    expect(first.softwareVersionDisplay).toBe('channel')
    expect(first.layoutDisabled).toBe(false)
    const second = createStore().store
    await second.load()
    expect(second.taskSettingsLayout).toBe('checklist')
    expect(axios.put).not.toHaveBeenCalled()
  })

  it('updates task layout immediately, saves only that field and serializes appearance edits', async () => {
    const { store } = createStore()
    await store.load()
    const save = deferred()
    axios.put.mockReturnValueOnce(save.promise)
    const pending = store.setTaskSettingsLayout('waterfall')
    expect(store.taskSettingsLayout).toBe('waterfall')
    expect(store.layoutSaving).toBe(true)
    expect(store.layoutDisabled).toBe(true)
    expect(await store.setTaskSettingsLayout('checklist')).toBe(false)
    expect(await store.setSoftwareVersionDisplay('channel')).toBe(false)
    expect(axios.put).toHaveBeenCalledWith(
      expect.stringMatching(/\/gui\/appearance$/),
      { task_settings_layout: 'waterfall' },
      { timeout: 5000 }
    )
    save.resolve({ data: { task_settings_layout: 'waterfall' } })
    expect(await pending).toBe(true)
    expect(store.layoutDisabled).toBe(false)
    expect(store.softwareVersionDisplay).toBe('version')
    expect(await store.setTaskSettingsLayout('waterfall')).toBe(true)
    expect(await store.setTaskSettingsLayout('grid')).toBe(false)
    expect(axios.put).toHaveBeenCalledOnce()
  })

  it.each(['rejected', 'unconfirmed'])(
    'rolls back a %s task layout save and retries without a software version error',
    async (failure) => {
      const { store } = createStore()
      await store.load()
      if (failure === 'rejected') axios.put.mockRejectedValueOnce(new Error('offline'))
      else axios.put.mockResolvedValueOnce({ data: { task_settings_layout: 'checklist' } })
      expect(await store.setTaskSettingsLayout('waterfall')).toBe(false)
      expect(store.taskSettingsLayout).toBe('checklist')
      expect(store.layoutError).toContain('已恢复原来的显示')
      expect(store.error).toBe('')
      expect(store.layoutSaving).toBe(false)
      expect(await store.retryTaskSettingsLayout()).toBe(true)
      expect(store.taskSettingsLayout).toBe('waterfall')
      expect(store.layoutError).toBe('')
      expect(store.error).toBe('')
      expect(axios.put.mock.calls.map(([, payload]) => payload)).toEqual([
        { task_settings_layout: 'waterfall' },
        { task_settings_layout: 'waterfall' }
      ])
    }
  )

  it('restores the saved task layout in a new application store', async () => {
    const saved = { software_version_display: 'channel', task_settings_layout: 'checklist' }
    axios.get.mockImplementation(async () => ({ data: { ...saved } }))
    axios.put.mockImplementation(async (_url, payload) => {
      Object.assign(saved, payload)
      return { data: { ...payload } }
    })
    const first = createStore().store
    await first.load()
    await first.setTaskSettingsLayout('waterfall')
    const reloaded = createStore().store
    await reloaded.load()
    expect(reloaded.taskSettingsLayout).toBe('waterfall')
    expect(reloaded.softwareVersionDisplay).toBe('channel')
  })

  it('loads the saved language and defaults older appearance responses to English', async () => {
    axios.get.mockResolvedValueOnce({
      data: { software_version_display: 'channel', software_version_language: 'zh' }
    })
    const first = createStore().store
    expect(await first.setSoftwareVersionLanguage('zh')).toBe(false)
    await first.load()
    expect(first.softwareVersionLanguage).toBe('zh')
    const older = createStore().store
    await older.load()
    expect(older.softwareVersionLanguage).toBe('en')
    expect(axios.put).not.toHaveBeenCalled()
  })

  it.each(['zh-CN', null, false, 1])('rejects the invalid loaded language %j', async (value) => {
    axios.get.mockResolvedValueOnce({
      data: { software_version_display: 'channel', software_version_language: value }
    })
    const { store } = createStore()
    expect(await store.load()).toBe(false)
    expect(store.softwareVersionLanguage).toBe('en')
    expect(store.displayDisabled).toBe(true)
    expect(store.error).toContain('读取失败')
    expect(await store.setSoftwareVersionLanguage('zh')).toBe(false)
    expect(axios.put).not.toHaveBeenCalled()
  })

  it('updates the shared language immediately, saves only that field and serializes appearance edits', async () => {
    const { pinia, store } = createStore()
    await store.load()
    const save = deferred()
    axios.put.mockReturnValueOnce(save.promise)
    const pending = store.setSoftwareVersionLanguage('zh')
    expect(useGuiStore(pinia).softwareVersionLanguage).toBe('zh')
    expect(store.saving).toBe(true)
    expect(store.displayDisabled).toBe(true)
    expect(await store.setSoftwareVersionDisplay('channel')).toBe(false)
    expect(await store.setTaskSettingsLayout('waterfall')).toBe(false)
    expect(await store.setSoftwareVersionLanguage('en')).toBe(false)
    expect(axios.put).toHaveBeenCalledWith(
      expect.stringMatching(/\/gui\/appearance$/),
      { software_version_language: 'zh' },
      { timeout: 5000 }
    )
    save.resolve({ data: { software_version_language: 'zh' } })
    expect(await pending).toBe(true)
    expect(store.softwareVersionDisplay).toBe('version')
    expect(store.taskSettingsLayout).toBe('checklist')
    expect(store.displayDisabled).toBe(false)
    expect(await store.setSoftwareVersionLanguage('zh')).toBe(true)
    expect(await store.setSoftwareVersionLanguage('中文')).toBe(false)
    expect(await store.setSoftwareVersionLanguage(null)).toBe(false)
    expect(axios.put).toHaveBeenCalledOnce()
  })

  it.each([
    ['rejected', 'en', 'zh'],
    ['rejected', 'zh', 'en'],
    ['unconfirmed', 'en', 'zh'],
    ['unconfirmed', 'zh', 'en']
  ])(
    'rolls back a %s language save from %s to %s and retries the requested language',
    async (failure, previous, requested) => {
      axios.get.mockResolvedValueOnce({
        data: { software_version_display: 'channel', software_version_language: previous }
      })
      const { store } = createStore()
      await store.load()
      if (failure === 'rejected') axios.put.mockRejectedValueOnce(new Error('offline'))
      else axios.put.mockResolvedValueOnce({ data: { software_version_language: previous } })
      expect(await store.setSoftwareVersionLanguage(requested)).toBe(false)
      expect(store.softwareVersionLanguage).toBe(previous)
      expect(store.softwareVersionDisplay).toBe('channel')
      expect(store.error).toContain('语言保存失败')
      expect(store.displayDisabled).toBe(false)
      expect(await store.retry()).toBe(true)
      expect(store.softwareVersionLanguage).toBe(requested)
      expect(store.error).toBe('')
      expect(store.layoutError).toBe('')
      expect(axios.put.mock.calls.map(([, payload]) => payload)).toEqual([
        { software_version_language: requested },
        { software_version_language: requested }
      ])
    }
  )

  it('restores the saved language after reload while keeping other appearance choices', async () => {
    const saved = {
      software_version_display: 'channel',
      software_version_language: 'en',
      task_settings_layout: 'waterfall'
    }
    axios.get.mockImplementation(async () => ({ data: { ...saved } }))
    axios.put.mockImplementation(async (_url, payload) => {
      Object.assign(saved, payload)
      return { data: { ...payload } }
    })
    const first = createStore().store
    await first.load()
    await first.setSoftwareVersionLanguage('zh')
    const reloaded = createStore().store
    await reloaded.load()
    expect(reloaded.softwareVersionLanguage).toBe('zh')
    expect(reloaded.softwareVersionDisplay).toBe('channel')
    expect(reloaded.taskSettingsLayout).toBe('waterfall')
  })
})
