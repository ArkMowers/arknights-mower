import { readFileSync } from 'node:fs'
import { parse } from '@vue/compiler-sfc'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { compile, createRenderer, h, nextTick, reactive, ssrContextKey } from 'vue'
import { NDropdown } from 'naive-ui'
import AppMenuBar from './AppMenuBar.vue'

vi.mock('naive-ui', async () => {
  const { cloneVNode, defineComponent, h } = await import('vue')
  return {
    NDropdown: defineComponent({
      props: { show: Boolean, options: Array, menuProps: Function, nodeProps: Function },
      emits: ['update:show', 'select'],
      setup(props, { emit, slots }) {
        return () =>
          h(
            'dropdown-boundary',
            {
              'data-menu-label': props.menuProps()['aria-label'],
              show: props.show,
              options: props.options,
              menuProps: props.menuProps,
              nodeProps: props.nodeProps,
              onSelect: (key, option) => emit('select', key, option)
            },
            slots
              .default()
              .map((trigger) =>
                cloneVNode(trigger, { onClick: () => emit('update:show', !props.show) })
              )
          )
      }
    })
  }
})

const { descriptor } = parse(readFileSync(new URL('./AppMenuBar.vue', import.meta.url), 'utf8'))
const ClientMenuBar = {
  ...AppMenuBar,
  components: { NDropdown },
  ssrRender: undefined,
  render: compile(descriptor.template.content, { hoistStatic: false }),
  setup: (props, context) => ({ ...AppMenuBar.setup(props, context) })
}
const node = (tag) => ({ tag, props: {}, style: {}, children: [], parent: null, text: '' })
function remove(element) {
  if (!element.parent) return
  const siblings = element.parent.children
  siblings.splice(siblings.indexOf(element), 1)
  element.parent = null
}
const renderer = createRenderer({
  createElement: node,
  createText: (text) => ({ ...node('#text'), text }),
  createComment: () => node('#comment'),
  setText: (element, text) => (element.text = text),
  setElementText: (element, text) => (element.text = text),
  parentNode: (element) => element.parent,
  nextSibling: (element) => {
    const siblings = element.parent?.children || []
    return siblings[siblings.indexOf(element) + 1] || null
  },
  patchProp: (element, key, _oldValue, value) => (element.props[key] = value),
  insert(element, parent, anchor) {
    remove(element)
    element.parent = parent
    const index = anchor ? parent.children.indexOf(anchor) : -1
    parent.children.splice(index < 0 ? parent.children.length : index, 0, element)
  },
  remove
})
const all = (element) => [element, ...element.children.flatMap(all)]
const nativeCallbacks = ['onControl', 'onToggleMaximize', 'onResize', 'onMove', 'onToggle-sidebar']
let app
let windowCallbacks

afterEach(() => {
  app?.unmount()
  app = null
  vi.unstubAllGlobals()
  for (const callback of Object.values(windowCallbacks || {}))
    expect(callback).not.toHaveBeenCalled()
  windowCallbacks = null
})

function mount(overrides = {}) {
  vi.stubGlobal('window', new EventTarget())
  windowCallbacks = Object.fromEntries(nativeCallbacks.map((name) => [name, vi.fn()]))
  const connectionAction = vi.fn()
  const profileAction = vi.fn()
  const helpAction = vi.fn()
  const viewAction = vi.fn()
  const options = reactive({ ...overrides })
  const root = node('root')
  const componentProps = {
    active: true,
    title: 'Mower',
    instanceName: '主实例',
    mowerPort: '9010',
    theme: 'light',
    controlSide: 'end',
    maximized: false,
    controls: [],
    busy: {},
    resizable: false,
    showSidebarToggle: true,
    ...windowCallbacks,
    'onConnection-action': connectionAction,
    'onProfile-action': profileAction,
    'onHelp-action': helpAction,
    'onView-action': viewAction,
    ...overrides
  }
  app = renderer.createApp({
    setup: () => () => h(ClientMenuBar, { ...componentProps, ...options })
  })
  app.provide(ssrContextKey, { modules: new Set() })
  app.mount(root)

  function menu(label = '连接') {
    const boundary = all(root).find((element) => element.props['data-menu-label'] === label)
    expect(boundary).toBeTruthy()
    return boundary
  }

  async function toggle(label = '连接') {
    const trigger = all(menu(label)).find((element) => element.tag === 'button')
    trigger.props.onClick()
    await nextTick()
  }

  async function select(selected, label = '连接') {
    menu(label).props.onSelect(selected.key, selected)
    await nextTick()
  }

  return {
    root,
    menu,
    toggle,
    select,
    connectionAction,
    profileAction,
    viewAction,
    helpAction,
    options
  }
}

