import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { readFileSync } from 'node:fs'
import * as Vue from 'vue'
import { createRenderer, h, markRaw, nextTick, reactive } from 'vue'
import { createPinia, setActivePinia } from 'pinia'
import { compile } from '@vue/compiler-dom'
import { compileScript, parse } from '@vue/compiler-sfc'
import axios from 'axios'
import Depot from './depot.vue'
import { useDepotPreferencesStore } from '@/stores/depotPreferences'
import { DEFAULT_BASELINE_CONFIG, DEFAULT_VIEW_PREFS } from '@/utils/depot_inventory'

const state = vi.hoisted(() => ({ depot: null }))
vi.mock('vue', async (original) => ({
  ...(await original()),
  useSSRContext: () => ({ modules: new Set() })
}))
vi.mock('axios', () => ({ default: { get: vi.fn(), put: vi.fn() } }))
vi.mock('@/stores/depot', () => ({ usedepotStore: () => state.depot }))
vi.mock('@/stores/config', async () => {
  const { defineStore } = await import('pinia')
  const { ref } = await import('vue')
  return { useConfigStore: defineStore('depotTestConfig', () => ({ theme: ref('light') })) }
})
vi.mock('naive-ui', () => ({
  useMessage: () => ({ info: vi.fn(), success: vi.fn(), warning: vi.fn(), error: vi.fn() })
}))
vi.mock('@/theme/mower', () => ({ mowerDarkCssVariables: {}, mowerLightCssVariables: {} }))
vi.mock('echarts/core', () => ({ use: vi.fn() }))
vi.mock('echarts/renderers', () => ({ CanvasRenderer: {} }))
vi.mock('echarts/charts', () => ({ LineChart: {} }))
vi.mock('echarts/components', () => ({
  GridComponent: {},
  TooltipComponent: {},
  DataZoomComponent: {},
  MarkLineComponent: {}
}))
vi.mock('vue-echarts', () => ({ default: () => null, THEME_KEY: Symbol('chart-theme') }))
vi.mock('@/components/HelpText.vue', () => ({ default: () => null }))
vi.mock('@/components/DepotBaselinePicker.vue', async () => {
  const { h } = await import('vue')
  return {
    default: {
      props: ['modelValue', 'history', 'disabled'],
      setup:
        (props, { emit }) =>
        () =>
          h('baseline-picker', {
            modelValue: props.modelValue,
            disabled: props.disabled,
            onChange: (value) => emit('update:modelValue', value)
          })
    }
  }
})

const { descriptor } = parse(readFileSync(new URL('./depot.vue', import.meta.url), 'utf8'))
const { bindings } = compileScript(descriptor, { id: 'depot-preferences-test' })
Depot.render = new Function(
  'Vue',
  compile(descriptor.template.content, {
    mode: 'function',
    prefixIdentifiers: true,
    bindingMetadata: bindings
  }).code
)(Vue)

function element(type, text = '') {
  return markRaw({
    type,
    text,
    props: {},
    children: [],
    parent: null,
    offsetHeight: 0,
    style: { setProperty() {} },
    getBoundingClientRect: () => ({ height: 0 }),
    querySelector: () => null
  })
}

const renderer = createRenderer({
  createElement: element,
  createText: (text) => element('text', text),
  createComment: (text) => element('comment', text),
  setText: (node, text) => (node.text = text),
  setElementText(node, text) {
    node.text = text
    node.children = []
  },
  patchProp: (node, key, _previous, value) => (node.props[key] = value),
  parentNode: (node) => node.parent,
  nextSibling: (node) => node.parent?.children[node.parent.children.indexOf(node) + 1],
  insert(node, parent, anchor = null) {
    if (node.parent) node.parent.children.splice(node.parent.children.indexOf(node), 1)
    node.parent = parent
    parent.children.splice(
      anchor ? parent.children.indexOf(anchor) : parent.children.length,
      0,
      node
    )
  },
  remove(node) {
    node.parent?.children.splice(node.parent.children.indexOf(node), 1)
    node.parent = null
  },
  setScopeId() {}
})

const descendants = (node) => [node, ...node.children.flatMap(descendants)]
const content = (node) => node.text + node.children.map(content).join('')
const wrapper = (tag) => ({
  setup:
    (_props, { attrs, slots }) =>
    () =>
      h(tag, attrs, [slots.default?.(), slots.trigger?.(), slots.action?.()])
})
const clone = (value) => JSON.parse(JSON.stringify(value))
let app
let root
let storage
let saved

async function settle() {
  for (let count = 0; count < 10; count++) await nextTick()
}

