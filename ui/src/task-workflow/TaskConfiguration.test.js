import { readFileSync } from 'node:fs'
import { parse } from '@vue/compiler-sfc'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { compile, createRenderer, defineComponent, h, nextTick, reactive, ssrContextKey } from 'vue'
import { routeLocationKey } from 'vue-router'
import {
  createDeviceConnectionNavigation,
  deviceConnectionNavigationKey
} from '@/composables/deviceConnectionNavigation'
import TaskConfiguration from './TaskConfiguration.vue'
import TaskWorkflow from './TaskWorkflow.vue'
import TaskSettingsPanels from '@/components/TaskSettingsPanels.vue'

const state = vi.hoisted(() => ({ config: null, resolveTarget: null, revealActive: null }))
vi.mock('@/stores/config', () => ({ useConfigStore: () => state.config }))
vi.mock('@/stores/gui', () => ({
  useGuiStore: () => reactive({ taskSettingsLayout: 'checklist' })
}))
vi.mock('./TaskWorkflow.vue', () => ({
  default: defineComponent({
    props: ['modelValue'],
    emits: ['update:modelValue'],
    setup(props, { emit, slots }) {
      return () =>
        h('section', { 'data-active-editor': props.modelValue }, [
          h('button', { onClick: () => emit('update:modelValue', '') }, '关闭'),
          slots.default?.()
        ])
    }
  })
}))
vi.mock('@/components/TaskSettingsPanels.vue', () => ({
  default: defineComponent({
    props: ['active'],
    emits: ['select'],
    setup(_, { emit, expose }) {
      expose({
        resolveTarget: (id) => state.resolveTarget(id),
        revealActive: (id) => state.revealActive(id)
      })
      return () => h('button', { onClick: () => emit('select', 'runtime') }, '运行参数')
    }
  })
}))

const { descriptor } = parse(
  readFileSync(new URL('./TaskConfiguration.vue', import.meta.url), 'utf8')
)
const ClientConfiguration = {
  ...TaskConfiguration,
  ssrRender: undefined,
  render: compile(descriptor.template.content, { hoistStatic: false }),
  setup: (props, context) => ({ ...TaskConfiguration.setup(props, context) })
}

beforeEach(() => {
  state.config = reactive({ theme: 'light', manager_owned_device: false })
  state.resolveTarget = vi.fn()
  state.revealActive = vi.fn()
})
const mounted = []
function node(tag) {
  return { tag, props: {}, children: [], parent: null }
}
const renderer = createRenderer({
  createElement: node,
  createText: (text) => ({ ...node('#text'), text }),
  createComment: () => node('#comment'),
  setText: (element, text) => (element.text = text),
  setElementText: (element, text) => (element.text = text),
  parentNode: (element) => element.parent,
  nextSibling: () => null,
  patchProp: (element, key, _previous, value) => (element.props[key] = value),
  insert(element, parent) {
    element.parent = parent
    parent.children.push(element)
  },
  remove(element) {
    const siblings = element.parent?.children
    if (siblings) siblings.splice(siblings.indexOf(element), 1)
  }
})

function mount(navigation, hash = '') {
  const reveal = vi.fn()
  const editing = vi.fn()
  const route = reactive({ hash })
  const app = renderer.createApp(ClientConfiguration, {
    onReveal: reveal,
    onEditing: editing
  })
  app.component('TaskWorkflow', TaskWorkflow)
  app.component('TaskSettingsPanels', TaskSettingsPanels)
  app.provide(ssrContextKey, { modules: new Set() })
  app.provide(routeLocationKey, route)
  if (navigation) app.provide(deviceConnectionNavigationKey, navigation)
  const root = node('root')
  app.mount(root)
  mounted.push(app)
  const all = (element) => [element, ...element.children.flatMap(all)]
  return {
    app,
    reveal,
    editing,
    openEditor: (id) => app._instance.exposed.openEditor(id),
    route,
    editor: () =>
      all(root).find((element) => 'data-active-editor' in element.props).props[
        'data-active-editor'
      ],
    close: () =>
      all(root)
        .find((element) => element.tag === 'button')
        .props.onClick()
  }
}

afterEach(() => {
  for (const app of mounted.splice(0)) app.unmount()
})

