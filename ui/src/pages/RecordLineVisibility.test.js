import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { readFileSync } from 'node:fs'
import * as Vue from 'vue'
import { createRenderer, markRaw, nextTick } from 'vue'
import { createPinia, setActivePinia } from 'pinia'
import { compile } from '@vue/compiler-dom'
import { compileScript, parse } from '@vue/compiler-sfc'
import { Chart } from 'chart.js'
import { NButton, NDatePicker, NModal } from 'naive-ui'
import RecordLine from './RecordLine.vue'
import RecordPie from './RecordPie.vue'
import MoodRateLegend from '@/components/MoodRateLegend.vue'
import { useMoodBoardStore } from '@/stores/mood_board'
import { MOOD_ORDER_KEY } from '@/utils/mood_order'

const state = vi.hoisted(() => ({ board: null, report: null, preferences: null }))

vi.mock('vue', async (original) => ({
  ...(await original()),
  useSSRContext: () => ({ modules: new Set() })
}))
vi.mock('axios', () => ({
  default: {
    get: vi.fn(async () => ({ data: { preferences: state.preferences } })),
    post: vi.fn(async (_url, preferences) => {
      state.preferences ??= preferences
      return { data: { preferences: state.preferences } }
    }),
    patch: vi.fn(async (_url, patch) => {
      state.preferences = { ...state.preferences, ...patch }
      return { data: { preferences: state.preferences } }
    }),
    delete: vi.fn(async () => ({}))
  }
}))
vi.mock('@/stores/record', () => ({
  useRecordStore: () => ({
    getMoodRatios: async () => state.report,
    getMoodCatalog: async () => [],
    getMoodSeries: async () => []
  })
}))
vi.mock('@/components/MoodCardGrid.vue', async () => {
  const { h } = await import('vue')
  return {
    default: {
      props: ['groups'],
      setup:
        (props, { slots }) =>
        () =>
          h(
            'div',
            props.groups.map((group) =>
              h('section', { key: group.boardKey }, slots.default({ group }))
            )
          )
    }
  }
})
vi.mock('@/components/MoodObservationEditor.vue', () => ({ default: () => null }))
vi.mock('chartjs-plugin-datalabels', () => ({ default: { id: 'datalabels' } }))
vi.mock('naive-ui', async () => {
  const { h } = await import('vue')
  return {
    NDatePicker: () => null,
    NButton: {
      setup:
        (_props, { attrs, slots }) =>
        () =>
          h('button', attrs, slots.default?.())
    },
    NModal: {
      props: ['show'],
      setup:
        (props, { slots }) =>
        () =>
          props.show ? h('aside', slots.default?.()) : null
    }
  }
})

function clientRender(file) {
  const { descriptor } = parse(readFileSync(file, 'utf8'))
  const { bindings } = compileScript(descriptor, { id: 'mood-chart-test' })
  const { code } = compile(descriptor.template.content, {
    mode: 'function',
    prefixIdentifiers: true,
    bindingMetadata: bindings
  })
  return new Function('Vue', code)(Vue)
}

// Vitest's Node transform emits SSR templates; use the same SFC templates in the client renderer.
RecordLine.render = clientRender(new URL('./RecordLine.vue', import.meta.url))
RecordPie.render = clientRender(new URL('./RecordPie.vue', import.meta.url))
MoodRateLegend.render = clientRender(new URL('../components/MoodRateLegend.vue', import.meta.url))

function element(type, text = '') {
  const node = markRaw({ type, text, props: {}, children: [], parent: null })
  if (type === 'canvas') {
    const context = new Proxy(
      {
        canvas: node,
        measureText: (value) => ({ width: String(value).length * 7 }),
        getLineDash: () => []
      },
      { get: (target, key) => (key in target ? target[key] : () => {}) }
    )
    Object.assign(node, { width: 600, height: 300, getContext: () => context })
  }
  return node
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
    const index = anchor ? parent.children.indexOf(anchor) : parent.children.length
    parent.children.splice(index, 0, node)
  },
  remove(node) {
    node.parent?.children.splice(node.parent.children.indexOf(node), 1)
    node.parent = null
  },
  setScopeId() {}
})

function descendants(node) {
  return [node, ...node.children.flatMap(descendants)]
}
function textContent(node) {
  return node.text + node.children.map(textContent).join('')
}
async function settle() {
  for (let turn = 0; turn < 8; turn++) await nextTick()
}

