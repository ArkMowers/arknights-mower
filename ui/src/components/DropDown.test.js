import { readFileSync } from 'node:fs'
import { parse } from '@vue/compiler-sfc'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { compile, createRenderer, h, nextTick, ref, ssrContextKey } from 'vue'
import * as NaiveUI from 'naive-ui'
import DropDown from './DropDown.vue'

vi.mock('naive-ui', async () => {
  const { defineComponent, h } = await import('vue')
  return {
    NButtonGroup: defineComponent({
      setup:
        (_, { attrs, slots }) =>
        () =>
          h('div', attrs, slots.default?.())
    }),
    NButton: defineComponent({
      inheritAttrs: false,
      props: { disabled: Boolean },
      setup:
        (props, { attrs, slots }) =>
        () =>
          h('button', { ...attrs, disabled: props.disabled }, [slots.icon?.(), slots.default?.()])
    }),
    NIcon: defineComponent({ setup: () => () => h('span') }),
    NDropdown: defineComponent({
      props: {
        trigger: String,
        show: Boolean,
        disabled: Boolean,
        options: Array,
        menuProps: Function,
        width: Number,
        placement: String
      },
      emits: ['update:show', 'select'],
      setup(props, { emit, slots }) {
        return () =>
          h(
            'div',
            {
              'data-dropdown-trigger': props.trigger,
              onClick: () => {
                if (props.trigger === 'click' && !props.disabled) emit('update:show', !props.show)
              },
              onMouseenter: () => {
                if (props.trigger === 'hover' && !props.disabled) emit('update:show', true)
              }
            },
            [
              slots.default?.(),
              props.show &&
                h(
                  'div',
                  {
                    ...props.menuProps?.(),
                    role: 'menu',
                    style: props.width ? { width: `${props.width}px` } : undefined,
                    'data-placement': props.placement
                  },
                  props.options.map((option) =>
                    h(
                      'button',
                      {
                        role: 'menuitem',
                        disabled: option.disabled,
                        onClick: (event) => {
                          event.stopPropagation()
                          emit('select', option.key)
                          emit('update:show', false)
                        }
                      },
                      option.label
                    )
                  )
                )
            ]
          )
      }
    })
  }
})

const { descriptor } = parse(readFileSync(new URL('./DropDown.vue', import.meta.url), 'utf8'))
const ClientDropDown = {
  ...DropDown,
  components: { ...NaiveUI },
  ssrRender: undefined,
  render: compile(descriptor.template.content, { hoistStatic: false }),
  setup: (props, context) => ({ ...DropDown.setup(props, context) })
}
const mounted = []
const all = (element) => [element, ...element.children.flatMap(all)]
const text = (element) => element.text + element.children.map(text).join('')
const node = (tag, text = '') => ({ tag, text, props: {}, children: [], parent: null })

function dispatch(element, eventName) {
  if (element.props.disabled) return
  let stopped = false
  const event = { stopPropagation: () => (stopped = true) }
  for (let current = element; current && !stopped; current = current.parent) {
    const handler = current.props[eventName]
    for (const callback of [handler].flat().filter(Boolean)) callback(event)
  }
}

function mount(mobile = true, overrides = {}) {
  const primary = vi.fn()
  const select = vi.fn()
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
      h(
        ClientDropDown,
        {
          select,
          options: [{ label: '载入心情数据', key: '1' }],
          menuLabel: '启动选项',
          ...overrides
        },
        { default: () => h('button', { onClick: primary }, '开始执行') }
      )
  })
  app.provide('mobile', ref(mobile))
  app.provide(ssrContextKey, { modules: new Set() })
  const root = node('root')
  app.mount(root)
  mounted.push(app)
  const find = (predicate) => {
    const element = all(root).find(predicate)
    expect(element).toBeTruthy()
    return element
  }
  return {
    primary,
    select,
    nodes: () => all(root),
    main: () => find((element) => element.tag === 'button' && text(element) === '开始执行'),
    arrow: () => find((element) => element.props['aria-label'] === '启动选项'),
    dropdown: () => find((element) => element.props['data-dropdown-trigger']),
    option: () => find((element) => element.props.role === 'menuitem')
  }
}

