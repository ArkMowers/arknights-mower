import { readFileSync } from 'node:fs'
import { parse } from '@vue/compiler-sfc'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { compile, createRenderer, h, nextTick, reactive, ssrContextKey } from 'vue'
import { NPopover } from 'naive-ui'
import LogOperator from './LogOperator.vue'
import TaskActionSubjects from './TaskActionSubjects.vue'

vi.mock('naive-ui', async () => {
  const { defineComponent, h } = await import('vue')
  return {
    NPopover: defineComponent({
      inheritAttrs: false,
      props: ['show'],
      setup:
        (props, { slots, attrs }) =>
        () =>
          props.show
            ? h('aside', { ...attrs, 'data-roster-portal': true }, slots.default?.())
            : null
    })
  }
})
vi.mock('./LogOperator.vue', async () => {
  const { defineComponent, h } = await import('vue')
  return {
    default: defineComponent({
      props: { name: String, size: Number, showName: Boolean },
      setup: (props) => () =>
        h(
          'span',
          { 'data-operator-name': props.name, 'data-size': props.size },
          props.showName ? props.name : ''
        )
    })
  }
})

const { descriptor } = parse(
  readFileSync(new URL('./TaskActionSubjects.vue', import.meta.url), 'utf8')
)
const client = {
  ...TaskActionSubjects,
  components: { NPopover, LogOperator },
  ssrRender: undefined,
  render: compile(descriptor.template.content),
  setup: (props, context) => ({ ...TaskActionSubjects.setup(props, context) })
}
const mounted = []
const all = (node) => [node, ...node.children.flatMap(all)]
const text = (node) => node.text + node.children.map(text).join('')

function mount(overrides = {}) {
  const props = reactive({ actions: [], facilityPlan: {}, ...overrides })
  const node = (tag, value = '') => ({
    tag,
    text: value,
    props: {},
    children: [],
    parent: null,
    getBoundingClientRect: () => ({ left: 20, right: 120, top: 100 }),
    contains(target) {
      return all(this).includes(target)
    }
  })
  const renderer = createRenderer({
    createElement: node,
    createText: (value) => node('#text', value),
    createComment: () => node('#comment'),
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
      element.parent.children.splice(element.parent.children.indexOf(element), 1)
    }
  })
  const app = renderer.createApp({ render: () => h(client, props) })
  app.provide(ssrContextKey, { modules: new Set() })
  const root = node('root')
  app.mount(root)
  mounted.push(app)
  return {
    props,
    all: () => all(root),
    buttons: () => all(root).filter((element) => element.tag === 'button'),
    popups: () => all(root).filter((element) => element.tag === 'aside'),
    text: () => text(root)
  }
}

afterEach(() => {
  for (const app of mounted.splice(0)) app.unmount()
  vi.useRealTimers()
})

const operators = ['芬', '红', '陈', '阿米娅', '凯尔希', '白面鸮', '赫默', '雷蛇']
const actions = operators.map((subject) => ({ kind: 'operator', subject, action: '下班' }))
const rosters = [
  ['people', actions, operators],
  [
    'group',
    [{ kind: 'group', subject: '感知', action: '上班', members: ['阿米娅', '凯尔希'] }],
    ['阿米娅', '凯尔希']
  ]
]

