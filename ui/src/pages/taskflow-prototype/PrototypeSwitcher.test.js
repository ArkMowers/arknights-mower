import { afterEach, describe, expect, it, vi } from 'vitest'
import { createRenderer, h, ssrContextKey } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import PrototypeSwitcher from './PrototypeSwitcher.vue'

// A minimal host mounts the real component and its window listener without a browser.
const renderer = createRenderer({
  createElement: (tag) => ({ tag, children: [] }),
  createText: (text) => ({ text }),
  createComment: (text) => ({ text }),
  setText: (node, text) => (node.text = text),
  setElementText: (node, text) => (node.text = text),
  parentNode: (node) => node.parent,
  nextSibling: () => null,
  patchProp: () => {},
  insert(node, parent) {
    node.parent = parent
    parent.children.push(node)
  },
  remove(node) {
    const siblings = node.parent.children
    siblings.splice(siblings.indexOf(node), 1)
  }
})

let app
afterEach(() => {
  app?.unmount()
  vi.unstubAllGlobals()
})

async function setup() {
  const listeners = new Map()
  vi.stubGlobal('window', {
    addEventListener: (name, listener) => listeners.set(name, listener),
    removeEventListener: (name) => listeners.delete(name)
  })
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/taskflow-prototype', component: { render: () => null } }]
  })
  await router.push('/taskflow-prototype?variant=E&token=demo')
  const replace = vi.spyOn(router, 'replace')
  // Vitest compiles SFC templates for SSR; these checks exercise setup and lifecycle.
  const Switcher = { ...PrototypeSwitcher, render: () => null }
  app = renderer.createApp({
    render: () =>
      h(Switcher, {
        variants: [
          { key: 'E', name: '程序清单' },
          { key: 'F', name: '工程图纸' }
        ]
      })
  })
  app.provide(ssrContextKey, { modules: new Set() })
  app.use(router)
  app.mount({ children: [] })
  return { router, replace, listeners, keydown: listeners.get('keydown') }
}

describe('prototype keyboard switching', () => {
  it('keeps the current variant when a field already handled the arrow key', async () => {
    const { router, replace, keydown } = await setup()
    keydown({ key: 'ArrowRight', defaultPrevented: true, target: { closest: () => null } })
    expect(replace).not.toHaveBeenCalled()
    expect(router.currentRoute.value.query.variant).toBe('E')
  })

  it.each(['input', '[role="slider"]', '[role="radio"]'])(
    'keeps keyboard focus on %s',
    async (fieldSelector) => {
      const { replace, keydown } = await setup()
      keydown({
        key: 'ArrowLeft',
        target: {
          closest: (selector) => (selector.split(', ').includes(fieldSelector) ? {} : null)
        }
      })
      expect(replace).not.toHaveBeenCalled()
    }
  )

  it('switches on an unhandled arrow key and preserves the remaining query', async () => {
    const { router, replace, keydown } = await setup()
    const preventDefault = vi.fn()
    keydown({ key: 'ArrowRight', target: { closest: () => null }, preventDefault })
    await replace.mock.results[0].value
    expect(router.currentRoute.value.query).toEqual({ variant: 'F', token: 'demo' })
    expect(preventDefault).toHaveBeenCalledOnce()
  })

  it('removes its global shortcut listener when unmounted', async () => {
    const { listeners } = await setup()
    app.unmount()
    app = undefined
    expect(listeners.has('keydown')).toBe(false)
  })
})
