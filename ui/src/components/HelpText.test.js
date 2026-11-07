import { readFileSync } from 'node:fs'
import { parse } from '@vue/compiler-sfc'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { compile, createRenderer, h, nextTick, ssrContextKey } from 'vue'
import * as NaiveUI from 'naive-ui'
import HelpText from './HelpText.vue'

vi.mock('naive-ui', async () => {
  const { cloneVNode, defineComponent, h } = await import('vue')
  return {
    NTooltip: defineComponent({
      props: ['trigger', 'show'],
      emits: ['update:show'],
      setup(props, { emit, slots }) {
        return () =>
          h('div', { 'data-tooltip-host': true, onOutside: () => emit('update:show', false) }, [
            cloneVNode(slots.trigger()[0], {
              onClick: () => {
                if (props.trigger === 'click') emit('update:show', !props.show)
              }
            }),
            props.show && h('aside', { role: 'tooltip' }, slots.default?.())
          ])
      }
    }),
    NButton: defineComponent({
      setup:
        (_, { attrs, slots }) =>
        () =>
          h('button', attrs, slots.icon?.())
    }),
    NIcon: defineComponent({ setup: () => () => h('span') })
  }
})

const { descriptor } = parse(readFileSync(new URL('./HelpText.vue', import.meta.url), 'utf8'))
const ClientHelpText = {
  ...HelpText,
  components: { ...NaiveUI },
  ssrRender: undefined,
  render: compile(descriptor.template.content, { hoistStatic: false }),
  setup: (props, context) => ({ ...HelpText.setup(props, context) })
}
const mounted = []
const all = (element) => [element, ...element.children.flatMap(all)]
const node = (tag, text = '') => ({ tag, text, props: {}, children: [], parent: null })

function dispatch(element, name) {
  let stopped = false
  const event = { stopPropagation: () => (stopped = true) }
  for (let current = element; current && !stopped; current = current.parent) {
    for (const handler of [current.props[name]].flat().filter(Boolean)) handler(event)
  }
}

function mount(props = {}) {
  const parentAction = vi.fn()
  const renderer = createRenderer({
    createElement: node,
    createText: (value) => node('#text', value),
    createComment: () => node('#comment'),
    setText: (element, value) => (element.text = value),
    setElementText(element, value) {
      element.text = value
      element.children = []
    },
    patchProp: (element, key, _previous, value) => (element.props[key] = value),
    parentNode: (element) => element.parent,
    nextSibling: (element) =>
      element.parent?.children[element.parent.children.indexOf(element) + 1],
    insert(element, parent, anchor = null) {
      if (element.parent) {
        const siblings = element.parent.children
        siblings.splice(siblings.indexOf(element), 1)
      }
      element.parent = parent
      const index = anchor ? parent.children.indexOf(anchor) : -1
      parent.children.splice(index < 0 ? parent.children.length : index, 0, element)
    },
    remove(element) {
      const siblings = element.parent?.children
      if (siblings) siblings.splice(siblings.indexOf(element), 1)
      element.parent = null
    }
  })
  const app = renderer.createApp({
    render: () =>
      h('div', { onClick: parentAction }, [
        h(ClientHelpText, { label: '新增任务说明', ...props }, () =>
          h('a', { href: '/help' }, '说明链接')
        )
      ])
  })
  const root = node('root')
  app.provide(ssrContextKey, { modules: new Set() })
  app.mount(root)
  mounted.push(app)
  const find = (predicate) => {
    const element = all(root).find(predicate)
    expect(element).toBeTruthy()
    return element
  }
  return {
    parentAction,
    button: () => find((element) => element.tag === 'button'),
    trigger: () => find((element) => element.props.class === 'help'),
    host: () => find((element) => element.props['data-tooltip-host']),
    tooltip: () => all(root).find((element) => element.props.role === 'tooltip')
  }
}

