import { readFileSync } from 'node:fs'
import { parse } from '@vue/compiler-sfc'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { compile, createRenderer, defineComponent, h, nextTick, ssrContextKey } from 'vue'
import { createPinia } from 'pinia'
import axios from 'axios'
import { useGuiStore } from '@/stores/gui'
import VersionWatermarkPreference from './VersionWatermarkPreference.vue'

vi.mock('axios', () => ({ default: { get: vi.fn(), put: vi.fn() } }))

const wrapper = defineComponent({
  setup:
    (_, { attrs, slots }) =>
    () =>
      h('div', attrs, slots.default?.())
})
const modal = defineComponent({
  props: ['show', 'title'],
  emits: ['update:show'],
  setup:
    (props, { emit, slots }) =>
    () =>
      props.show
        ? h(
            'section',
            {
              'data-modal': true,
              'data-title': props.title,
              onDismiss: () => emit('update:show', false)
            },
            [slots.default?.(), slots.footer?.()]
          )
        : null
})
const toggle = defineComponent({
  props: ['value', 'disabled'],
  emits: ['update:value'],
  setup:
    (props, { emit }) =>
    () =>
      h('button', {
        role: 'switch',
        disabled: props.disabled,
        'aria-checked': props.value,
        onClick: () => !props.disabled && emit('update:value', !props.value)
      })
})
const input = defineComponent({
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
})
const { descriptor } = parse(
  readFileSync(new URL('./VersionWatermarkPreference.vue', import.meta.url), 'utf8')
)
const ClientPreference = {
  ...VersionWatermarkPreference,
  components: {
    NFormItem: wrapper,
    NAlert: wrapper,
    NButton: 'button',
    NModal: modal,
    NSwitch: toggle,
    NInput: input
  },
  ssrRender: undefined,
  render: compile(descriptor.template.content, { hoistStatic: false }),
  setup: (props, context) => ({ ...VersionWatermarkPreference.setup(props, context) })
}
const mounted = []
const node = (tag, text = '') => ({ tag, text, props: {}, children: [], parent: null })
const all = (element) => [element, ...element.children.flatMap(all)]
const text = (element) => element.text + element.children.map(text).join('')
const confirmation = '反馈问题时务必说明具体版本'

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
    toggle: () => all(root).find((element) => element.props.role === 'switch'),
    modal: () => all(root).find((element) => element.props['data-modal']),
    confirm: () =>
      all(root).find((element) => element.props.class?.includes('watermark-confirm-button')),
    input: () => all(root).find((element) => element.tag === 'input'),
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

async function openStep(page, step) {
  page.toggle().props.onClick()
  await nextTick()
  for (let i = 1; i < step; i += 1) {
    page.confirm().props.onClick()
    await nextTick()
  }
}

beforeEach(() => {
  axios.get.mockResolvedValue({
    data: { software_version_display: 'version', watermark_visible: true }
  })
  axios.put.mockImplementation(async (_url, payload) => ({
    data: { watermark_visible: payload.watermark_visible }
  }))
})

afterEach(() => {
  for (const { app, gui } of mounted.splice(0)) {
    app.unmount()
    gui.$dispose()
  }
  vi.resetAllMocks()
})