describe('WebUI Mower 菜单', () => {
  function branch(bar, label) {
    return bar.menu('Mower').props.options.find((option) => option.label === label)
  }

  it('用一个 Mower 按钮展开共用菜单，底部显示实例、设备和端口', async () => {
    const bar = mount({
      mode: 'brand',
      emulatorName: 'MuMu · 测试设备',
      adbPort: '16384'
    })
    expect(all(bar.root).filter((element) => element.tag === 'dropdown-boundary')).toHaveLength(1)
    const button = all(bar.root).find((element) => element.tag === 'button')
    expect(button.props['aria-label']).toBe('Mower 菜单')
    expect(button.props['aria-expanded']).toBe(false)
    await bar.toggle('Mower')
    expect(button.props['aria-expanded']).toBe(true)
    const options = bar.menu('Mower').props.options
    expect(options.filter((option) => option.children).map((option) => option.label)).toEqual([
      '连接',
      '档案',
      '视图',
      '帮助'
    ])
    expect(options.at(-2).type).toBe('divider')
    const identity = options.at(-1).render()
    expect(identity.props).toMatchObject({ role: 'note', 'aria-label': '当前实例和设备' })
    expect(identity.children.map((child) => child.children)).toEqual([
      '主实例',
      'MuMu · 测试设备',
      '服务端口 9010 · ADB 端口 16384'
    ])
    expect(bar.profileAction).not.toHaveBeenCalled()
  })

  it('无设备时显示明确说明，深色菜单仍使用同一菜单样式', () => {
    const bar = mount({ mode: 'brand', theme: 'dark' })
    expect(bar.menu('Mower').props.options.at(-1).render().children[1].children).toBe('未选择设备')
    expect(bar.menu('Mower').props.menuProps().class).toContainEqual({
      'window-titlebar__dropdown--dark': true
    })
  })

  it.each([
    ['连接', 'select-emulator', 'connectionAction', ['select']],
    ['连接', 'test-connection', 'connectionAction', ['test']],
    ['连接', 'connection-settings', 'connectionAction', ['settings']],
    ['档案', 'add-profile', 'profileAction', ['create', undefined]],
    ['档案', 'export-profile', 'profileAction', ['export', undefined]],
    ['视图', 'view-toggle-sidebar', 'viewAction', ['toggle-sidebar']],
    ['视图', 'view-edit-sidebar', 'viewAction', ['edit-sidebar']],
    ['帮助', 'help-feedback', 'helpAction', ['feedback']],
    ['帮助', 'help-documentation', 'helpAction', ['documentation']],
    ['帮助', 'help-changelog', 'helpAction', ['changelog']],
    ['帮助', 'help-about', 'helpAction', ['about']]
  ])('“%s”中的 %s 复用原有操作', async (label, key, callback, args) => {
    const bar = mount({
      mode: 'brand',
      profileWriteDisabled: false,
      profileReadDisabled: false
    })
    await bar.toggle('Mower')
    await bar.select(
      branch(bar, label).children.find((option) => option.commandKey === key),
      'Mower'
    )
    expect(bar[callback]).toHaveBeenCalledExactlyOnceWith(...args)
    expect(bar.menu('Mower').props.show).toBe(false)
  })

  it('hover 档案时刷新，键盘打开子菜单时也刷新', async () => {
    const bar = mount({ mode: 'brand' })
    await bar.toggle('Mower')
    const menu = bar.menu('Mower')
    const profile = branch(bar, '档案')
    menu.props.nodeProps(profile).onMouseenter()
    await nextTick()
    expect(bar.profileAction).toHaveBeenCalledExactlyOnceWith('refresh')
    menu.props.menuProps(profile).onVnodeMounted()
    expect(bar.profileAction).toHaveBeenCalledOnce()
    menu.props.menuProps(profile).onVnodeUnmounted()
    menu.props.menuProps(profile).onVnodeMounted()
    expect(bar.profileAction).toHaveBeenCalledTimes(2)
  })

  it('保留禁用状态并拒绝旧菜单事件，所有子菜单 key 唯一', async () => {
    const bar = mount({ mode: 'brand', connectionTestDisabled: true })
    await bar.toggle('Mower')
    const selected = branch(bar, '连接').children.find(
      (option) => option.commandKey === 'test-connection'
    )
    expect(selected.disabled).toBe(true)
    await bar.select({ ...selected, disabled: false }, 'Mower')
    expect(bar.connectionAction).not.toHaveBeenCalled()
    const flatten = (options) =>
      options.flatMap((option) => [option, ...flatten(option.children || [])])
    const keys = flatten(bar.menu('Mower').props.options).map((option) => option.key)
    expect(new Set(keys).size).toBe(keys.length)
  })

  it('可用键盘打开与关闭，停用或切换模式时关闭并忽略旧选择事件', async () => {
    const bar = mount({ mode: 'brand' })
    const button = all(bar.root).find((element) => element.tag === 'button')
    const keydown = async (key) => {
      for (const handler of [].concat(button.props.onKeydown))
        handler({ key, preventDefault: vi.fn(), stopPropagation: vi.fn() })
      await nextTick()
    }
    await keydown('ArrowDown')
    expect(bar.menu('Mower').props.show).toBe(true)
    await keydown('Escape')
    expect(bar.menu('Mower').props.show).toBe(false)
    await keydown('ArrowDown')
    await keydown('Tab')
    expect(bar.menu('Mower').props.show).toBe(false)
    await keydown('ArrowDown')
    const feedback = branch(bar, '帮助').children.find(
      (option) => option.commandKey === 'help-feedback'
    )
    bar.options.active = false
    await nextTick()
    expect(bar.menu('Mower').props.show).toBe(false)
    await bar.select(feedback, 'Mower')
    expect(bar.helpAction).not.toHaveBeenCalled()
    bar.options.active = true
    await nextTick()
    await keydown('ArrowDown')
    bar.options.mode = 'bar'
    await nextTick()
    expect(
      all(bar.root)
        .filter((element) => element.tag === 'dropdown-boundary')
        .every((element) => !element.props.show)
    ).toBe(true)
  })
})