beforeEach(() => vi.useFakeTimers())
afterEach(() => {
  for (const app of mounted.splice(0)) app.unmount()
  vi.clearAllTimers()
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

describe('help text', () => {
  it('centers touch help within the visible viewport and tracks resize only while open', async () => {
    const viewport = Object.assign(new EventTarget(), { width: 390, offsetLeft: 0, offsetTop: 0 })
    vi.stubGlobal('visualViewport', viewport)
    vi.stubGlobal('document', { documentElement: {} })
    vi.stubGlobal('getComputedStyle', () => ({ zoom: '1' }))
    vi.stubGlobal('addEventListener', vi.fn())
    vi.stubGlobal('removeEventListener', vi.fn())
    const page = mount({ clickable: true, centered: true })
    let bounds = { left: 216, right: 244, top: 723 }
    page.trigger().getBoundingClientRect = () => bounds
    expect(addEventListener).not.toHaveBeenCalled()
    dispatch(page.button(), 'onClick')
    await nextTick()
    expect(page.tooltip()).toBeTruthy()
    expect(page.host().props.style.width).toBe('358px')
    expect(page.host().props.style.boxSizing).toBe('border-box')
    expect(page.host().props.style.left).toBe('-200px')
    expect(addEventListener).toHaveBeenCalledOnce()

    viewport.width = 320
    bounds = { left: 198, right: 222, top: 726 }
    viewport.dispatchEvent(new Event('resize'))
    await nextTick()
    expect(page.host().props.style.width).toBe('288px')
    expect(page.host().props.style.left).toBe('-182px')
    page.host().props.onOutside()
    await nextTick()
    expect(page.tooltip()).toBeUndefined()
    expect(removeEventListener).toHaveBeenCalledWith('resize', addEventListener.mock.calls[0][1])
    viewport.width = 390
    viewport.dispatchEvent(new Event('resize'))
    await nextTick()
    expect(page.host().props.style.width).toBe('288px')
  })

  it('opens and closes touch help from its button and responds to outside dismissal', async () => {
    const page = mount({ clickable: true })
    expect(page.tooltip()).toBeUndefined()
    expect(page.button().props['aria-expanded']).toBe(false)
    dispatch(page.button(), 'onClick')
    await nextTick()
    expect(page.tooltip()).toBeTruthy()
    expect(page.button().props['aria-expanded']).toBe(true)
    expect(page.parentAction).not.toHaveBeenCalled()

    dispatch(page.button(), 'onClick')
    await nextTick()
    expect(page.tooltip()).toBeUndefined()
    dispatch(page.button(), 'onClick')
    await nextTick()
    page.host().props.onOutside()
    await nextTick()
    expect(page.tooltip()).toBeUndefined()
    expect(page.button().props['aria-expanded']).toBe(false)
  })

  it('keeps hover help open while crossing to its links and then closes after the delay', async () => {
    const page = mount()
    dispatch(page.trigger(), 'onPointerenter')
    await nextTick()
    expect(page.tooltip()).toBeTruthy()
    dispatch(page.trigger(), 'onPointerleave')
    await vi.advanceTimersByTimeAsync(99)
    expect(page.tooltip()).toBeTruthy()
    const content = page.tooltip().children.find((element) => element.props.onPointerenter)
    dispatch(content, 'onPointerenter')
    await vi.advanceTimersByTimeAsync(100)
    expect(page.tooltip()).toBeTruthy()
    dispatch(content, 'onPointerleave')
    await vi.advanceTimersByTimeAsync(100)
    expect(page.tooltip()).toBeUndefined()
  })

  it('preserves keyboard focus help when clickable mode is not requested', async () => {
    const page = mount()
    dispatch(page.trigger(), 'onFocusin')
    await nextTick()
    expect(page.tooltip()).toBeTruthy()
    dispatch(page.trigger(), 'onFocusout')
    await nextTick()
    expect(page.tooltip()).toBeUndefined()
    expect(page.button().props['aria-expanded']).toBeUndefined()
  })
})
