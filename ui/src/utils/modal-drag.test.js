import { afterEach, describe, expect, it, vi } from 'vitest'
import { installModalDragging } from './modal-drag'

let dispose

function element(className, parentElement, tagName = 'div') {
  return {
    parentElement,
    closest(selector) {
      const matches = selector.split(',').some((part) => {
        const candidate = part.trim()
        return candidate === `.${className}` || candidate === tagName
      })
      return matches ? this : (this.parentElement?.closest(selector) ?? null)
    }
  }
}

function install({ draggable, interactive = false, nestedHeader = false } = {}) {
  const documentTarget = new EventTarget()
  const windowTarget = new EventTarget()
  vi.stubGlobal('document', documentTarget)
  vi.stubGlobal('window', windowTarget)
  const panel = {
    ...element('n-modal'),
    style: {},
    getAttribute: (name) => (name === 'data-modal-draggable' ? draggable : null),
    getBoundingClientRect: vi.fn(() => ({ left: 100, top: 80 }))
  }
  const headerParent = nestedHeader ? element('n-card', panel) : panel
  const handle = element('n-card-header', headerParent)
  const target = element('', handle, interactive ? 'button' : 'span')
  dispose = installModalDragging()
  const dispatch = (type, properties) => {
    const event = new Event(type)
    for (const [key, value] of Object.entries(properties)) {
      Object.defineProperty(event, key, { value })
    }
    ;(type === 'pointerdown' ? documentTarget : windowTarget).dispatchEvent(event)
  }
  return {
    panel,
    press: () =>
      dispatch('pointerdown', { button: 0, pointerId: 1, clientX: 120, clientY: 90, target }),
    move: () => dispatch('pointermove', { pointerId: 1, clientX: 150, clientY: 110 }),
    release: () => dispatch('pointerup', { pointerId: 1 })
  }
}

afterEach(() => {
  dispose?.()
  dispose = undefined
  vi.unstubAllGlobals()
})

describe('modal dragging', () => {
  it.each([false, true])(
    'keeps an opted-out modal centred when a header is dragged (nested card: %s)',
    (nestedHeader) => {
      const modal = install({ draggable: 'false', nestedHeader })
      modal.press()
      modal.move()
      expect(modal.panel.getBoundingClientRect).not.toHaveBeenCalled()
      expect(modal.panel.style).toEqual({})
      modal.release()
    }
  )

  it.each([undefined, 'true'])('continues moving ordinary modals with opt-out %s', (draggable) => {
    const modal = install({ draggable })
    modal.press()
    modal.move()
    expect(modal.panel.style).toMatchObject({ position: 'fixed', left: '130px', top: '100px' })
    modal.release()
    modal.move()
    expect(modal.panel.style.left).toBe('130px')
  })

  it('keeps header controls clickable without starting a drag', () => {
    const modal = install({ interactive: true })
    modal.press()
    modal.move()
    expect(modal.panel.style).toEqual({})
    modal.release()
  })
})
