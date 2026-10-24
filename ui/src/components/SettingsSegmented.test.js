import { readFileSync } from 'node:fs'
import { parse } from '@vue/compiler-sfc'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { compile, createRenderer, h, markRaw, nextTick, reactive, ssrContextKey } from 'vue'
import * as NaiveUI from 'naive-ui'
import SettingsSegmented from './SettingsSegmented.vue'

vi.mock('naive-ui', async () => {
  const { cloneVNode, defineComponent, Fragment, h } = await import('vue')
  const NTab = defineComponent({
    inheritAttrs: false,
    props: { name: String, disabled: Boolean },
    setup:
      (props, { attrs, slots }) =>
      () =>
        h('div', { ...attrs, 'data-option-value': props.name }, slots.default?.())
  })
  function flatten(children) {
    return children.flatMap((child) => {
      if (Array.isArray(child)) return flatten(child)
      if (child.type === Fragment) return flatten(child.children ?? [])
      return [child]
    })
  }
  return {
    NTab,
    NTabs: defineComponent({
      inheritAttrs: false,
      props: { value: String, type: String, size: String, animated: Boolean },
      emits: ['update:value'],
      setup(props, { attrs, slots, emit }) {
        return () =>
          h(
            'div',
            { ...attrs, 'data-selected-value': props.value },
            flatten(slots.default?.() ?? [])
              .filter((tab) => tab.type === NTab)
              .map((tab) =>
                cloneVNode(tab, {
                  onClick: () => {
                    if (!tab.props.disabled) emit('update:value', tab.props.name)
                  }
                })
              )
          )
      }
    }),
    NIcon: defineComponent({
      props: { component: Object, size: [Number, String] },
      setup: (props) => () =>
        h('span', { 'data-option-icon': true }, props.component ? h(props.component) : [])
    })
  }
})

const { descriptor } = parse(
  readFileSync(new URL('./SettingsSegmented.vue', import.meta.url), 'utf8')
)
const ClientSegmented = {
  ...SettingsSegmented,
  components: { ...NaiveUI },
  ssrRender: undefined,
  render: compile(descriptor.template.content, { hoistStatic: false }),
  setup: (props, context) => ({ ...SettingsSegmented.setup(props, context) })
}
const mounted = []

function node(tag, text = '') {
  return { tag, text, props: {}, children: [], parent: null }
}
const all = (element) => [element, ...element.children.flatMap(all)]
const text = (element) => element.text + element.children.map(text).join('')

function mount(overrides = {}) {
  const props = reactive({
    value: 'light',
    options: [
      { value: 'light', label: '浅色' },
      { value: 'dark', label: '深色' },
      { value: 'system', label: '跟随系统' }
    ],
    label: '界面主题',
    disabled: false,
    busy: false,
    ...overrides
  })
  const update = vi.fn()
  const renderer = createRenderer({
    createElement: (tag) => node(tag),
    createText: (value) => node('#text', value),
    createComment: () => node('#comment'),
    setText: (element, value) => (element.text = value),
    setElementText(element, value) {
      element.text = value
      element.children = []
    },
    parentNode: (element) => element.parent,
    nextSibling: (element) =>
      element.parent?.children[element.parent.children.indexOf(element) + 1],
    patchProp: (element, key, _previous, value) => (element.props[key] = value),
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
    render: () => h(ClientSegmented, { ...props, 'onUpdate:value': update })
  })
  app.provide(ssrContextKey, { modules: new Set() })
  const root = node('root')
  app.mount(root)
  mounted.push(app)
  return {
    props,
    update,
    choices: () => all(root).filter((element) => element.tag === 'button'),
    group: () => all(root).find((element) => element.props.role === 'group'),
    options: () => all(root).filter((element) => element.props['data-option-value'])
  }
}

async function click(button) {
  for (let current = button; current; current = current.parent) {
    current.props.onClick?.({ target: button })
  }
  await nextTick()
}

afterEach(() => {
  for (const app of mounted.splice(0)) app.unmount()
})

describe('shared settings segmented selection', () => {
  it('renders every option with its supplied value and readable label', () => {
    const page = mount()
    expect(page.group().props['aria-label']).toBe('界面主题')
    expect(page.options().map((option) => option.props['data-option-value'])).toEqual([
      'light',
      'dark',
      'system'
    ])
    expect(page.choices().map((choice) => text(choice).trim())).toEqual([
      '浅色',
      '深色',
      '跟随系统'
    ])
    expect(page.choices().map((choice) => choice.props['aria-pressed'])).toEqual([
      true,
      false,
      false
    ])
    expect(page.update).not.toHaveBeenCalled()
  })

  it('emits the selected option value and waits for the owning setting to update', async () => {
    const page = mount()
    await click(page.choices()[1])
    expect(page.update).toHaveBeenCalledExactlyOnceWith('dark')
    expect(page.props.value).toBe('light')
    expect(page.choices()[0].props['aria-pressed']).toBe(true)
    page.props.value = 'dark'
    await nextTick()
    expect(page.choices().map((choice) => choice.props['aria-pressed'])).toEqual([
      false,
      true,
      false
    ])
  })

  it('prevents disabled selection and accepts a later explicit selection after enabling', async () => {
    const page = mount({ disabled: true })
    expect(page.choices().every((choice) => choice.props.disabled)).toBe(true)
    await click(page.choices()[1])
    expect(page.update).not.toHaveBeenCalled()
    page.props.disabled = false
    await nextTick()
    expect(page.choices().every((choice) => !choice.props.disabled)).toBe(true)
    expect(page.update).not.toHaveBeenCalled()
    await click(page.choices()[1])
    expect(page.update).toHaveBeenCalledExactlyOnceWith('dark')
  })

  it('blocks only a disabled option while leaving other choices usable', async () => {
    const page = mount({
      options: [
        { value: 'light', label: '浅色' },
        { value: 'dark', label: '深色', disabled: true },
        { value: 'system', label: '跟随系统' }
      ]
    })
    expect(page.choices().map((choice) => Boolean(choice.props.disabled))).toEqual([
      false,
      true,
      false
    ])
    await click(page.choices()[1])
    expect(page.update).not.toHaveBeenCalled()
    await click(page.choices()[2])
    expect(page.update).toHaveBeenCalledExactlyOnceWith('system')
  })

  it('announces ongoing work without emitting a selection merely because busy changes', async () => {
    const page = mount({ busy: true })
    expect(page.group().props['aria-busy']).toBe(true)
    expect(page.update).not.toHaveBeenCalled()
    page.props.busy = false
    await nextTick()
    expect(page.group().props['aria-busy']).toBe(false)
    expect(page.update).not.toHaveBeenCalled()
  })

  it('keeps option labels readable when an optional decorative icon is supplied', () => {
    const icon = markRaw({ render: () => h('svg', { 'data-theme-icon': true }) })
    const page = mount({
      options: [
        { value: 'light', label: '浅色', icon },
        { value: 'dark', label: '深色' }
      ]
    })
    const [withIcon, withoutIcon] = page.choices()
    expect(text(withIcon).trim()).toBe('浅色')
    expect(text(withoutIcon).trim()).toBe('深色')
    expect(all(withIcon).some((element) => element.props['data-theme-icon'])).toBe(true)
    expect(all(withoutIcon).some((element) => element.props['data-option-icon'])).toBe(false)
    expect(
      all(withIcon).find((element) => element.props['data-option-icon']).props['aria-hidden']
    ).toBe('true')
  })
})
