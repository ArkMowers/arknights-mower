import { readFileSync } from 'node:fs'
import { parse } from '@vue/compiler-sfc'
import { afterEach, expect, it, vi } from 'vitest'
import { compile, createRenderer, createSSRApp, h, nextTick, ssrContextKey } from 'vue'
import { renderToString } from 'vue/server-renderer'
import IncomeTimeline from './IncomeTimeline.vue'

vi.mock('vue', async (original) => ({
  ...(await original()),
  useSSRContext: () => ({ modules: new Set() })
}))
vi.mock('naive-ui', async (original) => ({
  ...(await original()),
  NCollapse: {
    inheritAttrs: false,
    setup:
      (_, { slots }) =>
      () =>
        slots.default?.()
  },
  NCollapseItem: {
    inheritAttrs: false,
    setup:
      (_, { slots }) =>
      () =>
        slots.default?.()
  }
}))
vi.mock('@/riic/vendor/components/workbench/ScheduleTimelineGantt.vue', () => ({
  default: { render: () => null }
}))
vi.mock('./IncomeHorizontalScroll.vue', () => ({
  default: {
    setup:
      (_, { slots }) =>
      () =>
        slots.default?.()
  }
}))

const operator = (overrides = {}) => ({
  operatorId: 'char_123_fang',
  operatorName: '芬',
  mainWorkHours: 9,
  substituteWorkHours: 3,
  workHours: 12,
  exhaustedHours: 2,
  restHours: 6,
  idleHours: 4,
  workFraction: 0.5,
  workRestRatio: 2,
  finalMorale: 0,
  ...overrides
})
const render = (operators) =>
  renderToString(
    createSSRApp({
      render: () =>
        h(IncomeTimeline, {
          report: { observedHours: 24, operators },
          timelineData: { observedHours: 24, operatorTracks: [] }
        })
    })
  )

it('shows source duty statistics and separates zero-mood occupancy from work', async () => {
  const html = await render([operator()])
  for (const label of ['工作占比', '工休比', '主班', '替班', '心情涣散', '期末心情']) {
    expect(html).toContain(label)
  }
  const row = html.match(/<tbody[^>]*>([\s\S]*?)<\/tbody>/)[1]
  const cells = [...row.matchAll(/<td[^>]*>([\s\S]*?)<\/td>/g)].map((match) =>
    match[1].replace(/<[^>]*>/g, '').trim()
  )
  expect(cells).toEqual(['芬', '50%', '2 : 1', '12', '9', '3', '6', '4', '2', '0 / 24'])
})

it('leaves the ratio unavailable when the source reports no rest', async () => {
  const html = await render([operator({ restHours: 0, workRestRatio: null })])
  expect(html).toContain('—')
  expect(html).not.toContain('Infinity')
  expect(html).not.toContain('NaN')
})

