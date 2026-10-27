import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createSSRApp, effectScope, h, nextTick, ref } from 'vue'
import { parse as parseHtml } from '@vue/compiler-dom'
import { renderToString } from 'vue/server-renderer'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import { NDialogProvider, NMessageProvider } from 'naive-ui'
import axios from 'axios'
import { useConfigStore } from '@/stores/config'
import { usePlanStore } from '@/stores/plan'
import { useMowerStore } from '@/stores/mower'
import MowerSettings from './Settings.vue'
import TaskConfiguration from '@/task-workflow/TaskConfiguration.vue'
import TaskSettingsPanels from '@/components/TaskSettingsPanels.vue'
import { routes } from '@/routes'
import { themeSelectionKey } from '@/composables/themeSelection'

const state = vi.hoisted(() => ({ segmented: [], actions: {} }))

vi.mock('axios', () => ({ default: { get: vi.fn(), post: vi.fn(), patch: vi.fn() } }))
vi.mock('vue', async (original) => ({
  ...(await original()),
  useSSRContext: () => ({ modules: new Set() })
}))
vi.mock('naive-ui', async (original) => {
  const library = await original()
  const wrapper = (name) => ({
    inheritAttrs: false,
    props: ['value', 'checked', 'label', 'title', 'disabled', 'show'],
    setup(props, { attrs, slots }) {
      if (name === 'NButton' && attrs['aria-label']) {
        state.actions[attrs['aria-label']] = attrs.onClick
      }
      if (name === 'NTabs') {
        state.segmented.push({
          label: attrs['aria-label'],
          value: props.value,
          select: (value) => attrs['onUpdate:value']?.(value)
        })
      }
      return () => {
        if (name === 'NModal' && !props.show) return null
        const content = [props.title, props.label, slots.header?.(), slots.label?.()]
        if (name === 'NDynamicInput') {
          content.push(
            ...(props.value || []).map((value, index) => slots.default?.({ value, index }))
          )
        } else {
          content.push(slots.default?.())
        }
        if (['NInput', 'NInputNumber'].includes(name)) {
          content.push(h('input', { value: props.value, disabled: props.disabled, min: attrs.min }))
        }
        return h('div', { 'data-control': name }, content)
      }
    }
  })
  return {
    ...library,
    ...Object.fromEntries(
      Object.keys(library)
        .filter((name) => /^N[A-Z]/.test(name))
        .map((name) => [name, wrapper(name)])
    ),
    useDialog: () => ({}),
    useMessage: () => ({})
  }
})

let store
let plan
let scope

beforeEach(() => {
  state.segmented = []
  state.actions = {}
  const storage = { getItem: vi.fn(() => null), setItem: vi.fn(), removeItem: vi.fn() }
  vi.stubGlobal('sessionStorage', storage)
  vi.stubGlobal('localStorage', storage)
  vi.stubGlobal('window', { localStorage: storage, sessionStorage: storage })
})

afterEach(() => {
  scope?.stop()
  store?.$dispose()
  plan?.$dispose()
  vi.clearAllMocks()
  vi.unstubAllGlobals()
})

function setup(Page, overrides = {}, setTheme, pageProps = {}) {
  const app = createSSRApp({
    render: () =>
      h(NDialogProvider, null, {
        default: () =>
          h(NMessageProvider, null, {
            default: () =>
              h(Page, { ...(Page === TaskConfiguration ? { embedded: true } : {}), ...pageProps })
          })
      })
  })
  app.use(createPinia())
  app.use(createRouter({ history: createMemoryHistory(), routes }))
  app.provide('axios', axios)
  app.provide('loaded', ref(false))
  app.provide('mobile', ref(false))
  if (setTheme) app.provide(themeSelectionKey, setTheme)
  store = app.runWithContext(() => useConfigStore())
  plan = app.runWithContext(() => usePlanStore())
  app.runWithContext(() => useMowerStore()).updates_enabled = true
  Object.assign(store, {
    runtime_platform: 'windows',
    simulator: { name: 'MuMu12', wait_time: 75 },
    device_profile: { preset_id: 'windows.mumu12' },
    tap_to_launch_game: { mode: 'custom', command: 'saved-command', x: 200, y: 300 },
    run_order_grandet_mode: { enable: true, buffer_time: 25, back_to_index: true },
    waiting_scene: { LOADING: [3, 6] },
    skland_info: [],
    maa_long_task_type: 'sf',
    ...overrides
  })
  return app
}

