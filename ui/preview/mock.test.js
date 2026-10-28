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
import { ORDER_PRICES, ORDER_TYPES } from '../src/utils/baseReport.js'

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

describe('offline preview', () => {
  it('loads the new shop and copilot forms without device or resource access', async () => {
    const client = axios.create({ adapter: createPreviewAdapter(createPreviewData({})) })
    expect((await client.get('/maa-event-shop')).data).toEqual({ shops: [] })
    expect((await client.get('/maa-paradox')).data).toEqual({ scripts: [] })
    expect((await client.get('/maa-copilot')).data).toEqual({ scripts: [] })
    await expect(client.post('/maa-event-shop', {})).rejects.toMatchObject({
      response: { status: 405 }
    })
  })
  it('keeps depot choices across independent edits and ignores a later migration', async () => {
    const data = createPreviewData({ theme: 'light' })
    const client = axios.create({ adapter: createPreviewAdapter(data) })
    const options = { headers: { 'X-Mower-Config-Generation': 'obsolete' } }
    expect((await client.get('/gui/depot')).data).toEqual({ depot: null })

    const migrated = await client.put(
      '/gui/depot',
      { depot: { favorites: ['龙门币'] }, migrate: true },
      options
    )
    expect(migrated.data.depot).toEqual({
      favorites: ['龙门币'],
      view: {
        stockFilter: 'all',
        deltaFilter: 'all',
        showDerived: true,
        sortMode: 'tier',
        showcaseTab: 'core'
      },
      baseline: {
        mode: 'time',
        preset: 'previous',
        range: null,
        followLatest: true,
        startKey: 'previous',
        endKey: 'latest'
      }
    })
    const view = { ...migrated.data.depot.view, sortMode: 'name', showcaseTab: 'favorites' }
    await client.put('/gui/depot', { depot: { view } }, options)
    const afterRace = await client.put(
      '/gui/depot',
      { depot: { favorites: ['赤金'] }, migrate: true },
      options
    )
    expect(afterRace.data.depot).toEqual({ ...migrated.data.depot, view })
    afterRace.data.depot.favorites.push('赤金')
    expect((await client.get('/gui/depot')).data.depot.favorites).toEqual(['龙门币'])
    expect(data.config).toEqual({ theme: 'light' })
    const freshClient = axios.create({ adapter: createPreviewAdapter(createPreviewData({})) })
    expect((await freshClient.get('/gui/depot')).data).toEqual({ depot: null })
  })

  it.each([
    {},
    { depot: {} },
    { depot: [] },
    { depot: { unknown: true } },
    { depot: { favorites: [] }, migrate: 'yes' }
  ])('rejects malformed depot preference group update %j', async (payload) => {
    const client = axios.create({ adapter: createPreviewAdapter(createPreviewData({})) })
    await expect(client.put('/gui/depot', payload)).rejects.toMatchObject({
      response: { status: 400 }
    })
    expect((await client.get('/gui/depot')).data).toEqual({ depot: null })
  })

  it('previews image selection and reset independently of profile generation', async () => {
    const client = axios.create({ adapter: createPreviewAdapter(createPreviewData({})) })
    const options = { headers: { 'X-Mower-Config-Generation': 'obsolete' } }
    expect((await client.get('/gui/log-background')).status).toBe(204)
    const uploaded = await client.put(
      '/gui/log-background',
      new Blob(['png image'], { type: 'image/png' }),
      options
    )
    expect(uploaded.status).toBe(200)
    expect(uploaded.data.type).toBe('image/webp')
    expect((await client.get('/gui/log-background')).data).toBe(uploaded.data)
    expect((await client.delete('/gui/log-background', options)).status).toBe(204)
    expect((await client.get('/gui/log-background')).status).toBe(204)
  })
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
      watermark_visible: true,
      task_settings_layout: 'checklist',
      base_report_mode: 'standard'
    })
    await client.put('/gui/appearance', { task_settings_layout: 'waterfall' })
    await client.put('/gui/appearance', { software_version_display: 'channel' })
    await client.put('/gui/appearance', { software_version_language: 'zh' })
    await expect(
      client.put('/gui/appearance', {
        watermark_visible: false,
        watermark_confirmation: '反馈问题时务必说明具体版本'
      })
    ).resolves.toMatchObject({
      data: { watermark_visible: false }
    })
    expect((await client.get('/gui/appearance')).data).toEqual({
      software_version_display: 'channel',
      software_version_language: 'zh',
      watermark_visible: false,
      task_settings_layout: 'waterfall',
      base_report_mode: 'standard'
    })
    expect(data.config).toEqual(originalConfig)
    expect(data.appearance).not.toHaveProperty('watermark_confirmation')
    await client.put('/gui/appearance', {
      software_version_display: 'version',
      software_version_language: 'en',
      watermark_visible: true,
      task_settings_layout: 'checklist',
      base_report_mode: 'standard'
    })
    expect(data.appearance).toEqual({
      software_version_display: 'version',
      software_version_language: 'en',
      watermark_visible: true,
      task_settings_layout: 'checklist',
      base_report_mode: 'standard'
    })
  })

  it.each([
    {},
    { task_settings_layout: 'grid' },
    { task_settings_layout: 'waterfall', software_version_display: 'invalid' },
    { task_settings_layout: 'invalid', software_version_display: 'channel' },
    { software_version_language: 'zh-CN', software_version_display: 'channel' },
    { software_version_language: null },
    { watermark_visible: null },
    { watermark_visible: 0 },
    { watermark_visible: 1 },
    { watermark_visible: 'false' },
    { watermark_visible: [] },
    { watermark_visible: {} },
    { watermark_visible: false },
    { watermark_visible: false, watermark_confirmation: '我知道了' },
    { watermark_visible: false, watermark_confirmation: true },
    { watermark_visible: false, watermark_confirmation: ['反馈问题时务必说明具体版本'] },
    { watermark_confirmation: '反馈问题时务必说明具体版本' },
    { watermark_visible: true, watermark_confirmation: '反馈问题时务必说明具体版本' },
    { software_version_display: 'channel', watermark_visible: false },
    { software_version_display: 'channel', watermark_visible: 'true' },
    { task_settings_layout: 'waterfall', unknown: true },
    { task_settings_layout: 'waterfall', constructor: 'channel' },
    { base_report_mode: 'grid' },
    { base_report_mode: null },
    { base_report_mode: true },
    { base_report_mode: 'stock', task_settings_layout: 'grid' }
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

  it('stores the base report mode preference and rejects unknown modes', async () => {
    const data = createPreviewData({ theme: 'light' })
    const client = axios.create({ adapter: createPreviewAdapter(data) })
    expect((await client.get('/gui/appearance')).data.base_report_mode).toBe('standard')
    await client.put('/gui/appearance', { base_report_mode: 'stock' })
    expect((await client.get('/gui/appearance')).data).toMatchObject({
      software_version_display: 'version',
      task_settings_layout: 'checklist',
      base_report_mode: 'stock'
    })
    await expect(
      client.put('/gui/appearance', { base_report_mode: 'dividend' })
    ).rejects.toMatchObject({ response: { status: 400 } })
    expect((await client.get('/gui/appearance')).data.base_report_mode).toBe('stock')
    await client.put('/gui/appearance', { base_report_mode: 'standard' })
    expect((await client.get('/gui/appearance')).data.base_report_mode).toBe('standard')
    expect(data.config).toEqual({ theme: 'light' })
  })

  it('opens the stock mode from the preview URL parameter', () => {
    try {
      vi.stubGlobal('location', { search: '?base_report_mode=stock' })
      expect(createPreviewData({}).appearance.base_report_mode).toBe('stock')
    } finally {
      vi.unstubAllGlobals()
    }
    expect(createPreviewData({}).appearance.base_report_mode).toBe('standard')
  })

  it('serves a self-consistent daily order mix for the base report preview', async () => {
    const data = createPreviewData({})
    const client = axios.create({ adapter: createPreviewAdapter(data) })
    const report = (await client.get('/report/getReportData')).data
    const trading = (await client.get('/report/trading_history')).data
    expect(report).toHaveLength(30)
    expect(trading).toHaveLength(report.length)
    const trades = new Map(trading.map((row) => [row['日期'], row]))
    for (const row of report) {
      const trade = trades.get(row['日期'])
      expect(trade, row['日期']).toBeTruthy()
      let knownAmount = 0
      let knownCount = 0
      for (const type of ORDER_TYPES) {
        const count = trade[type] ?? 0
        expect(Number.isInteger(count) && count >= 0, `${row['日期']} ${type}`).toBe(true)
        knownAmount += count * ORDER_PRICES[type]
        knownCount += count
      }
      expect(knownAmount).toBeGreaterThan(0)
      expect(row['龙门币订单']).toBeGreaterThanOrEqual(knownAmount)
      expect(row['龙门币订单数']).toBeGreaterThanOrEqual(knownCount)
      expect(row['每单获取龙门币']).toBe(Math.round(row['龙门币订单'] / row['龙门币订单数']))
    }
  })

  it('groups recorded order samples into hourly, four-hour and game-day candles', async () => {
    const data = createPreviewData({})
    data.baseReport.trading = [{ 日期: '2026-10-28', 但书_2000: 1, 但书_2500: 2 }]
    const client = axios.create({ adapter: createPreviewAdapter(data) })
    const params = { startDate: '2026-10-28', endDate: '2026-10-28', period: '1h' }
    const hourly = (await client.get('/report/order-candles', { params })).data
    expect(hourly.candles).toHaveLength(24)
    expect(hourly.candles[0]).toMatchObject({ open: 2000, close: 2000, count: 1 })
    expect(hourly.candles[3]).toMatchObject({ open: null, mean: null, count: 0 })
    const fourHour = (
      await client.get('/report/order-candles', { params: { ...params, period: '4h' } })
    ).data
    expect(fourHour.candles).toHaveLength(6)
    expect(fourHour.candles[0]).toMatchObject({
      open: 2000,
      high: 2500,
      low: 2000,
      close: 2500,
      count: 3,
      amount: 7000
    })
    expect(fourHour.candles[0].mean).toBeCloseTo(7000 / 3)
    const daily = (
      await client.get('/report/order-candles', { params: { ...params, period: 'day' } })
    ).data
    expect(daily.candles).toHaveLength(1)
    expect(daily.recordedCount).toBe(3)
    expect(daily.amount).toBe(7000)
    await expect(
      client.get('/report/order-candles', { params: { ...params, period: 'minute' } })
    ).rejects.toMatchObject({ response: { status: 400 } })
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

describe('成长规划离线示例', () => {
  function growthClient() {
    return axios.create({
      adapter: createPreviewAdapter(createPreviewData(createPreviewConfiguration({})))
    })
  }

  it('列表接口不携带材料明细，详情接口带材料与目标', async () => {
    const client = growthClient()
    const list = await client.get('/mastery-recommendation', { params: { materials: 0 } })
    expect(list.data.has_data).toBe(true)
    expect(list.data.operators.length).toBeGreaterThan(10)
    const operator = list.data.operators.find((entry) => entry.recommendations.length)
    expect(operator.recommendations[0]).not.toHaveProperty('targets')
    const detail = await client.get('/mastery-recommendation', {
      params: { char_id: operator.char_id }
    })
    expect(detail.data.operators[0].recommendations[0].targets).toBeTruthy()
    expect(detail.data).not.toHaveProperty('goals')
  })

  it('养成计划、目标与顺序的修改只保存在预览内存中', async () => {
    const client = growthClient()
    const plan = await client.get('/mastery-plan')
    expect(plan.data.plans.length).toBeGreaterThan(0)
    const target = plan.data.plans[0]
    const added = await client.post('/mastery-plan', {
      planning: true,
      items: [
        {
          char_id: target.char_id,
          name: target.name,
          skill_index: 0,
          target_level: 2
        }
      ]
    })
    expect(['added', 'existing']).toContain(added.data.results[0].status)
    const goals = await client.post('/growth-plan', {
      char_id: target.char_id,
      module_id: 'elite2',
      selected: true
    })
    expect(goals.data.goals.some((goal) => goal.module_id === 'elite2')).toBe(true)
    const order = await client.get('/growth-crafting-order')
    expect(Array.isArray(order.data.planning_items)).toBe(true)
    expect(Array.isArray(order.data.items)).toBe(true)
    const survey = await client.get('/growth-survey')
    expect(survey.data.operators.length).toBeGreaterThan(10)
  })

  it('提供工作区需要的干员名列表与工作室状态', async () => {
    const client = growthClient()
    const names = await client.get('/operator')
    expect(names.data.length).toBeGreaterThan(10)
    const status = await client.get('/workshop-status')
    expect(status.data).toHaveProperty('execution')
    await expect(client.get('/growth-not-provided')).rejects.toMatchObject({
      code: 'ERR_PREVIEW_OPERATION'
    })
  })

  it('同阶段升级保留在完整计划中，跨阶段升级才进入合成列表', async () => {
    const client = growthClient()
    const list = await client.get('/mastery-recommendation', { params: { materials: 0 } })
    const leveling = list.data.operators.find(
      (operator) =>
        operator.elite === 2 &&
        operator.level < operator.level_goals.find((goal) => goal.id === 'elite2_max')?.level
    )
    const promotion = list.data.operators.find(
      (operator) => operator.elite < 2 && operator.level_goals.some((goal) => goal.id === 'elite2')
    )
    expect(leveling).toBeTruthy()
    expect(promotion).toBeTruthy()
    await client.post('/growth-plan', {
      char_id: leveling.char_id,
      module_id: 'elite2_max',
      selected: true
    })
    await client.post('/growth-plan', {
      char_id: promotion.char_id,
      module_id: 'elite2',
      selected: true
    })
    const { data: order } = await client.get('/growth-crafting-order')
    const levelingKey = `goal:${leveling.char_id}:elite2_max`
    const promotionKey = `goal:${promotion.char_id}:elite2`
    expect(order.planning_items.find((item) => item.key === levelingKey)).toMatchObject({
      crafting_required: false,
      label: leveling.level_goals.find((goal) => goal.id === 'elite2_max').label
    })
    expect(order.items.some((item) => item.key === levelingKey)).toBe(false)
    expect(order.planning_items.find((item) => item.key === promotionKey)).toMatchObject({
      crafting_required: true
    })
    expect(order.items.some((item) => item.key === promotionKey)).toBe(true)
  })

  it('失败计划保留失败原因并排除在可执行顺序之外', async () => {
    const client = growthClient()
    const { data: plans } = await client.get('/mastery-plan')
    const failed = plans.plans.find((plan) => plan.status === 'failed')
    expect(failed.failed_reason).toBeTruthy()
    const { data: order } = await client.get('/growth-crafting-order')
    expect(order.planning_items.some((item) => item.plan_id === failed.id)).toBe(false)
    expect(order.items.some((item) => item.plan_id === failed.id)).toBe(false)
  })

  it('既有计划和新建计划的辅助工时都使用小时', async () => {
    const client = growthClient()
    const { data: initial } = await client.get('/mastery-plan')
    const existing = initial.plans.find((plan) => plan.name === '泥岩')
    expect(existing.support_plan.stages.map((stage) => stage.hours)).toEqual([4.57, 9.14, 15])
    expect(existing.support_plan.hours).toBe(28.71)

    const { data: added } = await client.post('/mastery-plan', {
      planning: true,
      items: [{ char_id: 'char_2023_ling', name: '令', skill_index: 0, target_level: 3 }]
    })
    expect(added.results[0].status).toBe('added')
    const { data: updated } = await client.get('/mastery-plan')
    const created = updated.plans.find((plan) => plan.id === added.results[0].id)
    expect(created.support_plan.stages.map((stage) => stage.hours)).toEqual([4.57, 9.14, 15])
    expect(created.support_plan.hours).toBe(28.71)
  })
})
