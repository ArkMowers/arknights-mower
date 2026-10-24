import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createDragPreview } from './dragPreview'

function previewDocument() {
  const document = { documentElement: { style: { zoom: '1' } } }
  document.defaultView = {
    setTimeout,
    clearTimeout,
    getComputedStyle: (node) => ({
      [Symbol.iterator]: () => Object.keys(node.appearance)[Symbol.iterator](),
      getPropertyValue: (key) => node.appearance[key]
    })
  }
  function node(tagName = 'DIV', children = []) {
    const element = {
      tagName,
      children,
      ownerDocument: document,
      appearance: { color: 'rgb(20, 30, 40)', '--mower-surface': '#f8f9fa' },
      attributes: { id: 'original-card', draggable: 'true' },
      classes: new Set(),
      style: {
        setProperty(key, value) {
          this[key] = value
        }
      },
      classList: {
        add(name) {
          element.classes.add(name)
        }
      },
      removeAttribute(name) {
        delete this.attributes[name]
      },
      setAttribute(name, value) {
        this.attributes[name] = value
      },
      append(child) {
        this.children.push(child)
        child.parent = this
      },
      remove() {
        this.parent?.children.splice(this.parent.children.indexOf(this), 1)
      },
      getBoundingClientRect: () => ({ left: 50, top: 100, width: 320, height: 365 }),
      getContext: () => ({ drawImage: element.drawImage }),
      drawImage: vi.fn(),
      cloneNode: () =>
        node(
          tagName,
          children.map((child) => child.cloneNode(true))
        )
    }
    return element
  }
  document.createElement = () => node()
  document.body = node()
  return { document, node }
}

