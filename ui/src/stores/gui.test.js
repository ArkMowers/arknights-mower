import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia } from 'pinia'
import axios from 'axios'
import { useGuiStore } from './gui'
import { i18n } from '@/i18n'

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
  i18n.global.locale.value = 'zh-CN'
  axios.get.mockResolvedValue({ data: { software_version_display: 'version' } })
  axios.put.mockImplementation(async (_url, data) => ({ data }))
})

afterEach(() => {
  for (const store of stores.splice(0)) store.$dispose()
  vi.resetAllMocks()
  vi.unstubAllGlobals()
})

describe('shared GUI appearance preferences', () => {
  it('defaults the interface language to Chinese without linking it to version labels', async () => {
    const { store } = createStore()
    expect(store.interfaceLanguage).toBe('zh-CN')
    expect(store.interfaceLanguageDisabled).toBe(true)
    expect(await store.setInterfaceLanguage('en-US')).toBe(false)
    expect(await store.load()).toBe(true)
    expect(store.interfaceLanguage).toBe('zh-CN')
    expect(store.softwareVersionLanguage).toBe('en')
    expect(axios.put).not.toHaveBeenCalled()
  })

  it.each(['en-US', 'ja-JP', 'zh-TW', 'system'])(
    'restores %s in a new store after a reload',
    async (language) => {
      let saved = 'zh-CN'
      axios.get.mockImplementation(async () => ({
        data: { software_version_display: 'version', ui_language: saved }
      }))
      axios.put.mockImplementation(async (_url, payload) => {
        saved = payload.ui_language
        return { data: { ui_language: saved } }
      })
      const first = createStore().store
      await first.load()
      expect(await first.setInterfaceLanguage(language)).toBe(true)
      expect(axios.put).toHaveBeenCalledWith(
        expect.stringMatching(/\/gui\/appearance$/),
        { ui_language: language },
        { timeout: 5000 }
      )
      const reloaded = createStore().store
      await reloaded.load()
      expect(reloaded.interfaceLanguage).toBe(language)
      expect(reloaded.softwareVersionLanguage).toBe('en')
    }
  )

  it('keeps language selection disabled during a save and rejects invalid or unchanged choices', async () => {
    const { store } = createStore()
    await store.load()
    expect(await store.setInterfaceLanguage('zh-CN')).toBe(true)
    expect(await store.setInterfaceLanguage('fr-FR')).toBe(false)
    expect(axios.put).not.toHaveBeenCalled()
    const save = deferred()
    axios.put.mockReturnValueOnce(save.promise)
    const pending = store.setInterfaceLanguage('en-US')
    expect(store.interfaceLanguage).toBe('en-US')
    expect(store.interfaceLanguageDisabled).toBe(true)
    expect(await store.setInterfaceLanguage('zh-CN')).toBe(false)
    expect(await store.setSoftwareVersionLanguage('zh')).toBe(false)
    expect(axios.put).toHaveBeenCalledOnce()
    save.resolve({ data: { ui_language: 'en-US' } })
    expect(await pending).toBe(true)
    expect(store.interfaceLanguageDisabled).toBe(false)
  })

  it.each([
    ['request failure', 'en-US'],
    ['unconfirmed response', 'en-US'],
    ['request failure', 'system'],
    ['unconfirmed response', 'system']
  ])('restores the interface language after a %s and retries %s', async (failure, target) => {
    const { store } = createStore()
    await store.load()
    if (failure === 'request failure') axios.put.mockRejectedValueOnce(new Error('offline'))
    else axios.put.mockResolvedValueOnce({ data: { ui_language: 'zh-CN' } })
    expect(await store.setInterfaceLanguage(target)).toBe(false)
    expect(store.interfaceLanguage).toBe('zh-CN')
    expect(store.interfaceLanguageError).toContain('已恢复原来的语言')
    expect(await store.retryInterfaceLanguage()).toBe(true)
    expect(store.interfaceLanguage).toBe(target)
    expect(store.interfaceLanguageError).toBe('')
    expect(axios.put.mock.calls.map(([, payload]) => payload)).toEqual([
      { ui_language: target },
      { ui_language: target }
    ])
  })

  it('retries a failed initial language read without writing the default language', async () => {
    const { store } = createStore()
    axios.get.mockRejectedValueOnce(new Error('offline'))
    expect(await store.load()).toBe(false)
    expect(store.interfaceLanguage).toBe('zh-CN')
    expect(store.interfaceLanguageDisabled).toBe(true)
    expect(store.interfaceLanguageError).toContain('读取失败')
    axios.get.mockResolvedValueOnce({
      data: { software_version_display: 'version', ui_language: 'en-US' }
    })
    expect(await store.retryInterfaceLanguage()).toBe(true)
    expect(store.interfaceLanguage).toBe('en-US')
    expect(store.interfaceLanguageError).toBe('')
    expect(axios.put).not.toHaveBeenCalled()
  })

  it('defaults an unknown saved preference to Chinese without rewriting it', async () => {
    axios.get.mockResolvedValueOnce({
      data: { software_version_display: 'version', ui_language: 'other' }
    })
    const { store } = createStore()
    expect(await store.load()).toBe(true)
    expect(store.interfaceLanguage).toBe('zh-CN')
    expect(store.resolvedInterfaceLanguage).toBe('zh-CN')
    expect(store.interfaceLanguageDisabled).toBe(false)
    expect(axios.put).not.toHaveBeenCalled()
  })

  it('updates system mode on languagechange without requests and releases its listener on disposal', async () => {
    const target = new EventTarget()
    const remove = vi.spyOn(target, 'removeEventListener')
    const browser = { languages: ['zh-Hant-HK', 'en-US'] }
    vi.stubGlobal('window', target)
    vi.stubGlobal('navigator', browser)
    axios.get.mockResolvedValueOnce({
      data: { software_version_display: 'version', ui_language: 'system' }
    })
    const { store } = createStore()
    await store.load()
    expect(store.interfaceLanguage).toBe('system')
    expect(store.resolvedInterfaceLanguage).toBe('zh-TW')
    browser.languages = ['ja-JP']
    target.dispatchEvent(new Event('languagechange'))
    expect(store.resolvedInterfaceLanguage).toBe('ja-JP')
    expect(store.interfaceLanguage).toBe('system')
    expect(axios.get).toHaveBeenCalledOnce()
    expect(axios.put).not.toHaveBeenCalled()

    expect(await store.setInterfaceLanguage('en-US')).toBe(true)
    browser.languages = ['zh-CN']
    target.dispatchEvent(new Event('languagechange'))
    expect(store.resolvedInterfaceLanguage).toBe('en-US')
    expect(axios.put).toHaveBeenCalledOnce()
    await store.setInterfaceLanguage('system')
    expect(store.resolvedInterfaceLanguage).toBe('zh-CN')
    store.$dispose()
    expect(remove).toHaveBeenCalledWith('languagechange', expect.any(Function))
    browser.languages = ['ja-JP']
    target.dispatchEvent(new Event('languagechange'))
    expect(store.resolvedInterfaceLanguage).toBe('zh-CN')
  })

  it('restores system mode using the latest browser language when a manual save fails and retries its target', async () => {
    const target = new EventTarget()
    const browser = { languages: ['en-US'] }
    vi.stubGlobal('window', target)
    vi.stubGlobal('navigator', browser)
    axios.get.mockResolvedValueOnce({
      data: { software_version_display: 'version', ui_language: 'system' }
    })
    const { store } = createStore()
    await store.load()
    const save = deferred()
    axios.put.mockReturnValueOnce(save.promise)
    const pending = store.setInterfaceLanguage('ja-JP')
    expect(store.resolvedInterfaceLanguage).toBe('ja-JP')
    expect(store.interfaceLanguageDisabled).toBe(true)
    browser.languages = ['zh-HK']
    target.dispatchEvent(new Event('languagechange'))
    save.reject(new Error('offline'))
    expect(await pending).toBe(false)
    expect(store.interfaceLanguage).toBe('system')
    expect(store.resolvedInterfaceLanguage).toBe('zh-TW')
    expect(await store.retryInterfaceLanguage()).toBe(true)
    expect(store.interfaceLanguage).toBe('ja-JP')
    expect(axios.get).toHaveBeenCalledOnce()
    expect(axios.put.mock.calls.map(([, payload]) => payload)).toEqual([
      { ui_language: 'ja-JP' },
      { ui_language: 'ja-JP' }
    ])
  })

  it('updates existing preference errors when the interface language changes without retrying writes', async () => {
    const { store } = createStore()
    await store.load()
    axios.put.mockRejectedValueOnce(new Error('offline'))
    expect(await store.setSoftwareVersionDisplay('channel')).toBe(false)
    expect(store.error).toBe(i18n.global.t('settings.gui.versionSaveFailed'))
    const writes = axios.put.mock.calls.length
    i18n.global.locale.value = 'ja-JP'
    expect(store.error).toBe(i18n.global.t('settings.gui.versionSaveFailed'))
    expect(store.error).not.toContain('失败')
    expect(axios.put).toHaveBeenCalledTimes(writes)
    expect(store.softwareVersionDisplay).toBe('version')
  })

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

describe('shared version watermark preference', () => {
  const confirmation = '反馈问题时务必说明具体版本'

  it('keeps the default watermark visible until a successful read enables editing', async () => {
    const { store } = createStore()
    expect(store.watermarkVisible).toBe(true)
    expect(store.watermarkDisabled).toBe(true)
    expect(await store.setWatermarkVisible(false, confirmation)).toBe(false)
    expect(axios.put).not.toHaveBeenCalled()
    expect(await store.load()).toBe(true)
    expect(store.watermarkVisible).toBe(true)
    expect(store.watermarkDisabled).toBe(false)
    expect(axios.put).not.toHaveBeenCalled()
  })

  it('immediately shares confirmed hiding, serializes appearance saves and shows without confirmation', async () => {
    const { pinia, store } = createStore()
    await store.load()
    const save = deferred()
    axios.put.mockReturnValueOnce(save.promise)
    const pending = store.setWatermarkVisible(false, confirmation)
    expect(useGuiStore(pinia).watermarkVisible).toBe(false)
    expect(store.watermarkSaving).toBe(true)
    expect(store.watermarkDisabled).toBe(true)
    expect(store.displayDisabled).toBe(true)
    expect(store.layoutDisabled).toBe(true)
    expect(await store.setWatermarkVisible(true)).toBe(false)
    expect(await store.setSoftwareVersionDisplay('channel')).toBe(false)
    expect(await store.setSoftwareVersionLanguage('zh')).toBe(false)
    expect(await store.setTaskSettingsLayout('waterfall')).toBe(false)
    expect(axios.put).toHaveBeenCalledExactlyOnceWith(
      expect.stringMatching(/\/gui\/appearance$/),
      { watermark_visible: false, watermark_confirmation: confirmation },
      { timeout: 5000 }
    )
    save.resolve({ data: { watermark_visible: false } })
    expect(await pending).toBe(true)
    expect(store.watermarkVisible).toBe(false)
    expect(store.watermarkSaving).toBe(false)
    expect(store.watermarkDisabled).toBe(false)
    expect(await store.setWatermarkVisible(true)).toBe(true)
    expect(store.watermarkVisible).toBe(true)
    expect(axios.put.mock.calls[1][1]).toEqual({ watermark_visible: true })
    expect(store.softwareVersionDisplay).toBe('version')
    expect(store.softwareVersionLanguage).toBe('en')
    expect(store.taskSettingsLayout).toBe('checklist')
  })

  it('retains the visible watermark on a read failure and retries the saved hidden preference', async () => {
    axios.get.mockRejectedValueOnce(new Error('offline'))
    const { store } = createStore()
    expect(await store.load()).toBe(false)
    expect(store.watermarkVisible).toBe(true)
    expect(store.watermarkDisabled).toBe(true)
    expect(store.watermarkError).toContain('读取失败')
    expect(await store.setWatermarkVisible(false, confirmation)).toBe(false)
    expect(axios.put).not.toHaveBeenCalled()
    axios.get.mockResolvedValueOnce({
      data: { software_version_display: 'version', watermark_visible: false }
    })
    expect(await store.retryWatermarkVisible()).toBe(true)
    expect(store.watermarkVisible).toBe(false)
    expect(store.watermarkDisabled).toBe(false)
    expect(store.watermarkError).toBe('')
    expect(axios.get).toHaveBeenCalledTimes(2)
  })

  it.each([null, 0, 'false', {}])('rejects an invalid loaded watermark value %j', async (value) => {
    axios.get.mockResolvedValueOnce({
      data: { software_version_display: 'channel', watermark_visible: value }
    })
    const { store } = createStore()
    expect(await store.load()).toBe(false)
    expect(store.watermarkVisible).toBe(true)
    expect(store.watermarkDisabled).toBe(true)
    expect(store.watermarkError).toContain('读取失败')
    expect(store.softwareVersionDisplay).toBe('version')
    expect(axios.put).not.toHaveBeenCalled()
  })

  it.each(['rejected', 'unconfirmed'])(
    'restores visibility after a %s hide save and retains the acknowledgement for retry',
    async (failure) => {
      const { store } = createStore()
      await store.load()
      if (failure === 'rejected') axios.put.mockRejectedValueOnce(new Error('offline'))
      else axios.put.mockResolvedValueOnce({ data: { watermark_visible: true } })
      expect(await store.setWatermarkVisible(false, confirmation)).toBe(false)
      expect(store.watermarkVisible).toBe(true)
      expect(store.watermarkSaving).toBe(false)
      expect(store.watermarkDisabled).toBe(false)
      expect(store.watermarkError).toContain('已恢复原来的显示')
      expect(store.error).toBe('')
      expect(store.layoutError).toBe('')
      expect(await store.retryWatermarkVisible()).toBe(true)
      expect(store.watermarkVisible).toBe(false)
      expect(store.watermarkError).toBe('')
      expect(axios.put.mock.calls.map(([, payload]) => payload)).toEqual([
        { watermark_visible: false, watermark_confirmation: confirmation },
        { watermark_visible: false, watermark_confirmation: confirmation }
      ])
    }
  )

  it('retains the saved hidden preference if showing fails and retries without acknowledgement', async () => {
    axios.get.mockResolvedValueOnce({
      data: { software_version_display: 'version', watermark_visible: false }
    })
    const { store } = createStore()
    await store.load()
    axios.put.mockRejectedValueOnce(new Error('offline'))
    expect(await store.setWatermarkVisible(true)).toBe(false)
    expect(store.watermarkVisible).toBe(false)
    expect(await store.retryWatermarkVisible()).toBe(true)
    expect(store.watermarkVisible).toBe(true)
    expect(axios.put.mock.calls.map(([, payload]) => payload)).toEqual([
      { watermark_visible: true },
      { watermark_visible: true }
    ])
  })

  it('restores the hidden watermark after reload without changing separate appearance settings', async () => {
    const saved = {
      software_version_display: 'channel',
      software_version_language: 'zh',
      task_settings_layout: 'waterfall',
      watermark_visible: true
    }
    axios.get.mockImplementation(async () => ({ data: { ...saved } }))
    axios.put.mockImplementation(async (_url, payload) => {
      const changes = { ...payload }
      delete changes.watermark_confirmation
      Object.assign(saved, changes)
      return { data: changes }
    })
    const first = createStore().store
    await first.load()
    expect(await first.setWatermarkVisible(false, confirmation)).toBe(true)
    const reloaded = createStore().store
    expect(reloaded.watermarkVisible).toBe(true)
    expect(await reloaded.load()).toBe(true)
    expect(reloaded.watermarkVisible).toBe(false)
    expect(reloaded.softwareVersionDisplay).toBe('channel')
    expect(reloaded.softwareVersionLanguage).toBe('zh')
    expect(reloaded.taskSettingsLayout).toBe('waterfall')
    expect(saved).not.toHaveProperty('watermark_confirmation')
    expect(axios.put).toHaveBeenCalledOnce()
  })

  it('requires a Boolean choice and the exact acknowledgement before hiding', async () => {
    const { store } = createStore()
    await store.load()
    for (const value of [null, 0, 1, 'false', {}])
      expect(await store.setWatermarkVisible(value, confirmation)).toBe(false)
    expect(await store.setWatermarkVisible(false)).toBe(false)
    expect(await store.setWatermarkVisible(false, '我知道了')).toBe(false)
    expect(await store.setWatermarkVisible(true)).toBe(true)
    expect(await store.retryWatermarkVisible()).toBe(false)
    expect(store.watermarkVisible).toBe(true)
    expect(axios.put).not.toHaveBeenCalled()
  })

  it('does not interrupt another appearance preference save to hide the watermark', async () => {
    const { store } = createStore()
    await store.load()
    const save = deferred()
    axios.put.mockReturnValueOnce(save.promise)
    const pending = store.setTaskSettingsLayout('waterfall')
    expect(store.watermarkDisabled).toBe(true)
    expect(await store.setWatermarkVisible(false, confirmation)).toBe(false)
    expect(store.watermarkVisible).toBe(true)
    expect(axios.put).toHaveBeenCalledOnce()
    save.resolve({ data: { task_settings_layout: 'waterfall' } })
    expect(await pending).toBe(true)
    expect(store.watermarkDisabled).toBe(false)
  })
})
