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
  emits: ['select'],
  setup:
    (_, { emit, slots }) =>
    () =>
      h('main', [
        ...['device', 'runtime', 'report', 'skland', 'mail', 'visit', 'credit-fight', 'shop'].map(
          (id) => h('button', { 'data-select': id, onClick: () => emit('select', id) })
        ),
        slots.default?.()
      ])
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
      'Clue',
      'MaaWeekly',
      'LongTasks',
      'SKLand',
      'YituliuSyncSettings',
      'IncomeSettings',
      'MaaBasic',
      'TrustSettings'
    ].map((name) => [name, card])
  ),
  DailyMission: relatedAccounts,
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
    scrollIntoView: vi.fn(),
    querySelector(selector) {
      const id = selector.match(/^\[data-task-editor="([^"]+)"\]$/)?.[1]
      return all(this).find((child) => child.props['data-task-editor'] === id)
    },
    getAttribute: (key) => element.props[key],
    closest(selector) {
      for (let target = this; target; target = target.parent) {
        if (
          selector === 'a[href^="#task-"]' &&
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
    'NButton'
  ])
    app.component(name, wrapper)
  root = node('root')
  app.mount(root)
  await flush()
  return {
    config,
    gui,
    shown,
    route,
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
})
afterEach(() => {
  app?.unmount()
  app = undefined
  if (activePinia) disposePinia(activePinia)
  activePinia = undefined
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

describe('waterfall navigation target feedback', () => {
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

  it('reveals and highlights the first matching card through the configuration directory', async () => {
    const page = await mount()
    expect(highlighted()).toHaveLength(0)
    await page.select('device')
    expect(panels('device')).toHaveLength(2)
    expect(highlighted()).toEqual([panels('device')[0]])
    expect(panels('device')[0].scrollIntoView).toHaveBeenCalledWith({
      block: 'start',
      behavior: 'instant'
    })
    expect(panels('device')[1].scrollIntoView).not.toHaveBeenCalled()
    vi.advanceTimersByTime(1800)
    expect(highlighted()).toHaveLength(0)
  })

  it('restarts the same target feedback and lets a new target keep its own lifetime', async () => {
    const page = await mount()
    await page.select('device')
    vi.advanceTimersByTime(1200)
    await page.select('device')
    vi.advanceTimersByTime(1200)
    expect(highlighted()).toEqual([panels('device')[0]])
    expect(panels('device')[0].scrollIntoView).toHaveBeenCalledTimes(2)
    await page.select('runtime')
    vi.advanceTimersByTime(600)
    expect(highlighted()).toEqual([panels('runtime')[0]])
    vi.advanceTimersByTime(1200)
    expect(highlighted()).toHaveLength(0)
  })

  it('maps daily and credit entries to their shared cards without highlighting other cards', async () => {
    const page = await mount()
    for (const id of ['report', 'skland', 'mail']) {
      await page.select(id)
      expect(highlighted()).toEqual([panels('daily')[0]])
    }
    for (const id of ['visit', 'credit-fight', 'shop']) {
      await page.select(id)
      expect(highlighted()).toEqual([panels('credit')[0]])
    }
  })

  it('gives legacy links and related account actions the same target feedback', async () => {
    await mount('#task-long')
    expect(highlighted()).toEqual([panels('long')[0]])
    all(root)
      .find((element) => 'data-related-accounts' in element.props)
      .props.onClick()
    await flush()
    expect(panels('accounts')).toHaveLength(3)
    expect(highlighted()).toEqual([panels('accounts')[0]])
    expect(panels('accounts')[0].scrollIntoView).toHaveBeenCalledOnce()
  })

  it('clears feedback on a layout switch, cache deactivation and unmount', async () => {
    const page = await mount()
    await page.select('runtime')
    page.gui.taskSettingsLayout = 'checklist'
    await flush()
    expect(highlighted()).toHaveLength(0)
    expect(vi.getTimerCount()).toBe(0)
    page.gui.taskSettingsLayout = 'waterfall'
    await flush()
    await page.select('runtime')
    const target = panels('runtime')[0]
    const cachedPanel = panelInstance
    page.shown.value = false
    await flush()
    expect(classes(target)).not.toContain('task-panel--revealed')
    expect(vi.getTimerCount()).toBe(0)
    cachedPanel.exposed.revealActive()
    expect(vi.getTimerCount()).toBe(0)
    page.shown.value = true
    await flush()
    await page.select('runtime')
    expect(highlighted()).toEqual([target])
    app.unmount()
    app = undefined
    expect(classes(target)).not.toContain('task-panel--revealed')
    expect(vi.getTimerCount()).toBe(0)
  })
})
