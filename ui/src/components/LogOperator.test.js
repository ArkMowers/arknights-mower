import { readFileSync } from 'node:fs'
import { parse } from '@vue/compiler-sfc'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { compile, createRenderer, h, nextTick, reactive, ssrContextKey } from 'vue'
import emptyAvatar from '@/assets/log/empty-operator.svg?url&no-inline'
import LogOperator from './LogOperator.vue'

const { descriptor } = parse(readFileSync(new URL('./LogOperator.vue', import.meta.url), 'utf8'))
const clientOperator = {
  ...LogOperator,
  ssrRender: undefined,
  render: compile(descriptor.template.content),
  setup: (props, context) => ({ ...LogOperator.setup(props, context) })
}
const mounted = []
const node = (tag, value = '') => ({ tag, text: value, props: {}, children: [], parent: null })
const all = (element) => [element, ...element.children.flatMap(all)]
const text = (element) => element.text + element.children.map(text).join('')

function mount(overrides = {}) {
  const props = reactive({ name: '阿米娅', ...overrides })
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
        const previous = element.parent.children
        previous.splice(previous.indexOf(element), 1)
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
  const app = renderer.createApp({ render: () => h(clientOperator, props) })
  app.provide(ssrContextKey, { modules: new Set() })
  const host = node('root')
  app.mount(host)
  mounted.push(app)
  return {
    props,
    root: () => host.children[0],
    image: () => all(host).find((element) => element.tag === 'img'),
    text: () => text(host)
  }
}

afterEach(() => {
  for (const app of mounted.splice(0)) app.unmount()
  vi.unstubAllEnvs()
})

describe('log operator portraits', () => {
  it('uses encoded local portraits and a readable keyboard target without visible duplicate text', () => {
    vi.stubEnv('BASE_URL', '/mower/')
    const page = mount()
    const image = page.image()
    expect(image.props.src).toBe('/mower/avatar/%E9%98%BF%E7%B1%B3%E5%A8%85.webp')
    expect(image.props.width).toBe(24)
    expect(image.props.height).toBe(24)
    expect(image.props.loading).toBe('lazy')
    expect(image.props.decoding).toBe('async')
    expect(image.props.alt).toBe('')
    expect(image.props['aria-hidden']).toBe('true')
    expect(page.root().props.tabindex).toBe(0)
    expect(page.root().props.title).toBe('阿米娅')
    expect(page.root().props['aria-label']).toBe('阿米娅')
    expect(page.root().props['data-operator-name']).toBe('阿米娅')
    expect(page.text()).toBe('')
  })

  it('keeps one copied name with and without a successfully loaded portrait', async () => {
    const page = mount({ showName: true, size: 22 })
    expect(page.image().props.width).toBe(22)
    expect(page.image().props.alt).toBe('')
    expect(page.text()).toBe('阿米娅')
    expect(page.root().props['aria-label']).toBeUndefined()
    page.image().props.onError({ target: { getAttribute: () => page.image().props.src } })
    await nextTick()
    expect(page.image()).toBeUndefined()
    expect(page.text()).toBe('阿米娅')
  })

  it('can show the portrait and name without a duplicate tooltip', () => {
    const page = mount({ showName: true, hideHint: true })
    expect(page.text()).toBe('阿米娅')
    expect(page.root().props.title).toBe('')
  })

  it('preserves the focus target after failure and ignores errors from a previous portrait', async () => {
    const page = mount()
    const root = page.root()
    const previousImage = page.image()
    const previousSource = previousImage.props.src
    previousImage.props.onError({ target: { getAttribute: () => previousSource } })
    await nextTick()
    expect(page.root()).toBe(root)
    expect(root.props.tabindex).toBe(0)
    expect(root.props['aria-label']).toBe('阿米娅')
    expect(page.text()).toBe('阿米娅')
    expect(page.image()).toBeUndefined()

    page.props.name = '令'
    await nextTick()
    expect(page.image().props.src).toBe('/avatar/%E4%BB%A4.webp')
    previousImage.props.onError({ target: { getAttribute: () => previousSource } })
    await nextTick()
    expect(page.image().props.src).toBe('/avatar/%E4%BB%A4.webp')
    expect(page.root()).toBe(root)
    expect(root.props['aria-label']).toBe('令')
  })

  it.each([
    ['Free', 'Free（自动选择干员）'],
    ['Current', 'Current（保留当前干员）']
  ])(
    'explains the bundled %s portrait without replacing the task placeholder',
    (name, description) => {
      for (const showName of [false, true]) {
        const page = mount({ name, showName })
        expect(page.image().props.src).toBe(`/avatar/${name}.webp`)
        expect(page.image().props.alt).toBe('')
        expect(page.root().props.title).toBe(description)
        expect(page.root().props['aria-label']).toBe(showName ? undefined : description)
        expect(page.root().props['data-operator-name']).toBe(name)
        expect(page.root().props.tabindex).toBe(showName ? undefined : 0)
        expect(page.text()).toBe(showName ? name : '')
      }
    }
  )

  it.each(['_', ''])('shows the Empty portrait for the %j placeholder', (name) => {
    for (const showName of [false, true]) {
      const page = mount({ name, showName })
      expect(page.image().props.src).toBe(emptyAvatar)
      expect(page.root().props.title).toBe('Empty（留空）')
      expect(page.root().props['aria-label']).toBe(showName ? undefined : 'Empty（留空）')
      expect(page.text()).toBe(showName ? 'Empty' : '')
    }
  })
})
