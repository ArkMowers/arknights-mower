import { readFileSync } from 'node:fs'
import { parse } from '@vue/compiler-sfc'
import { createPinia, disposePinia } from 'pinia'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { compile, createRenderer, h, nextTick, ssrContextKey } from 'vue'
import axios from 'axios'
import Preference from './LogBackgroundPreference.vue'

vi.mock('axios', () => ({ default: { get: vi.fn(), put: vi.fn(), delete: vi.fn() } }))

const { descriptor } = parse(
  readFileSync(new URL('./LogBackgroundPreference.vue', import.meta.url), 'utf8')
)
const clientPreference = {
  ...Preference,
  ssrRender: undefined,
  render: compile(descriptor.template.content),
  setup: (props, context) => ({ ...Preference.setup(props, context) })
}
const mounted = []
const all = (element) => [element, ...element.children.flatMap(all)]
const text = (element) => element.text + element.children.map(text).join('')
const node = (tag, value = '') => ({ tag, text: value, props: {}, children: [], parent: null })

function mount() {
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
    }
  })
  const app = renderer.createApp(clientPreference)
  const pinia = createPinia()
  app.use(pinia)
  app.provide(ssrContextKey, { modules: new Set() })
  app.component('NFormItem', {
    setup:
      (_, { attrs, slots }) =>
      () =>
        h('div', attrs, [slots.label?.(), slots.default?.()])
  })
  app.component('NButton', {
    setup:
      (_, { attrs, slots }) =>
      () =>
        h('button', attrs, slots.default?.())
  })
  app.component('NAlert', {
    setup:
      (_, { attrs, slots }) =>
      () =>
        h('div', attrs, slots.default?.())
  })
  const root = node('root')
  app.mount(root)
  mounted.push({ app, pinia })
  return {
    all: () => all(root),
    find: (predicate) => {
      const target = all(root).find(predicate)
      expect(target).toBeTruthy()
      return target
    }
  }
}

async function flush() {
  await Promise.resolve()
  await nextTick()
  await Promise.resolve()
  await nextTick()
}

afterEach(() => {
  for (const { app, pinia } of mounted.splice(0)) {
    app.unmount()
    disposePinia(pinia)
  }
  vi.restoreAllMocks()
  vi.resetAllMocks()
})

describe('running log background preference', () => {
  it('selects an image, updates the preview and restores the default through the controls', async () => {
    axios.get.mockResolvedValueOnce({ status: 204 })
    axios.put.mockResolvedValueOnce({
      status: 200,
      data: new Blob(['saved'], { type: 'image/webp' })
    })
    axios.delete.mockResolvedValueOnce({ status: 204 })
    vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:custom-background')
    vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {})
    const page = mount()
    await flush()
    const select = page.find((target) => target.tag === 'button' && text(target) === '选择图片')
    const reset = page.find((target) => target.tag === 'button' && text(target) === '恢复默认')
    const picker = page.find((target) => target.tag === 'input' && target.props.type === 'file')
    expect(select.props.disabled).toBe(false)
    expect(reset.props.disabled).toBe(true)
    expect(
      page.all().some((target) => target.props['data-settings-keywords']?.includes('背景图'))
    ).toBe(true)
    picker.click = vi.fn()
    select.props.onClick()
    expect(picker.click).toHaveBeenCalledOnce()
    const file = new Blob(['selected'], { type: 'image/png' })
    const target = { files: [file], value: 'chosen.png' }
    picker.props.onChange({ target })
    expect(target.value).toBe('')
    await flush()
    expect(axios.put.mock.calls[0][1]).toBe(file)
    expect(page.find((target) => target.props.role === 'img').props.style.backgroundImage).toBe(
      "url('blob:custom-background')"
    )
    expect(reset.props.disabled).toBe(false)
    reset.props.onClick()
    await flush()
    expect(page.find((target) => target.props.role === 'img').props.style.backgroundImage).toBe(
      "url('/bg.webp')"
    )
    expect(reset.props.disabled).toBe(true)
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:custom-background')
  })
})