afterEach(() => {
  for (const app of mounted.splice(0)) app.unmount()
})

describe('split action dropdown', () => {
  it.each([true, false])(
    'fits glass menus to the complete button group on mobile=%s',
    async (mobile) => {
      const page = mount(mobile, { glassMenu: true, up: true })
      const group = page.nodes().find((element) => element.props.class?.includes('split-dropdown'))
      group.getBoundingClientRect = () => ({ width: 184 })
      page.arrow().getBoundingClientRect = () => ({ width: 44 })
      const open = () =>
        dispatch(mobile ? page.arrow() : page.main(), mobile ? 'onClick' : 'onMouseenter')
      open()
      await nextTick()
      let menu = page.nodes().find((element) => element.props.role === 'menu')
      expect(menu.props.style.width).toBe('184px')
      expect(menu.props['data-placement']).toBe('top-end')
      dispatch(page.option(), 'onClick')
      await nextTick()
      group.getBoundingClientRect = () => ({ width: 212 })
      open()
      await nextTick()
      menu = page.nodes().find((element) => element.props.role === 'menu')
      expect(menu.props.style.width).toBe('212px')
    }
  )

  it.each([true, false])('applies glass only when requested on mobile=%s', async (mobile) => {
    for (const glassMenu of [false, true]) {
      const page = mount(mobile, { glassMenu })
      dispatch(mobile ? page.arrow() : page.main(), mobile ? 'onClick' : 'onMouseenter')
      await nextTick()
      const menu = page.nodes().find((element) => element.props.role === 'menu')
      expect(menu).toBeTruthy()
      expect(menu.props.class).toBe(glassMenu ? 'mower-log-glass-menu' : undefined)
      if (!glassMenu) {
        expect(menu.props.style).toBeUndefined()
        expect(menu.props['data-placement']).toBe('bottom')
      }
    }
  })

  it('keeps the mobile primary action independent and opens the menu only from its arrow', async () => {
    const page = mount()
    expect(page.dropdown().props['data-dropdown-trigger']).toBe('click')
    expect(page.arrow().props['aria-haspopup']).toBe('menu')
    expect(page.arrow().props['aria-expanded']).toBe(false)
    dispatch(page.main(), 'onClick')
    await nextTick()
    expect(page.primary).toHaveBeenCalledOnce()
    expect(page.nodes().some((element) => element.props.role === 'menu')).toBe(false)
    dispatch(page.arrow(), 'onMouseenter')
    await nextTick()
    expect(page.arrow().props['aria-expanded']).toBe(false)
    dispatch(page.arrow(), 'onClick')
    await nextTick()
    expect(page.arrow().props['aria-expanded']).toBe(true)
    expect(page.primary).toHaveBeenCalledOnce()
    dispatch(page.option(), 'onClick')
    await nextTick()
    expect(page.select).toHaveBeenCalledExactlyOnceWith('1')
    expect(page.arrow().props['aria-expanded']).toBe(false)
  })

  it('keeps hover over the entire desktop button group as the menu trigger', async () => {
    const page = mount(false)
    expect(page.dropdown().props['data-dropdown-trigger']).toBe('hover')
    dispatch(page.main(), 'onClick')
    await nextTick()
    expect(page.primary).toHaveBeenCalledOnce()
    expect(page.arrow().props['aria-expanded']).toBe(false)
    dispatch(page.main(), 'onMouseenter')
    await nextTick()
    expect(page.arrow().props['aria-expanded']).toBe(true)
    dispatch(page.option(), 'onClick')
    await nextTick()
    expect(page.select).toHaveBeenCalledExactlyOnceWith('1')
    expect(page.arrow().props['aria-expanded']).toBe(false)
  })

  it.each([true, false])(
    'disables menu opening with disabled=true on mobile=%s',
    async (mobile) => {
      const page = mount(mobile, { disabled: true })
      expect(page.arrow().props.disabled).toBe(true)
      dispatch(page.arrow(), 'onClick')
      dispatch(page.main(), 'onMouseenter')
      await nextTick()
      expect(page.arrow().props['aria-expanded']).toBe(false)
      expect(page.select).not.toHaveBeenCalled()
    }
  )
})