describe('task configuration connection requests', () => {
  it('blocks managed runtime hashes and explicit requests while standalone instances retain them', async () => {
    state.config.manager_owned_device = true
    state.config.extra_settings_visible = true
    const page = mount(null, '#task-runtime')
    for (let tick = 0; tick < 4; tick += 1) await nextTick()
    page.openEditor('runtime')
    expect(page.editor()).toBe('base')
    expect(page.reveal).not.toHaveBeenCalled()
    state.config.manager_owned_device = false
    page.openEditor('runtime')
    await nextTick()
    expect(page.editor()).toBe('runtime')
    state.config.manager_owned_device = true
    await nextTick()
    expect(page.editor()).toBe('base')
  })

  it.each([
    ['#software-update', 'mower-updates'],
    ['#mower-data', 'mower-data']
  ])(
    'cannot reopen hidden managed maintenance settings through %s or explicit selection',
    async (hash, editor) => {
      state.config.manager_owned_device = true
      state.resolveTarget.mockReturnValue(editor)
      const page = mount(null, hash)
      for (let tick = 0; tick < 4; tick += 1) await nextTick()
      page.openEditor(editor)
      expect(page.editor()).toBe('base')
      expect(page.reveal).not.toHaveBeenCalled()
      expect(state.revealActive).not.toHaveBeenCalled()
      state.config.extra_settings_visible = true
      page.openEditor(editor)
      await nextTick()
      expect(page.editor()).toBe(editor)
      state.config.extra_settings_visible = false
      await nextTick()
      expect(page.editor()).toBe('base')
      page.openEditor('mower-notifications')
      await nextTick()
      expect(page.editor()).toBe('mower-notifications')
    }
  )

  it.each(['select', 'test', 'settings'])(
    'ignores managed %s requests and legacy links',
    async (action) => {
      state.config.manager_owned_device = true
      const navigation = createDeviceConnectionNavigation()
      navigation.open(action)
      const page = mount(navigation, '#task-devices')
      expect(page.editor()).toBe('base')
      expect(page.reveal).not.toHaveBeenCalled()
      page.openEditor('device')
      await nextTick()
      expect(page.editor()).toBe('base')
      state.config.manager_owned_device = false
      navigation.open(action)
      await nextTick()
      expect(page.editor()).toBe('device')
      state.config.manager_owned_device = true
      await nextTick()
      expect(page.editor()).toBe('base')
    }
  )

  it('opens a task editor without changing the URL', async () => {
    const page = mount(null)
    page.openEditor('recruit')
    await nextTick()
    expect(page.editor()).toBe('recruit')
    expect(page.reveal).toHaveBeenCalledOnce()
    expect(page.editing).toHaveBeenLastCalledWith(true)
    expect(page.route.hash).toBe('')
    page.openEditor('unknown-editor')
    await nextTick()
    expect(page.editor()).toBe('recruit')
    expect(page.reveal).toHaveBeenCalledOnce()
    page.close()
    await nextTick()
    expect(page.editing).toHaveBeenLastCalledWith(false)
  })

  it.each(['select', 'test', 'settings'])(
    'reveals the device editor for a pending %s request without modifying the URL',
    (action) => {
      const navigation = createDeviceConnectionNavigation()
      const request = navigation.open(action)
      const page = mount(navigation)
      expect(page.reveal).toHaveBeenCalledOnce()
      expect(page.editor()).toBe('device')
      expect(page.route.hash).toBe('')
      expect(navigation.request.value).toBe(request)
    }
  )

  it('reopens the device editor for repeated explicit requests on the same route', async () => {
    const navigation = createDeviceConnectionNavigation()
    const page = mount(navigation)
    expect(page.editor()).toBe('base')
    navigation.open('settings')
    expect(page.reveal).toHaveBeenCalledOnce()
    await nextTick()
    expect(page.editor()).toBe('device')
    page.close()
    await nextTick()
    expect(page.editor()).toBe('')
    navigation.open('settings')
    expect(page.reveal).toHaveBeenCalledTimes(2)
    await nextTick()
    expect(page.editor()).toBe('device')
    expect(page.route.hash).toBe('')
  })

  it('does not reveal or replay a consumed request after mounting again', async () => {
    const navigation = createDeviceConnectionNavigation()
    const first = mount(navigation)
    const request = navigation.open('test')
    expect(first.reveal).toHaveBeenCalledOnce()
    expect(navigation.consume(request)).toBe(true)
    expect(first.reveal).toHaveBeenCalledOnce()
    first.app.unmount()
    mounted.splice(mounted.indexOf(first.app), 1)
    const next = mount(navigation)
    await nextTick()
    expect(next.reveal).not.toHaveBeenCalled()
    expect(next.editor()).toBe('base')
  })

  it('retains legacy hash navigation when there is no connection controller', async () => {
    const page = mount(null, '#task-runtime')
    await nextTick()
    await nextTick()
    expect(page.reveal).toHaveBeenCalledOnce()
    expect(page.editor()).toBe('runtime')
    page.route.hash = '#task-devices'
    await nextTick()
    await nextTick()
    expect(page.reveal).toHaveBeenCalledTimes(2)
    expect(page.editor()).toBe('device')
  })

  it.each([
    ['#task-devices', 'device'],
    ['#task-runtime', 'runtime'],
    ['#task-base', 'base'],
    ['#task-daily', 'skland'],
    ['#task-long', 'long'],
    ['#task-accounts', 'accounts'],
    ['#task-maa', 'maa']
  ])(
    'retains the %s destination after category headings become plain text',
    async (hash, editor) => {
      const page = mount(null, hash)
      await nextTick()
      await nextTick()
      expect(page.editor()).toBe(editor)
      expect(page.route.hash).toBe(hash)
    }
  )

  it.each([
    ['#software-update', 'mower-updates'],
    ['#mower-data', 'mower-data'],
    ['#income-settings', 'accounts']
  ])('reveals the actual existing %s card after its panels mount', async (hash, editor) => {
    state.resolveTarget.mockReturnValue(editor)
    const page = mount(null, hash)
    for (let tick = 0; tick < 4; tick += 1) await nextTick()
    expect(state.resolveTarget).toHaveBeenCalledWith(hash.slice(1))
    expect(page.editor()).toBe(editor)
    expect(state.revealActive).toHaveBeenLastCalledWith(hash.slice(1))
    expect(page.route.hash).toBe(hash)
    expect(state.config).toEqual({ theme: 'light', manager_owned_device: false })
  })

  it('does not let a deferred old settings hash override a newer connection action', async () => {
    state.resolveTarget.mockReturnValue('mower-updates')
    const navigation = createDeviceConnectionNavigation()
    navigation.open('test')
    const page = mount(navigation, '#software-update')
    for (let tick = 0; tick < 4; tick += 1) await nextTick()
    expect(page.editor()).toBe('device')
    expect(state.revealActive).toHaveBeenLastCalledWith('')
  })

  it('opens the pending device request after applying an existing legacy hash', async () => {
    const navigation = createDeviceConnectionNavigation()
    navigation.open('test')
    const page = mount(navigation, '#task-runtime')
    await nextTick()
    await nextTick()
    expect(page.editor()).toBe('device')
    expect(page.route.hash).toBe('#task-runtime')
  })
})
