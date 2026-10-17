import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { readFileSync } from 'node:fs'
import * as Vue from 'vue'
import { createRenderer, markRaw, nextTick, reactive } from 'vue'
import { compile } from '@vue/compiler-dom'
import { compileScript, parse } from '@vue/compiler-sfc'
import { Chart } from 'chart.js'
import { NButton, NModal } from 'naive-ui'
import RecordLine from './RecordLine.vue'
import MoodRateLegend from '@/components/MoodRateLegend.vue'

const state = vi.hoisted(() => ({ board: null, report: null }))

vi.mock('vue', async (original) => ({
  ...(await original()),
  useSSRContext: () => ({ modules: new Set() })
}))
vi.mock('@/stores/mood_board', () => ({ useMoodBoardStore: () => state.board }))
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
vi.mock('naive-ui', async () => {
  const { h } = await import('vue')
  return {
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
  for (let turn = 0; turn < 4; turn++) await nextTick()
}

describe('mood curve visibility uses the existing Vue and Chart.js instance', () => {
  let app
  let root
  let chart
  let destroy

  beforeEach(async () => {
    state.board = reactive({ views: [], groupOrder: [], load: vi.fn() })
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
})
