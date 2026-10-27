import { readFileSync } from 'node:fs'
import { parse } from '@vue/compiler-sfc'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  createRenderer,
  compile,
  createSSRApp,
  defineComponent,
  h,
  nextTick,
  reactive,
  ssrContextKey
} from 'vue'
import { renderToString } from 'vue/server-renderer'
import { createPinia } from 'pinia'
import { useGuiStore } from '@/stores/gui'
import axios from 'axios'
import { useResourceVersionStore } from '@/stores/resourceVersion'
import SidebarBrand from './SidebarBrand.vue'
import SidebarUpdateChecks from './SidebarUpdateChecks.vue'
import SoftwareVersionBadge from './SoftwareVersionBadge.vue'

const messages = vi.hoisted(() => ({
  loading: vi.fn(),
  success: vi.fn(),
  info: vi.fn(),
  error: vi.fn(),
  destroy: vi.fn(),
  warning: vi.fn(),
  installSoftware: vi.fn()
}))
vi.mock('axios', () => ({ default: { get: vi.fn(), post: vi.fn() } }))
vi.mock('naive-ui', async (original) => ({
  ...(await original()),
  useMessage: () => messages,
  useDialog: () => ({ warning: messages.warning }),
  NTooltip: defineComponent({
    inheritAttrs: false,
    setup:
      (_, { slots }) =>
      () =>
        slots.trigger?.()
  })
}))

vi.mock('./SoftwareUpdate.vue', () => ({
  default: defineComponent({
    setup(_, { expose }) {
      expose({ installCheckedUpdate: messages.installSoftware })
      return () => h('div', '软件更新进度')
    }
  })
}))
vi.mock('./ResourceUpdate.vue', () => ({
  default: defineComponent({
    setup(_, { expose }) {
      expose({ installCheckedUpdate: useResourceVersionStore().installResource })
      return () => h('div', '资源更新进度')
    }
  })
}))

const metadata = {
  activity: {
    name: '昨日海',
    time: Date.parse('2026-10-10T00:00:00+08:00') / 1000,
    endTime: Date.parse('2026-10-20T00:00:00+08:00') / 1000
  }
}
let mounted
let mountedGui
const ClockBrand = { ...SidebarBrand, render: () => h('div') }
const descriptor = parse(
  readFileSync(new URL('./SidebarBrand.vue', import.meta.url), 'utf8')
).descriptor
const badgeDescriptor = parse(
  readFileSync(new URL('./SoftwareVersionBadge.vue', import.meta.url), 'utf8')
).descriptor
const ClientSoftwareVersionBadge = {
  ...SoftwareVersionBadge,
  ssrRender: undefined,
  render: compile(badgeDescriptor.template.content, { hoistStatic: false }),
  setup: (props, context) => ({ ...SoftwareVersionBadge.setup(props, context) })
}
const ClientBrand = {
  ...SidebarBrand,
  ssrRender: undefined,
  components: {
    SoftwareVersionBadge: ClientSoftwareVersionBadge,
    NTooltip: defineComponent({
      setup:
        (_, { slots }) =>
        () =>
          slots.trigger?.()
    })
  },
  render: compile(descriptor.template.content, { hoistStatic: false }),
  setup: (props, context) => ({ ...SidebarBrand.setup(props, context) })
}
const checksDescriptor = parse(
  readFileSync(new URL('./SidebarUpdateChecks.vue', import.meta.url), 'utf8')
).descriptor
const ClientChecks = {
  ...SidebarUpdateChecks,
  ssrRender: undefined,
  components: {
    SidebarBrand: ClientBrand,
    NModal: defineComponent({
      props: ['show'],
      setup:
        (props, { slots }) =>
        () =>
          props.show ? h('div', slots.default?.()) : null
    })
  },
  render: compile(checksDescriptor.template.content, { hoistStatic: false }),
  setup: (props, context) => ({ ...SidebarUpdateChecks.setup(props, context) })
}
const node = (tag) => ({ tag, props: {}, children: [], parent: null, text: '' })
const all = (element) => [element, ...element.children.flatMap(all)]
const textContent = (element) => element.text + element.children.map(textContent).join('')