describe('native card drag preview', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => vi.useRealTimers())

  it('captures the full card, inherited theme and chart pixels without changing its source', () => {
    const { document, node } = previewDocument()
    const chart = node('CANVAS')
    chart.width = 640
    chart.height = 400
    const source = node('SECTION', [node('H2'), chart])
    const transfer = { setDragImage: vi.fn() }
    const preview = createDragPreview()
    preview.start({ currentTarget: source, dataTransfer: transfer, clientX: 90, clientY: 125 })
    const [image, x, y] = transfer.setDragImage.mock.calls[0]
    const copy = image.children[0]
    expect(document.body.children).toEqual([image])
    expect(copy).not.toBe(source)
    expect(copy.tagName).toBe('SECTION')
    expect(copy.children.map((child) => child.tagName)).toEqual(['H2', 'CANVAS'])
    expect(copy.classes.has('mower-drag-preview')).toBe(true)
    expect(copy.style['--mower-surface']).toBe('#f8f9fa')
    expect(copy.children[0].style.color).toBe('rgb(20, 30, 40)')
    expect(copy.style.width).toBe('320px')
    expect(copy.children[1].drawImage).toHaveBeenCalledWith(chart, 0, 0)
    expect(copy.children[1].width).toBe(640)
    expect(copy.attributes).not.toHaveProperty('id')
    expect(copy.children[0].attributes).not.toHaveProperty('draggable')
    expect(image.inert).toBe(true)
    expect(image.attributes['aria-hidden']).toBe('true')
    expect([x, y]).toEqual([52, 37])
    expect(source.attributes).toEqual({ id: 'original-card', draggable: 'true' })
    expect(source.style).not.toHaveProperty('width')
    vi.runAllTimers()
    expect(document.body.children).toEqual([])
  })

  it('replaces a pending snapshot and clears it immediately on cancellation or unmount', () => {
    const { document, node } = previewDocument()
    const preview = createDragPreview()
    const event = {
      currentTarget: node(),
      dataTransfer: { setDragImage: vi.fn() },
      clientX: 0,
      clientY: 0
    }
    preview.start(event)
    const first = document.body.children[0]
    preview.start(event)
    expect(document.body.children).toHaveLength(1)
    expect(document.body.children[0]).not.toBe(first)
    expect(vi.getTimerCount()).toBe(1)
    preview.clear()
    preview.clear()
    expect(document.body.children).toEqual([])
    expect(vi.getTimerCount()).toBe(0)
  })

  it('keeps card dimensions, enlarged text and the pointer hotspot aligned at UI zoom 1.25', () => {
    const { document, node } = previewDocument()
    document.documentElement.style.zoom = '1.25'
    const source = node('SECTION')
    source.appearance['font-size'] = '14px'
    source.getBoundingClientRect = () => ({ left: 50, top: 100, width: 400, height: 200 })
    const transfer = { setDragImage: vi.fn() }
    const preview = createDragPreview()
    preview.start({ currentTarget: source, dataTransfer: transfer, clientX: 150, clientY: 150 })
    const [image, x, y] = transfer.setDragImage.mock.calls[0]
    const copy = image.children[0]
    expect(copy.style.width).toBe('320px')
    expect(copy.style.height).toBe('160px')
    expect(image.style.width).toBe('320px')
    expect(image.style.height).toBe('160px')
    expect(copy.style['font-size']).toBe('14px')
    expect(image.style).not.toHaveProperty('zoom')
    expect(document.documentElement.style.zoom).toBe('1.25')
    expect([x, y]).toEqual([115, 65])
    vi.runAllTimers()
    expect(document.body.children).toEqual([])
  })

  it('leaves unsupported transfers and hidden source elements alone', () => {
    const { document, node } = previewDocument()
    const preview = createDragPreview()
    preview.start({ currentTarget: node(), dataTransfer: {} })
    const hidden = node()
    hidden.getBoundingClientRect = () => ({ width: 0, height: 0 })
    const setDragImage = vi.fn()
    preview.start({ currentTarget: hidden, dataTransfer: { setDragImage } })
    expect(setDragImage).not.toHaveBeenCalled()
    expect(document.body.children).toEqual([])
    expect(vi.getTimerCount()).toBe(0)
  })

  it('continues dragging without leaking a temporary element if the platform rejects the snapshot', () => {
    const { document, node } = previewDocument()
    const preview = createDragPreview()
    expect(() =>
      preview.start({
        currentTarget: node(),
        clientX: 60,
        clientY: 110,
        dataTransfer: {
          setDragImage: () => {
            throw new Error('snapshot failed')
          }
        }
      })
    ).not.toThrow()
    expect(document.body.children).toEqual([])
    expect(vi.getTimerCount()).toBe(0)
  })

  it('continues dragging if capturing the card appearance fails', () => {
    const { document, node } = previewDocument()
    const preview = createDragPreview()
    const event = {
      currentTarget: node(),
      dataTransfer: { setDragImage: vi.fn() },
      clientX: 60,
      clientY: 110
    }
    preview.start(event)
    document.defaultView.getComputedStyle = () => {
      throw new Error('appearance unavailable')
    }
    expect(() => preview.start(event)).not.toThrow()
    expect(document.body.children).toEqual([])
    expect(vi.getTimerCount()).toBe(0)
    expect(event.dataTransfer.setDragImage).toHaveBeenCalledOnce()
  })

  it.each([
    [0, 200],
    [320, 0]
  ])('keeps an uninitialized %s by %s chart in the card without drawing it', (width, height) => {
    const { document, node } = previewDocument()
    const chart = node('CANVAS')
    chart.width = width
    chart.height = height
    const event = {
      currentTarget: node('SECTION', [chart]),
      dataTransfer: { setDragImage: vi.fn() },
      clientX: 60,
      clientY: 110
    }
    const preview = createDragPreview()
    expect(() => preview.start(event)).not.toThrow()
    expect(event.dataTransfer.setDragImage).toHaveBeenCalledOnce()
    const image = event.dataTransfer.setDragImage.mock.calls[0][0]
    const copiedChart = image.children[0].children[0]
    expect(copiedChart.width).toBe(width)
    expect(copiedChart.height).toBe(height)
    expect(copiedChart.drawImage).not.toHaveBeenCalled()
    vi.runAllTimers()
    expect(document.body.children).toEqual([])
  })
})
