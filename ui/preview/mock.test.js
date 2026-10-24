import axios from 'axios'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { createSSRApp, h } from 'vue'
import { renderToString } from 'vue/server-renderer'
import { NTimePicker } from 'naive-ui'
import { setup as setupSsrStyles } from '@css-render/vue3-ssr'
import {
  createPreviewAdapter,
  createPreviewConfiguration,
  createPreviewData,
  installPreviewBackend,
  previewWebSocket
} from './mock.js'

afterEach(() => vi.useRealTimers())

describe('offline preview', () => {
  it('serves all waiting scene rows while preserving supplied values and fixture isolation', async () => {
    const initial = { waiting_scene: { LOADING: [4, 20] } }
    const data = createPreviewData(createPreviewConfiguration(initial))
    const client = axios.create({ adapter: createPreviewAdapter(data) })
    const { data: config } = await client.get('/conf')
    expect(config.waiting_scene).toEqual({
      CONNECTING: [1, 10],
      UNKNOWN: [1, 10],
      LOADING: [4, 20],
      LOGIN_LOADING: [3, 10],
      LOGIN_MAIN_NOENTRY: [3, 10],
      OPERATOR_ONGOING: [10, 30]
    })
    await client.patch('/conf', { waiting_scene: { LOADING: [5, 15] } })
    expect(initial).toEqual({ waiting_scene: { LOADING: [4, 20] } })
    expect(createPreviewConfiguration({}).waiting_scene.LOADING).toEqual([2, 30])
  })

  it('merges appearance edits independently without changing business configuration', async () => {
    const data = createPreviewData({ theme: 'light' })
    const originalConfig = structuredClone(data.config)
    const client = axios.create({ adapter: createPreviewAdapter(data) })
    expect((await client.get('/gui/appearance')).data).toEqual({
      software_version_display: 'version',
      software_version_language: 'en',
      task_settings_layout: 'checklist'
    })
    await client.put('/gui/appearance', { task_settings_layout: 'waterfall' })
    await client.put('/gui/appearance', { software_version_display: 'channel' })
    await client.put('/gui/appearance', { software_version_language: 'zh' })
    expect((await client.get('/gui/appearance')).data).toEqual({
      software_version_display: 'channel',
      software_version_language: 'zh',
      task_settings_layout: 'waterfall'
    })
    expect(data.config).toEqual(originalConfig)
    await client.put('/gui/appearance', {
      software_version_display: 'version',
      software_version_language: 'en',
      task_settings_layout: 'checklist'
    })
    expect(data.appearance).toEqual({
      software_version_display: 'version',
      software_version_language: 'en',
      task_settings_layout: 'checklist'
    })
  })

  it.each([
    {},
    { task_settings_layout: 'grid' },
    { task_settings_layout: 'waterfall', software_version_display: 'invalid' },
    { task_settings_layout: 'invalid', software_version_display: 'channel' },
    { software_version_language: 'zh-CN', software_version_display: 'channel' },
    { software_version_language: null },
    { task_settings_layout: 'waterfall', unknown: true },
    { task_settings_layout: 'waterfall', constructor: 'channel' }
  ])('rejects invalid appearance update %j without partial writes', async (payload) => {
    const data = createPreviewData({})
    const original = structuredClone(data.appearance)
    const client = axios.create({ adapter: createPreviewAdapter(data) })
    await expect(
      client.put('/gui/appearance', JSON.stringify(payload), {
        headers: { 'Content-Type': 'application/json' }
      })
    ).rejects.toMatchObject({
      response: { status: 400 }
    })
    expect(data.appearance).toEqual(original)
  })

  it('omits embedded instance controls from the preview bridge', () => {
    const originalAdapter = axios.defaults.adapter
    try {
      const target = { innerWidth: 1280, innerHeight: 800 }
      installPreviewBackend({}, target)
      expect(target.pywebview.api).not.toHaveProperty('get_instances')
      expect(target.pywebview.api.get_platform).toBeTypeOf('function')
      expect(target.pywebview.api.get_window_launch_mode).toBeTypeOf('function')
    } finally {
      axios.defaults.adapter = originalAdapter
    }
  })

  it.each([
    ['get', '/instances'],
    ['post', '/instances/actions']
  ])(
    'rejects unsupported embedded instance API %s %s without changing preview state',
    async (method, path) => {
      const data = createPreviewData({ theme: 'light' })
      const original = structuredClone(data)
      const client = axios.create({ adapter: createPreviewAdapter(data) })
      await expect(
        client.request({ method, url: path, data: { action: 'start', idx: 0 } })
      ).rejects.toMatchObject({
        code: 'ERR_PREVIEW_OPERATION',
        response: { status: 405 }
      })
      expect(data).toEqual(original)
    }
  )

  it('provides read-only task configuration defaults without claiming a completed device test', async () => {
    const data = createPreviewData({ maa_conn_preset: 'General' })
    const original = structuredClone(data)
    const client = axios.create({ adapter: createPreviewAdapter(data) })
    const presets = (await client.get('/maa-conn-preset')).data
    expect(presets).toEqual(['General'])
    presets.push('changed response')
    expect((await client.get('/maa-conn-preset')).data).toEqual(['General'])
    const status = (await client.get('/device/performance-test')).data
    expect(status).toMatchObject({ status: 'idle', id: null })
    expect(status.message).toContain('离线预览')
    expect(status).not.toHaveProperty('recommended_mode')
    expect(status).not.toHaveProperty('device')
    status.status = 'passed'
    expect((await client.get('/device/performance-test')).data.status).toBe('idle')
    expect(data).toEqual(original)
  })

  it('keeps device and MAA operations unavailable after loading task configuration examples', async () => {
    const data = createPreviewData({ maa_conn_preset: 'General' })
    const original = structuredClone(data)
    const client = axios.create({ adapter: createPreviewAdapter(data) })
    await client.get('/maa-conn-preset')
    await client.get('/device/performance-test')
    for (const [method, path] of [
      ['post', '/maa-conn-preset'],
      ['post', '/device/performance-test'],
      ['delete', '/device/performance-test'],
      ['get', '/device/performance-test/screenshot'],
      ['get', '/check-maa'],
      ['get', '/check-maa/status'],
      ['post', '/maa-update/check'],
      ['post', '/maa-update/start'],
      ['post', '/maa-resource-update/check'],
      ['post', '/maa-resource-update/start']
    ]) {
      await expect(client.request({ method, url: path, data: {} })).rejects.toMatchObject({
        code: 'ERR_PREVIEW_OPERATION',
        response: { status: 405 }
      })
    }
    expect(data).toEqual(original)
  })

  it('loads backend-shaped settings and keeps notification edits in memory', async () => {
    const initial = { webview: { scale: 1.25 }, recipient: '', custom_smtp_server: {}, ai_type: '' }
    const original = structuredClone(initial)
    const data = createPreviewData(createPreviewConfiguration(initial))
    const client = axios.create({ adapter: createPreviewAdapter(data) })
    const config = (await client.get('/conf')).data
    expect(config).toMatchObject({
      webview: { scale: 1.25, tray: true },
      recipient: [],
      custom_smtp_server: {
        enable: false,
        server: '',
        encryption: 'starttls',
        ssl_port: 587
      },
      ai_type: 'deepseek'
    })
    await client.patch('/conf', {
      recipient: ['preview@example.invalid'],
      custom_smtp_server: { enable: true, server: 'smtp.example.invalid' },
      ai_type: 'custom-local'
    })
    expect((await client.get('/conf')).data).toMatchObject({
      recipient: ['preview@example.invalid'],
      custom_smtp_server: {
        enable: true,
        server: 'smtp.example.invalid',
        encryption: 'starttls',
        ssl_port: 587
      },
      ai_type: 'custom-local'
    })
    expect(initial).toEqual(original)
    for (const [method, path] of [
      ['get', '/test-email'],
      ['get', '/config-backup/export'],
      ['post', '/config-backup/import']
    ]) {
      await expect(client.request({ method, url: path })).rejects.toMatchObject({
        code: 'ERR_PREVIEW_OPERATION',
        response: { status: 405 }
      })
    }
  })

  it('exposes process confirmation examples while refusing to execute their actions', async () => {
    const data = createPreviewData({ theme: 'light' })
    const original = structuredClone(data)
    const client = axios.create({ adapter: createPreviewAdapter(data) })
    expect((await client.get('/process-control/info')).data).toMatchObject({
      ok: true,
      supported: true,
      running: true,
      name: '离线预览'
    })
    expect((await client.get('/process-control/info')).data.message).toContain('离线预览')
    for (const action of ['restart_resume', 'restart', 'stop']) {
      await expect(client.post('/process-control/action', { action })).rejects.toMatchObject({
        code: 'ERR_PREVIEW_OPERATION',
        response: { status: 405 }
      })
    }
    expect(data).toEqual(original)
    data.status = 'stopped'
    expect((await client.get('/process-control/info')).data.running).toBe(false)
  })

  it('keeps desktop preferences isolated in each preview bridge', async () => {
    const originalAdapter = axios.defaults.adapter
    try {
      const config = { webview: { tray: true } }
      const target = { innerWidth: 1280, innerHeight: 800 }
      installPreviewBackend(config, target)
      const api = target.pywebview.api
      expect(await api.get_close_preference()).toEqual({
        choice: 'tray',
        remember: false,
        tray_enabled: true
      })
      await expect(api.set_close_preference('exit', true)).resolves.toBe(true)
      await expect(api.set_window_launch_mode('maximized')).resolves.toBe(true)
      expect(await api.get_close_preference()).toMatchObject({ choice: 'exit', remember: true })
      expect(await api.get_window_launch_mode()).toBe('maximized')
      await expect(api.set_close_preference('unknown', true)).rejects.toThrow()
      await expect(api.set_close_preference('tray', 'true')).rejects.toThrow()
      await expect(api.set_window_launch_mode('unknown')).rejects.toThrow('窗口启动状态设置无效')
      expect(await api.get_window_launch_mode()).toBe('maximized')
      expect(config).toEqual({ webview: { tray: true } })

      const other = { innerWidth: 1024, innerHeight: 768 }
      installPreviewBackend({ webview: { tray: false } }, other)
      expect(await other.pywebview.api.get_window_launch_mode()).toBe('last')
      expect(await other.pywebview.api.get_close_preference()).toMatchObject({
        remember: false,
        tray_enabled: false
      })
      await expect(other.pywebview.api.set_close_preference('tray', true)).rejects.toThrow(
        '托盘图标未启用'
      )
      expect(await api.get_close_preference()).toMatchObject({ choice: 'exit', remember: true })
    } finally {
      axios.defaults.adapter = originalAdapter
    }
  })

  it('keeps proxy edits in adapter memory and returns the real settings response shape', async () => {
    const data = createPreviewData({ theme: 'light' })
    const original = structuredClone(data)
    const client = axios.create({ adapter: createPreviewAdapter(data) })
    const options = { headers: { 'X-Mower-Settings': '1' } }
    expect((await client.get('/network/settings')).data).toEqual({
      ok: true,
      http_proxy: '',
      github_proxy: ''
    })
    const saved = (
      await client.post(
        '/network/settings',
        { http_proxy: ' socks5h://127.0.0.1:7897/ ', github_proxy: ' https://proxy.example ' },
        options
      )
    ).data
    expect(saved).toEqual({
      ok: true,
      http_proxy: 'socks5h://127.0.0.1:7897',
      github_proxy: 'https://proxy.example/'
    })
    expect((await client.get('/network/settings')).data).toEqual(saved)
    expect(data).toEqual(original)
    const reset = axios.create({ adapter: createPreviewAdapter(createPreviewData({})) })
    expect((await reset.get('/network/settings')).data).toEqual({
      ok: true,
      http_proxy: '',
      github_proxy: ''
    })
    await client.post('/network/settings', { http_proxy: '', github_proxy: '' }, options)
    expect((await client.get('/network/settings')).data.http_proxy).toBe('')
  })

  it.each(['/network/settings', '/network/test'])(
    'requires the settings intent header for preview POST %s',
    async (path) => {
      const client = axios.create({ adapter: createPreviewAdapter(createPreviewData({})) })
      await expect(
        client.post(path, { http_proxy: 'http://127.0.0.1:7897', github_proxy: '' })
      ).rejects.toMatchObject({ response: { status: 403 } })
      expect((await client.get('/network/settings')).data).toEqual({
        ok: true,
        http_proxy: '',
        github_proxy: ''
      })
    }
  )

  it('rejects incomplete proxy settings without applying a partial edit', async () => {
    const client = axios.create({ adapter: createPreviewAdapter(createPreviewData({})) })
    await expect(
      client.post(
        '/network/settings',
        { http_proxy: 'http://127.0.0.1:7897' },
        { headers: { 'X-Mower-Settings': '1' } }
      )
    ).rejects.toMatchObject({ response: { status: 400 } })
    expect((await client.get('/network/settings')).data).toEqual({
      ok: true,
      http_proxy: '',
      github_proxy: ''
    })
  })

  it('returns a labeled offline connection example using the saved proxy settings', async () => {
    const client = axios.create({ adapter: createPreviewAdapter(createPreviewData({})) })
    const options = { headers: { 'X-Mower-Settings': '1' } }
    await client.post(
      '/network/settings',
      { http_proxy: 'http://127.0.0.1:7897', github_proxy: 'https://proxy.example/' },
      options
    )
    const result = (
      await client.post('/network/test', { http_proxy: 'http://unused.invalid' }, options)
    ).data
    expect(result).toEqual({
      ok: true,
      settings: {
        http_proxy: 'http://127.0.0.1:7897',
        github_proxy: 'https://proxy.example/'
      },
      results: [
        {
          label: 'GitHub 文件下载',
          ok: true,
          message: '离线预览 · 仅展示连接测试示例结果，未连接外网。',
          elapsed_ms: 128
        }
      ]
    })
  })

  it('shows update controls and saves software settings without changing the input configuration', async () => {
    const data = createPreviewData({ theme: 'light' })
    const original = structuredClone(data.config)
    const client = axios.create({ adapter: createPreviewAdapter(data) })
    expect((await client.get('/status')).data.updates_enabled).toBe(true)
    const initial = (await client.get('/software-update/info')).data
    expect(initial).toMatchObject({
      ok: true,
      deployment: 'release',
      version: '4.1.6-preview',
      blockers: [],
      settings: { channel: 'beta', background: true, auto_check: false, auto_update: false },
      last_check: { available: true, version: '4.1.7-beta.1' }
    })
    expect(initial.channels.map(({ value }) => value)).toEqual(['stable', 'beta', 'dev'])

    await client.post('/software-update/settings', {
      channel: 'stable',
      background: false,
      auto_update: true
    })
    expect((await client.get('/software-update/info')).data.settings).toEqual({
      channel: 'stable',
      background: false,
      auto_check: true,
      auto_update: true
    })
    await client.post('/software-update/auto-check', {})
    expect((await client.get('/software-update/status')).data).toMatchObject({
      ok: true,
      status: 'idle',
      last_check: { channel: 'stable', version: '4.1.6-preview', available: false }
    })
    await client.post('/software-update/settings', { auto_check: false, auto_update: false })
    expect((await client.get('/software-update/info')).data.settings.auto_check).toBe(false)
    expect(data.config).toEqual(original)
    const reset = axios.create({ adapter: createPreviewAdapter(createPreviewData(original)) })
    expect((await reset.get('/software-update/info')).data.settings.channel).toBe('beta')
  })

  it('checks the selected software channel and retains its result for status reads', async () => {
    const client = axios.create({ adapter: createPreviewAdapter(createPreviewData({})) })
    await client.post('/software-update/settings', { channel: 'dev' })
    const result = (await client.post('/software-update/check', { channel: 'dev' })).data
    expect(result).toMatchObject({
      ok: true,
      channel: 'dev',
      version: '4.1.7-beta.1',
      available: true,
      downgrade: false,
      check_id: 'preview-dev'
    })
    expect((await client.get('/software-update/status')).data.last_check).toEqual(result)
    await expect(
      client.post('/software-update/settings', { channel: 'unknown', background: false })
    ).rejects.toMatchObject({ response: { status: 400 } })
    expect((await client.get('/software-update/info')).data.settings).toMatchObject({
      channel: 'dev',
      background: true
    })
  })

  it('returns local resource details separately from the available update example', async () => {
    const client = axios.create({ adapter: createPreviewAdapter(createPreviewData({})) })
    const local = (await client.get('/resource-version?local=1')).data
    expect(local).toEqual({
      current_version: 'v2026.10.17',
      current_display: '资源预览 · 当前'
    })
    expect((await client.get('/resource-version', { params: { local: 1 } })).data).toEqual(local)
    expect((await client.get('/resource-version')).data).toMatchObject({
      ...local,
      remote_version: 'v2026.10.20',
      remote_display: '资源预览 · 可更新',
      update_available: true
    })
    expect((await client.get('/resource/status')).data).toEqual({
      ok: true,
      job: { status: 'idle' }
    })
  })

  it.each([
    '/software-update/start',
    '/software-update/manual/inspect',
    '/software-update/cancel',
    '/resource/install',
    '/resource-update/manual',
    '/restart'
  ])('keeps %s unavailable after preview update checks', async (path) => {
    const data = createPreviewData({ theme: 'light' })
    const original = structuredClone(data)
    const client = axios.create({ adapter: createPreviewAdapter(data) })
    await client.post('/software-update/check', { channel: 'beta' })
    await client.get('/resource-version')
    await expect(client.post(path, { check_id: 'preview-beta' })).rejects.toMatchObject({
      code: 'ERR_PREVIEW_OPERATION',
      response: { status: 405 }
    })
    expect((await client.get('/software-update/status')).data.status).toBe('idle')
    expect(data).toEqual(original)
  })

  it('provides grouped configuration selection and refuses changes during a run', async () => {
    const data = createPreviewData({ theme: 'light' })
    const client = axios.create({ adapter: createPreviewAdapter(data) })
    const { data: profiles } = await client.get('/config-profiles')
    expect(profiles).toMatchObject({ active_id: 'preview-default', generation: '0', busy: true })
    expect(profiles.groups).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ key: 'device', section: '连接与运行' }),
        expect.objectContaining({ key: 'normal_plan', section: '排班与计划' })
      ])
    )
    await expect(
      client.post('/config-profiles', { name: '新配置', inherit: [] })
    ).rejects.toMatchObject({ response: { status: 423 } })
    expect((await client.get('/config-profiles')).data.profiles).toHaveLength(1)
  })

  it('creates, renames and switches example configurations while rejecting stale saves', async () => {
    const data = createPreviewData({ theme: 'light', device: { instance_id: '0' } })
    data.status = 'stopped'
    const client = axios.create({ adapter: createPreviewAdapter(data) })
    client.defaults.headers.common['X-Mower-Config-Generation'] = '0'
    await client.patch('/conf', { theme: 'dark', device: { instance_id: '2' } })
    const { data: created } = await client.post('/config-profiles', {
      name: '示例副本',
      inherit: ['appearance']
    })
    expect(data.config).toEqual({ theme: 'dark', device: { instance_id: '0' } })
    expect(created.profiles).toHaveLength(2)
    await expect(client.patch('/conf', { theme: 'light' })).rejects.toMatchObject({
      response: { status: 409, data: { code: 'configuration_changed' } }
    })
    client.defaults.headers.common['X-Mower-Config-Generation'] = created.generation
    const { data: renamed } = await client.patch(`/config-profiles/${created.active_id}`, {
      name: '已重命名'
    })
    expect(renamed.profiles.find((profile) => profile.id === created.active_id).name).toBe(
      '已重命名'
    )
    const { data: switched } = await client.post('/config-profiles/preview-default/activate', {
      keep: []
    })
    expect(switched.active_id).toBe('preview-default')
    expect(data.config).toEqual({ theme: 'dark', device: { instance_id: '2' } })
  })

  it('round trips exported preview ZIPs entirely within the offline adapter', async () => {
    const data = createPreviewData({ theme: 'dark' })
    data.status = 'stopped'
    const client = axios.create({ adapter: createPreviewAdapter(data) })
    client.defaults.headers.common['X-Mower-Config-Generation'] = '0'
    const { data: file } = await client.get('/config-profiles/export')
    expect(file.type).toBe('application/zip')
    const form = new FormData()
    form.append('backup', file, 'preview.zip')
    form.append('name', 'ZIP 示例')
    form.append('keep', '[]')
    const { data: imported } = await client.post('/config-profiles/import', form)
    expect(imported.profiles.find((profile) => profile.id === imported.active_id).name).toBe(
      'ZIP 示例'
    )
    expect(data.config.theme).toBe('dark')
    expect(data.status).toBe('stopped')
  })

  it('renders preview long-task times with the real time picker without changing the store snapshot', async () => {
    const initial = { maa_rg_sleep_min: '00:00', maa_rg_sleep_max: '00:00' }
    const data = createPreviewData(createPreviewConfiguration(initial))
    const client = axios.create({ adapter: createPreviewAdapter(data) })
    const { data: config } = await client.get('/conf')
    const app = createSSRApp({
      render: () =>
        h('div', [
          h(NTimePicker, { format: 'H:mm', formattedValue: config.maa_rg_sleep_min }),
          h(NTimePicker, { format: 'H:mm', formattedValue: config.maa_rg_sleep_max })
        ])
    })
    setupSsrStyles(app)

    await expect(renderToString(app)).resolves.toContain('0:00')
    expect(initial).toEqual({ maa_rg_sleep_min: '00:00', maa_rg_sleep_max: '00:00' })
  })

  it('preserves an injected native bridge and waits for late desktop injection', () => {
    const originalAdapter = axios.defaults.adapter
    try {
      const api = { get_platform: vi.fn() }
      const target = { innerWidth: 1280, innerHeight: 800, pywebview: { api } }
      installPreviewBackend({}, target)
      expect(target.pywebview.api).toBe(api)
      const pending = {
        innerWidth: 1280,
        innerHeight: 800,
        location: { search: '?native_preview=1' }
      }
      installPreviewBackend({}, pending)
      expect(pending.pywebview).toBeUndefined()
      pending.pywebview = { api }
      expect(pending.pywebview.api).toBe(api)
    } finally {
      axios.defaults.adapter = originalAdapter
    }
  })
  it('serves filled log, task and screenshot data without a transport', async () => {
    const data = createPreviewData({ theme: 'light' })
    const client = axios.create({ adapter: createPreviewAdapter(data) })
    expect(data.logs.length).toBeGreaterThanOrEqual(50)
    for (const level of ['INFO', 'WARNING', 'ERROR'])
      expect(data.logs.some((line) => line.includes(level))).toBe(true)
    const { data: tasks } = await client.get('http://real-backend.invalid/task')
    expect(tasks).toHaveLength(5)
    expect(
      tasks.every((task) => task.time.includes('T') && task.plan && task.type.display_value)
    ).toBe(true)
    const { data: image } = await client.get('/screenshot/latest')
    expect(image.type).toBe('image/svg+xml')
    expect(await image.text()).toContain('离线预览 · 示例截图')
  })

  it.each([
    ['running', true, 'running'],
    ['stopped', false, 'closed']
  ])(
    'reports the %s preview state without claiming a connected device',
    async (status, active, deviceStatus) => {
      const data = createPreviewData({ device: { last_serial: '127.0.0.1:16384' } })
      data.status = status
      const original = structuredClone(data)
      const client = axios.create({ adapter: createPreviewAdapter(data) })

      const { data: result } = await client.get('http://real-backend.invalid/device/status')

      expect(result).toMatchObject({
        host_platform: 'windows',
        active,
        status: deviceStatus,
        serial: '',
        readiness: null,
        managed_instance_presets: [],
        preflight: {
          kind: 'preflight',
          ok: false,
          error: { code: 'preview_unavailable' }
        }
      })
      expect(result.preflight.error.message).toContain('离线预览')
      expect(data).toEqual(original)
    }
  )

  it('returns an explicit unavailable preflight result without saving or starting a device', async () => {
    const data = createPreviewData({
      device: { preset_id: 'manual.other', last_serial: '127.0.0.1:16384' }
    })
    data.status = 'stopped'
    const original = structuredClone(data)
    const requests = []
    const client = axios.create({ adapter: createPreviewAdapter(data, requests) })

    const { data: result } = await client.post('http://real-backend.invalid/device/preflight', {
      device: { preset_id: 'windows.mumu12', instance_id: '0', last_serial: '' },
      start_manager: true
    })

    expect(result).toMatchObject({
      kind: 'preflight',
      ok: false,
      status: 'unavailable',
      serial: '',
      error: { code: 'preview_unavailable', action: 'none', fields: [] }
    })
    expect(result.error.message).toContain('不能连接或检测真实设备')
    expect(data).toEqual(original)
    expect(requests).toEqual([{ method: 'POST', path: '/device/preflight' }])
  })

  it.each([
    '/device/start',
    '/device/discover',
    '/device/avd/start',
    '/device/redroid/start',
    '/device/genymotion/start'
  ])('keeps %s unavailable in offline preview', async (path) => {
    const data = createPreviewData({ device: { last_serial: '127.0.0.1:16384' } })
    const original = structuredClone(data)
    const client = axios.create({ adapter: createPreviewAdapter(data) })

    await expect(client.post(path, {})).rejects.toMatchObject({
      code: 'ERR_PREVIEW_OPERATION',
      response: { status: 405 }
    })
    expect(data).toEqual(original)
  })

  it('keeps preview edits in memory and rejects unprovided actions', async () => {
    const data = createPreviewData({ theme: 'light' })
    const client = axios.create({ adapter: createPreviewAdapter(data) })
    await client.patch('/conf', { theme: 'dark' })
    expect((await client.get('/conf')).data.theme).toBe('dark')
    await expect(client.post('/device/start', {})).rejects.toMatchObject({
      code: 'ERR_PREVIEW_OPERATION',
      response: { status: 405 }
    })
    await expect(client.get('/stop')).rejects.toMatchObject({ code: 'ERR_PREVIEW_OPERATION' })
  })

  it('delivers the fixture through the WebSocket API without opening a connection', () => {
    vi.useFakeTimers()
    const Socket = previewWebSocket(['INFO preview', 'ERROR preview'])
    const socket = new Socket('ws://real-backend.invalid/log')
    const listener = vi.fn()
    socket.addEventListener('message', listener)
    vi.runAllTimers()
    expect(JSON.parse(listener.mock.calls[0][0].data)).toEqual({
      type: 'log',
      data: 'INFO preview\nERROR preview'
    })
    socket.close()
    expect(socket.readyState).toBe(Socket.CLOSED)
  })
})
