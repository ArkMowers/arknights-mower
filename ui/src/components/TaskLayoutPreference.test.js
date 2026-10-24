import { readFileSync } from 'node:fs'
import { parse } from '@vue/compiler-sfc'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { compile, createRenderer, defineComponent, h, nextTick, ssrContextKey } from 'vue'
import { createPinia } from 'pinia'
import axios from 'axios'
import { useGuiStore } from '@/stores/gui'
import TaskLayoutPreference from './TaskLayoutPreference.vue'
import SettingsSegmented from './SettingsSegmented.vue'

vi.mock('axios', () => ({ default: { get: vi.fn(), put: vi.fn() } }))
vi.mock('./SettingsSegmented.vue', async () => {
  const { defineComponent, h } = await import('vue')
  return {
    default: defineComponent({
      props: ['value', 'options', 'disabled', 'busy', 'label'],
      emits: ['update:value'],
      setup:
        (props, { emit }) =>
        () =>
          h(
            'div',
            { 'aria-label': props.label, 'aria-busy': props.busy },
            props.options.map((option) =>
              h(
                'button',
                {
                  disabled: props.disabled,
                  'aria-pressed': props.value === option.value,
                  onClick: () => !props.disabled && emit('update:value', option.value)
                },
                option.label
              )
            )
          )
    })
  }
})

const wrapper = defineComponent({
  inheritAttrs: false,
  setup:
    (_, { attrs, slots }) =>
    () =>
      h('div', attrs, slots.default?.())
})
const { descriptor } = parse(
  readFileSync(new URL('./TaskLayoutPreference.vue', import.meta.url), 'utf8')
)
const ClientPreference = {
  ...TaskLayoutPreference,
  components: { NFormItem: wrapper, NAlert: wrapper, NButton: 'button', SettingsSegmented },
  ssrRender: undefined,
  render: compile(descriptor.template.content, { hoistStatic: false }),
  setup: (props, context) => ({ ...TaskLayoutPreference.setup(props, context) })
}
const mounted = []
const node = (tag, text = '') => ({ tag, text, props: {}, children: [], parent: null })
const all = (element) => [element, ...element.children.flatMap(all)]
const text = (element) => element.text + element.children.map(text).join('')

function mount() {
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
  const pinia = createPinia()
  const app = renderer.createApp(ClientPreference)
  app.use(pinia)
  app.provide(ssrContextKey, { modules: new Set() })
  const gui = useGuiStore(pinia)
  const root = node('root')
  app.mount(root)
  mounted.push({ app, gui })
  return {
    gui,
    nodes: () => all(root),
    button: (label) =>
      all(root).find((element) => element.tag === 'button' && text(element).trim() === label),
    alert: () => all(root).find((element) => element.props.role === 'alert')
  }
}

async function flush() {
  await Promise.resolve()
  await nextTick()
  await Promise.resolve()
  await nextTick()
}

beforeEach(() => {
  axios.get.mockResolvedValue({
    data: { software_version_display: 'version', task_settings_layout: 'checklist' }
  })
  axios.put.mockImplementation(async (_url, data) => ({ data }))
})

afterEach(() => {
  for (const { app, gui } of mounted.splice(0)) {
    app.unmount()
    gui.$dispose()
  }
  vi.resetAllMocks()
})

describe('task layout preference', () => {
  it('loads the saved layout before enabling the two concise choices', async () => {
    let resolve
    axios.get.mockReturnValueOnce(new Promise((done) => (resolve = done)))
    const page = mount()
    expect(page.button('任务清单').props.disabled).toBe(true)
    expect(page.button('瀑布流').props.disabled).toBe(true)
    expect(page.nodes().some((element) => element.props.label === '任务配置显示')).toBe(true)
    resolve({ data: { software_version_display: 'channel', task_settings_layout: 'waterfall' } })
    await flush()
    expect(page.button('瀑布流').props['aria-pressed']).toBe(true)
    expect(page.button('任务清单').props.disabled).toBe(false)
    expect(page.alert()).toBeUndefined()
    expect(axios.put).not.toHaveBeenCalled()
  })

  it('disables the choices during saving, then restores and retries a failed layout', async () => {
    const page = mount()
    await flush()
    let reject
    axios.put.mockReturnValueOnce(new Promise((_, fail) => (reject = fail)))
    page.button('瀑布流').props.onClick()
    await nextTick()
    expect(page.button('瀑布流').props['aria-pressed']).toBe(true)
    expect(page.button('任务清单').props.disabled).toBe(true)
    reject(new Error('offline'))
    await flush()
    expect(page.button('任务清单').props['aria-pressed']).toBe(true)
    expect(text(page.alert())).toContain('已恢复原来的显示')
    expect(page.gui.error).toBe('')
    page.button('重试').props.onClick()
    await flush()
    expect(page.button('瀑布流').props['aria-pressed']).toBe(true)
    expect(page.alert()).toBeUndefined()
    expect(axios.put.mock.calls.map(([, payload]) => payload)).toEqual([
      { task_settings_layout: 'waterfall' },
      { task_settings_layout: 'waterfall' }
    ])
  })

  it('offers retry after the initial read fails and keeps edits disabled', async () => {
    axios.get.mockRejectedValueOnce(new Error('offline'))
    const page = mount()
    await flush()
    expect(page.button('瀑布流').props.disabled).toBe(true)
    expect(text(page.alert())).toContain('读取失败')
    page.button('重试').props.onClick()
    await flush()
    expect(page.button('瀑布流').props.disabled).toBe(false)
    expect(page.alert()).toBeUndefined()
    expect(axios.get).toHaveBeenCalledTimes(2)
    expect(axios.put).not.toHaveBeenCalled()
  })
})
