import { readFileSync } from 'node:fs'
import { parse } from '@vue/compiler-sfc'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { compile, createRenderer, h, ssrContextKey } from 'vue'
import AppMenuBar from './AppMenuBar.vue'
import WindowTitlebar from './WindowTitlebar.vue'

const menuDescriptor = parse(
  readFileSync(new URL('./AppMenuBar.vue', import.meta.url), 'utf8')
).descriptor
const ClientMenuBar = {
  ...AppMenuBar,
  ssrRender: undefined,
  render: compile(menuDescriptor.template.content, { hoistStatic: false }),
  setup: (props, context) => ({ ...AppMenuBar.setup(props, context) })
}
const { descriptor } = parse(readFileSync(new URL('./WindowTitlebar.vue', import.meta.url), 'utf8'))
const ClientTitlebar = {
  ...WindowTitlebar,
  components: { AppMenuBar: ClientMenuBar },
  ssrRender: undefined,
  render: compile(descriptor.template.content, { hoistStatic: false }),
  setup: (props, context) => ({ ...WindowTitlebar.setup(props, context) })
}
const node = (tag) => ({ tag, props: {}, style: {}, children: [], parent: null })
const renderer = createRenderer({
  createElement: node,
  createText: (text) => ({ ...node('#text'), text }),
  createComment: () => node('#comment'),
  setText: (element, text) => (element.text = text),
  setElementText: (element, text) => (element.text = text),
  parentNode: (element) => element.parent,
  nextSibling: () => null,
  patchProp: (element, key, _oldValue, value) => (element.props[key] = value),
  insert(element, parent) {
    element.parent = parent
    parent.children.push(element)
  },
  remove: () => {}
})
let app

function mount(overrides = {}, menuComponent = ClientMenuBar) {
  vi.stubGlobal('window', new EventTarget())
  const props = {
    active: true,
    title: 'Mower',
    instanceName: 'Mower',
    theme: 'light',
    controlSide: 'end',
    maximized: false,
    controls: [],
    busy: {},
    resizable: false,
    onControl: vi.fn(),
    onToggleMaximize: vi.fn(),
    onResize: vi.fn(),
    onMove: vi.fn(),
    showSidebarToggle: true,
    sidebarCollapsed: false,
    'onToggle-sidebar': vi.fn(),
    ...overrides
  }
  const root = node('root')
  app = renderer.createApp({ ...ClientTitlebar, components: { AppMenuBar: menuComponent } }, props)
  app.provide(ssrContextKey, { modules: new Set() })
  app.mount(root)
  const all = (element) => [element, ...element.children.flatMap(all)]
  return { props, nodes: all(root) }
}

function dispatch(element, type, details = {}) {
  const event = {
    button: 0,
    screenX: 100,
    screenY: 100,
    ...details,
    preventDefault: vi.fn(),
    stopPropagation: vi.fn()
  }
  for (let target = element; target; target = target.parent) {
    target.props[type]?.(event)
    if (event.stopPropagation.mock.calls.length) break
  }
}

function movePointer() {
  window.dispatchEvent(
    Object.assign(new Event('mousemove'), { buttons: 1, screenX: 120, screenY: 100 })
  )
}

afterEach(() => {
  app?.unmount()
  app = null
  vi.unstubAllGlobals()
})

