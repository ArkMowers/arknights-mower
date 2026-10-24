import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { NScrollbar } from 'naive-ui'
import SidebarScroll from './SidebarScroll.vue'

const hooks = vi.hoisted(() => ({}))
vi.mock('vue', async (original) => ({
  ...(await original()),
  useSSRContext: () => ({ modules: new Set() }),
  onMounted: (callback) => (hooks.mount = callback),
  onBeforeUnmount: (callback) => (hooks.unmount = callback)
}))

let component, container, content, scrollbar, internalScrollTo, observer

beforeEach(() => {
  vi.stubGlobal('window', { matchMedia: () => ({ matches: false }) })
  vi.stubGlobal(
    'ResizeObserver',
    class {
      constructor(callback) {
        observer = { callback, observe: vi.fn(), disconnect: vi.fn() }
        return observer
      }
    }
  )
  container = { clientHeight: 200, scrollHeight: 600, scrollTop: 0 }
  content = {}
  scrollbar = NScrollbar.setup()
  internalScrollTo = vi.fn()
  scrollbar.scrollbarInstRef.value = { scrollTo: internalScrollTo }
  component = SidebarScroll.setup({}, { expose: vi.fn() })
  component.scrollbar.value = scrollbar
  component.root.value = {
    querySelector: (selector) =>
      ({ '.n-scrollbar-container': container, '.n-scrollbar-content': content })[selector] ?? null
  }
  hooks.mount()
})

afterEach(() => {
  hooks.unmount()
  vi.unstubAllGlobals()
})

describe('sidebar scrollbar endpoints', () => {
  it('dims the upper endpoint at the start and the lower endpoint at the end', () => {
    expect(component.canScrollUp.value).toBe(false)
    expect(component.canScrollDown.value).toBe(true)
    container.scrollTop = 150
    component.sync()
    expect(component.canScrollUp.value).toBe(true)
    expect(component.canScrollDown.value).toBe(true)
    container.scrollTop = 400
    component.sync()
    expect(component.canScrollUp.value).toBe(true)
    expect(component.canScrollDown.value).toBe(false)
  })

  it('hides both endpoints when collapsed groups fit without scrolling', () => {
    expect(component.scrollRange.value).toBe(400)
    container.scrollHeight = 160
    observer.callback()
    expect(component.scrollRange.value).toBe(0)
    expect(component.canScrollUp.value).toBe(false)
    expect(component.canScrollDown.value).toBe(false)
    container.scrollHeight = 600
    observer.callback()
    expect(component.scrollRange.value).toBe(400)
    expect(component.canScrollDown.value).toBe(true)
  })

  it('tracks viewport changes as well as content changes', () => {
    expect(observer.observe).toHaveBeenCalledWith(container)
    expect(observer.observe).toHaveBeenCalledWith(content)
    container.clientHeight = 700
    observer.callback()
    expect(component.scrollRange.value).toBe(0)
    container.clientHeight = 300
    observer.callback()
    expect(component.scrollRange.value).toBe(300)
  })

  it('scrolls by a readable step and stops at the actual boundaries', () => {
    component.scroll(1)
    expect(internalScrollTo).toHaveBeenLastCalledWith({ top: 140, behavior: 'smooth' }, undefined)
    container.scrollTop = 360
    component.sync()
    component.scroll(1)
    expect(internalScrollTo).toHaveBeenLastCalledWith({ top: 400, behavior: 'smooth' }, undefined)
    container.scrollTop = 40
    component.sync()
    component.scroll(-1)
    expect(internalScrollTo).toHaveBeenLastCalledWith({ top: 0, behavior: 'smooth' }, undefined)
  })

  it('uses immediate scrolling when reduced motion is requested', () => {
    window.matchMedia = () => ({ matches: true })
    component.scroll(1)
    expect(internalScrollTo).toHaveBeenCalledWith({ top: 140, behavior: 'auto' }, undefined)
  })

  it('measures the DOM with the actual public NScrollbar instance', () => {
    expect(scrollbar.containerRef).toBeUndefined()
    expect(scrollbar.contentRef).toBeUndefined()
    expect(scrollbar.handleMouseEnterWrapper).toBeUndefined()
    expect(component.scrollRange.value).toBe(400)
    expect(observer.observe).toHaveBeenCalledWith(container)
    component.scroll(1)
    expect(internalScrollTo).toHaveBeenCalledWith({ top: 140, behavior: 'smooth' }, undefined)
  })

  it('releases both resize observations when the sidebar unmounts', () => {
    hooks.unmount()
    expect(observer.disconnect).toHaveBeenCalledOnce()
  })
})