function mount() {
  root = element('root')
  app = renderer.createApp(Depot)
  for (const name of ['card', 'icon', 'tag', 'tooltip', 'dropdown', 'alert', 'empty', 'space']) {
    app.component(`n-${name}`, wrapper(name))
  }
  app.component('n-button', wrapper('button'))
  for (const name of ['radio-group', 'radio-button', 'select', 'checkbox', 'input']) {
    app.component(`n-${name}`, wrapper(name))
  }
  app.component('n-drawer', { setup: () => () => null })
  app.component('n-drawer-content', wrapper('aside'))
  app.mount(root)
  return useDepotPreferencesStore()
}

function node(type, predicate = () => true) {
  return descendants(root).find((item) => item.type === type && predicate(item))
}

beforeEach(() => {
  setActivePinia(createPinia())
  storage = { getItem: vi.fn(), setItem: vi.fn(), removeItem: vi.fn() }
  vi.stubGlobal('localStorage', storage)
  saved = {
    favorites: ['龙门币'],
    view: { ...DEFAULT_VIEW_PREFS, sortMode: 'name' },
    baseline: { ...DEFAULT_BASELINE_CONFIG, preset: '7d' }
  }
  axios.get.mockImplementation(async () => ({ data: { depot: clone(saved) } }))
  axios.put.mockImplementation(async (_url, payload) => {
    saved = { ...saved, ...clone(payload.depot) }
    return { data: { depot: clone(saved) } }
  })
  state.depot = reactive({
    report: {
      depot: [
        {
          'A 常用资源': {
            龙门币: { number: 200, sort: 1 },
            合成玉: { number: 600, sort: 2 }
          }
        },
        '',
        '200'
      ]
    },
    loading: false,
    reportLoaded: true,
    reportError: '',
    historyError: '',
    history: [
      { at: 100, items: { 龙门币: 100, 合成玉: 600 }, complete: true },
      { at: 200, items: { 龙门币: 200, 合成玉: 600 }, complete: true }
    ],
    loadReport: vi.fn(async () => {})
  })
})

afterEach(() => {
  app?.unmount()
  app = null
  vi.unstubAllGlobals()
  vi.resetAllMocks()
})

describe('depot page preference persistence', () => {
  it('loads saved instance preferences on mount and displays them in the actual page controls', async () => {
    const preferences = mount()
    await settle()
    expect(preferences.loaded).toBe(true)
    expect(axios.get).toHaveBeenCalledWith(expect.stringMatching(/\/gui\/depot$/), {
      timeout: 5000
    })
    expect(node('select').props.value).toBe('name')
    expect(node('baseline-picker').props.modelValue.preset).toBe('7d')
    expect(
      node('button', (item) => item.props.class?.includes('card-star-btn starred')).props.title
    ).toBe('取消关注')
    expect(storage.getItem).not.toHaveBeenCalled()
    expect(axios.put).not.toHaveBeenCalled()
  })

  it('keeps preference controls disabled after a read failure until the page retry succeeds', async () => {
    axios.get.mockRejectedValueOnce(new Error('offline'))
    const preferences = mount()
    await settle()
    expect(node('radio-group', (item) => item.props.name === 'stockFilter').props.disabled).toBe(
      true
    )
    expect(node('select').props.disabled).toBe(true)
    expect(node('baseline-picker').props.disabled).toBe(true)
    expect(content(root)).toContain('仓库偏好读取失败')
    node('button', (item) => content(item).trim() === '重试').props.onClick()
    await settle()
    expect(preferences.loaded).toBe(true)
    expect(node('select').props.disabled).toBe(false)
    expect(node('baseline-picker').props.disabled).toBe(false)
    expect(axios.put).not.toHaveBeenCalled()
  })

  it('persists favorites, filters and baseline edits from page events without browser writes', async () => {
    const preferences = mount()
    await settle()
    node('button', (item) => item.props.class?.includes('card-star-btn starred')).props.onClick({
      stopPropagation() {}
    })
    await settle()
    expect(saved.favorites).toEqual([])
    node('radio-group', (item) => item.props.name === 'stockFilter').props['onUpdate:value'](
      'owned'
    )
    await settle()
    expect(saved.view.stockFilter).toBe('owned')
    expect(saved.view.sortMode).toBe('name')
    node('baseline-picker').props.onChange({ ...DEFAULT_BASELINE_CONFIG, preset: '30d' })
    await settle()
    expect(saved.baseline.preset).toBe('30d')
    expect(preferences.baseline.preset).toBe('30d')
    expect(axios.put.mock.calls.map((call) => Object.keys(call[1].depot))).toEqual([
      ['favorites'],
      ['view'],
      ['baseline']
    ])
    expect(storage.setItem).not.toHaveBeenCalled()
    expect(storage.removeItem).not.toHaveBeenCalled()
  })
})