describe('compact task action subjects', () => {
  it('shows one person with two horizontal tail portraits and the remaining count', () => {
    const page = mount({ actions })
    const people = page.buttons()[0]
    expect(people.props['aria-label']).toBe(`下班：${operators.join('、')}，共8人`)
    expect(people.props['aria-expanded']).toBe(false)
    const portraits = page.all().filter((element) => element.props['data-operator-name'])
    expect(portraits.map((element) => element.props['data-operator-name'])).toEqual(
      operators.slice(0, 3)
    )
    const stack = page
      .all()
      .find((element) => element.props.class?.includes('task-action-subjects__stack'))
    expect(
      all(stack)
        .filter((element) => element.props['data-operator-name'])
        .map((element) => element.props['data-operator-name'])
    ).toEqual(operators.slice(0, 3))
    expect(portraits.every((element) => element.props.tabindex === -1)).toBe(true)
    expect(page.text()).toBe('+7下班')
    expect(page.popups()).toHaveLength(0)
    expect(
      page.all().find((element) => element.props['data-source-text']).props['data-source-text']
    ).toBe(operators.join('、') + '下班')
  })

  it('keeps the visible name after the whole avatar stack without duplicating names', () => {
    const page = mount({ actions, showNames: true })
    const people = page.buttons()[0]
    const stack = all(people).find((element) =>
      element.props.class?.includes('task-action-subjects__stack')
    )
    expect(text(stack)).toBe('')
    expect(text(people)).toBe('芬+7')
    expect(page.text()).toBe('芬+7下班')
    expect(all(people).filter((element) => element.props['data-operator-name'])).toHaveLength(3)
  })

  it('keeps the queue roster available for a single operator', async () => {
    const page = mount({ actions: actions.slice(0, 1) })
    const [trigger] = page.buttons()
    trigger.props.onMouseenter({ currentTarget: trigger })
    await nextTick()
    expect(page.popups()).toHaveLength(1)
    expect(text(page.popups()[0])).toContain('芬')
  })

  it('opens the complete roster on hover and focus, then closes it with Escape', async () => {
    vi.useFakeTimers()
    const page = mount({ actions })
    const trigger = page.buttons()[0]
    trigger.props.onMouseenter({ currentTarget: trigger })
    await nextTick()
    expect(page.popups()).toHaveLength(1)
    expect(page.popups()[0].props.class).toContain('mower-log-glass-surface')
    expect(text(page.popups()[0])).toContain(operators.join(''))
    trigger.props.onMouseleave()
    trigger.props.onFocus({ currentTarget: trigger })
    await nextTick()
    trigger.props.onKeydown({ key: 'Escape', stopPropagation: vi.fn() })
    await nextTick()
    expect(page.popups()).toHaveLength(0)
    expect(trigger.props['aria-expanded']).toBe(false)
  })

  it.each(rosters)(
    'keeps the %s roster open when polling replaces actions with equivalent objects',
    async (_kind, initial, members) => {
      const page = mount({ actions: initial })
      const trigger = page.buttons()[0]
      trigger.props.onMouseenter({ currentTarget: trigger })
      await nextTick()
      expect(page.popups()).toHaveLength(1)

      page.props.actions = JSON.parse(JSON.stringify(initial))
      await nextTick()

      expect(page.popups()).toHaveLength(1)
      expect(text(page.popups()[0])).toContain(members.join(''))
      expect(page.buttons()[0].props['aria-expanded']).toBe(true)
    }
  )

  it.each(rosters)(
    'keeps the %s roster open when an unrelated facility plan is refreshed',
    async (_kind, initial, members) => {
      const page = mount({ actions: initial })
      const trigger = page.buttons()[0]
      trigger.props.onMouseenter({ currentTarget: trigger })
      await nextTick()
      expect(page.popups()).toHaveLength(1)

      page.props.facilityPlan = { central: { plans: [{ agent: '陈', group: '其他组' }] } }
      await nextTick()

      expect(page.popups()).toHaveLength(1)
      expect(text(page.popups()[0])).toContain(members.join(''))
      expect(page.buttons()[0].props['aria-expanded']).toBe(true)
    }
  )

  it('keeps the active group open when another action changes', async () => {
    const group = {
      kind: 'group',
      subject: '感知',
      action: '上班',
      members: ['阿米娅', '凯尔希']
    }
    const page = mount({
      actions: [group, { kind: 'operator', subject: '芬', action: '休息' }]
    })
    const trigger = page.buttons()[0]
    trigger.props.onMouseenter({ currentTarget: trigger })
    await nextTick()

    page.props.actions = [{ ...group }, { kind: 'operator', subject: '陈', action: '休息' }]
    await nextTick()

    expect(page.popups()).toHaveLength(1)
    expect(text(page.popups()[0])).toContain('阿米娅凯尔希')
    expect(text(page.popups()[0])).not.toContain('陈')
  })

  it.each([
    [
      'group membership',
      [{ kind: 'group', subject: '感知', action: '上班', members: ['阿米娅', '凯尔希'] }],
      [{ kind: 'group', subject: '感知', action: '上班', members: ['阿米娅', '陈'] }]
    ],
    [
      'group action',
      [{ kind: 'group', subject: '感知', action: '上班', members: ['阿米娅', '凯尔希'] }],
      [{ kind: 'group', subject: '感知', action: '下班', members: ['阿米娅', '凯尔希'] }]
    ],
    [
      'personal membership',
      [{ kind: 'operator', subject: '芬', action: '下班' }],
      [{ kind: 'operator', subject: '红', action: '下班' }]
    ],
    [
      'personal action',
      [{ kind: 'operator', subject: '芬', action: '下班' }],
      [{ kind: 'operator', subject: '芬', action: '休息' }]
    ]
  ])('closes a stale roster when the active %s changes', async (_kind, initial, changed) => {
    const page = mount({ actions: initial })
    const trigger = page.buttons()[0]
    trigger.props.onMouseenter({ currentTarget: trigger })
    await nextTick()
    expect(page.popups()).toHaveLength(1)

    page.props.actions = changed
    await nextTick()

    expect(page.popups()).toHaveLength(0)
    expect(page.buttons()[0].props['aria-expanded']).toBe(false)
  })

  it('keeps the roster open across the popover padding and closes after leaving its container', async () => {
    vi.useFakeTimers()
    const page = mount({ actions })
    const trigger = page.buttons()[0]
    trigger.props.onMouseenter({ currentTarget: trigger })
    await nextTick()
    trigger.props.onMouseleave()
    await vi.advanceTimersByTimeAsync(80)
    const popup = page.popups()[0]
    popup.props.onMouseenter?.({ currentTarget: popup })

    await vi.advanceTimersByTimeAsync(1000)
    await nextTick()

    expect(page.popups()).toHaveLength(1)
    expect(trigger.props['aria-expanded']).toBe(true)
    page.popups()[0].props.onMouseleave?.()
    await vi.advanceTimersByTimeAsync(121)
    await nextTick()
    expect(page.popups()).toHaveLength(0)
  })

  it('keeps a touch-open roster pinned despite synthetic hover and toggles it on the next tap', async () => {
    const page = mount({ actions })
    const trigger = page.buttons()[0]
    trigger.props.onMouseenter({ currentTarget: trigger })
    trigger.props.onFocus({ currentTarget: trigger })
    trigger.props.onClick({ currentTarget: trigger })
    trigger.props.onMouseleave()
    await nextTick()
    expect(trigger.props['aria-expanded']).toBe(true)
    trigger.props.onMouseenter({ currentTarget: trigger })
    trigger.props.onClick({ currentTarget: trigger })
    await nextTick()
    expect(trigger.props['aria-expanded']).toBe(false)
    expect(page.popups()).toHaveLength(0)
  })

  it('uses group snapshots for the full roster and does not invent members for an empty snapshot', async () => {
    const page = mount({
      actions: [{ kind: 'group', subject: '感知', action: '上班', members: ['阿米娅', '凯尔希'] }],
      facilityPlan: { central: { plans: [{ agent: '陈', group: '感知' }] } }
    })
    const trigger = page.buttons()[0]
    expect(page.text()).toBe('感知上班')
    trigger.props.onClick({ currentTarget: trigger })
    await nextTick()
    expect(text(page.popups()[0])).toContain('阿米娅凯尔希')
    expect(text(page.popups()[0])).not.toContain('陈')
    page.props.actions[0].members = []
    await nextTick()
    page.buttons()[0].props.onClick({ currentTarget: page.buttons()[0] })
    await nextTick()
    expect(text(page.popups()[0])).toContain('暂无成员信息')
    expect(text(page.popups()[0])).not.toContain('陈')
  })
})
