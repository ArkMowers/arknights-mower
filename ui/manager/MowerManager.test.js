import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { effectScope, nextTick } from 'vue'
import MowerManager from './MowerManager.vue'
import { managerCall } from './bridge.js'

const hooks = vi.hoisted(() => ({ mounted: [], unmounted: [] }))
vi.mock('vue', async (original) => ({
  ...(await original()),
  useSSRContext: () => ({ modules: new Set() }),
  onMounted: (callback) => hooks.mounted.push(callback),
  onUnmounted: (callback) => hooks.unmounted.push(callback)
}))

describe('manager instance controls', () => {
  let scope, component, api, rows
  const stopped = () => ({
    name: 'first',
    path: '/first',
    token: '',
    port: null,
    state: 'stopped',
    editable: true,
    can_start: true,
    ai_assistant_enabled: false,
    can_stop: false
  })

  beforeEach(() => {
    vi.useFakeTimers()
    hooks.mounted = []
    hooks.unmounted = []
    rows = [stopped()]
    api = {
      get_instances: vi.fn(async () => structuredClone(rows)),
      mark_ready: vi.fn(async () => {}),
      start: vi.fn(async () => {
        rows[0] = {
          ...rows[0],
          state: 'starting',
          editable: false,
          can_start: false,
          can_stop: true
        }
        return { ok: true }
      }),
      stop: vi.fn(async () => {
        rows[0] = { ...rows[0], state: 'stopping', can_stop: false }
        return { ok: true }
      }),
      start_all: vi.fn(async () => ({ ok: true })),
      stop_all: vi.fn(async () => ({ ok: true })),
      rename: vi.fn(async () => {}),
      select_path: vi.fn(async () => null),
      remove: vi.fn(async () => {}),
      update_settings: vi.fn(async () => {})
    }
    vi.stubGlobal('window', { pywebview: { api }, addEventListener() {}, removeEventListener() {} })
  })

  async function mount() {
    scope = effectScope()
    component = scope.run(() => MowerManager.setup({}, { expose() {} }))
    await Promise.all(hooks.mounted.map((callback) => callback()))
    await nextTick()
  }

  afterEach(() => {
    hooks.unmounted.forEach((callback) => callback())
    scope?.stop()
    scope = null
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })

  it('changes start to stop and suppresses repeat clicks while dispatch is pending', async () => {
    await mount()
    component.lifecycle(0)
    component.lifecycle(0)
    await vi.advanceTimersByTimeAsync(0)
    expect(api.start).toHaveBeenCalledOnce()
    expect(component.instances.value[0].state).toBe('starting')
    component.lifecycle(0)
    await vi.advanceTimersByTimeAsync(0)
    expect(api.stop).toHaveBeenCalledOnce()
    expect(component.instances.value[0].state).toBe('stopping')
    component.lifecycle(0)
    expect(api.stop).toHaveBeenCalledOnce()
  })

  it.each(['start', 'stop'])(
    'requires confirmation before bulk %s and cancellation does nothing',
    async (action) => {
      await mount()
      component.confirmBulk(action)
      expect(component.confirmation.value).toBe(action)
      expect(api.start_all).not.toHaveBeenCalled()
      expect(api.stop_all).not.toHaveBeenCalled()
      component.confirmation.value = null
      expect(api.start_all).not.toHaveBeenCalled()
      expect(api.stop_all).not.toHaveBeenCalled()
      component.confirmBulk(action)
      await component.applyBulk()
      expect(api[action === 'start' ? 'start_all' : 'stop_all']).toHaveBeenCalledOnce()
    }
  )

  it('does not submit disabled individual starts and does not implement a bulk bypass', async () => {
    rows[0].can_start = false
    await mount()
    component.lifecycle(0)
    expect(api.start).not.toHaveBeenCalled()
    component.confirmBulk('start')
    await component.applyBulk()
    expect(api.start_all).toHaveBeenCalledOnce()
    expect(api.start).not.toHaveBeenCalled()
  })

  it('requires named deletion confirmation and cancellation does nothing', async () => {
    await mount()
    component.confirmDelete(0)
    expect(component.deleting.value).toEqual({ idx: 0, name: 'first', path: '/first' })
    expect(api.remove).not.toHaveBeenCalled()
    component.deleting.value = null
    await component.applyDelete()
    expect(api.remove).not.toHaveBeenCalled()
    component.confirmDelete(0)
    await component.applyDelete()
    expect(api.remove).toHaveBeenCalledExactlyOnceWith(0)
    expect(component.deleting.value).toBeNull()
  })

  it.each(['running', 'replaced'])(
    'cancels deletion when the selected row is %s',
    async (change) => {
      await mount()
      component.confirmDelete(0)
      if (change === 'running') rows[0].editable = false
      else rows[0].name = 'other'
      await component.refresh()
      expect(component.deleting.value).toBeNull()
      await component.applyDelete()
      expect(api.remove).not.toHaveBeenCalled()
    }
  )

  it('clears old warnings after bulk success but retains actual startup failures', async () => {
    await mount()
    component.error.value = 'old warning'
    component.confirmBulk('start')
    await component.applyBulk()
    expect(component.error.value).toBe('')
    api.start_all.mockResolvedValueOnce({ ok: false, message: 'spawn failed' })
    component.confirmBulk('start')
    await component.applyBulk()
    expect(component.error.value).toBe('spawn failed')
  })

  it('requires five seconds and acknowledgement on enable, then waits for Save', async () => {
    await mount()
    component.edit(0, 'settings')
    await component.changeAssistant(true)
    expect(component.assistantConfirmation.value).toMatchObject({ idx: 0, original: false })
    expect(component.draft.value.ai_assistant_enabled).toBe(false)
    await component.save()
    expect(api.update_settings).not.toHaveBeenCalled()
    component.riskAcknowledged.value = true
    await vi.advanceTimersByTimeAsync(4999)
    component.confirmAssistantChange()
    expect(component.draft.value.ai_assistant_enabled).toBe(false)
    await vi.advanceTimersByTimeAsync(1)
    component.riskAcknowledged.value = false
    component.confirmAssistantChange()
    expect(component.draft.value.ai_assistant_enabled).toBe(false)
    component.riskAcknowledged.value = true
    component.confirmAssistantChange()
    expect(component.assistantConfirmation.value).toBeNull()
    expect(component.draft.value.ai_assistant_enabled).toBe(true)
    expect(component.editing.value).toEqual({ idx: 0, kind: 'settings' })
    expect(api.update_settings).not.toHaveBeenCalled()
    component.draft.value.token = 'after-reading'
    component.draft.value.port = 58001
    await component.save()
    expect(api.update_settings).toHaveBeenCalledExactlyOnceWith(0, {
      token: 'after-reading',
      port: 58001,
      ai_assistant_enabled: true
    })
    expect(component.editing.value).toBeNull()
  })

  it('disables without a reading dialog and persists only on Save', async () => {
    rows[0].ai_assistant_enabled = true
    await mount()
    component.edit(0, 'settings')
    await component.changeAssistant(false)
    expect(component.assistantConfirmation.value).toBeNull()
    expect(component.draft.value.ai_assistant_enabled).toBe(false)
    expect(api.update_settings).not.toHaveBeenCalled()
    await component.save()
    expect(api.update_settings).toHaveBeenCalledExactlyOnceWith(0, {
      token: '',
      port: null,
      ai_assistant_enabled: false
    })
  })

  it('cancels without saving and starts a fresh reading interval on retry', async () => {
    await mount()
    component.edit(0, 'settings')
    component.draft.value.token = 'keep-draft'
    await component.changeAssistant(true)
    await vi.advanceTimersByTimeAsync(5000)
    component.cancelAssistantConfirmation()
    expect(api.update_settings).not.toHaveBeenCalled()
    expect(component.draft.value.ai_assistant_enabled).toBe(false)
    expect(component.draft.value.token).toBe('keep-draft')
    await component.changeAssistant(true)
    component.riskAcknowledged.value = true
    component.confirmAssistantChange()
    expect(api.update_settings).not.toHaveBeenCalled()
    expect(component.riskSeconds.value).toBe(5)
  })

  it('retains the saved AI choice and draft when a confirmed write fails', async () => {
    await mount()
    component.edit(0, 'settings')
    await component.changeAssistant(true)
    await vi.advanceTimersByTimeAsync(5000)
    component.riskAcknowledged.value = true
    component.confirmAssistantChange()
    api.update_settings.mockRejectedValueOnce(new Error('write failed'))
    await component.save()
    expect(rows[0].ai_assistant_enabled).toBe(false)
    expect(component.draft.value.ai_assistant_enabled).toBe(true)
    expect(component.editing.value).toEqual({ idx: 0, kind: 'settings' })
    expect(component.error.value).toBe('write failed')
  })

  it.each(['running', 'replaced'])(
    'cancels AI confirmation when its instance is %s',
    async (change) => {
      await mount()
      component.edit(0, 'settings')
      await component.changeAssistant(true)
      if (change === 'running') rows[0].editable = false
      else rows[0].path = '/other'
      await component.refresh()
      await vi.advanceTimersByTimeAsync(5000)
      component.riskAcknowledged.value = true
      await component.confirmAssistantChange()
      expect(component.assistantConfirmation.value).toBeNull()
      expect(component.draft.value.ai_assistant_enabled).toBe(false)
      expect(api.update_settings).not.toHaveBeenCalled()
    }
  )

  it('does not retain an enabled draft after cancelling the settings editor', async () => {
    await mount()
    component.edit(0, 'settings')
    await component.changeAssistant(true)
    await vi.advanceTimersByTimeAsync(5000)
    component.riskAcknowledged.value = true
    component.confirmAssistantChange()
    component.editing.value = null
    component.edit(0, 'settings')
    expect(component.draft.value.ai_assistant_enabled).toBe(false)
    expect(api.update_settings).not.toHaveBeenCalled()
    await component.changeAssistant(true)
    expect(component.riskSeconds.value).toBe(5)
    expect(component.riskAcknowledged.value).toBe(false)
  })

  it('requires a new acknowledgement when an enabled draft is turned off and on again', async () => {
    await mount()
    component.edit(0, 'settings')
    await component.changeAssistant(true)
    await vi.advanceTimersByTimeAsync(5000)
    component.riskAcknowledged.value = true
    component.confirmAssistantChange()
    await component.changeAssistant(false)
    await component.changeAssistant(true)
    expect(component.draft.value.ai_assistant_enabled).toBe(false)
    expect(component.riskAcknowledged.value).toBe(false)
    expect(component.riskSeconds.value).toBe(5)
    expect(api.update_settings).not.toHaveBeenCalled()
  })

  it('only persists confirmed settings and preserves drafts after write failure', async () => {
    await mount()
    component.edit(0, 'settings')
    component.draft.value.token = 'new-secret'
    component.draft.value.port = 58001
    expect(api.update_settings).not.toHaveBeenCalled()
    await component.refresh()
    expect(component.draft.value.token).toBe('new-secret')
    api.update_settings.mockRejectedValueOnce(new Error('write failed'))
    await component.save()
    expect(component.editing.value).toEqual({ idx: 0, kind: 'settings' })
    expect(component.error.value).toBe('write failed')
    expect(component.draft.value.port).toBe(58001)
    await component.save()
    expect(api.update_settings).toHaveBeenLastCalledWith(0, { token: 'new-secret', port: 58001 })
    expect(component.editing.value).toBeNull()
  })

  it('locks all editing on running-process state and closes an obsolete draft', async () => {
    await mount()
    component.edit(0, 'name')
    rows[0] = { ...rows[0], state: 'running', editable: false, can_start: false, can_stop: true }
    await vi.advanceTimersByTimeAsync(1500)
    expect(component.editing.value).toBeNull()
    component.edit(0, 'settings')
    expect(component.editing.value).toBeNull()
    expect(api.rename).not.toHaveBeenCalled()
    expect(api.update_settings).not.toHaveBeenCalled()
  })

  it('disables actions when state refresh fails and recovers on a later snapshot', async () => {
    await mount()
    api.get_instances.mockRejectedValueOnce(new Error('unreadable'))
    await vi.advanceTimersByTimeAsync(1500)
    expect(component.unavailable.value).toBe(true)
    component.lifecycle(0)
    expect(api.start).not.toHaveBeenCalled()
    await vi.advanceTimersByTimeAsync(1500)
    expect(component.unavailable.value).toBe(false)
  })

  it('does not let an older status response replace a newer snapshot', async () => {
    await mount()
    let resolveOld
    api.get_instances.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolveOld = resolve
        })
    )
    const old = component.refresh()
    await vi.advanceTimersByTimeAsync(0)
    rows[0].name = 'new'
    await component.refresh()
    resolveOld([{ ...stopped(), name: 'old' }])
    await old
    expect(component.instances.value[0].name).toBe('new')
  })

  it('cleans up status refresh on unmount', async () => {
    await mount()
    hooks.unmounted.forEach((callback) => callback())
    const calls = api.get_instances.mock.calls.length
    await vi.advanceTimersByTimeAsync(3000)
    expect(api.get_instances).toHaveBeenCalledTimes(calls)
  })

  it.each(['confirm', 'cancel'])(
    'keeps folder selection busy past the API deadline until %s',
    async (outcome) => {
      await mount()
      let finish
      api.select_path.mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            finish = () => {
              if (outcome === 'confirm') rows[0].path = '/selected'
              resolve(outcome === 'confirm' ? '/selected' : null)
            }
          })
      )
      const reads = api.get_instances.mock.calls.length
      const pending = component.selectPath(0)
      await vi.advanceTimersByTimeAsync(16000)
      expect(component.busy.value).toBe(true)
      expect(component.unavailable.value).toBe(true)
      expect(component.error.value).toBe('')
      expect(api.get_instances).toHaveBeenCalledTimes(reads)
      component.lifecycle(0)
      expect(api.start).not.toHaveBeenCalled()
      finish()
      await pending
      expect(component.busy.value).toBe(false)
      expect(component.unavailable.value).toBe(false)
      expect(component.error.value).toBe('')
      expect(component.instances.value[0].path).toBe(outcome === 'confirm' ? '/selected' : '/first')
      expect(api.select_path).toHaveBeenCalledExactlyOnceWith(0)
    }
  )

  it('reports folder selection errors only when the native dialog returns', async () => {
    await mount()
    let reject
    api.select_path.mockImplementationOnce(
      () =>
        new Promise((resolve, failure) => {
          reject = failure
        })
    )
    const pending = component.selectPath(0)
    await vi.advanceTimersByTimeAsync(16000)
    expect(component.busy.value).toBe(true)
    expect(component.error.value).toBe('')
    reject(new Error('selection failed'))
    await pending
    expect(component.error.value).toBe('selection failed')
    expect(component.busy.value).toBe(false)
    expect(component.instances.value[0].path).toBe('/first')
  })

  it('still bounds ordinary API calls without retrying the action', async () => {
    await mount()
    api.start.mockImplementationOnce(() => new Promise(() => {}))
    const pending = component.execute(() => api.start(0))
    await vi.advanceTimersByTimeAsync(16000)
    await pending
    expect(component.error.value).toContain('操作超时')
    expect(component.busy.value).toBe(false)
    expect(api.start).toHaveBeenCalledExactlyOnceWith(0)
  })

  it('bounds an unresponsive manager call', async () => {
    const pending = managerCall(() => new Promise(() => {}), 50)
    const result = expect(pending).rejects.toThrow('操作超时')
    await vi.advanceTimersByTimeAsync(50)
    await result
  })
})