describe('共用视图菜单', () => {
  it.each([true, false])('分派侧栏显隐和编辑操作，可见=%s', async (sidebarVisible) => {
    const bar = mount({ sidebarVisible })
    await bar.toggle('视图')
    const options = bar.menu('视图').props.options
    expect(options.map((item) => item.label)).toEqual([
      sidebarVisible ? '隐藏侧边栏' : '显示侧边栏',
      '编辑侧边栏'
    ])
    await bar.select(options[0], '视图')
    expect(bar.viewAction).toHaveBeenCalledExactlyOnceWith('toggle-sidebar')
    expect(bar.menu('视图').props.show).toBe(false)
    await bar.toggle('视图')
    await bar.select(options[1], '视图')
    expect(bar.viewAction).toHaveBeenLastCalledWith('edit-sidebar')
    expect(bar.connectionAction).not.toHaveBeenCalled()
    expect(bar.profileAction).not.toHaveBeenCalled()
    expect(bar.helpAction).not.toHaveBeenCalled()
  })
})

describe('共用帮助菜单', () => {
  it.each([
    ['反馈问题', 'feedback'],
    ['文档', 'documentation'],
    ['更新日志', 'changelog'],
    ['关于', 'about']
  ])('分派“%s”', async (label, action) => {
    const bar = mount()
    await bar.toggle('帮助')
    const selected = bar.menu('帮助').props.options.find((item) => item.label === label)

    await bar.select(selected, '帮助')

    expect(bar.helpAction).toHaveBeenCalledExactlyOnceWith(action)
    expect(bar.menu('帮助').props.show).toBe(false)
    expect(bar.connectionAction).not.toHaveBeenCalled()
    expect(bar.profileAction).not.toHaveBeenCalled()
  })

  it('仅保留连接、档案、视图和帮助入口', async () => {
    const bar = mount({})
    expect(
      all(bar.root)
        .filter((element) => element.tag === 'dropdown-boundary')
        .map((element) => element.props['data-menu-label'])
    ).toEqual(['连接', '档案', '视图', '帮助'])

    await bar.toggle('档案')
    expect(bar.profileAction).toHaveBeenCalledExactlyOnceWith('refresh')
    await bar.toggle('连接')
    await bar.select(
      bar.menu('连接').props.options.find((item) => item.key === 'connection-settings'),
      '连接'
    )
    expect(bar.connectionAction).toHaveBeenCalledExactlyOnceWith('settings')
    await bar.toggle('帮助')
    await bar.select(
      bar.menu('帮助').props.options.find((item) => item.key === 'help-feedback'),
      '帮助'
    )
    expect(bar.helpAction).toHaveBeenCalledExactlyOnceWith('feedback')
  })

  it('按当前菜单处理左右方向键', async () => {
    const labels = ['连接', '档案', '视图', '帮助']
    const bar = mount()
    const menu = all(bar.root).find((element) => element.tag === 'nav')
    const buttons = all(bar.root).filter((element) => element.tag === 'button')
    for (const button of buttons) button.focus = vi.fn()
    menu.querySelectorAll = () => buttons
    const help = buttons.at(-1)
    const handlers = [].concat(help.props.onKeydown)
    for (const handler of handlers)
      handler({ key: 'ArrowRight', preventDefault: vi.fn(), stopPropagation: vi.fn() })
    expect(buttons[0].focus).toHaveBeenCalledOnce()
    expect(buttons).toHaveLength(labels.length)

    await bar.toggle('帮助')
    const settings = buttons.at(-2)
    for (const handler of [].concat(settings.props.onKeydown))
      handler({ key: 'ArrowRight', preventDefault: vi.fn(), stopPropagation: vi.fn() })
    await nextTick()
    expect(help.focus).toHaveBeenCalledOnce()
    expect(bar.menu('帮助').props.show).toBe(true)
  })
})

