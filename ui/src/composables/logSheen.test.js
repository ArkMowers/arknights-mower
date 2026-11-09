import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createRenderer, defineComponent, h, nextTick, shallowRef } from 'vue'
import { useLogSheen } from './logSheen'

let app
let frames
let observers
let mutations

const rect = (left, top, width, height) => ({
  left,
  top,
  width,
  height,
  right: left + width,
  bottom: top + height
})

function fixture() {
  const fontListeners = new Set()
  const document = {
    documentElement: {},
    fonts: {
      addEventListener: (_event, listener) => fontListeners.add(listener),
      removeEventListener: (_event, listener) => fontListeners.delete(listener)
    },
    createRange() {
      let selected
      return {
        selectNodeContents(node) {
          selected = node
        },
        getClientRects: () => selected.rects
      }
    }
  }
  const text = {
    nodeType: 3,
    textContent: '正在安排干员进驻贸易站，并读取信息',
    rects: [rect(40, 22, 200, 18), rect(40, 52, 100, 18)]
  }
  const image = { tagName: 'IMG', getBoundingClientRect: () => rect(95, 20, 20, 20) }
  const properties = new Map()
  const heading = {
    bounds: rect(40, 20, 200, 50),
    ownerDocument: document,
    childNodes: [text, { tagName: 'SPAN', childNodes: [image] }],
    getBoundingClientRect() {
      return this.bounds
    },
    style: {
      setProperty: (key, value) => properties.set(key, value),
      removeProperty: (key) => properties.delete(key)
    }
  }
  const lines = {}
  const svg = { elapsed: 0, getCurrentTime: () => svg.elapsed }
  const root = {
    ownerDocument: document,
    active: [heading],
    querySelector: (selector) => (selector === '.log-sheen-filter' ? svg : lines),
    querySelectorAll() {
      return this.active
    }
  }
  return { document, text, image, heading, root, lines, svg, properties, fontListeners }
}

async function mount(target) {
  let sheen
  const renderer = createRenderer({
    createElement: () => ({}),
    insert() {},
    remove() {},
    patchProp() {},
    parentNode: () => null,
    nextSibling: () => null,
    createText: () => ({}),
    createComment: () => ({}),
    setText() {},
    setElementText() {}
  })
  app = renderer.createApp(
    defineComponent({
      setup() {
        sheen = useLogSheen(shallowRef(target))
        return () => h('div')
      }
    })
  )
  app.mount({})
  await flushFrames()
  return sheen
}

async function flushFrames() {
  const callbacks = [...frames.values()]
  frames.clear()
  for (const callback of callbacks) callback()
  await nextTick()
}

