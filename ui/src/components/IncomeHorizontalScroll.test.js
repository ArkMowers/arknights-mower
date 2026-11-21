import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'
import IncomeHorizontalScroll from './IncomeHorizontalScroll.vue'

const hooks = vi.hoisted(() => ({}))
vi.mock('vue', async (original) => ({
  ...(await original()),
  useSSRContext: () => ({ modules: new Set() }),
  onMounted: (callback) => (hooks.mount = callback),
  onBeforeUnmount: (callback) => (hooks.unmount = callback)
}))
let component, target, selected, resize, mutation
const makeTarget = () =>
  Object.assign(new EventTarget(), {
    scrollWidth: 1040,
    clientWidth: 600,
    scrollLeft: 0,
    firstElementChild: {}
  })
beforeEach(() => {
  vi.stubGlobal(
    'ResizeObserver',
    class {
      constructor(callback) {
        resize = { callback, observe: vi.fn(), disconnect: vi.fn() }
        return resize
      }
    }
  )
  vi.stubGlobal(
    'MutationObserver',
    class {
      constructor(callback) {
        mutation = { callback, observe: vi.fn(), disconnect: vi.fn() }
        return mutation
      }
    }
  )
  target = selected = makeTarget()
  component = IncomeHorizontalScroll.setup({ selector: '.content' }, { expose: vi.fn() })
  component.root.value = { querySelector: () => selected }
  component.scrollbar.value = { scrollLeft: 0 }
  hooks.mount()
})
afterEach(() => {
  hooks.unmount()
  vi.unstubAllGlobals()
})

it('synchronizes dragging the bottom scrollbar and scrolling the original content', () => {
  component.scrollbar.value.scrollLeft = 300
  component.syncFromScrollbar()
  expect(target.scrollLeft).toBe(300)
  target.scrollLeft = 120
  target.dispatchEvent(new Event('scroll'))
  expect(component.scrollbar.value.scrollLeft).toBe(120)
})

it('updates the scroll range after resizing and preserves the content position', async () => {
  expect(component.contentWidth.value).toBe(1040)
  expect(component.viewportWidth.value).toBe(600)
  target.clientWidth = 800
  target.scrollLeft = 240
  resize.callback()
  await nextTick()
  expect(component.viewportWidth.value).toBe(800)
  expect(component.scrollbar.value.scrollLeft).toBe(240)
})

it('attaches to a newly expanded chart and detaches from collapsed content', async () => {
  selected = null
  mutation.callback()
  expect(component.contentWidth.value).toBe(0)
  target.scrollLeft = 100
  target.dispatchEvent(new Event('scroll'))
  expect(component.scrollbar.value.scrollLeft).toBe(0)
  selected = makeTarget()
  selected.scrollLeft = 200
  mutation.callback()
  await nextTick()
  expect(resize.observe).toHaveBeenCalledWith(selected)
  expect(component.scrollbar.value.scrollLeft).toBe(200)
})

it('releases observers and scroll listeners when the dialog closes', () => {
  hooks.unmount()
  expect(resize.disconnect).toHaveBeenCalled()
  expect(mutation.disconnect).toHaveBeenCalled()
  target.scrollLeft = 100
  target.dispatchEvent(new Event('scroll'))
  expect(component.scrollbar.value.scrollLeft).toBe(0)
})
