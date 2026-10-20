import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createSSRApp, effectScope } from 'vue'
import { renderToString } from 'vue/server-renderer'
import { createMemoryHistory, createRouter } from 'vue-router'
import SessionLink from './SessionLink.vue'

const state = vi.hoisted(() => ({ router: null }))
vi.mock('vue', async (original) => ({
  ...(await original()),
  useSSRContext: () => ({ modules: new Set() })
}))
vi.mock('vue-router', async (original) => ({
  ...(await original()),
  useRouter: () => state.router,
  useRoute: () => state.router.currentRoute.value
}))

const emptyPage = { render: () => null }
let scope

beforeEach(async () => {
  state.router = createRouter({
    history: createMemoryHistory(),
    routes: ['/', '/mowersettings', '/maasettings', '/plan-editor', '/record/report'].map(
      (path) => ({ path, component: emptyPage })
    )
  })
  await state.router.push('/?token=session-token&window_shell=1')
  vi.stubGlobal('window', {
    pywebview: { api: {} },
    location: { search: '?token=session-token&window_shell=1' }
  })
  scope = effectScope()
})
afterEach(() => {
  scope.stop()
  vi.unstubAllGlobals()
})

function link(to, replace = false) {
  return scope.run(() => SessionLink.setup({ to, replace }, { expose: () => {} }))
}
function click(fields = {}) {
  const event = new Event('click', { cancelable: true })
  Object.assign(event, { button: 0, ...fields })
  return event
}

describe('session links', () => {
  it('renders a credentialed href before a click, retaining destination query and fragment', async () => {
    const app = createSSRApp(SessionLink, {
      to: '/mowersettings?view=details#software-update',
      class: 'back-link',
      title: 'Settings'
    })
    app.use(state.router)
    const html = await renderToString(app)
    expect(html).toContain(
      'href="/mowersettings?token=session-token&amp;window_shell=1&amp;view=details#software-update"'
    )
    expect(html).toContain('class="back-link"')
    expect(html).toContain('title="Settings"')
  })

  it.each([
    ['/mowersettings', {}],
    ['/maasettings', { ctrlKey: true }],
    ['/plan-editor', { metaKey: true }],
    ['/record/report', { shiftKey: true }],
    ['/mowersettings', { button: 1 }]
  ])('keeps desktop navigation to %s inside the window', async (path, modifiers) => {
    const navigate = vi.fn()
    const event = click(modifiers)
    await link(path).follow(event, navigate)
    expect(event.defaultPrevented).toBe(true)
    expect(navigate).not.toHaveBeenCalled()
    expect(state.router.currentRoute.value.path).toBe(path)
    expect(state.router.currentRoute.value.query.token).toBe('session-token')
  })

  it.each([{ ctrlKey: true }, { metaKey: true }, { shiftKey: true }, { button: 1 }])(
    'keeps desktop links inside the window before bridge injection with %j',
    async (modifiers) => {
      window.pywebview = undefined
      const event = click(modifiers)
      const navigate = vi.fn()
      await link('/mowersettings').follow(event, navigate)
      expect(event.defaultPrevented).toBe(true)
      expect(navigate).not.toHaveBeenCalled()
      expect(state.router.currentRoute.value.path).toBe('/mowersettings')
      expect(state.router.currentRoute.value.query.token).toBe('session-token')
    }
  )

  it('uses the desktop URL marker when the current route has no shell query', async () => {
    window.pywebview = undefined
    await state.router.push('/?token=session-token')
    const event = click({ ctrlKey: true })
    const navigate = vi.fn()
    await link('/mowersettings').follow(event, navigate)
    expect(event.defaultPrevented).toBe(true)
    expect(navigate).not.toHaveBeenCalled()
    expect(state.router.currentRoute.value.path).toBe('/mowersettings')
  })

  it('retains desktop navigation after the current URL loses its shell marker', async () => {
    window.pywebview = undefined
    const component = link('/mowersettings')
    window.location.search = '?token=session-token'
    await state.router.push('/?token=session-token')
    const event = click({ button: 1 })
    const navigate = vi.fn()
    await component.follow(event, navigate)
    expect(event.defaultPrevented).toBe(true)
    expect(navigate).not.toHaveBeenCalled()
    expect(state.router.currentRoute.value.path).toBe('/mowersettings')
  })

  it('keeps bridge-backed desktop links internal without shell metadata', async () => {
    window.location.search = '?token=session-token'
    await state.router.push('/?token=session-token')
    const event = click({ ctrlKey: true })
    const navigate = vi.fn()
    await link('/mowersettings').follow(event, navigate)
    expect(event.defaultPrevented).toBe(true)
    expect(navigate).not.toHaveBeenCalled()
    expect(state.router.currentRoute.value.path).toBe('/mowersettings')
  })

  it('keeps an explicit destination token and supports replacement navigation', async () => {
    await link('/mowersettings?token=destination-token#software-update', true).follow(
      click(),
      vi.fn()
    )
    expect(state.router.currentRoute.value.query.token).toBe('destination-token')
    expect(state.router.currentRoute.value.hash).toBe('#software-update')
  })

  it.each([{ ctrlKey: true }, { metaKey: true }, { shiftKey: true }, { button: 1 }])(
    'leaves browser link gestures to RouterLink with credentials and %j',
    async (modifiers) => {
      window.pywebview = undefined
      window.location.search = '?token=session-token'
      await state.router.push('/?token=session-token')
      const component = link('/mowersettings')
      const event = click(modifiers)
      const navigate = vi.fn()
      await component.follow(event, navigate)
      expect(event.defaultPrevented).toBe(false)
      expect(navigate).toHaveBeenCalledWith(event)
      expect(component.destination.value.query.token).toBe('session-token')
      expect(state.router.currentRoute.value.path).toBe('/')
    }
  )

  it('leaves context-menu clicks alone without changing the page', async () => {
    const event = click({ button: 2 })
    const navigate = vi.fn()
    await link('/mowersettings').follow(event, navigate)
    expect(event.defaultPrevented).toBe(false)
    expect(state.router.currentRoute.value.path).toBe('/')
  })

  it('does not invent a token for a session without credentials', async () => {
    await state.router.push('/')
    const app = createSSRApp(SessionLink, { to: '/mowersettings' })
    app.use(state.router)
    expect(await renderToString(app)).toContain('href="/mowersettings"')
  })

  it('does not override an already prevented click', async () => {
    const event = click()
    event.preventDefault()
    const navigate = vi.fn()
    await link('/mowersettings').follow(event, navigate)
    expect(navigate).toHaveBeenCalledWith(event)
    expect(state.router.currentRoute.value.path).toBe('/')
  })
})
