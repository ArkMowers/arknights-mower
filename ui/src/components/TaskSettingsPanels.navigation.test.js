import { readFileSync } from 'node:fs'
import { parse } from '@vue/compiler-sfc'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  compile,
  createRenderer,
  defineComponent,
  getCurrentInstance,
  h,
  KeepAlive,
  nextTick,
  reactive,
  ref,
  ssrContextKey
} from 'vue'
import { createPinia, disposePinia } from 'pinia'
import { routeLocationKey } from 'vue-router'
import axios from 'axios'
import { useConfigStore } from '@/stores/config'
import { useGuiStore } from '@/stores/gui'
import TaskConfiguration from '@/task-workflow/TaskConfiguration.vue'
import TaskSettingsPanels from './TaskSettingsPanels.vue'
import Clue from './Clue.vue'
import DailyMission from './DailyMission.vue'
import { createTaskWorkflow } from '@/task-workflow/model'

vi.mock('axios', () => ({ default: { get: vi.fn(), post: vi.fn(), patch: vi.fn() } }))

const card = defineComponent({
  inheritAttrs: false,
  setup: () => () => h('div', { class: 'n-card' })
})
const relatedAccounts = defineComponent({
  emits: ['configure-accounts'],
  setup:
    (_, { emit }) =>
    () =>
      h('div', { class: 'n-card' }, [
        h('button', { 'data-related-accounts': '', onClick: () => emit('configure-accounts') })
      ])
})
const wrapper = defineComponent({
  inheritAttrs: false,
  setup:
    (_, { attrs, slots }) =>
    () =>
      h('div', attrs, [slots.header?.(), slots.label?.(), slots.default?.()])
})
const workflow = defineComponent({
  props: ['modelValue', 'editorRequest'],
  emits: ['select'],
  setup:
    (props, { emit, slots }) =>
    () =>
      h(
        'main',
        {
          class: 'task-workspace',
          'data-selected-editor': props.modelValue,
          'data-editor-request': props.editorRequest
        },
        [
          h('button', { class: 'checklist-mobile-toggle' }),
          ...[
            'device',
            'runtime',
            'report',
            'skland',
            'mail',
            'event-sign-in',
            'visit',
            'credit-fight',
            'shop'
          ].map((id) => h('button', { 'data-select': id, onClick: () => emit('select', id) })),
          slots.default?.()
        ]
      )
})

function clientComponent(component, path, setupComponents = {}) {
  const { descriptor } = parse(readFileSync(new URL(path, import.meta.url), 'utf8'))
  return {
    ...component,
    components: setupComponents,
    ssrRender: undefined,
    render: compile(descriptor.template.content, { hoistStatic: false }),
    setup: (props, context) => ({ ...component.setup(props, context), ...setupComponents })
  }
}

let panelInstance
const ClientPanels = clientComponent(TaskSettingsPanels, './TaskSettingsPanels.vue', {
  ...Object.fromEntries(
    [
      'DeviceSettings',
      'PerformanceSettings',
      'WorkshopManualSettings',
      'Recruit',
      'MaaReward',
      'MaaWeekly',
      'LongTasks',
      'SKLand',
      'YituliuSyncSettings',
      'IncomeSettings',
      'MaaBasic',
      'TrustSettings'
    ].map((name) => [name, card])
  ),
  MowerSettings: defineComponent({
    setup: () => {
      const config = useConfigStore()
      return () =>
        h(
          'div',
          createTaskWorkflow(config)
            .tasks.filter(({ group }) => group === 'mower')
            .map(({ id }) => h('section', { 'data-task-editor': id }))
        )
    }
  }),
  DailyMission: clientComponent(DailyMission, './DailyMission.vue'),
  Clue: clientComponent(Clue, './Clue.vue'),
  Depotswitch: relatedAccounts
})
const setupPanels = ClientPanels.setup
ClientPanels.setup = (props, context) => {
  panelInstance = getCurrentInstance()
  return setupPanels(props, context)
}
const ClientConfiguration = clientComponent(
  TaskConfiguration,
  '../task-workflow/TaskConfiguration.vue',
  { TaskWorkflow: workflow, TaskSettingsPanels: ClientPanels }
)

