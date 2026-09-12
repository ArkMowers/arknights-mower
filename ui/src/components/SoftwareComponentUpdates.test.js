import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest'
import { effectScope } from 'vue'
import Component from './SoftwareComponentUpdates.vue'
const state = vi.hoisted(() => ({ mounted: [], unmounted: [], client: null, confirm: vi.fn() }))
vi.mock('vue', async (original) => ({
  ...(await original()),
  useSSRContext: () => ({ modules: new Set() }),
  inject: () => state.client,
  onMounted: (fn) => state.mounted.push(fn),
  onUnmounted: (fn) => state.unmounted.push(fn)
}))
vi.mock('naive-ui', () => ({
  useDialog: () => ({ warning: state.confirm }),
  useMessage: () => ({ success: vi.fn() })
}))
describe('optional component updates', () => {
  let scope
  let component
  beforeEach(() => {
    vi.useFakeTimers()
    state.mounted = []
    state.unmounted = []
    state.confirm.mockClear()
    state.client = {
      get: vi.fn(async () => ({
        data: {
          ok: true,
          installed: { version: '1.0.0', sha256: 'a' },
          latest: { available: false, sha256: 'a' },
          auto_check: true
        }
      })),
      post: vi.fn(async () => ({ data: { ok: true } }))
    }
    scope = effectScope()
    component = scope.run(() =>
      Component.setup(
        {
          component: {
            label: 'interface',
            endpoint: '/component',
            check: true,
            hint: 'New instances use the updated interface'
          },
          disabled: false
        },
        { expose: () => {} }
      )
    )
  })
  afterEach(() => {
    state.unmounted.forEach((fn) => fn())
    scope.stop()
    vi.useRealTimers()
  })
  it('only reads cached status on mount, never installs or checks the network implicitly', async () => {
    await Promise.all(state.mounted.map((fn) => fn()))
    expect(state.client.get).toHaveBeenCalledWith('/component')
    expect(state.client.post).not.toHaveBeenCalled()
  })
  it('sends the same update intent header used by shared update routes', async () => {
    await component.run({ action: 'check' })
    expect(state.client.post).toHaveBeenCalledWith(
      '/component',
      { action: 'check' },
      { headers: { 'X-Mower-Update': '1' } }
    )
  })
  it('waits for confirmation before install or reset', async () => {
    component.confirm('install')
    expect(state.client.post).not.toHaveBeenCalled()
    await state.confirm.mock.calls[0][0].onPositiveClick()
    expect(state.client.post.mock.calls[0][1]).toEqual({ action: 'install' })
  })
})
