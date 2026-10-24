import { readFileSync } from 'node:fs'
import { parse } from '@vue/compiler-sfc'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { compile, createRenderer, h, nextTick, provide, reactive, ref, ssrContextKey } from 'vue'
import { NDropdown } from 'naive-ui'
import NativeDropdown from 'naive-ui/es/dropdown/src/Dropdown.mjs'
import NativeDropdownOption from 'naive-ui/es/dropdown/src/DropdownOption.mjs'
import { dropdownMenuInjectionKey } from 'naive-ui/es/dropdown/src/context.mjs'
import { popoverBodyInjectionKey } from 'naive-ui/es/popover/src/interface.mjs'
import MowerManager from '../../manager/MowerManager.vue'
import AppMenuBar from './AppMenuBar.vue'

const state = vi.hoisted(() => ({ manager: null, managerProps: null, mounts: 0 }))

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

vi.mock('../../manager/MowerManager.vue', async () => {
  const { defineComponent, h } = await import('vue')
  return {
    default: defineComponent({
      props: { embedded: Boolean, active: Boolean },
      setup(props, { expose }) {
        state.mounts += 1
        state.managerProps = props
        expose(state.manager)
        return () => h('manager-boundary', { embedded: props.embedded, active: props.active })
      }
    })
  }
})