const mounted = []
afterEach(() => mounted.splice(0).forEach((app) => app.unmount()))
const { descriptor } = parse(readFileSync(new URL('./IncomeTimeline.vue', import.meta.url), 'utf8'))
const container = {
  setup:
    (_, { slots }) =>
    () =>
      h('div', slots.default?.())
}
const ClientTimeline = {
  ...IncomeTimeline,
  components: {
    NCollapse: container,
    NCollapseItem: container,
    NTable: {
      setup:
        (_, { slots }) =>
        () =>
          h('table', slots.default?.())
    },
    NInput: {
      props: ['value', 'inputProps'],
      emits: ['update:value'],
      setup:
        (props, { emit }) =>
        () =>
          h('input', {
            ...props.inputProps,
            value: props.value,
            onInput: (event) => emit('update:value', event.target.value)
          })
    },
    NPagination: {
      props: ['page', 'itemCount', 'pageSize'],
      emits: ['update:page'],
      setup:
        (props, { emit }) =>
        () =>
          h(
            'button',
            { onClick: () => emit('update:page', props.page + 1) },
            String(props.itemCount)
          )
    },
    IncomeHorizontalScroll: container,
    ScheduleTimelineGantt: { render: () => null }
  },
  ssrRender: undefined,
  render: compile(descriptor.template.content, { hoistStatic: false }),
  setup: (props, context) => ({ ...IncomeTimeline.setup(props, context) })
}
const node = (tag, text = '') => ({ tag, text, props: {}, children: [], parent: null })
const all = (element) => [element, ...element.children.flatMap(all)]
const nodeText = (element) => element.text + element.children.map(nodeText).join('')
function mount(operators) {
  const renderer = createRenderer({
    createElement: node,
    createText: (value) => node('text', value),
    createComment: () => node('comment'),
    setText: (element, value) => (element.text = value),
    setElementText: (element, value) => {
      element.text = value
      element.children = []
    },
    patchProp: (element, key, _previous, value) => (element.props[key] = value),
    parentNode: (element) => element.parent,
    nextSibling: (element) =>
      element.parent?.children[element.parent.children.indexOf(element) + 1],
    insert(element, parent, anchor = null) {
      if (element.parent)
        element.parent.children.splice(element.parent.children.indexOf(element), 1)
      element.parent = parent
      const index = anchor ? parent.children.indexOf(anchor) : -1
      parent.children.splice(index < 0 ? parent.children.length : index, 0, element)
    },
    remove(element) {
      element.parent?.children.splice(element.parent.children.indexOf(element), 1)
      element.parent = null
    }
  })
  const app = renderer.createApp(ClientTimeline, { report: { observedHours: 24, operators } })
  app.provide(ssrContextKey, { modules: new Set() })
  const root = node('root')
  app.mount(root)
  mounted.push(app)
  return {
    root,
    rows: () =>
      all(root)
        .filter((element) => element.tag === 'tbody')
        .flatMap((body) =>
          all(body)
            .filter((element) => element.tag === 'tr')
            .map(nodeText)
        ),
    search: async (value) => {
      all(root)
        .find((element) => element.tag === 'input')
        .props.onInput({ target: { value } })
      await nextTick()
    }
  }
}

it('searches all operators before pagination and resets the page when searching or clearing', async () => {
  const operators = Array.from({ length: 21 }, (_, index) =>
    operator({ operatorId: `operator-${index}`, operatorName: `干员${index + 1}` })
  )
  operators.push(operator({ operatorName: '芬' }))
  const view = mount(operators)
  expect(view.rows()).toHaveLength(20)
  all(view.root)
    .find((element) => element.tag === 'button')
    .props.onClick()
  await nextTick()
  expect(view.rows()).toHaveLength(2)
  await view.search(' 干员 ')
  expect(view.rows()).toHaveLength(20)
  expect(view.rows()[0]).toContain('干员1')
  expect(all(view.root).find((element) => element.tag === 'button').text).toBe('21')
  await view.search('芬')
  expect(view.rows()).toHaveLength(1)
  expect(view.rows()[0]).toContain('芬')
  expect(all(view.root).some((element) => element.tag === 'button')).toBe(false)
  await view.search('不存在')
  expect(view.rows()).toEqual(['没有匹配的干员'])
  await view.search('')
  expect(view.rows()).toHaveLength(20)
  expect(view.rows()[0]).toContain('干员1')
  expect(operators).toHaveLength(22)
})

it('matches partial names without case sensitivity and handles reports without operators', async () => {
  const view = mount([operator({ operatorName: 'Lancet-2' }), operator()])
  await view.search(' LANCET ')
  expect(view.rows()).toHaveLength(1)
  expect(view.rows()[0]).toContain('Lancet-2')
  expect(mount(undefined).rows()).toEqual(['暂无干员数据'])
})

it.each([
  ['sikadi', '斯卡蒂'],
  ['SKD', '斯卡蒂'],
  ['lvgu', '旅骨']
])('reuses operator name matching for %s', async (query, name) => {
  const view = mount([
    operator({ operatorId: 'char_263_skadi', operatorName: '斯卡蒂' }),
    operator({ operatorId: 'char_444_lu', operatorName: '旅骨' }),
    operator({ operatorId: 'char_123_fang', operatorName: '芬' })
  ])
  await view.search(query)
  expect(view.rows()).toHaveLength(1)
  expect(view.rows()[0]).toContain(name)
})