function taskSections(html) {
  const sections = new Map()
  for (const node of elements(parseHtml(html))) {
    const id = attribute(node, 'data-task-editor')
    if (!id) continue
    const previous = sections.get(id)
    sections.set(id, {
      tag: previous?.tag || node.loc.source.slice(0, node.loc.source.indexOf('>') + 1),
      content: (previous?.content || '') + node.loc.source
    })
  }
  return sections
}

function elements(node) {
  return [node, ...(node.children || []).flatMap(elements)]
}

function attribute(node, name) {
  return node.props?.find((prop) => prop.name === name)?.value?.content
}

describe('settings page ownership', () => {
  it.each([0, 19, 20, 100])('无人机输入框传递最小值 20 和当前值 %s', async (limit) => {
    const html = await renderToString(setup(TaskSettingsPanels, { drone_count_limit: limit }))
    const forms = elements(parseHtml(html)).filter(
      (node) => attribute(node, 'data-control') === 'NFormItem'
    )
    const field = forms.find((node) => node.loc.source.includes('无人机使用阈值'))
    expect(field).toBeDefined()
    const input = elements(field).find((node) => node.tag === 'input')
    expect(attribute(input, 'min')).toBe('20')
    expect(attribute(input, 'value')).toBe(String(limit))
    expect(store.drone_count_limit).toBe(limit)
  })

  it.each([false, null])('keeps update controls hidden with permission %s', async (permission) => {
    const app = setup(MowerSettings)
    app.runWithContext(() => useMowerStore()).updates_enabled = permission
    const html = await renderToString(app)
    expect(html).not.toContain('软件更新')
    expect(html).not.toContain('资源更新')
    expect(html).toContain('截图保存时间')
    expect(axios.post).not.toHaveBeenCalled()
  })

  it('keeps software preferences and storage controls on Mower settings', async () => {
    const html = await renderToString(setup(MowerSettings))
    for (const label of [
      '界面缩放',
      '软件版本显示',
      '版本水印',
      '版本类型',
      '邮件提醒',
      '软件更新',
      '截图保存时间',
      '仓库历史',
      '完整备份与恢复',
      '导出当前档案',
      '导入档案'
    ]) {
      expect(html).toContain(label)
    }
    expect(html).toContain('aria-label="软件版本显示预览"')
    expect(html).toContain('version-workflow-targets')
    expect(state.segmented.map((control) => control.label)).toEqual(
      expect.arrayContaining(['显示主题', '软件版本显示'])
    )
    expect(html.match(/class="sidebar-brand-channel\b/g)).toHaveLength(4)
    for (const kind of ['source', 'alpha', 'nightly', 'stable']) {
      expect(html.match(new RegExp(`sidebar-brand-channel--${kind}`, 'g'))).toHaveLength(1)
    }
    for (const label of [
      '配置导出与导入',
      '导出配置',
      '导入配置',
      '启动游戏',
      '公开招募',
      '仓库物品混合读取',
      '跑单前置延时',
      '无人机使用阈值',
      '无人机加速间隔',
      '材料价值与基报算法'
    ]) {
      expect(html).not.toContain(label)
    }
    expect(axios.post).not.toHaveBeenCalled()
    expect(axios.patch).not.toHaveBeenCalled()
  })

  it('lets the application capture the old appearance before applying a theme selection', async () => {
    const setTheme = vi.fn()
    const html = await renderToString(setup(MowerSettings, { theme: 'light' }, setTheme))
    const control = state.segmented.find((entry) => entry.label === '显示主题')
    expect(control).toMatchObject({ value: 'light' })
    expect(html).toContain('跟随系统')
    control.select('system')
    expect(setTheme).toHaveBeenCalledExactlyOnceWith('system')
    expect(store.theme).toBe('light')
    expect(axios.patch).not.toHaveBeenCalled()
  })

  it('updates the theme directly when no transition owner is provided', async () => {
    await renderToString(setup(MowerSettings, { theme: 'dark' }))
    const control = state.segmented.find((entry) => entry.label === '显示主题')
    expect(control).toMatchObject({ value: 'dark' })
    control.select('light')
    await nextTick()
    expect(store.theme).toBe('light')
    expect(axios.patch).not.toHaveBeenCalled()
  })

  it('renders moved controls and the existing MAA tasks together', async () => {
    const html = await renderToString(setup(TaskConfiguration))
    for (const label of [
      '启动命令',
      '截图最短间隔',
      '跑单前置延时',
      '无人机使用阈值',
      '无人机加速间隔',
      '公开招募',
      '森空岛签到',
      '仓库物品混合读取',
      '自动切换信赖',
      '获取信用及购物',
      '大型任务',
      '触控模式'
    ]) {
      expect(html).toContain(label)
    }
    for (const label of ['界面缩放', '邮件提醒', '截图保存时间', '仓库历史']) {
      expect(html).toContain(label)
    }
    expect(html).toContain('saved-command')
    const accounts = html.slice(
      html.indexOf('<section id="task-accounts"'),
      html.indexOf('<section id="task-maa"')
    )
    expect(accounts).toContain('材料价值与基报算法')
    expect(axios.post).not.toHaveBeenCalled()
    expect(axios.patch).not.toHaveBeenCalled()
  })

  it('preserves the Android server and performance controls without desktop lifecycle options', async () => {
    const html = await renderToString(setup(TaskConfiguration, { runtime_platform: 'android' }))
    expect(html).toContain('设备连接由 Android 应用管理')
    expect(html).toContain('Bilibili 服')
    expect(html).toContain('设备性能适配')
    expect(html).not.toContain('启动命令')
    const runtime = html.slice(
      html.indexOf('<section id="task-runtime"'),
      html.indexOf('<section id="task-base"')
    )
    expect(runtime).not.toContain('任务结束后')
  })

  it('retains a physical device preference while omitting emulator shutdown from the UI', async () => {
    const app = setup(TaskConfiguration, {
      device_profile: { preset_id: 'manual.physical' },
      close_simulator_when_idle: true
    })
    const html = await renderToString(app)
    expect(html).not.toContain('关闭模拟器')
    expect(store.close_simulator_when_idle).toBe(true)
    expect(store.device_profile.preset_id).toBe('manual.physical')
  })

  it('edits the migrated idle action through the existing mutually exclusive fields', async () => {
    const app = setup(TaskConfiguration, { return_home_when_idle: true })
    scope = effectScope()
    const component = scope.run(() =>
      app.runWithContext(() =>
        TaskSettingsPanels.setup({ active: 'idle' }, { expose: () => {}, emit: () => {} })
      )
    )
    expect(component.displayedIdleAction.value).toBe('home')
    component.displayedIdleAction.value = 'exit'
    await nextTick()
    expect(store.return_home_when_idle).toBe(false)
    expect(store.exit_game_when_idle).toBe(true)
    expect(store.close_simulator_when_idle).toBe(false)
    component.reset_launch_command()
    expect(store.tap_to_launch_game.command).toBe(
      'input keyevent KEYCODE_WAKEUP; wm dismiss-keyguard; am start -n {package}/{activity}'
    )
    expect(store.tap_to_launch_game.x).toBe(200)
    expect(store.tap_to_launch_game.y).toBe(300)
  })

  it('redirects both old settings addresses to the unified page', () => {
    const children = routes[0].children
    const legacyTasks = children.find((route) => route.path === 'maasettings')
    expect(legacyTasks.component).toBeUndefined()
    expect(legacyTasks.redirect({ query: { token: 'demo' }, hash: '#task-devices' })).toEqual({
      name: 'settings',
      query: { token: 'demo' },
      hash: '#task-devices'
    })
    const legacyMower = children.find((route) => route.path === 'mowersettings')
    expect(legacyMower.component).toBeUndefined()
    expect(legacyMower.redirect({ query: { token: 'demo' }, hash: '#mower-data' })).toEqual({
      name: 'settings',
      query: { token: 'demo' },
      hash: '#mower-data'
    })
  })
})

describe('settings page layouts', () => {
  it('opens the clue configuration from the combined credit card', async () => {
    const select = vi.fn()
    await renderToString(
      setup(TaskSettingsPanels, {}, undefined, {
        active: 'credit',
        checklist: true,
        onSelect: select
      })
    )

    state.actions['配置线索搜集与交流']()

    expect(select).toHaveBeenCalledExactlyOnceWith('clue')
    expect(store.enable_party).toBe(true)
  })

  it('keeps launch and idle controls visible in the continuous page', async () => {
    const html = await renderToString(
      setup(TaskSettingsPanels, {}, undefined, {
        active: 'device',
        layout: 'checklist',
        checklist: true
      })
    )
    expect(html).toContain('task-settings-panels--continuous')
    expect(html).toContain('游戏启动')
    expect(html).toContain('任务运行')
    expect(html).toContain('启动游戏')
    expect(html).toContain('任务结束后')
    expect(html).toContain('saved-command')

    const defaultHtml = await renderToString(
      setup(TaskSettingsPanels, {}, undefined, { active: 'device' })
    )
    expect(defaultHtml).not.toContain('task-settings-panels--checklist')
    expect(defaultHtml).toContain('游戏启动')
    expect(defaultHtml).toContain('任务运行')
    expect(axios.post).not.toHaveBeenCalled()
    expect(axios.patch).not.toHaveBeenCalled()
  })

  it('keeps daily task intervals in their own checklist editor and task-specific intervals on their task cards', async () => {
    const html = await renderToString(
      setup(
        TaskSettingsPanels,
        { maa_gap: 7, drone_interval: 13, recruit_gap: 9, trust_rotation_interval: 27 },
        undefined,
        { active: 'intervals', layout: 'checklist', checklist: true }
      )
    )
    const sections = taskSections(html)
    const intervals = sections.get('intervals')
    expect(intervals.tag).not.toMatch(/display:\s*none/)
    const intervalFields = elements(parseHtml(intervals.content)).filter(
      (node) => attribute(node, 'data-control') === 'NFormItem'
    )
    for (const [label, value] of [['日常任务间隔', 7]]) {
      const field = intervalFields.find((node) =>
        elements(node).some((child) => child.type === 2 && child.content === label)
      )
      expect(field, label).toBeDefined()
      expect(
        elements(field)
          .filter((node) => node.tag === 'input')
          .map((node) => attribute(node, 'value')),
        label
      ).toEqual([String(value)])
    }
    expect(intervals.content.match(/data-control="NInputNumber"/g)).toHaveLength(1)
    expect(intervals.content).not.toContain('data-control="NSwitch"')
    expect(intervals.content).not.toContain('data-control="NCheckbox"')
    expect([...sections.keys()].some((id) => id.startsWith('category:'))).toBe(false)
    const droneInterval = elements(parseHtml(sections.get('drone').content)).find(
      (node) =>
        attribute(node, 'data-control') === 'NFormItem' &&
        elements(node).some((child) => child.type === 2 && child.content === '无人机加速间隔')
    )
    expect(droneInterval).toBeDefined()
    expect(attribute(droneInterval, 'style') || '').not.toMatch(/display:\s*none/)
    expect(sections.get('recruit').content).toContain('启动间隔')
    expect(sections.get('trust').content).toContain('检查间隔')
    expect(axios.post).not.toHaveBeenCalled()
    expect(axios.patch).not.toHaveBeenCalled()
  })

  it('renders continuous cards in directory order without fixed column groups', async () => {
    const app = setup(
      TaskSettingsPanels,
      {
        maa_gap: 7,
        drone_interval: 13,
        recruit_gap: 9,
        trust_rotation_interval: 27,
        visit_friend_enable: true,
        maa_mall_enable: true,
        maa_mall_mode: 'maa'
      },
      undefined,
      { active: 'recruit', layout: 'waterfall', checklist: false }
    )
    const html = await renderToString(app)
    const sections = taskSections(html)
    for (const id of [
      'device',
      'runtime',
      'idle',
      'base',
      'runorder',
      'drone',
      'clue',
      'workshop',
      'training',
      'trust',
      'credit',
      'daily',
      'recruit',
      'depot',
      'stage-plan',
      'rewards',
      'long',
      'accounts',
      'maa',
      'intervals'
    ]) {
      expect(sections.has(id), id).toBe(true)
      expect(sections.get(id).tag, id).not.toMatch(/display:\s*none/)
    }
    expect([...sections.keys()].some((id) => id.startsWith('category:'))).toBe(false)
    const content = (id) => sections.get(id).content
    expect(html).not.toContain('task-settings-panels--checklist')
    expect(content('device')).toContain('游戏启动')
    expect(content('device')).toContain('saved-command')
    expect(content('idle')).toContain('任务运行')
    expect(content('base')).toContain('自动救急')
    expect(content('runtime')).not.toContain('日常任务间隔')
    expect(content('intervals')).toContain('日常任务间隔')
    expect(content('intervals')).toContain('value="7"')
    for (const label of ['信用作战', '访问好友', '信用商店购物', '编队', '优先购买', '黑名单'])
      expect(content('credit')).toContain(label)
    expect(content('credit')).toContain('data-control="NCheckbox"')
    for (const label of ['每日任务', '森空岛签到', '领取邮件', '读取基报', '尚未添加森空岛账号'])
      expect(content('daily')).toContain(label)
    expect(content('daily')).toContain('data-control="NCheckbox"')
    for (const label of ['公开招募', '启动间隔', '三星招募阈值'])
      expect(content('recruit')).toContain(label)
    expect(content('recruit')).toContain('data-control="NCheckbox"')
    expect(content('recruit')).toContain('value="9"')
    expect(content('drone')).toContain('无人机加速间隔')
    expect(content('drone')).toContain('value="13"')
    expect(content('trust')).toContain('检查间隔')
    expect(content('trust')).toContain('value="27"')
    expect(content('maa')).toContain('MAA 核心')
    const tree = parseHtml(html)
    const panels = elements(tree).find((node) =>
      attribute(node, 'class')?.includes('task-settings-panels--continuous')
    )
    expect(
      panels.children.map((node) => attribute(node, 'data-task-editor')).filter(Boolean)
    ).toEqual([
      'device',
      'device',
      'idle',
      'base',
      'runorder',
      'drone',
      'clue',
      'workshop',
      'training',
      'trust',
      'daily',
      'recruit',
      'depot',
      'credit',
      'rewards',
      'stage-plan',
      'long',
      'intervals',
      'runtime',
      'accounts',
      'accounts',
      'accounts',
      'maa'
    ])
    expect(html).not.toContain('data-waterfall-group')
    expect(axios.post).not.toHaveBeenCalled()
    expect(axios.patch).not.toHaveBeenCalled()
  })

  it('includes Mower settings in the continuous page with one shared directory and no layout selector', async () => {
    const html = await renderToString(setup(TaskConfiguration))
    expect(html).toContain('task-workspace--continuous')
    expect(html).not.toContain('settings-aside')
    expect(html).not.toContain('settings-search-results')
    expect(html).not.toContain('全部设置显示')
    expect(html).not.toContain('配置分类')
    for (const label of [
      '界面缩放',
      '邮件提醒',
      '软件更新',
      '仓库历史',
      '完整备份与恢复',
      '自动救急',
      '连接与启动'
    ])
      expect(html).toContain(label)
    for (const id of [
      'mower-interface',
      'mower-notifications',
      'mower-profiles',
      'mower-updates',
      'mower-data'
    ])
      expect(html).toContain(`data-task-editor="${id}"`)
    expect(axios.post).not.toHaveBeenCalled()
    expect(axios.patch).not.toHaveBeenCalled()
  })
})

describe('managed optional maintenance settings', () => {
  it('keeps selectable profile actions and live restart-resume outside hidden maintenance', async () => {
    const app = setup(MowerSettings, {
      manager_owned_device: true,
      extra_settings_visible: false
    })
    const mower = app.runWithContext(() => useMowerStore())
    let sections = taskSections(await renderToString(app))
    expect(sections.get('mower-profiles')?.content).toContain('导入档案')
    expect(sections.get('mower-profiles')?.content).toContain('导出当前档案')
    expect(sections.get('mower-profiles')?.content).not.toContain('data-settings-label="重启续接"')

    mower.running = true
    sections = taskSections(await renderToString(app))
    const profiles = sections.get('mower-profiles')?.content
    expect(profiles).toContain('重启续接')
    expect(profiles).not.toContain('重启 Mower 进程')
    expect(profiles).not.toContain('结束 Mower 进程')
    expect(sections.has('mower-updates')).toBe(false)
    expect(sections.has('mower-data')).toBe(false)
    expect(axios.post).not.toHaveBeenCalled()
  })

  it.each([true, false])(
    'locks only inherited screenshot fields (inherited=%s)',
    async (inherited) => {
      const html = await renderToString(
        setup(MowerSettings, {
          manager_owned_device: true,
          extra_settings_visible: true,
          manager_inherited_settings: inherited ? ['screenshot', 'screenshot_archive_limit_mb'] : []
        })
      )
      const forms = elements(parseHtml(html)).filter(
        (node) => attribute(node, 'data-control') === 'NFormItem'
      )
      for (const label of ['截图保存时间', '报错归档空间上限']) {
        const field = forms.find((node) =>
          elements(node).some((child) => child.type === 2 && child.content === label)
        )
        expect(field, label).toBeDefined()
        const input = elements(field).find((node) => node.tag === 'input')
        expect(
          input.props.some((prop) => prop.name === 'disabled'),
          label
        ).toBe(inherited)
      }
      expect(html.includes('当前使用通用设置，请在多开管理器中修改或选择使用本实例值。')).toBe(
        inherited
      )
      expect(axios.patch).not.toHaveBeenCalled()
    }
  )

  it.each([false, true])(
    'omits the complete managed runtime panel with extra settings visibility %s',
    async (visible) => {
      const app = setup(TaskSettingsPanels, {
        manager_owned_device: true,
        extra_settings_visible: visible
      })
      const html = await renderToString(app)
      expect(taskSections(html).has('runtime')).toBe(false)
      expect(html).not.toContain('场景等待参数')
      expect(html).not.toContain('截图最短间隔')
      expect(html).not.toContain('选人采样间隔')
    }
  )

  it.each([
    [true, false, false],
    [true, true, true],
    [false, false, true]
  ])(
    'renders managed=%s visibility=%s with maintenance groups=%s',
    async (managed, visible, expected) => {
      const app = setup(MowerSettings, {
        manager_owned_device: managed,
        extra_settings_visible: visible
      })
      const mower = app.runWithContext(() => useMowerStore())
      mower.updates_enabled = false
      mower.ai_assistant_enabled = false
      const html = await renderToString(app)
      const ids = [...taskSections(html).keys()]
      expect(ids).toEqual([
        'mower-interface',
        'mower-notifications',
        'mower-profiles',
        ...(expected ? ['mower-updates', 'mower-data'] : [])
      ])
      expect(mower.updates_enabled).toBe(false)
      expect(mower.ai_assistant_enabled).toBe(false)
      expect(axios.patch).not.toHaveBeenCalled()
    }
  )
})