const { descriptor } = parse(readFileSync(new URL('./AppMenuBar.vue', import.meta.url), 'utf8'))
const ClientMenuBar = {
  ...AppMenuBar,
  components: { NDropdown, MowerManager },
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
const commands = [
  'initialize',
  'addInstance',
  'edit',
  'editBatch',
  'selectPath',
  'confirmBulk',
  'lifecycle',
  'confirmDelete'
]
const nativeCallbacks = ['onControl', 'onToggleMaximize', 'onResize', 'onMove', 'onToggle-sidebar']
let app
let nativeDropdownApp
let windowCallbacks

beforeEach(() => {
  state.mounts = 0
  state.managerProps = null
  state.manager = reactive({
    instances: [
      {
        name: '主实例',
        path: 'D:/profiles/main',
        state: 'running',
        editable: false,
        can_start: false,
        can_stop: true
      },
      {
        name: '第二实例',
        path: 'D:/profiles/second',
        state: 'stopped',
        editable: true,
        can_start: true,
        can_stop: false
      },
      {
        name: '待配置',
        path: '',
        state: 'stopped',
        editable: true,
        can_start: false,
        can_stop: false
      }
    ],
    ready: true,
    connected: true,
    busy: false,
    loading: false,
    get unavailable() {
      return !this.ready || !this.connected || this.busy || this.loading
    },
    hasDialog: false,
    initializationError: '',
    ...Object.fromEntries(commands.map((command) => [command, vi.fn()]))
  })
})

afterEach(() => {
  app?.unmount()
  nativeDropdownApp?.unmount()
  app = null
  nativeDropdownApp = null
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

  function menu(label = '实例') {
    const boundary = all(root).find((element) => element.props['data-menu-label'] === label)
    expect(boundary).toBeTruthy()
    return boundary
  }

  async function toggle(label = '实例') {
    const trigger = all(menu(label)).find((element) => element.tag === 'button')
    trigger.props.onClick()
    await nextTick()
  }

  function option(label, instance) {
    const options = instance
      ? menu().props.options.find((row) => row.accessibleLabel === instance)?.children
      : menu().props.options
    const found = options?.find((item) => item.label === label)
    expect(found).toBeTruthy()
    return found
  }

  async function select(selected, label = '实例') {
    menu(label).props.onSelect(selected.key, selected)
    await nextTick()
  }

  return {
    root,
    menu,
    toggle,
    option,
    select,
    connectionAction,
    profileAction,
    viewAction,
    helpAction,
    options
  }
}

function expectOnlyCommand(command, args) {
  for (const name of commands) {
    if (name === command) {
      expect(state.manager[name]).toHaveBeenCalledExactlyOnceWith(...args)
    } else expect(state.manager[name]).not.toHaveBeenCalled()
  }
}

describe('WebUI Mower 菜单', () => {
  function branch(bar, label) {
    return bar.menu('Mower').props.options.find((option) => option.label === label)
  }

  it('用一个 Mower 按钮展开共用菜单，底部显示实例、设备和端口', async () => {
    const bar = mount({
      mode: 'brand',
      showInstanceMenu: false,
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
    expect(state.mounts).toBe(0)
    expect(bar.profileAction).not.toHaveBeenCalled()
  })

  it('无设备时显示明确说明，深色菜单仍使用同一菜单样式', () => {
    const bar = mount({ mode: 'brand', showInstanceMenu: false, theme: 'dark' })
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
      showInstanceMenu: false,
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
    expect(state.mounts).toBe(0)
    expectOnlyCommand()
  })

  it('hover 档案时刷新，键盘打开子菜单时也刷新，实例仍延迟挂载', async () => {
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
    expect(state.mounts).toBe(0)

    menu.props.nodeProps(branch(bar, '实例')).onMouseenter()
    await nextTick()
    expect(state.mounts).toBe(1)
    expect(state.managerProps.active).toBe(true)
    menu.props.menuProps(branch(bar, '实例')).onVnodeUnmounted()
    await nextTick()
    expect(state.managerProps.active).toBe(false)
    menu.props.menuProps(branch(bar, '实例')).onVnodeMounted()
    await nextTick()
    expect(state.mounts).toBe(1)
    expect(state.manager.initialize).toHaveBeenCalledOnce()
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
    expectOnlyCommand()
  })

  it('可用键盘打开与关闭，停用或切换模式时关闭并忽略旧选择事件', async () => {
    const bar = mount({ mode: 'brand', showInstanceMenu: false })
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
    const bar = mount({ sidebarVisible, showInstanceMenu: false })
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
    expect(state.mounts).toBe(0)
    expectOnlyCommand()
  })
})

describe('共用帮助菜单', () => {
  it.each([
    ['反馈问题', 'feedback'],
    ['文档', 'documentation'],
    ['更新日志', 'changelog'],
    ['关于', 'about']
  ])('分派“%s”且不加载实例管理器', async (label, action) => {
    const bar = mount()
    await bar.toggle('帮助')
    const selected = bar.menu('帮助').props.options.find((item) => item.label === label)

    await bar.select(selected, '帮助')

    expect(bar.helpAction).toHaveBeenCalledExactlyOnceWith(action)
    expect(bar.menu('帮助').props.show).toBe(false)
    expect(bar.connectionAction).not.toHaveBeenCalled()
    expect(bar.profileAction).not.toHaveBeenCalled()
    expect(state.mounts).toBe(0)
    expectOnlyCommand()
  })

  it('无实例管理能力时保留连接、档案、视图和帮助入口', async () => {
    const bar = mount({ showInstanceMenu: false })
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
    expect(state.mounts).toBe(0)
    expectOnlyCommand()
  })

  it.each([
    [true, ['实例', '连接', '档案', '视图', '帮助']],
    [false, ['连接', '档案', '视图', '帮助']]
  ])('按当前可见菜单处理左右方向键，实例入口可见=%s', async (showInstanceMenu, labels) => {
    const bar = mount({ showInstanceMenu })
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
    expectOnlyCommand()
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
  it('shows named profiles, refreshes on opening and switches without mounting the instance manager', async () => {
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
    expect(state.mounts).toBe(0)
    expectOnlyCommand()
  })

  it.each([
    ['add-profile', 'create'],
    ['copy-profile', 'copy'],
    ['rename-profile', 'rename'],
    ['import-profile', 'import'],
    ['export-profile', 'export'],
    ['reload-profiles', 'refresh']
  ])('dispatches %s before the instance manager guard', async (key, action) => {
    const bar = mount({ profileState, profileWriteDisabled: false, profileReadDisabled: false })
    const option = bar.menu('档案').props.options.find((item) => item.key === key)
    await bar.select(option, '档案')
    expect(bar.profileAction).toHaveBeenCalledExactlyOnceWith(action, undefined)
    expect(state.mounts).toBe(0)
    expectOnlyCommand()
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
  ])('未打开实例菜单时“%s”仍分派连接操作', async (label, action) => {
    const bar = mount()
    await bar.toggle('连接')
    const selected = bar.menu('连接').props.options.find((item) => item.label === label)
    expect(selected.disabled).not.toBe(true)

    await bar.select(selected, '连接')

    expect(bar.connectionAction).toHaveBeenCalledExactlyOnceWith(action)
    expect(bar.menu('连接').props.show).toBe(false)
    expect(state.mounts).toBe(0)
    expectOnlyCommand()
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
    expectOnlyCommand()
  })
})

describe('标题栏实例菜单', () => {
  it.each([
    ['保存目录说明', true],
    ['菜单留白', false]
  ])('鼠标从实例移到二级菜单的%s时保持二级菜单打开', async (_label, nested) => {
    const bar = mount()
    await bar.toggle()
    const instance = bar
      .menu()
      .props.options.find((item) => item.accessibleLabel === '第二实例，已停止')
    const submenuProps = bar.menu().props.menuProps(instance)
    const submenu = {
      dataset: 'data-dropdown-option' in submenuProps ? { dropdownOption: true } : {},
      parentElement: null
    }
    const destination = nested ? { dataset: {}, parentElement: submenu } : submenu
    const NativeOptionEvents = {
      ...NativeDropdownOption,
      render() {
        return h('native-option', {
          expanded: this.mergedShowSubmenu,
          onMouseenter: this.handleMouseEnter,
          onMouseleave: this.handleMouseLeave
        })
      }
    }
    const NativeMenu = {
      setup() {
        provide(dropdownMenuInjectionKey, {
          showIconRef: ref(false),
          hasSubmenuRef: ref(true)
        })
        provide(popoverBodyInjectionKey, ref(null))
        return () => h(NativeOptionEvents, { clsPrefix: 'n', tmNode: instanceNode })
      }
    }
    let instanceNode
    const NativeMenuState = {
      ...NativeDropdown,
      render() {
        instanceNode = this.tmNodes[0]
        return h(NativeMenu)
      }
    }
    const nativeRoot = node('root')
    nativeDropdownApp = renderer.createApp(NativeMenuState, {
      show: true,
      options: [instance],
      keyboard: false,
      animated: true
    })
    nativeDropdownApp.provide(ssrContextKey, { modules: new Set() })
    nativeDropdownApp.provide('@css-render/vue3-ssr', { styles: [], ids: new Set() })
    nativeDropdownApp.mount(nativeRoot)
    const option = all(nativeRoot).find((element) => element.tag === 'native-option')
    option.props.onMouseenter()
    await nextTick()
    expect(option.props.expanded).toBe(true)

    option.props.onMouseleave({ relatedTarget: destination })
    await nextTick()

    expect(option.props.expanded).toBe(true)
    expect(bar.menu().props.show).toBe(true)
    expectOnlyCommand()

    option.props.onMouseleave({ relatedTarget: { dataset: {}, parentElement: null } })
    await nextTick()
    expect(option.props.expanded).toBe(false)
  })

  it('只在首次打开实例菜单时挂载管理器，再次打开时刷新并复用管理器', async () => {
    const bar = mount()
    expect(state.mounts).toBe(0)
    await bar.toggle('连接')
    await bar.toggle('档案')
    expect(state.mounts).toBe(0)

    await bar.toggle()
    expect(state.mounts).toBe(1)
    expect(state.managerProps.embedded).toBe(true)
    expect(state.managerProps.active).toBe(true)
    expect(
      bar
        .menu()
        .props.options.filter((item) => item.children)
        .map((item) => item.accessibleLabel)
    ).toEqual(['主实例，运行中', '第二实例，已停止', '待配置，已停止'])

    await bar.toggle()
    expect(state.managerProps.active).toBe(false)
    await bar.toggle()
    expect(state.mounts).toBe(1)
    expect(state.manager.initialize).toHaveBeenCalledOnce()
    expect(state.managerProps.active).toBe(true)
  })

  it.each([
    ['第二实例，已停止', '启动实例', 'lifecycle', [1]],
    ['主实例，运行中', '停止实例', 'lifecycle', [0]],
    ['第二实例，已停止', '重命名实例…', 'edit', [1, 'name']],
    ['第二实例，已停止', '实例配置…', 'edit', [1, 'settings']],
    ['第二实例，已停止', '选择保存目录…', 'selectPath', [1]],
    ['第二实例，已停止', '删除实例…', 'confirmDelete', [1]]
  ])('%s 的“%s”交给管理器操作对应实例', async (instance, label, command, args) => {
    const bar = mount()
    await bar.toggle()
    const selected = bar.option(label, instance)
    expect(selected.disabled).toBe(false)

    await bar.select(selected)

    expectOnlyCommand(command, args)
    expect(bar.menu().props.show).toBe(false)
  })

  it.each([
    ['添加实例', 'addInstance', []],
    ['批量配置…', 'editBatch', []],
    ['全部打开…', 'confirmBulk', ['start']],
    ['全部关闭…', 'confirmBulk', ['stop']],
    ['刷新实例列表', 'initialize', []]
  ])('“%s”使用管理器已有操作或确认入口', async (label, command, args) => {
    const bar = mount()
    await bar.toggle()
    const selected = bar.option(label)
    expect(selected.disabled).toBe(false)

    await bar.select(selected)

    expectOnlyCommand(command, args)
    expect(bar.menu().props.show).toBe(false)
  })

  it('管理对话框打开时保留管理器活动状态，关闭后暂停', async () => {
    const bar = mount()
    await bar.toggle()
    state.manager.hasDialog = true
    await bar.select(bar.option('重命名实例…', '第二实例，已停止'))
    expect(bar.menu().props.show).toBe(false)
    expect(state.managerProps.active).toBe(true)

    state.manager.hasDialog = false
    await nextTick()
    expect(state.managerProps.active).toBe(false)
  })

  it('禁用的实例操作即使触发选择事件也不执行', async () => {
    const bar = mount()
    await bar.toggle()
    const disabled = [
      bar.option('重命名实例…', '主实例，运行中'),
      bar.option('实例配置…', '主实例，运行中'),
      bar.option('选择保存目录…', '主实例，运行中'),
      bar.option('删除实例…', '主实例，运行中'),
      bar.option('实例配置…', '待配置，已停止'),
      bar.option('启动实例', '待配置，已停止')
    ]

    for (const selected of disabled) {
      expect(selected.disabled).toBe(true)
      await bar.select(selected)
    }

    expectOnlyCommand()
  })

  it('没有可操作实例时禁用批量入口，仍允许添加实例', async () => {
    state.manager.instances = [state.manager.instances[2]]
    const bar = mount()
    await bar.toggle()
    for (const label of ['批量配置…', '全部打开…', '全部关闭…']) {
      const selected = bar.option(label)
      expect(selected.disabled).toBe(true)
      await bar.select(selected)
    }
    expect(bar.option('添加实例').disabled).toBe(false)
    expectOnlyCommand()
  })

  it.each([
    ['ready', false],
    ['connected', false],
    ['busy', true],
    ['loading', true]
  ])('管理器 %s=%s 时拒绝之前仍可用的菜单项', async (field, value) => {
    const bar = mount()
    await bar.toggle()
    const pending = [
      bar.option('重命名实例…', '第二实例，已停止'),
      bar.option('启动实例', '第二实例，已停止'),
      bar.option('添加实例'),
      bar.option('批量配置…'),
      bar.option('全部打开…'),
      bar.option('全部关闭…')
    ]
    state.manager[field] = value
    await nextTick()

    for (const selected of pending) await bar.select(selected)

    expect(state.manager.unavailable).toBe(true)
    expectOnlyCommand()
  })

  it('正在刷新时禁用重新加载，初始化失败后允许从菜单重试', async () => {
    state.manager.ready = false
    state.manager.connected = false
    state.manager.loading = true
    const bar = mount()
    await bar.toggle()
    const reload = bar.option('刷新实例列表')
    expect(reload.disabled).toBe(true)
    expect(bar.option('正在加载实例…').disabled).toBe(true)
    await bar.select(reload)
    expectOnlyCommand()

    state.manager.loading = false
    state.manager.initializationError = '读取失败'
    await nextTick()
    expect(bar.option('无法加载实例列表').disabled).toBe(true)
    const retry = bar.option('刷新实例列表')
    expect(retry.disabled).toBe(false)
    await bar.select(retry)
    expectOnlyCommand('initialize', [])
  })

  it.each(['名称变化', '目录变化', '实例移除'])('%s 后旧菜单只刷新列表', async (change) => {
    const bar = mount()
    await bar.toggle()
    const stale = bar.option('删除实例…', '第二实例，已停止')
    const original = state.manager.instances[1]
    if (change === '名称变化') {
      state.manager.instances[1] = { ...original, name: '替换实例' }
    } else if (change === '目录变化') {
      state.manager.instances[1] = { ...original, path: 'D:/profiles/replacement' }
    } else state.manager.instances.splice(1, 1)
    await nextTick()

    await bar.select(stale)

    expectOnlyCommand('initialize', [])
    expect(bar.menu().props.show).toBe(false)
  })
})