function node(tag) {
  const element = {
    tag,
    props: {},
    children: [],
    parent: null,
    style: {},
    listeners: new Map(),
    addEventListener(type, callback) {
      this.listeners.set(type, callback)
    },
    removeEventListener(type, callback) {
      if (this.listeners.get(type) === callback) this.listeners.delete(type)
    },
    get ownerDocument() {
      return documentStub
    },
    get parentElement() {
      return this.parent
    },
    getBoundingClientRect() {
      return this.bounds || { top: 0, bottom: 0, height: 0, width: 0 }
    },
    scrollIntoView: vi.fn(),
    querySelector(selector) {
      if (selector === '.checklist-mobile-toggle')
        return all(this).find((child) => classes(child).includes('checklist-mobile-toggle'))
      const id = selector.match(/^\[data-task-editor="([^"]+)"\]$/)?.[1]
      return all(this).find((child) => child.props['data-task-editor'] === id)
    },
    querySelectorAll(selector) {
      return all(this).filter((child) =>
        selector === '[id]'
          ? child.props.id
          : selector === '[data-task-editor]' && child.props['data-task-editor']
      )
    },
    get id() {
      return this.props.id
    },
    getAttribute: (key) => element.props[key],
    closest(selector) {
      for (let target = this; target; target = target.parent) {
        if (selector === '[data-task-editor]' && target.props['data-task-editor']) return target
        if (selector === '.task-workspace' && classes(target).includes('task-workspace'))
          return target
        if (
          selector === 'a[href^="#"]' &&
          target.tag === 'a' &&
          target.props.href?.startsWith('#task-')
        )
          return target
      }
      return null
    },
    classList: {
      add(name) {
        element.props.class = [...new Set([...classes(element), name])].join(' ')
      },
      remove(name) {
        element.props.class = classes(element)
          .filter((value) => value !== name)
          .join(' ')
      }
    }
  }
  return element
}
const all = (element) => [element, ...element.children.flatMap(all)]
const classes = (element) => String(element.props.class || '').split(/\s+/)
let app
let root
let activePinia
let documentStub
let scrollport
let viewport
let frames
let observers
const renderer = createRenderer({
  createElement: node,
  createText: () => node('#text'),
  createComment: () => node('#comment'),
  setText() {},
  setElementText() {},
  patchProp: (element, key, _old, value) => (element.props[key] = value),
  parentNode: (element) => element.parent,
  nextSibling: (element) =>
    element.parent?.children[element.parent.children.indexOf(element) + 1] || null,
  insert(element, parent, anchor) {
    if (element.parent) element.parent.children.splice(element.parent.children.indexOf(element), 1)
    element.parent = parent
    const index = anchor ? parent.children.indexOf(anchor) : -1
    parent.children.splice(index < 0 ? parent.children.length : index, 0, element)
  },
  remove(element) {
    element.parent?.children.splice(element.parent.children.indexOf(element), 1)
    element.parent = null
  }
})

async function flush() {
  await nextTick()
  await nextTick()
}