describe('version watermark preference', () => {
  it('waits for the initial read and offers retry without changing visibility', async () => {
    axios.get.mockRejectedValueOnce(new Error('offline'))
    const page = mount()
    expect(page.toggle().props.disabled).toBe(true)
    await flush()
    expect(page.gui.watermarkVisible).toBe(true)
    expect(text(page.alert())).toContain('读取失败')
    page.button('重试').props.onClick()
    await flush()
    expect(page.toggle().props.disabled).toBe(false)
    expect(page.alert()).toBeUndefined()
    expect(axios.put).not.toHaveBeenCalled()
  })

  it('requires five reminders with moving buttons and the exact final acknowledgement', async () => {
    const page = mount()
    await flush()
    page.toggle().props.onClick()
    await nextTick()
    const cancel = page.button('保留水印')
    for (let step = 1; step <= 5; step += 1) {
      expect(page.modal().props['data-title']).toContain(`${step}/5`)
      expect(text(page.modal())).toContain(
        '隐藏水印后，反馈问题时请提供完整版本号。版本号可在“帮助 → 关于”查看。'
      )
      expect(page.confirm().props.class).toContain(`watermark-confirm-position-${step - 1}`)
      expect(page.button('保留水印')).toBe(cancel)
      expect(page.toggle().props.disabled).toBe(true)
      expect(page.gui.watermarkVisible).toBe(true)
      expect(axios.put).not.toHaveBeenCalled()
      if (step < 5) {
        page.confirm().props.onClick()
        await nextTick()
      }
    }
    expect(page.confirm().props.disabled).toBe(true)
    expect(page.input().props.id).toBe('watermark-confirmation-text')
    page.input().props.onInput({ target: { value: '最新版' } })
    await nextTick()
    page.confirm().props.onClick()
    expect(axios.put).not.toHaveBeenCalled()
    expect(page.confirm().props.disabled).toBe(true)
    page.input().props.onInput({ target: { value: confirmation } })
    await nextTick()
    expect(page.confirm().props.disabled).toBe(false)
    page.confirm().props.onClick()
    await flush()
    expect(page.modal()).toBeUndefined()
    expect(page.gui.watermarkVisible).toBe(false)
    expect(axios.put).toHaveBeenCalledExactlyOnceWith(
      expect.stringMatching(/\/gui\/appearance$/),
      { watermark_visible: false, watermark_confirmation: confirmation },
      { timeout: 5000 }
    )
    page.toggle().props.onClick()
    await flush()
    expect(page.modal()).toBeUndefined()
    expect(page.gui.watermarkVisible).toBe(true)
    expect(axios.put.mock.calls[1][1]).toEqual({ watermark_visible: true })
  })

  it.each([1, 2, 3, 4, 5])(
    'cancels at reminder %s without saving and restarts at the beginning',
    async (step) => {
      const page = mount()
      await flush()
      await openStep(page, step)
      if (step === 5) page.input().props.onInput({ target: { value: confirmation } })
      page.button('保留水印').props.onClick()
      await nextTick()
      expect(page.modal()).toBeUndefined()
      expect(page.gui.watermarkVisible).toBe(true)
      expect(axios.put).not.toHaveBeenCalled()
      await openStep(page, 5)
      expect(page.input().props.value).toBe('')
      expect(page.confirm().props.disabled).toBe(true)
      page.modal().props.onDismiss()
      await nextTick()
      expect(page.modal()).toBeUndefined()
      expect(page.gui.watermarkVisible).toBe(true)
      expect(axios.put).not.toHaveBeenCalled()
    }
  )

  it('restores the watermark after a failed hide and retries the already confirmed request', async () => {
    const page = mount()
    await flush()
    await openStep(page, 5)
    page.input().props.onInput({ target: { value: confirmation } })
    await nextTick()
    let reject
    axios.put.mockReturnValueOnce(new Promise((_, fail) => (reject = fail)))
    page.confirm().props.onClick()
    await nextTick()
    expect(page.toggle().props.disabled).toBe(true)
    reject(new Error('offline'))
    await flush()
    expect(page.gui.watermarkVisible).toBe(true)
    expect(text(page.alert())).toContain('已恢复原来的显示')
    page.button('重试').props.onClick()
    await flush()
    expect(page.gui.watermarkVisible).toBe(false)
    expect(page.alert()).toBeUndefined()
    expect(axios.put.mock.calls.map(([, payload]) => payload)).toEqual([
      { watermark_visible: false, watermark_confirmation: confirmation },
      { watermark_visible: false, watermark_confirmation: confirmation }
    ])
  })
})