describe('共用档案菜单', () => {
  const profileState = {
    active_id: 'first',
    profiles: [
      { id: 'first', name: '主账号' },
      { id: 'second', name: '备用账号' }
    ]
  }
  it('shows named profiles, refreshes on opening and switches profiles', async () => {
    const bar = mount({ profileState, profileWriteDisabled: false, profileReadDisabled: false })
    await bar.toggle('档案')
    expect(bar.profileAction).toHaveBeenCalledExactlyOnceWith('refresh')
    const options = bar.menu('档案').props.options
    expect(options.find((item) => item.profileId === 'first')).toMatchObject({
      checked: true,
      disabled: true
    })
    const second = options.find((item) => item.profileId === 'second')
    expect(second).toMatchObject({ checked: false, disabled: false })
    bar.profileAction.mockClear()
    await bar.select(second, '档案')
    expect(bar.profileAction).toHaveBeenCalledExactlyOnceWith('activate', 'second')
    expect(bar.menu('档案').props.show).toBe(false)
  })

  it.each([
    ['add-profile', 'create'],
    ['copy-profile', 'copy'],
    ['rename-profile', 'rename'],
    ['import-profile', 'import'],
    ['export-profile', 'export'],
    ['reload-profiles', 'refresh']
  ])('dispatches %s', async (key, action) => {
    const bar = mount({ profileState, profileWriteDisabled: false, profileReadDisabled: false })
    const option = bar.menu('档案').props.options.find((item) => item.key === key)
    await bar.select(option, '档案')
    expect(bar.profileAction).toHaveBeenCalledExactlyOnceWith(action, undefined)
  })

  it('rejects disabled and forged stale write events while preserving read-only export', async () => {
    const bar = mount({ profileState, profileWriteDisabled: true, profileReadDisabled: false })
    for (const option of bar.menu('档案').props.options.filter((item) => item.disabled)) {
      await bar.select(option, '档案')
      await bar.select({ ...option, disabled: false }, '档案')
    }
    expect(bar.profileAction).not.toHaveBeenCalled()
    await bar.select(
      bar.menu('档案').props.options.find((item) => item.key === 'export-profile'),
      '档案'
    )
    expect(bar.profileAction).toHaveBeenCalledExactlyOnceWith('export', undefined)
  })
})

describe('标题栏连接菜单', () => {
  it.each([
    ['选择模拟器…', 'select'],
    ['测试连接', 'test'],
    ['连接设置…', 'settings']
  ])('“%s”分派连接操作', async (label, action) => {
    const bar = mount()
    await bar.toggle('连接')
    const selected = bar.menu('连接').props.options.find((item) => item.label === label)
    expect(selected.disabled).not.toBe(true)

    await bar.select(selected, '连接')

    expect(bar.connectionAction).toHaveBeenCalledExactlyOnceWith(action)
    expect(bar.menu('连接').props.show).toBe(false)
  })

  it('锁定时禁用测试并拒绝旧菜单事件，仍可查看设备设置', async () => {
    const bar = mount({ connectionTestDisabled: true })
    const options = bar.menu('连接').props.options
    const test = options.find((item) => item.key === 'test-connection')
    expect(test.disabled).toBe(true)
    await bar.select(test, '连接')
    await bar.select({ ...test, disabled: false }, '连接')
    expect(bar.connectionAction).not.toHaveBeenCalled()

    await bar.select(
      options.find((item) => item.key === 'connection-settings'),
      '连接'
    )
    expect(bar.connectionAction).toHaveBeenCalledExactlyOnceWith('settings')
  })
})