function mountClock(props, component = ClockBrand, copies = 1) {
  const renderer = createRenderer({
    createElement: node,
    createText: (text) => ({ ...node('#text'), text }),
    createComment: () => node('#comment'),
    setText: (element, text) => (element.text = text),
    setElementText(element, text) {
      element.text = text
      element.children = []
    },
    patchProp: (element, key, _oldValue, value) => (element.props[key] = value),
    insert(element, parent, anchor) {
      const previousIndex = element.parent?.children.indexOf(element) ?? -1
      if (previousIndex >= 0) element.parent.children.splice(previousIndex, 1)
      element.parent = parent
      const index = anchor ? parent.children.indexOf(anchor) : -1
      if (index >= 0) parent.children.splice(index, 0, element)
      else parent.children.push(element)
    },
    remove(element) {
      const index = element.parent?.children.indexOf(element) ?? -1
      if (index >= 0) element.parent.children.splice(index, 1)
      element.parent = null
    },
    parentNode: (element) => element.parent,
    nextSibling: (element) => element.parent?.children[element.parent.children.indexOf(element) + 1]
  })
  const root = node('root')
  mounted = renderer.createApp({
    render: () =>
      h(
        'div',
        Array.from({ length: copies }, () => h(component, props))
      )
  })
  const pinia = createPinia()
  mounted.use(pinia)
  mountedGui = useGuiStore(pinia)
  mounted.provide(ssrContextKey, { modules: new Set() })
  mounted.mount(root)
  return {
    gui: mountedGui,
    nodes: () => all(root),
    button: () =>
      all(root).find(
        (element) =>
          element.tag === 'button' && element.props.class?.includes('sidebar-brand-channel')
      ),
    resourceButton: () =>
      all(root).find(
        (element) =>
          element.tag === 'button' &&
          element.props.class?.split(' ').includes('sidebar-brand-resource')
      )
  }
}

beforeEach(() => {
  vi.resetAllMocks()
  messages.loading.mockReturnValue({ destroy: messages.destroy })
  vi.useFakeTimers()
  vi.setSystemTime(new Date('2026-10-15T00:00:00+08:00'))
})
afterEach(() => {
  mounted?.unmount()
  mounted = null
  mountedGui?.$dispose()
  mountedGui = null
  vi.clearAllTimers()
  vi.useRealTimers()
})

