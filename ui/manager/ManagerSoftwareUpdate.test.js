import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { effectScope } from 'vue'
import ManagerSoftwareUpdate from './ManagerSoftwareUpdate.vue'

const hooks = vi.hoisted(() => ({ mounted: [], unmounted: [] }))
vi.mock('vue', async (original) => ({
  ...(await original()),
  useSSRContext: () => ({ modules: new Set() }),
  onMounted: (callback) => hooks.mounted.push(callback),
  onUnmounted: (callback) => hooks.unmounted.push(callback)
}))
describe('manager Mower update', () => {
  let api, view, scope, props
  beforeEach(async () => {
    vi.useFakeTimers()
    hooks.mounted = []
    hooks.unmounted = []
    api = {
      get_mower_update_info: vi.fn(async () => ({
        ok: true,
        version: 'old',
        blockers: [],
        settings: { channel: 'beta', background: true },
        channels: [],
        instances: [{ name: 'one' }]
      })),
      get_mower_update_status: vi.fn(async () => ({ status: 'idle' })),
      check_mower_update: vi.fn(async () => ({
        ok: true,
        available: true,
        version: 'new',
        check_id: 'receipt'
      })),
      start_mower_update: vi.fn(async () => ({ ok: true, id: 'job' })),
      cancel_mower_update: vi.fn(async () => ({ ok: true }))
    }
    props = { api, disabled: false }
    scope = effectScope()
    view = scope.run(() => ManagerSoftwareUpdate.setup(props, { expose() {} }))
    await Promise.all(hooks.mounted.map((callback) => callback()))
  })
  afterEach(() => {
    hooks.unmounted.forEach((callback) => callback())
    scope.stop()
    vi.useRealTimers()
  })
  it('checks selected channel and submits only the confirmed target and restart mode', async () => {
    await view.check()
    expect(api.check_mower_update).toHaveBeenCalledWith('beta')
    view.requestInstall()
    expect(api.start_mower_update).not.toHaveBeenCalled()
    view.checked.value = { available: true, version: 'different', check_id: 'other' }
    view.background.value = false
    await view.install()
    expect(api.start_mower_update).toHaveBeenCalledWith('receipt', true)
  })
  it('clears a prior check when changing channels and blocks installation for local blockers', async () => {
    await view.check()
    view.channel.value = 'stable'
    await Promise.resolve()
    expect(view.checked.value).toBeNull()
    await view.check()
    view.info.value.blockers = ['read only']
    view.requestInstall()
    expect(view.confirmation.value).toBeNull()
  })
  it('reports submit failure without claiming an update started', async () => {
    await view.check()
    view.requestInstall()
    api.start_mower_update.mockRejectedValue(new Error('expired'))
    await view.install()
    expect(view.error.value).toBe('expired')
    expect(view.job.value.status).toBe('idle')
  })
  it('polls an existing job and stops at completion or unmount', async () => {
    api.get_mower_update_status
      .mockResolvedValueOnce({ status: 'running' })
      .mockResolvedValue({ status: 'succeeded' })
    await view.load()
    await vi.advanceTimersByTimeAsync(2000)
    const count = api.get_mower_update_status.mock.calls.length
    await vi.advanceTimersByTimeAsync(6000)
    expect(api.get_mower_update_status).toHaveBeenCalledTimes(count)
    api.get_mower_update_status.mockResolvedValue({ status: 'running' })
    await view.load()
    hooks.unmounted.forEach((callback) => callback())
    const finalCount = api.get_mower_update_status.mock.calls.length
    await vi.advanceTimersByTimeAsync(6000)
    expect(api.get_mower_update_status).toHaveBeenCalledTimes(finalCount)
  })
  it('blocks update while MAA maintenance is active and delegates cancellation', async () => {
    await view.check()
    props.disabled = true
    view.requestInstall()
    expect(view.confirmation.value).toBeNull()
    view.job.value = { id: 'job', status: 'running', cancellable: true }
    await view.cancel()
    expect(api.cancel_mower_update).toHaveBeenCalledWith('job')
  })
})
