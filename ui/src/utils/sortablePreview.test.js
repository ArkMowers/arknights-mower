import { describe, expect, it, vi } from 'vitest'
import { normalizeSortablePreview } from './sortablePreview'

function fixture({ rootZoom = '1', bodyZoom = '1', sourceZoom = '1' } = {}) {
  const document = {}
  function element(parentElement = null, appearance = {}, children = []) {
    const node = {
      ownerDocument: document,
      parentElement,
      appearance,
      children,
      style: {
        setProperty(property, value, priority) {
          this[property] = value
          this[`${property}-priority`] = priority
        }
      },
      removeAttribute: vi.fn(),
      classList: { remove: vi.fn() },
      append(child) {
        if (child.parentElement) {
          const siblings = child.parentElement.children
          siblings.splice(siblings.indexOf(child), 1)
        }
        child.parentElement = this
        this.children.push(child)
      },
      cloneNode() {
        const copy = element(null, appearance)
        Object.assign(copy.style, this.style)
        return copy
      },
      get firstChild() {
        return this.children[0]
      }
    }
    for (const child of children) child.parentElement = node
    return node
  }
  document.defaultView = { getComputedStyle: (node) => node.appearance }
  document.documentElement = element(null, { zoom: rootZoom })
  document.body = element(document.documentElement, { zoom: bodyZoom })
  const child = element()
  const source = element(document.body, { zoom: sourceZoom, font: '14px / 22px sans-serif' })
  source.getBoundingClientRect = () => ({ left: 10, top: 240, width: 242.5, height: 45 })
  const preview = element(document.body, {}, [child])
  Object.assign(preview.style, { left: '10px', top: '240px', transform: 'matrix(1,0,0,1,12,12)' })
  document.body.children.push(source, preview)
  document.body.querySelector = () => preview
  return { document, source, preview, child }
}

describe('Sortable preview under CSS zoom', () => {
  it('keeps unscaled previews unchanged', () => {
    const { source, preview, child } = fixture()
    expect(normalizeSortablePreview({ item: source })).toEqual({
      preview,
      content: preview,
      scale: 1
    })
    expect(preview.children).toEqual([child])
    expect(preview.style.zoom).toBeUndefined()
  })

  it('cancels ancestor zoom on the movement shell while preserving content scale and text', () => {
    const { source, preview, child } = fixture({ rootZoom: '1.25' })
    const originalSource = { ...source.style }
    const result = normalizeSortablePreview({ item: source })
    expect(result.preview).toBe(preview)
    expect(result.scale).toBe(1.25)
    expect(preview.style).toMatchObject({
      zoom: '0.8',
      left: '10px',
      top: '240px',
      width: '242.5px',
      height: '45px',
      transform: 'matrix(1,0,0,1,12,12)',
      display: 'block',
      'display-priority': 'important',
      background: 'transparent',
      border: '0'
    })
    expect(result.content.style).toMatchObject({
      width: '194px',
      height: '36px',
      zoom: '1.25',
      font: '14px / 22px sans-serif',
      position: 'static',
      transform: 'none'
    })
    expect(result.content.children).toEqual([child])
    expect(preview.children).toEqual([result.content])
    expect(source.style).toEqual(originalSource)
    expect(result.content.removeAttribute).toHaveBeenCalledWith('id')
    expect(normalizeSortablePreview({ item: source })).toBe(result)
    expect(preview.children).toHaveLength(1)
  })

  it('combines ancestor zoom factors separately from source-only zoom', () => {
    const { source, preview } = fixture({ rootZoom: '125%', bodyZoom: '0.8', sourceZoom: '1.5' })
    const { content, scale } = normalizeSortablePreview({ item: source })
    expect(preview.style.zoom).toBe('1')
    expect(scale).toBeCloseTo(1.5)
    expect(Number(content.style.zoom)).toBeCloseTo(1.5)
    expect(Number.parseFloat(content.style.width)).toBeCloseTo(242.5 / 1.5)
  })

  it('does nothing without an active preview', () => {
    const { document, source } = fixture()
    document.body.querySelector = () => null
    expect(normalizeSortablePreview({ item: source })).toBeNull()
    expect(normalizeSortablePreview()).toBeNull()
  })
})
