import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createRenderer, defineComponent, h, KeepAlive, nextTick, ref } from 'vue'
import { useMeasuredMasonry } from './measuredMasonry'

let app
let observers
let frames

function node(tag) {
  const properties = new Map()
  return {
    tag,
    props: {},
    attributes: new Map(),
    children: [],
    parent: null,
    offsetHeight: 0,
    style: {
      setProperty: (key, value) => properties.set(key, value),
      removeProperty: (key) => properties.delete(key),
      getPropertyValue: (key) => properties.get(key) || ''
    },
    get firstElementChild() {
      return this.children.find((child) => !child.tag.startsWith('#'))
    },
    hasAttribute(key) {
      return Object.hasOwn(this.props, key) || this.attributes.has(key)
    },
    setAttribute(key, value) {
      this.attributes.set(key, value)
    },
    removeAttribute(key) {
      this.attributes.delete(key)
    }
  }
}

async function mount() {
  const enabled = ref(true)
  const shown = ref(true)
  const root = ref(null)
  const draft = ref('unfinished draft')
  const Probe = defineComponent({
    setup() {
      useMeasuredMasonry(root, enabled)
      return () =>
        h('div', { ref: root }, [
          ...[180, 72, 320].map((height, index) =>
            h('section', { 'data-task-editor': String(index) }, [
              h('div', { height }, [h('input', { value: draft.value })])
            ])
          )
        ])
    }
  })
  const renderer = createRenderer({
    createElement: node,
    createText: () => node('#text'),
    createComment: () => node('#comment'),
    setText() {},
    setElementText() {},
    parentNode: (element) => element.parent,
    nextSibling: (element) =>
      element.parent?.children[element.parent.children.indexOf(element) + 1] || null,
    patchProp(element, key, _old, value) {
      element.props[key] = value
      if (key === 'height') element.offsetHeight = value
    },
    insert(element, parent, anchor) {
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
  app = renderer.createApp({
    setup: () => () => h(KeepAlive, null, { default: () => (shown.value ? h(Probe) : null) })
  })
  app.mount(node('root'))
  await nextTick()
  return { enabled, shown, root, draft }
}

function flushFrames() {
  const pending = [...frames.values()]
  frames.clear()
  for (const callback of pending) callback()
}

beforeEach(() => {
  observers = []
  frames = new Map()
  let nextFrame = 0
  vi.stubGlobal('requestAnimationFrame', (callback) => {
    frames.set(++nextFrame, callback)
    return nextFrame
  })
  vi.stubGlobal('cancelAnimationFrame', (id) => frames.delete(id))
  vi.stubGlobal(
    'ResizeObserver',
    class {
      constructor(callback) {
        this.callback = callback
        this.observe = vi.fn()
        this.disconnect = vi.fn()
        observers.push(this)
      }
    }
  )
})

afterEach(() => {
  app?.unmount()
  app = undefined
  vi.unstubAllGlobals()
})

describe('measured task card layout', () => {
  it('reserves each natural card height and updates both growing and shrinking content', async () => {
    const { root } = await mount()
    const cards = root.value.children
    const observer = observers.at(-1)
    expect(root.value.hasAttribute('data-masonry-ready')).toBe(true)
    expect(observer.observe.mock.calls.map(([element]) => element)).toEqual(
      cards.map((card) => card.firstElementChild)
    )
    const spans = () => cards.map((card) => card.style.getPropertyValue('--task-card-span'))
    expect(spans()).toEqual(['190', '82', '330'])
    cards[0].firstElementChild.offsetHeight = 420
    observer.callback()
    observer.callback()
    expect(frames.size).toBe(1)
    flushFrames()
    expect(spans()).toEqual(['430', '82', '330'])
    cards[0].firstElementChild.offsetHeight = 48
    observer.callback()
    flushFrames()
    expect(spans()).toEqual(['58', '82', '330'])
  })

  it('releases measurements when changing layouts and retains mounted inputs and drafts', async () => {
    const { root, enabled, draft } = await mount()
    const cards = [...root.value.children]
    const input = cards[0].firstElementChild.firstElementChild
    const observer = observers.at(-1)
    draft.value = 'changed draft'
    observer.callback()
    enabled.value = false
    await nextTick()
    expect(observer.disconnect).toHaveBeenCalledOnce()
    expect(frames.size).toBe(0)
    expect(root.value.hasAttribute('data-masonry-ready')).toBe(false)
    expect(cards.every((card) => !card.style.getPropertyValue('--task-card-span'))).toBe(true)
    enabled.value = true
    await nextTick()
    expect(root.value.children).toEqual(cards)
    expect(cards[0].firstElementChild.firstElementChild).toBe(input)
    expect(input.props.value).toBe('changed draft')
    expect(root.value.hasAttribute('data-masonry-ready')).toBe(true)
  })

  it('disconnects while the cached page is inactive and measures again on return', async () => {
    const { shown, root } = await mount()
    const target = root.value
    const observer = observers.at(-1)
    shown.value = false
    await nextTick()
    expect(observer.disconnect).toHaveBeenCalledOnce()
    expect(target.hasAttribute('data-masonry-ready')).toBe(false)
    shown.value = true
    await nextTick()
    expect(root.value).toBe(target)
    expect(target.hasAttribute('data-masonry-ready')).toBe(true)
    const returnedObserver = observers.at(-1)
    app.unmount()
    app = undefined
    expect(returnedObserver.disconnect).toHaveBeenCalledOnce()
  })

  it('keeps the unmeasured layout readable when the browser observer is unavailable', async () => {
    vi.stubGlobal('ResizeObserver', undefined)
    const { root } = await mount()
    expect(root.value.hasAttribute('data-masonry-ready')).toBe(false)
    expect(root.value.children).toHaveLength(3)
    expect(root.value.children[0].firstElementChild.firstElementChild.props.value).toBe(
      'unfinished draft'
    )
  })
})