describe('desktop title bar controls', () => {
  it('leaves the Cocoa traffic lights outside draggable HTML and omits duplicate window buttons', () => {
    const { nodes } = mount({
      nativeControls: true,
      controls: ['minimize', 'maximize', 'close'].map((id) => ({ id, icon: id, label: id }))
    })
    const header = nodes.find((element) => 'data-window-shell' in element.props)
    expect(header.props.class).toContain('window-titlebar--native-controls')
    expect(
      nodes.findIndex((element) => element.props.class === 'window-titlebar__native-controls')
    ).toBeLessThan(nodes.findIndex((element) => 'data-window-drag-region' in element.props))
    expect(nodes.filter((element) => element.props['data-window-control'])).toEqual([])
    expect(nodes.some((element) => element.props['aria-controls'] === 'sidebar-navigation')).toBe(
      true
    )
    expect(nodes.filter((element) => element.props['aria-haspopup'] === 'menu')).toHaveLength(4)
  })

  it('keeps the three HTML window controls for GTK, Qt and WinForms', () => {
    const { nodes } = mount({
      nativeControls: false,
      controls: ['minimize', 'maximize', 'close'].map((id) => ({ id, icon: id, label: id }))
    })
    const header = nodes.find((element) => 'data-window-shell' in element.props)
    expect(header.props.class).not.toContain('window-titlebar--native-controls')
    expect(
      nodes.some((element) => element.props.class === 'window-titlebar__native-controls')
    ).toBe(false)
    expect(nodes.filter((element) => element.props['data-window-control'])).toHaveLength(3)
    expect(nodes.some((element) => element.props['data-window-control'] === 'close')).toBe(true)
    expect(nodes.some((element) => element.props['aria-controls'] === 'sidebar-navigation')).toBe(
      true
    )
    expect(nodes.filter((element) => element.props['aria-haspopup'] === 'menu')).toHaveLength(4)
  })

  it('keeps Cocoa controls before the logo and leaves application buttons outside native drag regions', () => {
    const { nodes } = mount({
      nativeControls: true,
      nativeInteractions: true,
      controlSide: 'start'
    })
    const header = nodes.find((element) => 'data-window-shell' in element.props)
    const reservation = nodes.find(
      (element) => element.props.class === 'window-titlebar__native-controls'
    )
    const logo = nodes.find((element) => element.props.class === 'window-titlebar__brand')
    const toggle = nodes.find((element) => element.props['aria-controls'] === 'sidebar-navigation')
    const menus = nodes.find((element) => element.tag === 'nav')

    expect(header.children.indexOf(reservation)).toBeLessThan(header.children.indexOf(logo))
    expect(header.children.indexOf(logo)).toBeLessThan(header.children.indexOf(toggle))
    expect(header.children.indexOf(toggle)).toBeLessThan(header.children.indexOf(menus))
    expect(reservation.props['data-window-controls']).toBeDefined()
    expect(reservation.props['data-window-drag-region']).toBeUndefined()
    for (const button of nodes.filter((element) => element.tag === 'button')) {
      for (let target = button; target; target = target.parent) {
        expect(target.props['data-window-drag-region']).toBeUndefined()
      }
    }
    expect(nodes.filter((element) => element.props['data-window-control'])).toEqual([])
  })

  it.each(['window-titlebar__brand', 'window-titlebar__drag-region'])(
    'leaves gestures on %s to the native input handler',
    (className) => {
      const { nodes, props } = mount({ nativeControls: true, nativeInteractions: true })
      const caption = nodes.find((element) => element.props.class === className)
      dispatch(caption, 'onMousedown')
      movePointer()
      dispatch(caption, 'onDblclick')
      expect(props.onMove).not.toHaveBeenCalled()
      expect(props.onToggleMaximize).not.toHaveBeenCalled()
    }
  )

  it.each([false, true])(
    'delegates HTML resize grips only without native interactions: %s',
    (nativeInteractions) => {
      const { nodes, props } = mount({ nativeInteractions, resizable: true })
      const grip = nodes.find((element) => element.props['data-window-resize-edge'] === 'top-left')
      dispatch(grip, 'onMousedown')
      if (nativeInteractions) expect(props.onResize).not.toHaveBeenCalled()
      else expect(props.onResize).toHaveBeenCalledExactlyOnceWith('top-left')
    }
  )
})

