import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createSSRApp, effectScope, nextTick, ref } from 'vue'
import { renderToString } from 'vue/server-renderer'
import SoftwareUpdate from './SoftwareUpdate.vue'
import ResourceUpdate from './ResourceUpdate.vue'
import { showSoftwareUpdateDialog, showResourceUpdateDialog } from '@/utils/updateDialog'
import { pendingSoftwarePackage } from '@/stores/updateUpload'

const state = vi.hoisted(() => ({
  mounted: [],
  unmounted: [],
  switches: new Map(),
  client: null,
  config: null,
  resource: null,
  warning: vi.fn()
}))

// Exercise the component's setup and lifecycle without launching a browser.
vi.mock('vue', async (original) => ({
  ...(await original()),
  useSSRContext: () => ({ modules: new Set() }),
  inject: () => state.client,
  onMounted: (callback) => state.mounted.push(callback),
  onUnmounted: (callback) => state.unmounted.push(callback)
}))
vi.mock('naive-ui', async (original) => {
  const actual = await original()
  const { h } = await import('vue')
  const Switch = {
    props: ['value', 'disabled'],
    emits: ['update:value'],
    setup:
      (props, { attrs, emit }) =>
      () => {
        const buttonProps = {
          role: 'switch',
          'aria-label': attrs['aria-label'],
          'aria-checked': props.value,
          disabled: props.disabled,
          onClick: () => {
            if (!props.disabled) emit('update:value', !props.value)
          }
        }
        state.switches.set(attrs['aria-label'], { props: buttonProps })
        return h('button', buttonProps)
      }
  }
  const container = {
    setup:
      (_, { slots }) =>
      () =>
        h('section', slots.default?.())
  }
  return {
    ...actual,
    ...Object.fromEntries(
      Object.keys(actual)
        .filter((name) => /^N[A-Z]/.test(name))
        .map((name) => [name, container])
    ),
    NSwitch: Switch,
    useDialog: () => ({ warning: state.warning }),
    useMessage: () => ({ error: vi.fn(), info: vi.fn() })
  }
})
vi.mock('@/utils/updateDialog', () => ({
  showSoftwareUpdateDialog: vi.fn(),
  showResourceUpdateDialog: vi.fn()
}))
vi.mock('@/stores/config', () => ({ useConfigStore: () => state.config }))
vi.mock('@/stores/plan', () => ({ usePlanStore: () => ({ load_operators: vi.fn() }) }))
vi.mock('@/stores/resourceVersion', () => ({ useResourceVersionStore: () => state.resource }))

function mountSwitches(componentType, scope) {
  let exposed
  const setupState = scope.run(() =>
    componentType.setup({}, { expose: (value) => (exposed = value) })
  )
  return {
    flushSettings: () => exposed.flushSettings(),
    render: () => renderToString(createSSRApp({ ...componentType, setup: () => setupState })),
    switch: (label) => state.switches.get(label)
  }
}

