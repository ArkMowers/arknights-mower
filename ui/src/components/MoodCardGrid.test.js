import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import MoodCardGrid from './MoodCardGrid.vue'

const state = vi.hoisted(() => ({
  preview: { start: vi.fn(), clear: vi.fn() },
  unmount: null
}))
vi.mock('@/utils/dragPreview', () => ({ createDragPreview: () => state.preview }))
vi.mock('vue', async (original) => ({
  ...(await original()),
  useSSRContext: () => ({ modules: new Set() }),
  onBeforeUnmount: (callback) => {
    state.unmount = callback
  }
}))

describe('mood card drag feedback', () => {
  let component
  let emit
  let listeners
  const groups = [
    { groupName: '第一组', boardKey: 'first' },
    { groupName: '第二组', boardKey: 'second' }
  ]
  const transferEvent = () => ({
    dataTransfer: { setData: vi.fn(), getData: () => 'first' },
    preventDefault: vi.fn()
  })

  beforeEach(() => {
    vi.clearAllMocks()
    listeners = new Map()
    vi.stubGlobal('window', {
      addEventListener: (name, callback) => listeners.set(name, callback),
      removeEventListener: (name) => listeners.delete(name)
    })
    emit = vi.fn()
    component = MoodCardGrid.setup({ groups }, { expose: vi.fn(), emit })
  })
  afterEach(() => {
    state.unmount()
    vi.unstubAllGlobals()
  })

  it('captures a complete source before dimming it and clears feedback after drop or cancellation', () => {
    const event = transferEvent()
    state.preview.start.mockImplementationOnce(() => expect(component.dragged.value).toBe(''))
    component.dragStart(groups[0], event)
    expect(state.preview.start).toHaveBeenCalledWith(event)
    expect(event.dataTransfer.setData).toHaveBeenCalledWith('text/plain', 'first')
    expect(component.dragged.value).toBe('first')
    component.dragOver(groups[1], event)
    expect(component.hovered.value).toBe('second')
    expect(event.dataTransfer.dropEffect).toBe('move')
    component.onDrop(groups[1], event)
    expect(emit).toHaveBeenCalledWith('reorder', 'first', 'second')
    expect(component.dragged.value).toBe('')
    expect(component.hovered.value).toBe('')
    expect(state.preview.clear).toHaveBeenCalledOnce()
    component.dragStart(groups[0], event)
    component.pointerCancel()
    expect(emit).toHaveBeenCalledTimes(1)
    expect(component.dragged.value).toBe('')
    expect(state.preview.clear).toHaveBeenCalledTimes(2)
  })

  it('removes the previous target highlight while crossing cards without losing the source', () => {
    const event = transferEvent()
    component.dragStart(groups[0], event)
    component.dragOver(groups[1], event)
    const currentTarget = { contains: vi.fn(() => true) }
    component.dragLeave(groups[1], { currentTarget, relatedTarget: {} })
    expect(component.hovered.value).toBe('second')
    currentTarget.contains.mockReturnValue(false)
    component.dragLeave(groups[1], { currentTarget, relatedTarget: null })
    expect(component.hovered.value).toBe('')
    expect(component.dragged.value).toBe('first')
    component.onDrop(groups[0], event)
    expect(emit).not.toHaveBeenCalled()
  })

  it('keeps touch and keyboard ordering and releases pointer listeners on unmount', () => {
    const destination = { dataset: { moodCardKey: 'second' } }
    vi.stubGlobal('document', { elementFromPoint: () => ({ closest: () => destination }) })
    component.root.value = { contains: () => true, querySelectorAll: () => [null, destination] }
    const pointer = {
      pointerType: 'touch',
      isPrimary: true,
      pointerId: 8,
      clientX: 10,
      clientY: 20,
      preventDefault: vi.fn()
    }
    component.pointerStart(groups[0], pointer)
    expect(listeners.size).toBe(3)
    listeners.get('pointermove')(pointer)
    expect(component.hovered.value).toBe('second')
    listeners.get('pointerup')(pointer)
    expect(emit).toHaveBeenCalledWith('reorder', 'first', 'second')
    expect(listeners.size).toBe(0)
    component.keyboardMove(groups[0], 0, { key: 'ArrowRight', preventDefault: vi.fn() })
    expect(emit).toHaveBeenCalledTimes(2)
    component.pointerStart(groups[0], pointer)
    state.unmount()
    expect(listeners.size).toBe(0)
    expect(component.dragged.value).toBe('')
  })
})