describe('native titlebar sidebar control', () => {
  it.each([
    ['connection-action', ['settings']],
    ['profile-action', ['activate', 'second']],
    ['view-action', ['edit-sidebar']],
    ['help-action', ['feedback']]
  ])('forwards the shared %s action without invoking window controls', (event, args) => {
    const selected = vi.fn()
    const MenuAction = {
      emits: ['connection-action', 'profile-action', 'view-action', 'help-action'],
      setup(_props, { emit }) {
        return () => h('button', { 'aria-label': '菜单操作', onClick: () => emit(event, ...args) })
      }
    }
    const { nodes, props } = mount(
      { [`on${event[0].toUpperCase()}${event.slice(1)}`]: selected },
      MenuAction
    )

    dispatch(
      nodes.find((element) => element.props['aria-label'] === '菜单操作'),
      'onClick'
    )

    expect(selected).toHaveBeenCalledExactlyOnceWith(...args)
    expect(props.onMove).not.toHaveBeenCalled()
    expect(props.onToggleMaximize).not.toHaveBeenCalled()
    expect(props.onControl).not.toHaveBeenCalled()
  })

  it('places the decorative logo before the sidebar control and menus', () => {
    const { nodes } = mount()
    const header = nodes.find((element) => 'data-window-shell' in element.props)
    const logo = nodes.find(
      (element) => element.tag === 'img' && element.props.src === '/favicon.ico'
    )
    const toggle = nodes.find((element) => element.props['aria-controls'] === 'sidebar-navigation')
    const menus = nodes.find((element) => element.props['aria-label'] === '连接、档案、视图和帮助')
    expect(logo).toBeTruthy()
    expect(logo.props.draggable).toBe('false')
    expect(logo.parent.props['aria-hidden']).toBe('true')
    expect(logo.parent.props.onClick).toBeUndefined()
    expect(header.children.indexOf(logo.parent)).toBeLessThan(header.children.indexOf(toggle))
    expect(header.children.indexOf(toggle)).toBeLessThan(header.children.indexOf(menus))
  })

  it.each([
    [false, '收起侧边栏', true],
    [true, '展开侧边栏', false]
  ])('announces and toggles the sidebar when collapsed=%s', (collapsed, label, expanded) => {
    const { nodes, props } = mount({ sidebarCollapsed: collapsed })
    const button = nodes.find((element) => element.props['aria-label'] === label)
    expect(button).toBeTruthy()
    expect(button.props['aria-expanded']).toBe(expanded)
    expect(button.props['aria-controls']).toBe('sidebar-navigation')

    dispatch(button, 'onMousedown')
    movePointer()
    dispatch(button, 'onClick')
    dispatch(button, 'onDblclick')
    expect(props['onToggle-sidebar']).toHaveBeenCalledOnce()
    expect(props.onMove).not.toHaveBeenCalled()
    expect(props.onToggleMaximize).not.toHaveBeenCalled()
  })

  it('omits the desktop sidebar control when it is unavailable', () => {
    const { nodes } = mount({ showSidebarToggle: false })
    expect(
      nodes.filter((element) => element.props['aria-controls'] === 'sidebar-navigation')
    ).toEqual([])
  })

  it.each(['连接', '档案', '视图', '帮助'])(
    'keeps the %s menu separate from native window actions',
    (label) => {
      const { nodes, props } = mount()
      const button = nodes.find(
        (element) =>
          element.props['aria-haspopup'] === 'menu' &&
          element.children.some((child) => child.text?.trim() === label)
      )
      expect(button).toBeTruthy()
      expect(button.props['aria-expanded']).toBe(false)

      dispatch(button, 'onMousedown')
      movePointer()
      dispatch(button, 'onDblclick')
      expect(props.onMove).not.toHaveBeenCalled()
      expect(props.onToggleMaximize).not.toHaveBeenCalled()
      expect(props['onToggle-sidebar']).not.toHaveBeenCalled()
    }
  )

  it.each(['window-titlebar__brand', 'window-titlebar__drag-region'])(
    'preserves dragging and double-click maximization on %s',
    (className) => {
      const { nodes, props } = mount()
      const caption = nodes.find((element) => element.props.class === className)
      dispatch(caption, 'onMousedown')
      expect(props.onMove).not.toHaveBeenCalled()
      movePointer()
      expect(props.onMove).toHaveBeenCalledOnce()
      dispatch(caption, 'onDblclick')
      expect(props.onToggleMaximize).toHaveBeenCalledOnce()
      expect(props['onToggle-sidebar']).not.toHaveBeenCalled()
    }
  )

  it('allows double-click maximization on the logo before any dragging begins', () => {
    const { nodes, props } = mount()
    const logo = nodes.find(
      (element) => element.tag === 'img' && element.props.src === '/favicon.ico'
    )
    dispatch(logo, 'onMousedown')
    window.dispatchEvent(new Event('mouseup'))
    dispatch(logo, 'onMousedown')
    window.dispatchEvent(new Event('mouseup'))
    dispatch(logo, 'onDblclick')
    expect(props.onToggleMaximize).toHaveBeenCalledOnce()
    expect(props.onMove).not.toHaveBeenCalled()
    expect(props['onToggle-sidebar']).not.toHaveBeenCalled()
  })
})