describe('sidebar version badges', () => {
  it('keeps the exact resource display in a keyboard-accessible badge without the little label', async () => {
    const html = await renderToString(
      createSSRApp(SidebarBrand, {
        version: '4.1.6-alpha.12+unknown',
        resourceVersion: '昨日海 · 当前资源',
        resourceMetadata: metadata
      })
    )
    expect(html).toContain('sidebar-brand-channel--alpha')
    expect(html).toContain('4.1.6-alpha.12+unknown')
    expect(html).toContain('>昨日海 · 当前资源</button>')
    expect(html).toContain('sidebar-brand-resource--dated')
    expect(html).toContain('--resource-badge-hue:70')
    expect(html).toContain('tabindex="0"')
    expect(html).toContain('活动「昨日海」结束')
    expect(html).not.toContain('sidebar-brand-version-label')
    expect(vi.getTimerCount()).toBe(0)
  })

  it('shows nightly only for the installed nightly format and leaves unknown resource dates neutral', async () => {
    const html = await renderToString(
      createSSRApp(SidebarBrand, {
        version: '4.1.6-alpha.12.gdeadbeef',
        resourceVersion: '当前资源'
      })
    )
    expect(html).toContain('sidebar-brand-channel--nightly')
    expect(html).not.toContain('sidebar-brand-resource--dated')
    expect(html).toContain('未提供有效的活动或卡池结束时间')
  })

  it.each(['4.1.6-alpha.12+deadbee', '4.1.6-alpha.12.gdeadbeef'])(
    'shows one source badge in the original version row while preserving the actual version %s',
    async (version) => {
      const html = await renderToString(
        createSSRApp(SidebarBrand, { version, deployment: 'source' })
      )
      expect(html).toContain('sidebar-brand-channel--source')
      expect(html).toContain('源码启动')
      expect(html).toContain(`软件版本 ${version}`)
      expect(html.match(/class="sidebar-brand-channel\b/g)).toHaveLength(1)
      expect(html.indexOf('sidebar-brand-name')).toBeLessThan(html.indexOf('sidebar-brand-channel'))
      expect(html.indexOf('sidebar-brand-channel')).toBeGreaterThan(
        html.indexOf('sidebar-brand-versions')
      )
      expect(html).not.toContain('sidebar-brand-channel--nightly')
      expect(html).not.toContain('sidebar-brand-channel--alpha')
    }
  )

  it.each([
    ['4.1.6-alpha.12.gdeadbeef+deadbee', 'release', 'nightly'],
    ['4.1.6-alpha.12+deadbee', 'release', 'alpha'],
    ['4.1.6-alpha.12.gdeadbeef', null, 'nightly']
  ])('uses the version badge for %s with deployment %s', async (version, deployment, badge) => {
    const html = await renderToString(createSSRApp(SidebarBrand, { version, deployment }))
    expect(html).toContain(`sidebar-brand-channel--${badge}`)
    expect(html).not.toContain('sidebar-brand-channel--source')
    expect(html.match(/class="sidebar-brand-channel\b/g)).toHaveLength(1)
  })

  it('does not guess source from a release SHA and removes the collapsed badge from keyboard navigation', async () => {
    const release = await renderToString(
      createSSRApp(SidebarBrand, { version: '4.1.6+deadbeef', deployment: 'release' })
    )
    expect(release).toContain('sidebar-brand-channel--stable')
    expect(release).not.toContain('sidebar-brand-channel--source')
    const collapsed = await renderToString(
      createSSRApp(SidebarBrand, {
        version: '4.1.6-alpha.12.gdeadbeef',
        deployment: 'source',
        collapsed: true
      })
    )
    expect(collapsed).toContain('aria-hidden="true"')
    expect(collapsed).toContain('tabindex="-1"')
  })

  it.each([
    ['4.1.6-alpha.12.gdeadbeef+deadbee', 'source', 'source'],
    ['4.1.6-alpha.12.gdeadbeef', 'release', 'nightly'],
    ['4.1.6-alpha.12+unknown', 'release', 'alpha'],
    ['v4.1.6+build.42-foo', 'release', 'stable']
  ])(
    'uses a native button to check software updates while preserving the display mode for %s',
    async (version, deployment, channel) => {
      const update = vi.fn()
      const check = vi.fn()
      const props = reactive({
        version,
        deployment,
        displayMode: 'version',
        updatesEnabled: true,
        onCheckSoftware: check,
        'onUpdate:displayMode': update
      })
      const view = mountClock(props, ClientBrand)
      expect(view.button().props.type).toBe('button')
      expect(textContent(view.button())).toBe(version)
      expect(view.button().props['aria-pressed']).toBeUndefined()
      expect(view.button().props.class).toContain(`sidebar-brand-channel--${channel}`)
      expect(view.button().props.title).toContain(`软件版本 ${version}`)
      view.button().props.onClick()
      await nextTick()
      expect(check).toHaveBeenCalledOnce()
      expect(update).not.toHaveBeenCalled()
      expect(textContent(view.button())).toBe(version)
      props.displayMode = 'channel'
      await nextTick()
      expect(textContent(view.button())).toBe(channel)
      expect(view.button().props.title).toContain('点击检查软件更新')
      view.button().props.onClick()
      expect(check).toHaveBeenCalledTimes(2)
      props.displayMode = 'version'
      await nextTick()
      expect(textContent(view.button())).toBe(version)
      expect(update).not.toHaveBeenCalled()
    }
  )

  it('keeps the chosen display mode when deployment, version and collapse props change', async () => {
    const props = reactive({
      version: '4.1.6-alpha.12.gdeadbeef',
      deployment: null,
      displayMode: 'channel',
      collapsed: false
    })
    const view = mountClock(props, ClientBrand)
    expect(textContent(view.button())).toBe('nightly')
    props.deployment = 'source'
    await nextTick()
    expect(textContent(view.button())).toBe('source')
    props.version = '4.1.7+deadbee'
    props.deployment = 'release'
    await nextTick()
    expect(textContent(view.button())).toBe('stable')
    props.collapsed = true
    await nextTick()
    expect(view.button().props.tabindex).toBe(-1)
    props.collapsed = false
    await nextTick()
    expect(textContent(view.button())).toBe('stable')
  })

  it.each([
    ['4.1.6-alpha.12+deadbee', 'source', 'source', '源码部署'],
    ['4.1.6-alpha.12+unknown', 'release', 'alpha', '公测版'],
    ['4.1.6-alpha.12.gdeadbeef', 'release', 'nightly', '开发版'],
    ['4.1.6+build.42-foo', 'release', 'stable', '正式版'],
    ['4.1.6-rc.2', 'release', '', '4.1.6-rc.2']
  ])(
    'synchronizes translated software type labels across sidebar copies for %s',
    async (version, deployment, channel, chinese) => {
      const check = vi.fn()
      const props = reactive({
        version,
        deployment,
        displayMode: 'channel',
        updatesEnabled: true,
        onCheckSoftware: check
      })
      const view = mountClock(props, ClientBrand, 2)
      const buttons = () =>
        view
          .nodes()
          .filter(
            (element) =>
              element.tag === 'button' && element.props.class?.includes('sidebar-brand-channel')
          )
      expect(buttons().map(textContent)).toEqual([channel || version, channel || version])
      view.gui.softwareVersionLanguage = 'zh'
      await nextTick()
      expect(buttons().map(textContent)).toEqual([chinese, chinese])
      for (const button of buttons()) {
        if (channel) expect(button.props.class).toContain(`sidebar-brand-channel--${channel}`)
        expect(button.props.title).toContain(version)
        expect(button.props.title).toContain('点击检查软件更新')
        button.props.onClick()
      }
      expect(check).toHaveBeenCalledTimes(2)
      props.displayMode = 'version'
      await nextTick()
      expect(buttons().map(textContent)).toEqual([version, version])
      props.displayMode = 'channel'
      view.gui.softwareVersionLanguage = 'en'
      await nextTick()
      expect(buttons().map(textContent)).toEqual([channel || version, channel || version])
    }
  )

  it('keeps an unknown version available for update checks and hides an empty version', async () => {
    const props = reactive({
      version: 'custom-developer-build',
      deployment: null,
      updatesEnabled: true
    })
    const view = mountClock(props, ClientBrand)
    expect(textContent(view.button())).toBe('custom-developer-build')
    expect(view.button().props.disabled).toBe(false)
    props.version = ''
    props.deployment = 'source'
    await nextTick()
    expect(view.button()).toBeUndefined()
  })

  it('keeps version badges read-only when updates are not authorized', () => {
    const checkSoftware = vi.fn()
    const checkResource = vi.fn()
    const view = mountClock(
      {
        version: '4.1.6',
        deployment: 'release',
        resourceVersion: '当前资源',
        onCheckSoftware: checkSoftware,
        onCheckResource: checkResource
      },
      ClientBrand
    )
    expect(textContent(view.button())).toBe('4.1.6')
    expect(view.button().props.disabled).toBe(true)
    expect(view.resourceButton().props.disabled).toBe(true)
    view.button().props.onClick()
    view.resourceButton().props.onClick()
    expect(checkSoftware).not.toHaveBeenCalled()
    expect(checkResource).not.toHaveBeenCalled()
  })

  it('uses independent update actions and busy states for the software and resource badges', async () => {
    const software = vi.fn()
    const resource = vi.fn()
    const props = reactive({
      version: '4.1.6',
      resourceVersion: '当前资源',
      updatesEnabled: true,
      softwareChecking: false,
      resourceChecking: false,
      onCheckSoftware: software,
      onCheckResource: resource
    })
    const view = mountClock(props, ClientBrand)
    expect(view.resourceButton().props.type).toBe('button')
    view.button().props.onClick()
    view.resourceButton().props.onClick()
    expect(software).toHaveBeenCalledOnce()
    expect(resource).toHaveBeenCalledOnce()
    props.softwareChecking = true
    await nextTick()
    expect(view.button().props.disabled).toBe(true)
    expect(view.button().props['aria-busy']).toBe(true)
    expect(view.resourceButton().props.disabled).toBe(false)
    props.resourceChecking = true
    await nextTick()
    expect(view.resourceButton().props.disabled).toBe(true)
    expect(view.resourceButton().props['aria-busy']).toBe(true)
    view.button().props.onClick()
    view.resourceButton().props.onClick()
    expect(software).toHaveBeenCalledOnce()
    expect(resource).toHaveBeenCalledOnce()
  })

  it.each([true, false])(
    'confirms the checked software target before installing (visible=%s)',
    async (extraSettingsVisible) => {
      let finish
      axios.get.mockResolvedValue({
        data: {
          ok: true,
          version: '4.1.6',
          blockers: [],
          instances: [{}],
          settings: { channel: 'stable' },
          channels: [{ value: 'stable', label: '正式版' }]
        }
      })
      axios.post.mockImplementationOnce(() => new Promise((resolve) => (finish = resolve)))
      const update = vi.fn()
      const view = mountClock(
        { version: '4.1.6', enabled: true, extraSettingsVisible, 'onUpdate:displayMode': update },
        ClientChecks
      )
      const request = view.button().props.onClick()
      await vi.advanceTimersByTimeAsync(0)
      expect(view.button().props.disabled).toBe(true)
      view.button().props.onClick()
      expect(axios.get).toHaveBeenCalledExactlyOnceWith(
        expect.stringContaining('/software-update/info')
      )
      expect(axios.post).toHaveBeenCalledExactlyOnceWith(
        expect.stringContaining('/software-update/check'),
        { channel: 'stable' },
        { headers: { 'X-Mower-Update': '1' } }
      )
      finish({
        data: {
          ok: true,
          available: true,
          version: '4.1.7',
          check_id: 'sidebar-check',
          channel: 'stable',
          notes: '修复设置页面显示'
        }
      })
      await request
      await vi.advanceTimersByTimeAsync(0)
      const confirmation = messages.warning.mock.calls[0][0]
      const previewHtml = await renderToString(createSSRApp({ render: confirmation.content }))
      expect(previewHtml).toContain('4.1.7')
      expect(previewHtml).toContain('更新渠道 · 正式版')
      expect(previewHtml).toContain('修复设置页面显示')
      expect(previewHtml).not.toContain('自动检查更新')
      expect(confirmation.positiveText).toBe('立即更新')
      expect(messages.installSoftware).not.toHaveBeenCalled()
      await confirmation.onPositiveClick()
      expect(messages.installSoftware).toHaveBeenCalledExactlyOnceWith(
        expect.objectContaining({
          check_id: 'sidebar-check',
          version: '4.1.7',
          confirm_downgrade: false
        })
      )
      expect(messages.destroy).toHaveBeenCalledOnce()
      expect(view.button().props.disabled).toBe(false)
      expect(update).not.toHaveBeenCalled()
      expect(axios.post).toHaveBeenCalledOnce()
    }
  )

  it('checks resources through the shared store and reports failures before allowing retry', async () => {
    axios.get
      .mockResolvedValueOnce({
        data: { current_display: '当前资源', update_available: null, error: '代理连接失败' }
      })
      .mockResolvedValueOnce({ data: { current_display: '当前资源', update_available: false } })
    const view = mountClock({ resourceVersion: '当前资源', enabled: true }, ClientChecks)
    await view.resourceButton().props.onClick()
    await vi.advanceTimersByTimeAsync(0)
    expect(messages.error).toHaveBeenCalledWith('资源检查未完成：代理连接失败')
    expect(view.resourceButton().props.disabled).toBe(false)
    await view.resourceButton().props.onClick()
    await vi.advanceTimersByTimeAsync(0)
    expect(messages.success).toHaveBeenCalledWith('资源已是最新版本。')
    expect(axios.get).toHaveBeenCalledTimes(2)
    expect(axios.get).toHaveBeenCalledWith(expect.stringMatching(/\/resource-version$/))
    expect(axios.post).not.toHaveBeenCalled()
  })

  it('shares one software request and busy state across mounted navigation copies', async () => {
    let finish
    axios.get.mockImplementationOnce(() => new Promise((resolve) => (finish = resolve)))
    axios.post.mockResolvedValue({ data: { ok: true, available: false } })
    const view = mountClock({ version: '4.1.6', enabled: true }, ClientChecks, 2)
    const buttons = () =>
      view.nodes().filter((node) => node.props.class?.includes('sidebar-brand-channel'))
    buttons()[0].props.onClick()
    buttons()[1].props.onClick()
    await nextTick()
    expect(buttons().every((button) => button.props.disabled)).toBe(true)
    expect(messages.loading).toHaveBeenCalledOnce()
    expect(axios.get).toHaveBeenCalledOnce()
    finish({ data: { ok: true, settings: { channel: 'beta' } } })
    await vi.advanceTimersByTimeAsync(0)
    expect(axios.post).toHaveBeenCalledOnce()
    expect(messages.success).toHaveBeenCalledWith('软件已与所选渠道一致。')
    expect(buttons().every((button) => !button.props.disabled)).toBe(true)
  })

  it('shares one fresh resource check across navigation copies without installing an available update', async () => {
    let finish
    axios.get.mockImplementationOnce(() => new Promise((resolve) => (finish = resolve)))
    const view = mountClock({ resourceVersion: '当前资源', enabled: true }, ClientChecks, 2)
    const buttons = () =>
      view.nodes().filter((node) => node.props.class?.split(' ').includes('sidebar-brand-resource'))
    buttons()[0].props.onClick()
    buttons()[1].props.onClick()
    await nextTick()
    expect(buttons().every((button) => button.props.disabled)).toBe(true)
    expect(messages.loading).toHaveBeenCalledOnce()
    expect(axios.get).toHaveBeenCalledOnce()
    finish({
      data: { update_available: true, remote_display: '新资源', current_display: '当前资源' }
    })
    await vi.advanceTimersByTimeAsync(0)
    expect(messages.warning).toHaveBeenCalledWith(
      expect.objectContaining({
        content: expect.any(Function),
        positiveText: '立即更新'
      })
    )
    const previewHtml = await renderToString(
      createSSRApp({
        render: messages.warning.mock.calls[0][0].content
      })
    )
    expect(previewHtml).toContain('新资源')
    expect(buttons().every((button) => !button.props.disabled)).toBe(true)
    expect(axios.post).not.toHaveBeenCalled()
  })

  it('starts a resource installation only after confirmation', async () => {
    axios.get.mockResolvedValue({
      data: {
        current_version: 'old',
        remote_version: 'new',
        remote_display: '新资源',
        update_available: true
      }
    })
    axios.post.mockResolvedValue({
      data: { ok: true, job: { id: 'resource-job', status: 'success' } }
    })
    const view = mountClock({ resourceVersion: '当前资源', enabled: true }, ClientChecks)
    await view.resourceButton().props.onClick()
    await vi.advanceTimersByTimeAsync(0)
    expect(axios.post).not.toHaveBeenCalled()
    const confirmation = messages.warning.mock.calls[0][0]
    expect(confirmation.positiveText).toBe('立即更新')
    await confirmation.onPositiveClick()
    expect(axios.post).toHaveBeenCalledExactlyOnceWith(
      expect.stringContaining('/resource/install'),
      { background: true }
    )
  })

  it('does not offer installation when the software check has blockers', async () => {
    axios.get.mockResolvedValue({
      data: {
        ok: true,
        settings: { channel: 'stable' },
        blockers: ['无法停止实例'],
        instances: [{}]
      }
    })
    axios.post.mockResolvedValue({ data: { ok: true, available: true, check_id: 'blocked' } })
    const view = mountClock({ version: '4.1.6', enabled: true }, ClientChecks)
    await view.button().props.onClick()
    await vi.advanceTimersByTimeAsync(0)
    expect(messages.warning).not.toHaveBeenCalled()
    expect(messages.error).toHaveBeenCalledWith('无法停止实例')
    expect(messages.installSoftware).not.toHaveBeenCalled()
  })

  it('reports software setting and check errors and reads saved settings again on retry', async () => {
    axios.get
      .mockResolvedValueOnce({ data: { ok: false, message: '更新设置读取失败' } })
      .mockResolvedValueOnce({ data: { ok: true, settings: { channel: 'dev' } } })
      .mockResolvedValueOnce({ data: { ok: true, settings: { channel: 'stable' } } })
    axios.post
      .mockResolvedValueOnce({ data: { ok: false, message: '代理连接失败' } })
      .mockResolvedValueOnce({ data: { ok: true, available: false } })
    const view = mountClock({ version: '4.1.6', enabled: true }, ClientChecks)
    view.button().props.onClick()
    await vi.advanceTimersByTimeAsync(0)
    expect(messages.error).toHaveBeenLastCalledWith('软件检查未完成：更新设置读取失败')
    expect(axios.post).not.toHaveBeenCalled()
    expect(view.button().props.disabled).toBe(false)
    view.button().props.onClick()
    await vi.advanceTimersByTimeAsync(0)
    expect(messages.error).toHaveBeenLastCalledWith('软件检查未完成：代理连接失败')
    expect(view.button().props.disabled).toBe(false)
    view.button().props.onClick()
    await vi.advanceTimersByTimeAsync(0)
    expect(messages.success).toHaveBeenCalledWith('软件已与所选渠道一致。')
    expect(axios.post.mock.calls.map(([, payload]) => payload)).toEqual([
      { channel: 'dev' },
      { channel: 'stable' }
    ])
    expect(messages.destroy).toHaveBeenCalledTimes(3)
  })

  it('keeps managed instances without update authorization from requesting checks', async () => {
    const view = mountClock(
      { version: '4.1.6', resourceVersion: '当前资源', enabled: false },
      ClientChecks
    )
    view.button().props.onClick()
    view.resourceButton().props.onClick()
    await vi.advanceTimersByTimeAsync(0)
    expect(axios.get).not.toHaveBeenCalled()
    expect(axios.post).not.toHaveBeenCalled()
    expect(messages.loading).not.toHaveBeenCalled()
  })

  it('runs one local clock while visible and removes it on collapse, expiry and unmount', async () => {
    const props = reactive({
      resourceVersion: '当前资源',
      resourceMetadata: metadata,
      collapsed: false
    })
    mountClock(props)
    expect(vi.getTimerCount()).toBe(1)
    props.collapsed = true
    await nextTick()
    expect(vi.getTimerCount()).toBe(0)
    props.collapsed = false
    await nextTick()
    expect(vi.getTimerCount()).toBe(1)
    vi.setSystemTime(new Date('2026-10-20T00:00:00+08:00'))
    await vi.advanceTimersByTimeAsync(60000)
    expect(vi.getTimerCount()).toBe(0)
    props.resourceMetadata = {
      activity: { ...metadata.activity, endTime: metadata.activity.endTime + 86400 }
    }
    await nextTick()
    expect(vi.getTimerCount()).toBe(1)
    mounted.unmount()
    mounted = null
    expect(vi.getTimerCount()).toBe(0)
  })

  it('does not run a clock when the installed metadata has no known interval', () => {
    mountClock({ resourceVersion: '当前资源', resourceMetadata: {} })
    expect(vi.getTimerCount()).toBe(0)
  })
})