async function mount(hash = '') {
  const pinia = createPinia()
  activePinia = pinia
  const route = reactive({ hash })
  const shown = ref(true)
  let configuration
  app = renderer.createApp({
    setup: () => () =>
      h(KeepAlive, null, {
        default: () =>
          shown.value
            ? h(ClientConfiguration, { ref: (instance) => (configuration = instance) })
            : null
      })
  })
  app.use(pinia)
  app.provide(ssrContextKey, { modules: new Set() })
  app.provide(routeLocationKey, route)
  app.provide('axios', axios)
  app.provide('loaded', ref(false))
  app.provide('mobile', ref(false))
  const config = app.runWithContext(() => useConfigStore(pinia))
  const gui = app.runWithContext(() => useGuiStore(pinia))
  gui.taskSettingsLayout = 'waterfall'
  config.runtime_platform = 'windows'
  for (const name of [
    'NCard',
    'NForm',
    'NFormItem',
    'NSelect',
    'NRadioGroup',
    'NSpace',
    'NRadio',
    'NAlert',
    'NCheckbox',
    'NFlex',
    'NInput',
    'NTable',
    'MowerInputNumber',
    'HelpText',
    'SessionLink',
    'NButton',
    'NDivider',
    'NTooltip',
    'NTabs',
    'NTabPane'
  ])
    app.component(name, wrapper)
  root = node('root')
  root.parent = scrollport
  scrollport.children.push(root)
  app.mount(root)
  await flush()
  return {
    config,
    gui,
    shown,
    route,
    selected: () =>
      all(root).find((element) => element.tag === 'main').props['data-selected-editor'],
    async select(id) {
      all(root)
        .find((element) => element.props['data-select'] === id)
        .props.onClick()
      await flush()
    },
    async open(id) {
      configuration.openEditor(id)
      await flush()
    }
  }
}

function panels(id) {
  return all(root).filter((element) => element.props['data-task-editor'] === id)
}
const highlighted = () =>
  all(root).filter((element) => classes(element).includes('task-panel--revealed'))