beforeEach(() => {
  frames = new Map()
  observers = []
  mutations = []
  let frameId = 0
  vi.stubGlobal('requestAnimationFrame', (callback) => {
    frames.set(++frameId, callback)
    return frameId
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
  vi.stubGlobal(
    'MutationObserver',
    class {
      constructor(callback) {
        this.callback = callback
        this.observe = vi.fn()
        this.disconnect = vi.fn()
        mutations.push(this)
      }
    }
  )
})

afterEach(() => {
  app?.unmount()
  app = null
  vi.unstubAllGlobals()
})

describe('running log sheen', () => {
  it('uses actual text fragments and an inline portrait to sweep wrapped lines in reading order', async () => {
    const sample = fixture()
    const sheen = await mount(sample.root)
    const [filter] = sheen.filters.value
    expect(filter.lines).toHaveLength(2)
    expect(filter.lines[0]).toMatchObject({
      width: 0.48,
      height: 0.52,
      keyTimes: '0;0.533333;1',
      yValues: '0;-2;-2'
    })
    expect(filter.lines[1]).toMatchObject({
      width: 0.24,
      height: 0.48,
      keyTimes: '0;0.533333;0.8;1',
      yValues: '-2;0.52;-2;-2'
    })
    expect(filter.protectedRegions).toEqual([{ x: 0.275, y: 0, width: 0.1, height: 0.4 }])
    expect(sample.properties.get('--log-sheen-filter')).toBe(`url(#${filter.id})`)
    expect(sample.heading.childNodes[0]).toBe(sample.text)
    expect(sample.heading.childNodes[1].childNodes[0]).toBe(sample.image)
  })

  it('protects each fragment of a wrapped colored token without treating neutral text as protected', async () => {
    const sample = fixture()
    const room = {
      tagName: 'SPAN',
      matches: (selector) => selector.includes('.log-token--room'),
      childNodes: [
        {
          nodeType: 3,
          textContent: '贸易站 B101',
          rects: [rect(200, 22, 40, 18), rect(40, 52, 32, 18)]
        }
      ]
    }
    sample.heading.childNodes.push(room)
    const sheen = await mount(sample.root)
    expect(sheen.filters.value[0].protectedRegions).toEqual([
      { x: 0.275, y: 0, width: 0.1, height: 0.4 },
      { x: 0.8, y: 0.04, width: 0.2, height: 0.36 },
      { x: 0, y: 0.64, width: 0.16, height: 0.36 }
    ])
  })

  it('keeps an unchanged filter so unrelated updates do not restart its animation', async () => {
    const sample = fixture()
    const sheen = await mount(sample.root)
    const filters = sheen.filters.value
    sample.svg.elapsed = 2.3
    sheen.refresh()
    sheen.refresh()
    expect(frames.size).toBe(1)
    await flushFrames()
    expect(sheen.filters.value).toBe(filters)
    expect(sheen.filters.value[0].begin).toBe('0s')
  })

  it('starts a newly rendered title at the first line even when the SVG is midway through an older sweep', async () => {
    const sample = fixture()
    const sheen = await mount(sample.root)
    const first = sheen.filters.value[0]
    const next = fixture()
    sample.root.active = [sample.heading, next.heading]
    sample.svg.elapsed = 2.3
    sheen.refresh()
    await flushFrames()
    expect(sheen.filters.value[0]).toBe(first)
    expect(sheen.filters.value[1].begin).toBe('2.3s')
    expect(sheen.filters.value[1].id).not.toBe(first.id)
    expect(sheen.filters.value[1].lines[0].yValues).toBe('0;-2;-2')
    expect(sheen.filters.value[1].lines[1].yValues).toBe('-2;0.52;-2;-2')
  })

  it('recomputes wrapping after a resize while preserving the heading filter identity', async () => {
    const sample = fixture()
    const sheen = await mount(sample.root)
    const id = sheen.filters.value[0].id
    sample.svg.elapsed = 2.3
    sample.heading.bounds = rect(40, 20, 300, 20)
    sample.text.rects = [rect(40, 22, 300, 18)]
    observers[0].callback()
    await flushFrames()
    expect(sheen.filters.value[0].id).toBe(id)
    expect(sheen.filters.value[0].begin).toBe('2.3s')
    expect(sheen.filters.value[0].lines).toEqual([
      {
        from: -0.56,
        width: 0.48,
        height: 1,
        values: '-0.56;1.12;1.12',
        keyTimes: '0;0.8;1',
        yValues: '0;-2;-2'
      }
    ])
  })

  it('remeasures child rendering and font changes without observing its own filter styles', async () => {
    const sample = fixture()
    const sheen = await mount(sample.root)
    expect(mutations[0].observe).toHaveBeenCalledWith(sample.lines, {
      childList: true,
      characterData: true,
      subtree: true
    })
    expect(mutations[0].observe).toHaveBeenCalledWith(sample.document.documentElement, {
      attributes: true,
      attributeFilter: ['data-mower-theme', 'data-window-shell-theme']
    })
    sample.heading.childNodes = [sample.text]
    sample.text.rects = [rect(40, 22, 180, 18), rect(40, 52, 120, 18)]
    mutations[0].callback()
    await flushFrames()
    expect(sheen.filters.value[0].lines[0].keyTimes).toBe('0;0.48;1')
    sample.text.rects = [rect(40, 22, 150, 18), rect(40, 52, 150, 18)]
    for (const listener of sample.fontListeners) listener()
    await flushFrames()
    expect(sheen.filters.value[0].lines[0].keyTimes).toBe('0;0.4;1')
  })

  it('removes finished headings and releases observers, listeners and pending work on unmount', async () => {
    const sample = fixture()
    const sheen = await mount(sample.root)
    sample.root.active = []
    sheen.refresh()
    await flushFrames()
    expect(sheen.filters.value).toEqual([])
    expect(sample.properties.has('--log-sheen-filter')).toBe(false)
    sample.root.active = [sample.heading]
    sheen.refresh()
    await flushFrames()
    sheen.refresh()
    expect(frames.size).toBe(1)
    app.unmount()
    app = null
    expect(frames.size).toBe(0)
    expect(sample.fontListeners.size).toBe(0)
    expect(observers[0].disconnect).toHaveBeenCalledOnce()
    expect(mutations[0].disconnect).toHaveBeenCalledOnce()
    expect(sample.properties.size).toBe(0)
  })

  it('leaves hidden or unmeasurable headings static until layout becomes available', async () => {
    const sample = fixture()
    sample.heading.bounds = rect(0, 0, 0, 0)
    const sheen = await mount(sample.root)
    expect(sheen.filters.value).toEqual([])
    expect(sample.properties.size).toBe(0)
    sample.heading.bounds = rect(40, 20, 200, 50)
    observers[0].callback()
    await flushFrames()
    expect(sheen.filters.value).toHaveLength(1)
  })
})