describe('offline software package installation', () => {
  let scope
  let component

  beforeEach(() => {
    vi.useFakeTimers()
    vi.stubGlobal('sessionStorage', { getItem: () => null, setItem: vi.fn(), removeItem: vi.fn() })
    state.mounted = []
    state.unmounted = []
    state.switches.clear()
    state.warning.mockClear()
    vi.mocked(showSoftwareUpdateDialog).mockClear()
    vi.mocked(showResourceUpdateDialog).mockClear()
    state.client = {
      defaults: { headers: { common: {} } },
      get: vi.fn(async (url) => ({
        data: url.endsWith('/info')
          ? {
              ok: true,
              deployment: 'release',
              version: '4.1.6-alpha.4',
              blockers: [],
              instances: [{ name: 'one' }],
              channels: [],
              settings: { channel: 'beta', auto_check: true, auto_update: true, background: true }
            }
          : { ok: true, status: 'idle' }
      })),
      post: vi.fn(async (url) => {
        if (url.endsWith('/manual/inspect'))
          return {
            data: {
              ok: true,
              check_id: 'preview',
              version: 'v4.1.5',
              downgrade: true,
              manual: true
            }
          }
        if (url.endsWith('/auto-check')) throw new Error('Network checks unavailable')
        if (url.endsWith('/start') || url.endsWith('/manual/discard'))
          return { data: { ok: true, id: 'offline-job' } }
        throw new Error('Unexpected request')
      })
    }
    scope = effectScope()
  })

  afterEach(() => {
    state.unmounted.forEach((callback) => callback())
    scope.stop()
    pendingSoftwarePackage.value = null
    vi.unstubAllGlobals()
    vi.useRealTimers()
  })

  async function mount(file) {
    component = scope.run(() => SoftwareUpdate.setup({}, { expose: () => {} }))
    await Promise.all(state.mounted.map((callback) => callback()))
    await nextTick()
    state.client.post.mockClear()
    component.dropSoftwarePackage({ dataTransfer: { files: [file] } })
    await nextTick()
  }

  it('installs a confirmed sidebar target with the saved restart preference and no second check', async () => {
    component = scope.run(() => SoftwareUpdate.setup({}, { expose: () => {} }))
    const get = state.client.get.getMockImplementation()
    state.client.get.mockImplementation(async (url) => {
      const response = await get(url)
      if (url.endsWith('/info')) response.data.settings.background = false
      else response.data = { ok: true, id: 'offline-job', status: 'running', phase: 'preparing' }
      return response
    })
    await component.installCheckedUpdate({
      check_id: 'confirmed-sidebar',
      confirm_downgrade: false
    })
    expect(state.client.post).toHaveBeenCalledExactlyOnceWith(
      '/software-update/start',
      { check_id: 'confirmed-sidebar', background: false, force: false, confirm_downgrade: false },
      { headers: { 'X-Mower-Update': '1' } }
    )
    expect(state.warning).not.toHaveBeenCalled()
    expect(component.showProgress.value).toBe(true)
  })

  it('rechecks installation blockers after sidebar confirmation', async () => {
    component = scope.run(() => SoftwareUpdate.setup({}, { expose: () => {} }))
    const get = state.client.get.getMockImplementation()
    state.client.get.mockImplementation(async (url) => {
      const response = await get(url)
      if (url.endsWith('/info')) response.data.blockers = ['正在停止实例']
      return response
    })
    await expect(component.installCheckedUpdate({ check_id: 'confirmed-sidebar' })).rejects.toThrow(
      '正在停止实例'
    )
    expect(state.client.post).not.toHaveBeenCalled()
  })

  it('shows only the checked preview and progress in the sidebar software panel', async () => {
    const props = {
      compact: true,
      preview: { channel: '开发版', version: '4.1.7', notes: '修复设置目录高度' }
    }
    const file = new File(['offline'], 'package.zip')
    pendingSoftwarePackage.value = file
    component = scope.run(() => SoftwareUpdate.setup(props, { expose: () => {} }))
    await Promise.all(state.mounted.map((callback) => callback()))
    component.job.value = {
      status: 'running',
      phase: 'downloading',
      progress: 40,
      current: 1048576,
      total: 2621440,
      message: '正在下载更新包'
    }
    const html = await renderToString(
      createSSRApp({ ...SoftwareUpdate, setup: () => component }, props)
    )
    expect(html).toContain('更新渠道 · 开发版')
    expect(html).toContain('修复设置目录高度')
    expect(html).toContain('正在下载更新包')
    expect(html).toContain('已下载 1.0 MiB')
    for (const text of [
      '自动检查更新',
      '自动更新',
      '更新后后台静默重启',
      '从本地安装包更新',
      '强制更新',
      '检查更新',
      '独立更新进度'
    ]) {
      expect(html).not.toContain(text)
    }
    expect(pendingSoftwarePackage.value).toBe(file)
    expect(state.client.post).not.toHaveBeenCalled()
  })

  it('shows resource preview and progress without checking again or changing saved preferences', async () => {
    state.config = {
      resource_update_enable: ref(true),
      resource_update_auto_update: ref(true),
      load_item: vi.fn(),
      load_shop: vi.fn()
    }
    state.resource = {
      canInstall: ref(false),
      info: ref({}),
      loading: ref(false),
      installing: ref(true),
      install_message: ref(''),
      progress_error: ref(''),
      job: ref({ status: 'running', phase: 'download', progress: 20, message: '正在下载资源包' }),
      loadResourceJob: vi.fn(),
      loadResourceVersion: vi.fn(),
      loadResourceVersionLocal: vi.fn()
    }
    const props = { compact: true, skipInitialCheck: true, preview: { version: '新资源' } }
    const setup = scope.run(() => ResourceUpdate.setup(props, { expose: () => {} }))
    await Promise.all(state.mounted.map((callback) => callback()))
    const html = await renderToString(
      createSSRApp({ ...ResourceUpdate, setup: () => setup }, props)
    )
    expect(html).toContain('新资源')
    expect(html).toContain('此版本未提供更新日志。')
    expect(html).toContain('正在下载资源包')
    for (const text of ['自动检查更新', '自动更新', '从本地资源包更新', '检查更新']) {
      expect(html).not.toContain(text)
    }
    expect(state.resource.loadResourceVersion).not.toHaveBeenCalled()
    expect(state.resource.loadResourceVersionLocal).not.toHaveBeenCalled()
    expect(state.config.resource_update_enable.value).toBe(true)
    expect(state.config.resource_update_auto_update.value).toBe(true)
  })

  it.each(['v4.1.5', 'v4.1.6-alpha.12.gfdc9e8b4'])(
    'offers the online channel target %s with ordinary installation confirmation',
    async (version) => {
      await mount(new File(['unused'], 'package.zip'))
      component.packageFiles.value = []
      state.client.post.mockResolvedValueOnce({
        data: {
          ok: true,
          available: true,
          check_id: 'channel-target',
          version,
          downgrade: false,
          message: '发现可用更新'
        }
      })
      await component.checkUpdate()
      const html = await renderToString(createSSRApp({ ...SoftwareUpdate, setup: () => component }))
      expect(html).toContain('可更新')
      expect(html).toContain('下载并安装')
      expect(html).not.toContain('可回退')
      expect(html).not.toContain('回退并安装')
      await component.requestInstall(false)
      expect(showSoftwareUpdateDialog).toHaveBeenCalledExactlyOnceWith(
        expect.objectContaining({ warning: state.warning }),
        component.info.value,
        expect.objectContaining({ check_id: 'channel-target', version, downgrade: false })
      )
      expect(state.warning).not.toHaveBeenCalled()
      expect(state.client.post.mock.calls.some(([url]) => url.endsWith('/start'))).toBe(false)
    }
  )
  it('renders saved software switch values and persists changes through update:value', async () => {
    state.client.post.mockResolvedValue({ data: { ok: true } })
    const view = mountSwitches(SoftwareUpdate, scope)
    await Promise.all(state.mounted.map((callback) => callback()))
    await view.render()
    const labels = ['自动检查更新', '自动更新', '更新后后台静默重启']
    for (const label of labels) expect(view.switch(label).props['aria-checked']).toBe(true)
    state.client.post.mockClear()

    view.switch('自动检查更新').props.onClick()
    await view.flushSettings()
    await view.render()
    expect(view.switch('自动检查更新').props['aria-checked']).toBe(false)
    expect(view.switch('自动更新').props['aria-checked']).toBe(false)
    expect(state.client.post.mock.calls.find(([url]) => url.endsWith('/settings'))[1]).toEqual({
      channel: 'beta',
      auto_check: false,
      auto_update: false,
      background: true
    })

    state.client.post.mockClear()
    view.switch('自动更新').props.onClick()
    await view.flushSettings()
    await view.render()
    expect(view.switch('自动检查更新').props['aria-checked']).toBe(true)
    expect(view.switch('自动更新').props['aria-checked']).toBe(true)
    expect(state.client.post.mock.calls.find(([url]) => url.endsWith('/settings'))[1]).toEqual({
      channel: 'beta',
      auto_check: true,
      auto_update: true,
      background: true
    })

    state.client.post.mockClear()
    view.switch('更新后后台静默重启').props.onClick()
    await view.flushSettings()
    await view.render()
    expect(view.switch('更新后后台静默重启').props['aria-checked']).toBe(false)
    expect(
      state.client.post.mock.calls.find(([url]) => url.endsWith('/settings'))[1].background
    ).toBe(false)
  })

  it('opens the shared resource update dialog without installing from the settings button', () => {
    state.config = {
      resource_update_enable: ref(false),
      resource_update_auto_update: ref(false),
      load_item: vi.fn(),
      load_shop: vi.fn()
    }
    state.resource = {
      canInstall: ref(true),
      info: ref({ remote_version: 'next', update_available: true }),
      loading: ref(false),
      installing: ref(false),
      install_message: ref(''),
      job: ref({ status: 'idle' }),
      progress_error: ref(''),
      installResource: vi.fn()
    }
    const setup = scope.run(() => ResourceUpdate.setup({}, { expose: () => {} }))
    setup.request_install()
    expect(showResourceUpdateDialog).toHaveBeenCalledExactlyOnceWith(
      expect.objectContaining({ warning: state.warning }),
      state.resource,
      state.resource.info.value
    )
    expect(state.resource.installResource).not.toHaveBeenCalled()
  })

  it('renders resource switch values and updates both dependent settings through update:value', async () => {
    state.config = {
      resource_update_enable: ref(true),
      resource_update_auto_update: ref(true),
      load_item: vi.fn(),
      load_shop: vi.fn()
    }
    state.resource = {
      canInstall: ref(false),
      info: ref({}),
      loading: ref(false),
      installing: ref(false),
      install_message: ref(''),
      job: ref({ status: 'idle' }),
      progress_error: ref('')
    }
    const view = mountSwitches(ResourceUpdate, scope)
    await view.render()
    expect(view.switch('自动检查更新').props['aria-checked']).toBe(true)
    expect(view.switch('自动更新').props['aria-checked']).toBe(true)

    view.switch('自动检查更新').props.onClick()
    await view.render()
    expect(state.config.resource_update_enable.value).toBe(false)
    expect(state.config.resource_update_auto_update.value).toBe(false)
    expect(view.switch('自动检查更新').props['aria-checked']).toBe(false)
    expect(view.switch('自动更新').props['aria-checked']).toBe(false)

    view.switch('自动更新').props.onClick()
    await view.render()
    expect(state.config.resource_update_enable.value).toBe(true)
    expect(state.config.resource_update_auto_update.value).toBe(true)
    expect(view.switch('自动检查更新').props['aria-checked']).toBe(true)
    expect(view.switch('自动更新').props['aria-checked']).toBe(true)
  })

  it('starts with foreground restart and honors an explicitly saved background choice', async () => {
    component = scope.run(() => SoftwareUpdate.setup({}, { expose: () => {} }))
    expect(component.background.value).toBe(false)
    await Promise.all(state.mounted.map((callback) => callback()))
    expect(component.background.value).toBe(true)
  })

  it.each([
    { silentRestart: false, restarted: false, reload: false },
    { silentRestart: false, restarted: true, reload: true },
    { silentRestart: true, restarted: false, reload: true },
    { silentRestart: undefined, restarted: false, reload: true }
  ])(
    'handles successful installation with host capabilities %j',
    async ({ silentRestart, restarted, reload }) => {
      const storage = new Map()
      vi.stubGlobal('sessionStorage', {
        getItem: (key) => storage.get(key),
        setItem: (key, value) => storage.set(key, value),
        removeItem: (key) => storage.delete(key)
      })
      const refresh = vi.fn()
      vi.stubGlobal('window', { location: { reload: refresh } })
      await mount(new File(['offline'], 'package.zip'))
      component.info.value.capabilities = { silent_restart: silentRestart }
      const installed = {
        ok: true,
        id: 'offline-job',
        status: 'succeeded',
        restarted,
        message: restarted ? 'Mower 已更新并重新启动' : '停止并重新启动手机服务后生效。'
      }
      state.client.get.mockImplementation(async (url) => ({
        data: url.endsWith('/status') ? installed : component.info.value
      }))
      await component.install(false, null, { check_id: 'preview' })
      expect(refresh).toHaveBeenCalledTimes(reload ? 1 : 0)
      expect(component.showProgress.value).toBe(true)
      expect(component.job.value.message).toBe(installed.message)
      expect(storage.size).toBe(0)
    }
  )

  it('consumes a global drop before mounting without triggering an online check or install', async () => {
    const file = new File(['offline'], '任意改名 (1).bin')
    pendingSoftwarePackage.value = file
    component = scope.run(() => SoftwareUpdate.setup({}, { expose: () => {} }))
    await Promise.all(state.mounted.map((callback) => callback()))
    expect(pendingSoftwarePackage.value).toBeNull()
    expect(component.packageFiles.value[0].file).toBe(file)
    expect(component.expandedDetails.value).toContain('manual')
    expect(state.client.post).not.toHaveBeenCalled()
    expect(state.warning).not.toHaveBeenCalled()
    const replacement = new File(['replacement'], 'new.zip')
    pendingSoftwarePackage.value = replacement
    await nextTick()
    expect(component.packageFiles.value[0].file).toBe(replacement)
    expect(pendingSoftwarePackage.value).toBeNull()
    expect(state.client.post).not.toHaveBeenCalled()
  })

  it('reveals a dropped package after update information finishes loading', async () => {
    let finishInfo
    const initialGet = state.client.get.getMockImplementation()
    state.client.get.mockImplementation((url) =>
      url.endsWith('/info')
        ? new Promise((resolve) => {
            finishInfo = resolve
          })
        : initialGet(url)
    )
    pendingSoftwarePackage.value = new File(['offline'], 'package.zip')
    component = scope.run(() => SoftwareUpdate.setup({}, { expose: () => {} }))
    const scrollIntoView = vi.fn()
    component.card.value = { $el: { querySelector: () => ({ scrollIntoView }) } }
    const mounting = Promise.all(state.mounted.map((callback) => callback()))
    await nextTick()
    expect(component.expandedDetails.value).toContain('manual')
    expect(scrollIntoView).not.toHaveBeenCalled()
    finishInfo(await initialGet('/software-update/info'))
    await mounting
    await nextTick()
    expect(scrollIntoView).toHaveBeenCalledWith({ block: 'nearest' })
    expect(state.client.post).not.toHaveBeenCalled()
  })

  it('waits through service disconnection and reloads after the restarted server is ready', async () => {
    const storage = new Map()
    vi.stubGlobal('sessionStorage', {
      getItem: (key) => storage.get(key),
      setItem: (key, value) => storage.set(key, value),
      removeItem: (key) => storage.delete(key)
    })
    const refresh = vi.fn()
    vi.stubGlobal('window', { location: { reload: refresh } })
    await mount(new File(['offline'], 'package.zip'))
    component.info.value.capabilities = { silent_restart: false }
    state.client.get
      .mockResolvedValueOnce({
        data: { ok: true, id: 'offline-job', status: 'running', phase: 'restarting' }
      })
      .mockRejectedValueOnce(new Error('Service stopped'))
      .mockResolvedValueOnce({
        data: { ok: true, id: 'offline-job', status: 'succeeded', restarted: true }
      })
    await component.install(false, null, { check_id: 'preview' })
    await vi.advanceTimersByTimeAsync(2000)
    expect(component.disconnected.value).toBe(true)
    expect(refresh).not.toHaveBeenCalled()
    await vi.advanceTimersByTimeAsync(2000)
    expect(component.disconnected.value).toBe(false)
    expect(refresh).toHaveBeenCalledOnce()
    expect(storage.size).toBe(0)
  })

  it('keeps the default update channel after a manual PR installation', async () => {
    await mount(new File(['offline'], 'package.zip'))
    expect(component.channel.value).toBe('beta')
    await component.install(false, { check_id: 'pr', source_pr: 7 })
    expect(component.channel.value).toBe('beta')
    expect(component.autoUpdate.value).toBe(false)
  })

  it('loads a Release rollback choice and requires confirmation before installation', async () => {
    component = scope.run(() => SoftwareUpdate.setup({}, { expose: () => {} }))
    await Promise.all(state.mounted.map((callback) => callback()))
    state.client.get.mockImplementation(async (url) => ({
      data: url.endsWith('/release/rollback-options')
        ? { ok: true, options: [{ version: 'v4.1.6-alpha.3' }] }
        : { ok: true, status: 'idle' }
    }))
    state.client.post.mockImplementation(async (url) => ({
      data: url.endsWith('/release/rollback-check')
        ? { ok: true, check_id: 'rollback', version: 'v4.1.6-alpha.3', downgrade: true }
        : { ok: true, id: 'rollback-job' }
    }))
    await component.loadRollbackOptions()
    expect(component.rollbackOptions.value).toEqual([
      { label: 'v4.1.6-alpha.3', value: 'v4.1.6-alpha.3' }
    ])
    component.rollbackVersion.value = 'v4.1.6-alpha.3'
    await component.requestRollback()
    expect(state.client.post).toHaveBeenCalledWith(
      '/software-update/release/rollback-check',
      { channel: 'beta', version: 'v4.1.6-alpha.3' },
      { headers: { 'X-Mower-Update': '1' } }
    )
    expect(state.warning.mock.calls[0][0].title).toBe('确认回退版本？')
    await state.warning.mock.calls[0][0].onPositiveClick()
    expect(state.client.post.mock.calls.find(([url]) => url.endsWith('/start'))[1]).toMatchObject({
      check_id: 'rollback',
      confirm_downgrade: true
    })
  })

  it.each([true, false])(
    'inspects local contents before confirming, install=%s',
    async (confirm) => {
      const file = new File(['offline'], '任意改名 (1).bin')
      await mount(file)
      expect(state.client.post).not.toHaveBeenCalled()
      expect(state.warning).not.toHaveBeenCalled()
      await component.requestInstall(true)
      expect(state.client.post).toHaveBeenCalledOnce()
      expect(state.client.post.mock.calls[0][0]).toBe('/software-update/manual/inspect')
      expect(state.client.post.mock.calls[0][1].get('file').name).toBe(file.name)
      const dialog = state.warning.mock.calls[0][0]
      expect(dialog.title).toBe('确认回退版本？')
      expect(dialog.content).toContain('v4.1.5')
      if (confirm) {
        await dialog.onPositiveClick()
        const submission = state.client.post.mock.calls.find(([url]) => url.endsWith('/start'))
        expect(submission[1]).toMatchObject({ check_id: 'preview', confirm_downgrade: true })
      } else {
        await dialog.onNegativeClick()
        expect(state.client.post.mock.calls.map(([url]) => url)).toEqual([
          '/software-update/manual/inspect',
          '/software-update/manual/discard'
        ])
      }
      expect(
        state.client.post.mock.calls.some(
          ([url]) => url.endsWith('/check') || url.endsWith('/auto-check')
        )
      ).toBe(false)
    }
  )

  it('an unrelated pending online check does not block manual installation', async () => {
    await mount(new File(['offline'], 'arknights-mower_4.2.0_windows_x64.zip'))
    let finishCheck
    state.client.post.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          finishCheck = resolve
        })
    )
    const checking = component.checkUpdate()
    // Wait until the online request has actually started.
    for (let i = 0; i < 5 && !finishCheck; i++) await nextTick()
    expect(finishCheck).toBeTypeOf('function')
    expect(component.checking.value).toBe(true)
    await component.requestInstall(true)
    expect(state.warning).toHaveBeenCalledOnce()
    await state.warning.mock.calls[0][0].onPositiveClick()
    expect(state.client.post.mock.calls.map(([url]) => url)).toEqual([
      '/software-update/check',
      '/software-update/manual/inspect',
      '/software-update/start',
      '/software-update/manual/discard'
    ])
    finishCheck({ data: { ok: true, available: false } })
    await checking
  })
})