beforeEach(() => {
  vi.useFakeTimers()
  vi.stubGlobal('ResizeObserver', undefined)
  frames = new Map()
  observers = []
  let nextFrame = 0
  viewport = node('window')
  viewport.innerHeight = 900
  viewport.requestAnimationFrame = vi.fn((callback) => {
    frames.set(++nextFrame, callback)
    return nextFrame
  })
  viewport.cancelAnimationFrame = vi.fn((id) => frames.delete(id))
  viewport.getComputedStyle = (element) => ({
    overflowY: element.style.overflowY || 'visible',
    scrollMarginTop: '12px'
  })
  viewport.ResizeObserver = class {
    constructor(callback) {
      this.callback = callback
      this.observe = vi.fn()
      this.disconnect = vi.fn()
      observers.push(this)
    }
  }
  scrollport = node('scrollport')
  Object.assign(scrollport, {
    scrollTop: 0,
    scrollHeight: 5000,
    clientHeight: 600,
    offsetHeight: 600,
    clientTop: 0,
    bounds: { top: 100, bottom: 700, height: 600 }
  })
  scrollport.style.overflowY = 'auto'
  documentStub = { defaultView: viewport, scrollingElement: node('document') }
})
afterEach(() => {
  app?.unmount()
  app = undefined
  if (activePinia) disposePinia(activePinia)
  activePinia = undefined
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

describe('continuous settings directory and scroll selection', () => {
  it('displays the scheduler idle-action priority for old conflicting flags and saves one choice', async () => {
    const { config } = await mount()
    config.close_simulator_when_idle = true
    config.exit_game_when_idle = true
    config.return_home_when_idle = true
    await flush()
    const field = all(panels('idle')[0]).find(
      (element) => element.props['aria-label'] === '任务结束后'
    )
    expect(field.props.value).toBe('close')
    field.props['onUpdate:value']('home')
    await flush()
    expect(config.close_simulator_when_idle).toBe(false)
    expect(config.exit_game_when_idle).toBe(false)
    expect(config.return_home_when_idle).toBe(true)
  })

  it.each(['checklist', 'waterfall'])(
    'unmounts managed connection panels in %s layout',
    async (layout) => {
      const page = await mount('#task-devices')
      page.gui.taskSettingsLayout = layout
      expect(panels('device')).toHaveLength(2)
      expect(panels('idle')).toHaveLength(1)
      page.config.manager_owned_device = true
      await flush()
      expect(panels('device')).toHaveLength(0)
      expect(panels('idle')).toHaveLength(0)
      await page.open('device')
      expect(panels('device')).toHaveLength(0)
      page.config.manager_owned_device = false
      await flush()
      await page.open('device')
      expect(panels('device')).toHaveLength(2)
      expect(panels('idle')).toHaveLength(1)
    }
  )

  it.each([
    [false, false],
    [true, false],
    [true, true]
  ])(
    'renders all settings in directory order with manager ownership %s and maintenance visibility %s',
    async (managed, visible) => {
      const page = await mount()
      page.config.manager_owned_device = managed
      page.config.extra_settings_visible = visible
      page.config.visit_friend_enable = true
      page.config.maa_mall_enable = true
      await flush()
      const model = createTaskWorkflow(page.config)
      const directory = [
        ...(managed ? [] : ['device']),
        ...model.groups.flatMap((group) =>
          model.tasks.filter((task) => task.group === group.id).map((task) => task.editor)
        )
      ]
      const rendered = all(root)
        .map((element) => element.props['data-task-editor'])
        .filter((id) => id && !['daily', 'credit'].includes(id))
        .map((id) => (id === 'idle' ? 'device' : id))
        .filter((id, index, ids) => id !== ids[index - 1])
      expect(rendered).toEqual(directory)
    }
  )

  it('positions directory requests without temporary card highlighting or timers', async () => {
    const page = await mount()
    await page.select('device')
    const target = panels('device')[0]
    expect(target.scrollIntoView).toHaveBeenCalledWith({ block: 'start', behavior: 'instant' })
    expect(panels('device')[1].scrollIntoView).not.toHaveBeenCalled()
    expect(highlighted()).toHaveLength(0)
    expect(vi.getTimerCount()).toBe(0)
    await page.select('device')
    expect(target.scrollIntoView).toHaveBeenCalledTimes(2)
    expect(highlighted()).toHaveLength(0)
  })

  it('maps shared cards and legacy links to existing editors without a flash', async () => {
    const page = await mount('#task-long')
    expect(panels('long')[0].scrollIntoView).toHaveBeenCalledOnce()
    for (const id of ['report', 'skland', 'mail', 'event-sign-in']) {
      await page.select(id)
      expect(panels(id)[0].scrollIntoView).toHaveBeenCalledOnce()
    }
    expect(panels('daily')[0].scrollIntoView).not.toHaveBeenCalled()
    for (const id of ['visit', 'credit-fight', 'shop']) {
      await page.select(id)
      if (panels(id).length) expect(panels(id)[0].scrollIntoView).toHaveBeenCalledOnce()
      else expect(panels('credit')[0].scrollIntoView).toHaveBeenCalled()
    }
    all(root)
      .find((element) => 'data-related-accounts' in element.props)
      .props.onClick()
    await flush()
    expect(panels('accounts')[0].scrollIntoView).toHaveBeenCalledOnce()
    expect(highlighted()).toHaveLength(0)
  })

  it('follows actual scroll events without scrolling back or saving configuration', async () => {
    const page = await mount()
    place(panels('device')[0], 0, 500)
    place(panels('base')[0], 500, 400)
    place(panels('runtime')[0], 900, 200)
    await frame()
    expect(page.selected()).toBe('device')
    const writes = [axios.post.mock.calls.length, axios.patch.mock.calls.length]
    scrollport.scrollTop = 550
    scrollport.listeners.get('scroll')()
    scrollport.listeners.get('scroll')()
    expect(frames.size).toBe(1)
    await frame()
    expect(page.selected()).toBe('base')
    expect(all(root).some((element) => element.scrollIntoView.mock.calls.length)).toBe(false)
    expect([axios.post.mock.calls.length, axios.patch.mock.calls.length]).toEqual(writes)
    scrollport.scrollTop = 920
    scrollport.listeners.get('scroll')()
    await frame()
    expect(page.selected()).toBe('runtime')
    scrollport.scrollTop = 50
    scrollport.listeners.get('scroll')()
    await frame()
    expect(page.selected()).toBe('device')
  })

  it('uses scrollport scale and mobile sticky directory height for the active section', async () => {
    const page = await mount()
    scrollport.bounds = { top: 100, bottom: 1300, height: 1200 }
    place(panels('device')[0], 0, 500)
    place(panels('runtime')[0], 500, 500)
    scrollport.scrollTop = 470
    await frame()
    expect(page.selected()).toBe('device')
    const toggle = all(root).find((element) => classes(element).includes('checklist-mobile-toggle'))
    toggle.bounds = { top: 100, bottom: 204, height: 104 }
    viewport.listeners.get('resize')()
    await frame()
    expect(page.selected()).toBe('runtime')
    expect(all(root).some((element) => element.scrollIntoView.mock.calls.length)).toBe(false)
  })

  it('tracks individual entries inside a shared daily task card', async () => {
    const page = await mount()
    place(panels('daily')[0], 0, 900)
    place(panels('skland')[0], 40, 100)
    place(panels('mail')[0], 200, 80)
    place(panels('report')[0], 300, 100)
    scrollport.scrollTop = 210
    scrollport.listeners.get('scroll')()
    await frame()
    expect(page.selected()).toBe('mail')
    expect(all(root).some((element) => element.scrollIntoView.mock.calls.length)).toBe(false)
  })

  it('selects the final short section at the scroll bottom and ignores hidden sections', async () => {
    const page = await mount()
    const settings = all(root).find((element) => classes(element).includes('task-settings-panels'))
    place(settings, 0, 5000)
    place(panels('mower-updates')[0], 3900, 900)
    place(panels('mower-data')[0], 4800, 200)
    place(panels('device')[0], 4990, 0)
    scrollport.scrollTop = 4400
    await frame()
    expect(page.selected()).toBe('mower-data')
    expect(highlighted()).toHaveLength(0)
  })

  it('keeps hidden managed device and runtime settings out of passive selection', async () => {
    const page = await mount()
    place(panels('device')[0], 0, 500)
    place(panels('runtime')[0], 500, 500)
    await frame()
    expect(page.selected()).toBe('device')
    page.config.manager_owned_device = true
    await flush()
    await frame()
    expect(page.selected()).toBe('base')
    expect(panels('device')).toHaveLength(0)
    expect(panels('runtime')).toHaveLength(0)
    await page.open('device')
    await page.open('runtime')
    expect(page.selected()).toBe('base')
  })

  it('removes scroll listeners, observers and pending frames while deactivated and unmounted', async () => {
    const page = await mount()
    place(panels('runtime')[0], 0, 1000)
    const target = panels('runtime')[0]
    const cachedPanel = panelInstance
    const pending = [...frames.keys()]
    expect(pending).not.toHaveLength(0)
    const observer = observers.at(-1)
    page.shown.value = false
    await flush()
    expect(scrollport.listeners.has('scroll')).toBe(false)
    expect(viewport.listeners.has('resize')).toBe(false)
    expect(observer.disconnect).toHaveBeenCalledOnce()
    expect(frames.size).toBe(0)
    cachedPanel.exposed.revealActive()
    expect(target.scrollIntoView).not.toHaveBeenCalled()
    expect(frames.size).toBe(0)
    page.shown.value = true
    await flush()
    expect(scrollport.listeners.has('scroll')).toBe(true)
    await frame()
    expect(page.selected()).toBe('runtime')
    const activeObserver = observers.at(-1)
    scrollport.listeners.get('scroll')()
    app.unmount()
    app = undefined
    expect(scrollport.listeners.has('scroll')).toBe(false)
    expect(activeObserver.disconnect).toHaveBeenCalledOnce()
    expect(frames.size).toBe(0)
  })
})

function place(element, top, height) {
  element.getBoundingClientRect = () => {
    const scale = scrollport.bounds.height / scrollport.offsetHeight
    const screenTop = scrollport.bounds.top + (top - scrollport.scrollTop) * scale
    return {
      top: screenTop,
      bottom: screenTop + height * scale,
      height: height * scale,
      width: 600
    }
  }
}

async function frame() {
  const callbacks = [...frames.values()]
  frames.clear()
  for (const callback of callbacks) callback()
  await flush()
}