describe('mood curve visibility uses the existing Vue and Chart.js instance', () => {
  let app
  let root
  let chart
  let destroy
  let storage

  beforeEach(async () => {
    state.preferences = null
    const stored = new Map()
    storage = {
      getItem: (key) => stored.get(key) ?? null,
      setItem: (key, value) => stored.set(key, value)
    }
    vi.stubGlobal('window', { localStorage: storage })
    setActivePinia(createPinia())
    state.board = useMoodBoardStore()
    state.report = [
      {
        groupName: '深海',
        moodData: {
          datasets: ['歌蕾蒂娅', '乌尔比安'].map((label) => ({
            label,
            data: [
              { x: '2026-10-17T00:00:00+08:00', y: 24 },
              { x: '2026-10-17T01:00:00+08:00', y: 23 }
            ]
          }))
        }
      }
    ]
    root = element('root')
    app = renderer.createApp(RecordLine)
    app.component('n-button', NButton)
    app.component('n-modal', NModal)
    app.mount(root)
    await settle()
    chart = Object.values(Chart.instances)[0]
    expect(chart).toBeInstanceOf(Chart)
    expect(Object.values(Chart.instances)).toHaveLength(1)
    destroy = vi.spyOn(chart, 'destroy')
  })

  afterEach(() => {
    app?.unmount()
    expect(Object.values(Chart.instances)).toHaveLength(0)
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  function button(predicate) {
    return descendants(root).find((node) => node.type === 'button' && predicate(node))
  }
  function expectSameChart() {
    expect(Object.values(Chart.instances)).toHaveLength(1)
    expect(Object.values(Chart.instances)[0] === chart).toBe(true)
    expect(destroy).not.toHaveBeenCalled()
  }

  it('keeps a single curve toggle after the data watcher updates without remounting', async () => {
    const legend = () => button((node) => node.props['aria-label']?.startsWith('歌蕾蒂娅 消耗'))

    legend().props.onClick()
    await settle()

    expectSameChart()
    expect(chart.isDatasetVisible(0)).toBe(false)
    expect(chart.isDatasetVisible(1)).toBe(true)
    expect(chart.data.datasets[0].hidden).toBe(true)
    expect(legend().props['aria-pressed']).toBe(false)

    legend().props.onClick()
    await settle()

    expectSameChart()
    expect(chart.isDatasetVisible(0)).toBe(true)
    expect(chart.data.datasets[0].hidden).toBe(false)
    expect(legend().props['aria-pressed']).toBe(true)
  })

  it('keeps bulk hide/show and a later single toggle synchronized with updated datasets', async () => {
    button((node) => textContent(node).trim() === '隐藏全部').props.onClick()
    await settle()

    expectSameChart()
    expect([0, 1].map((index) => chart.isDatasetVisible(index))).toEqual([false, false])
    expect(chart.data.datasets.map((dataset) => dataset.hidden)).toEqual([true, true])

    button((node) => node.props['aria-label']?.startsWith('歌蕾蒂娅 消耗')).props.onClick()
    await settle()

    expectSameChart()
    expect([0, 1].map((index) => chart.isDatasetVisible(index))).toEqual([true, false])

    button((node) => textContent(node).trim() === '显示全部').props.onClick()
    await settle()

    expectSameChart()
    expect([0, 1].map((index) => chart.isDatasetVisible(index))).toEqual([true, true])
    expect(chart.data.datasets.map((dataset) => dataset.hidden)).toEqual([false, false])
  })

  async function remount(component) {
    await state.board.flushSaves()
    app.unmount()
    setActivePinia(createPinia())
    state.board = useMoodBoardStore()
    app = renderer.createApp(component)
    app.component('n-button', NButton)
    app.component('n-modal', NModal)
    app.component('n-date-picker', NDatePicker)
    app.mount(root)
    await settle()
  }

  it('persists curve exclusion and applies it when opening the pie page with a fresh store', async () => {
    button((node) => node.props['aria-label']?.startsWith('歌蕾蒂娅 消耗')).props.onClick()
    await settle()

    await remount(RecordPie)
    button((node) => textContent(node).trim() === '深海').props.onClick()
    await settle()

    expect(
      button((node) => node.props['aria-label'] === '将歌蕾蒂娅设为深海的默认干员')
    ).toBeUndefined()
    expect(
      button((node) => node.props['aria-label'] === '将乌尔比安设为深海的默认干员')
    ).toBeDefined()
    expect(JSON.parse(storage.getItem(MOOD_ORDER_KEY)).hiddenLines).toEqual({ 深海: ['歌蕾蒂娅'] })

    await remount(RecordLine)
    const restored = Object.values(Chart.instances)[0]
    expect(restored.isDatasetVisible(0)).toBe(false)
    expect(restored.isDatasetVisible(1)).toBe(true)
  })

  it('hides a window in both pages after reload and restores it with the page button', async () => {
    button((node) => node.props['aria-label'] === '隐藏深海窗口').props.onClick()
    await settle()
    expect(Object.values(Chart.instances)).toHaveLength(0)

    await remount(RecordPie)
    expect(button((node) => textContent(node).trim() === '深海')).toBeUndefined()
    button((node) => textContent(node).includes('还原隐藏窗口')).props.onClick()
    await settle()
    expect(button((node) => textContent(node).trim() === '深海')).toBeDefined()

    await remount(RecordLine)
    expect(Object.values(Chart.instances)).toHaveLength(1)
    expect(state.board.hiddenGroups).toEqual([])
  })

  it('clicks a default operator and preserves it across page reload', async () => {
    state.report[0].moodData.datasets[1].data = [
      { x: '2026-10-17T00:00:00+08:00', y: 24 },
      { x: '2026-10-17T03:00:00+08:00', y: 21 },
      { x: '2026-10-17T04:00:00+08:00', y: 24 }
    ]
    await remount(RecordPie)
    expect(textContent(root)).toContain('当前干员：乌尔比安')
    button((node) => textContent(node).trim() === '深海').props.onClick()
    await settle()
    button((node) => node.props['aria-label'] === '将歌蕾蒂娅设为深海的默认干员').props.onClick()
    await settle()

    expect(textContent(root)).toContain('当前干员：歌蕾蒂娅')
    expect(Object.values(Chart.instances)[0].data.datasets[0].data).toEqual([0, 100])

    await remount(RecordPie)
    expect(textContent(root)).toContain('当前干员：歌蕾蒂娅')
    expect(Object.values(Chart.instances)[0].data.datasets[0].data).toEqual([0, 100])
  })
})
