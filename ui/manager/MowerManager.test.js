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
    updates_enabled: false,
    can_stop: false,
    can_open_browser: false
  })

  beforeEach(() => {
    vi.useFakeTimers()
    hooks.mounted = []
    hooks.unmounted = []
    rows = [stopped()]
    api = {
      get_instances: vi.fn(async () => structuredClone(rows)),
      get_common_settings: vi.fn(async () => ({ values: {}, fields: [] })),
      select_common_path: vi.fn(async () => null),
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
      open_browser: vi.fn(async () => ({ ok: true })),
      rename: vi.fn(async () => {}),
      select_path: vi.fn(async () => null),
      remove: vi.fn(async () => {}),
      update_settings: vi.fn(async () => {}),
      update_all_settings: vi.fn(async (changes) => ({
        ok: true,
        results: changes.map(({ idx }) => ({
          idx,
          name: rows[idx].name,
          status: rows[idx].editable ? 'updated' : 'skipped',
          message: rows[idx].editable ? '已更新' : '实例进程运行期间不能修改配置'
        }))
      }))
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

  it('saves public launch settings with no instances and does not change row permissions', async () => {
    rows = []
    await mount()
    await component.editBatch()
    component.commonDraft.value = {
      maa_path: 'C:/MAA',
      account: 'sender@example.com',
      startup_mode: 'background'
    }
    await component.save()
    expect(api.update_all_settings).toHaveBeenCalledExactlyOnceWith([], [], {
      original: {},
      values: {
        maa_path: 'C:/MAA',
        account: 'sender@example.com',
        startup_mode: 'background'
      }
    })
    expect(component.editing.value).toBeNull()
  })

  it('opens a ready instance in the browser with its captured name and directory', async () => {
    rows[0] = { ...stopped(), state: 'running', can_open_browser: true }
    await mount()
    await component.openBrowser(0)
    expect(api.open_browser).toHaveBeenCalledExactlyOnceWith(0, { name: 'first', path: '/first' })
    expect(api.start).not.toHaveBeenCalled()
  })

  it.each(['stopped', 'starting', 'stopping'])(
    'does not send browser commands while an instance is %s',
    async (state) => {
      rows[0] = { ...stopped(), state }
      await mount()
      await component.openBrowser(0)
      expect(api.open_browser).not.toHaveBeenCalled()
    }
  )

  it('reports browser dispatch failure and refreshes the current state', async () => {
    rows[0] = { ...stopped(), state: 'running', can_open_browser: true }
    api.open_browser.mockResolvedValue({ ok: false, message: '实例正在停止，无法打开网页' })
    await mount()
    await component.openBrowser(0)
    expect(component.error.value).toBe('实例正在停止，无法打开网页')
    expect(component.busy.value).toBe(false)
    expect(api.get_instances).toHaveBeenCalledTimes(2)
  })

  it('loads saved public choices on reopening and discards cancelled drafts', async () => {
    api.get_common_settings.mockResolvedValue({ values: { screenshot: 2 }, fields: [] })
    await mount()
    await component.editBatch()
    component.commonDraft.value.screenshot = 3
    component.editing.value = null
    await component.editBatch()
    expect(component.commonDraft.value).toEqual({ screenshot: 2 })
    expect(component.commonChanged.value).toBe(false)
    delete component.commonDraft.value.screenshot
    await component.save()
    expect(api.update_all_settings).toHaveBeenCalledWith([], [{ name: 'first', path: '/first' }], {
      original: { screenshot: 2 },
      values: {}
    })
  })

  it('does not allow a failed public read to overwrite configuration with defaults', async () => {
    api.get_common_settings.mockRejectedValue(new Error('unreadable'))
    await mount()
    await component.editBatch()
    component.batchDraft.value[0].token = 'new'
    await component.save()
    expect(component.commonError.value).toBe('unreadable')
    expect(api.update_all_settings).not.toHaveBeenCalled()
  })

  it('does not use a late public settings read in another editor', async () => {
    let resolve
    api.get_common_settings.mockImplementation(
      () =>
        new Promise((done) => {
          resolve = done
        })
    )
    await mount()
    const opening = component.editBatch()
    await vi.advanceTimersByTimeAsync(0)
    component.editing.value = null
    component.edit(0, 'settings')
    resolve({ values: { account: 'stale' }, fields: [] })
    await opening
    expect(component.commonDraft.value).toEqual({})
    expect(component.editing.value.kind).toBe('settings')
  })

  it.each(['name', 'settings', 'batch'])(
    'retains the %s editor presentation until its closing transition finishes',
    async (kind) => {
      await mount()
      if (kind === 'batch') {
        await component.editBatch()
        component.batchDraft.value[0].token = 'draft-token'
      } else {
        component.edit(0, kind)
        component.draft.value.token = 'draft-token'
      }
      const editor = component.editing.value
      component.editing.value = null
      await nextTick()
      expect(component.displayedEditing.value).toBe(editor)
      if (kind === 'batch') {
        expect(component.displayedEditing.value.targets[0].name).toBe('first')
        expect(component.batchChanges.value).toEqual([
          { idx: 0, settings: { token: 'draft-token' } }
        ])
      } else expect(component.draft.value.token).toBe('draft-token')
      await component.save()
      expect(api.rename).not.toHaveBeenCalled()
      expect(api.update_settings).not.toHaveBeenCalled()
      expect(api.update_all_settings).not.toHaveBeenCalled()
      component.clearClosedEditor()
      expect(component.displayedEditing.value).toBeNull()
      expect(component.batchChanges.value).toEqual([])
    }
  )

  it('does not clear a reopened editor when an earlier closing transition finishes', async () => {
    await mount()
    await component.editBatch()
    component.editing.value = null
    component.edit(0, 'settings')
    component.clearClosedEditor()
    expect(component.displayedEditing.value).toBe(component.editing.value)
    expect(component.displayedEditing.value.kind).toBe('settings')
    expect(component.batchChanges.value).toEqual([])
  })

  it.each(['settings', 'batch'])(
    'retains the %s editor presentation after a successful save until it finishes closing',
    async (kind) => {
      await mount()
      if (kind === 'batch') {
        await component.editBatch()
        component.batchDraft.value[0].token = 'saved-token'
      } else {
        component.edit(0, kind)
        component.draft.value.token = 'saved-token'
      }
      const editor = component.editing.value
      await component.save()
      expect(component.editing.value).toBeNull()
      expect(component.displayedEditing.value).toBe(editor)
      component.clearClosedEditor()
      expect(component.displayedEditing.value).toBeNull()
    }
  )

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
    expect(component.editing.value).toMatchObject({ idx: 0, kind: 'settings' })
    expect(api.update_settings).not.toHaveBeenCalled()
    component.draft.value.token = 'after-reading'
    component.draft.value.port = 58001
    await component.save()
    expect(api.update_settings).toHaveBeenCalledExactlyOnceWith(
      0,
      { token: 'after-reading', port: 58001, ai_assistant_enabled: true },
      { name: 'first', path: '/first' }
    )
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
    expect(api.update_settings).toHaveBeenCalledExactlyOnceWith(
      0,
      { token: '', port: null, ai_assistant_enabled: false },
      { name: 'first', path: '/first' }
    )
  })

  it.each([true, false])(
    'does not submit an untouched AI choice after external authorization changes from %s',
    async (original) => {
      rows[0].ai_assistant_enabled = original
      await mount()
      component.edit(0, 'settings')
      component.draft.value.token = 'only-token-edited'
      rows[0].ai_assistant_enabled = !original
      await component.refresh()
      await component.save()
      expect(api.update_settings).toHaveBeenCalledOnce()
      expect(api.update_settings.mock.calls[0][1]).toEqual({
        token: 'only-token-edited',
        port: null
      })
      expect(component.assistantConfirmation.value).toBeNull()
    }
  )

  it.each(['renamed', 'moved', 'removed', 'replaced'])(
    'invalidates a confirmed single-instance draft when its target is %s',
    async (change) => {
      await mount()
      component.edit(0, 'settings')
      await component.changeAssistant(true)
      await vi.advanceTimersByTimeAsync(5000)
      component.riskAcknowledged.value = true
      component.confirmAssistantChange()
      expect(component.draft.value.ai_assistant_enabled).toBe(true)
      if (change === 'renamed') rows[0].name = 'renamed'
      else if (change === 'moved') rows[0].path = '/moved'
      else if (change === 'removed') rows = []
      else rows[0] = { ...stopped(), name: 'replacement', path: '/replacement' }
      await component.refresh()
      expect(component.editing.value).toBeNull()
      expect(component.assistantConfirmation.value).toBeNull()
      await component.save()
      expect(api.update_settings).not.toHaveBeenCalled()
    }
  )

  it('sends the captured instance identity even before a replacement is refreshed', async () => {
    await mount()
    component.edit(0, 'settings')
    await component.changeAssistant(true)
    await vi.advanceTimersByTimeAsync(5000)
    component.riskAcknowledged.value = true
    component.confirmAssistantChange()
    rows[0] = { ...stopped(), name: 'replacement', path: '/replacement' }
    await component.save()
    expect(api.update_settings).toHaveBeenCalledExactlyOnceWith(
      0,
      { token: '', port: null, ai_assistant_enabled: true },
      { name: 'first', path: '/first' }
    )
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
    expect(component.editing.value).toMatchObject({ idx: 0, kind: 'settings' })
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

  it('opens a batch draft with no selected changes and does not write it', async () => {
    await mount()
    await component.editBatch()
    expect(component.editing.value).toMatchObject({
      kind: 'batch',
      targets: [{ name: 'first', path: '/first' }]
    })
    expect(component.batchChanges.value).toEqual([])
    expect(component.batchDraft.value).toEqual([
      { token: '', port: null, ai_assistant_enabled: false, updates_enabled: false }
    ])
    await component.save()
    expect(api.update_all_settings).not.toHaveBeenCalled()
    expect(api.update_settings).not.toHaveBeenCalled()
  })

  it('keeps the enabled update default and disabled AI in individual and batch drafts', async () => {
    rows[0].updates_enabled = true
    await mount()
    component.edit(0, 'settings')
    expect(component.draft.value.updates_enabled).toBe(true)
    expect(component.draft.value.ai_assistant_enabled).toBe(false)
    await component.save()
    expect(api.update_settings.mock.calls[0][1]).toEqual({ token: '', port: null })
    await component.editBatch()
    expect(component.batchDraft.value[0].updates_enabled).toBe(true)
    expect(component.batchDraft.value[0].ai_assistant_enabled).toBe(false)
    expect(component.batchChanges.value).toEqual([])
    expect(component.assistantConfirmation.value).toBeNull()
    await component.save()
    expect(api.update_all_settings).not.toHaveBeenCalled()
  })

  it('saves update permission separately without triggering the AI notice', async () => {
    await mount()
    component.edit(0, 'settings')
    component.draft.value.updates_enabled = true
    expect(component.assistantConfirmation.value).toBeNull()
    expect(api.update_settings).not.toHaveBeenCalled()
    await component.save()
    expect(api.update_settings).toHaveBeenCalledExactlyOnceWith(
      0,
      { token: '', port: null, updates_enabled: true },
      { name: 'first', path: '/first' }
    )
  })

  it.each([true, false])(
    'does not overwrite an untouched update choice %s after external changes',
    async (original) => {
      rows[0].updates_enabled = original
      await mount()
      component.edit(0, 'settings')
      rows[0].updates_enabled = !original
      component.draft.value.token = 'edited'
      await component.refresh()
      await component.save()
      expect(api.update_settings.mock.calls[0][1]).toEqual({ token: 'edited', port: null })
    }
  )

  it('changes all editable update drafts and saves only changed cells', async () => {
    rows.push(
      { ...stopped(), name: 'second', path: '/second' },
      { ...stopped(), name: 'live', path: '/live', editable: false, state: 'running' },
      { ...stopped(), name: 'missing', path: '' }
    )
    await mount()
    await component.editBatch()
    component.changeBatchUpdates(true)
    expect(component.batchDraft.value.map((row) => row.updates_enabled)).toEqual([
      true,
      true,
      false,
      false
    ])
    expect(component.batchDraft.value.every((row) => row.ai_assistant_enabled === false)).toBe(true)
    expect(component.assistantConfirmation.value).toBeNull()
    expect(api.update_all_settings).not.toHaveBeenCalled()
    component.changeBatchUpdates(false, 1)
    await component.save()
    expect(api.update_all_settings).toHaveBeenCalledExactlyOnceWith(
      [{ idx: 0, settings: { updates_enabled: true } }],
      rows.map(({ name, path }) => ({ name, path }))
    )
  })

  it('can cancel a bulk update choice or turn it all off before saving', async () => {
    rows[0].updates_enabled = true
    await mount()
    await component.editBatch()
    component.changeBatchUpdates(false)
    expect(component.batchChanges.value).toEqual([{ idx: 0, settings: { updates_enabled: false } }])
    component.editing.value = null
    await component.editBatch()
    expect(component.batchDraft.value[0].updates_enabled).toBe(true)
    expect(component.batchChanges.value).toEqual([])
    expect(api.update_all_settings).not.toHaveBeenCalled()
  })

  it('requires one reading notice for a batch, then saves all confirmed fields once', async () => {
    rows.push(
      { ...stopped(), name: 'second', path: '/second' },
      { ...stopped(), name: 'live', path: '/live', editable: false, state: 'running' }
    )
    await mount()
    await component.editBatch()
    const targets = rows.map(({ name, path }) => ({ name, path }))
    await component.changeBatchAssistant(true)
    expect(component.assistantConfirmation.value.kind).toBe('batch')
    expect(component.batchDraft.value.map((row) => row.ai_assistant_enabled)).toEqual([
      false,
      false,
      false
    ])
    component.riskAcknowledged.value = true
    await vi.advanceTimersByTimeAsync(4999)
    component.confirmAssistantChange()
    expect(component.batchDraft.value.map((row) => row.ai_assistant_enabled)).toEqual([
      false,
      false,
      false
    ])
    await component.save()
    expect(api.update_all_settings).not.toHaveBeenCalled()
    await vi.advanceTimersByTimeAsync(1)
    component.confirmAssistantChange()
    expect(component.batchDraft.value.map((row) => row.ai_assistant_enabled)).toEqual([
      true,
      true,
      false
    ])
    expect(api.update_all_settings).not.toHaveBeenCalled()
    component.batchDraft.value[0].token = 'first-secret'
    component.batchDraft.value[1].token = 'second-secret'
    component.batchDraft.value[1].port = 59001
    await component.save()
    expect(api.update_all_settings).toHaveBeenCalledExactlyOnceWith(
      [
        { idx: 0, settings: { token: 'first-secret', ai_assistant_enabled: true } },
        { idx: 1, settings: { token: 'second-secret', port: 59001, ai_assistant_enabled: true } }
      ],
      targets
    )
    expect(component.editing.value).toBeNull()
    expect(component.batchSummary.value).toBe('已更新 2 个，跳过 0 个，失败 0 个')
    expect(api.update_settings).not.toHaveBeenCalled()
  })

  it('shares one acknowledgement between individual AI cells and the all-on action', async () => {
    rows.push(
      { ...stopped(), name: 'second', path: '/second' },
      { ...stopped(), name: 'live', path: '/live', editable: false, state: 'running' }
    )
    await mount()
    await component.editBatch()
    await component.changeBatchAssistant(true, 0)
    await vi.advanceTimersByTimeAsync(5000)
    component.riskAcknowledged.value = true
    component.confirmAssistantChange()
    expect(component.batchDraft.value.map((row) => row.ai_assistant_enabled)).toEqual([
      true,
      false,
      false
    ])
    await component.changeBatchAssistant(true, 1)
    expect(component.assistantConfirmation.value).toBeNull()
    expect(component.batchDraft.value.map((row) => row.ai_assistant_enabled)).toEqual([
      true,
      true,
      false
    ])
    await component.changeBatchAssistant(false)
    await component.changeBatchAssistant(true)
    expect(component.assistantConfirmation.value).toBeNull()
    expect(component.batchDraft.value.map((row) => row.ai_assistant_enabled)).toEqual([
      true,
      true,
      false
    ])
    expect(api.update_all_settings).not.toHaveBeenCalled()
  })

  it('submits only changed cells and does not replace untouched values refreshed elsewhere', async () => {
    rows.push({ ...stopped(), name: 'second', path: '/second', token: 'other', port: 58001 })
    await mount()
    await component.editBatch()
    component.batchDraft.value[0].token = 'first-new'
    rows[1].port = 59000
    await component.refresh()
    await component.save()
    expect(api.update_all_settings).toHaveBeenCalledExactlyOnceWith(
      [{ idx: 0, settings: { token: 'first-new' } }],
      [
        { name: 'first', path: '/first' },
        { name: 'second', path: '/second' }
      ]
    )
  })

  it('restoring a cell to its original value removes the pending change', async () => {
    await mount()
    await component.editBatch()
    component.batchDraft.value[0].port = 59000
    expect(component.batchChanges.value).toEqual([{ idx: 0, settings: { port: 59000 } }])
    component.batchDraft.value[0].port = null
    await component.save()
    expect(component.batchChanges.value).toEqual([])
    expect(api.update_all_settings).not.toHaveBeenCalled()
  })

  it('batch disables without reading and leaves Token and port unchanged', async () => {
    rows[0].ai_assistant_enabled = true
    await mount()
    await component.editBatch()
    await component.changeBatchAssistant(false)
    expect(component.assistantConfirmation.value).toBeNull()
    await component.save()
    expect(api.update_all_settings).toHaveBeenCalledExactlyOnceWith(
      [{ idx: 0, settings: { ai_assistant_enabled: false } }],
      [{ name: 'first', path: '/first' }]
    )
  })

  it('batch Token clearing and random ports do not send an unselected AI setting', async () => {
    rows[0].token = 'old'
    rows[0].port = 59000
    await mount()
    await component.editBatch()
    component.batchDraft.value[0].token = ''
    component.batchDraft.value[0].port = null
    await component.save()
    expect(api.update_all_settings).toHaveBeenCalledExactlyOnceWith(
      [{ idx: 0, settings: { token: '', port: null } }],
      [{ name: 'first', path: '/first' }]
    )
  })

  it('cancelled batch reading retains the earlier choice and other drafts', async () => {
    await mount()
    await component.editBatch()
    component.batchDraft.value[0].token = 'draft'
    await component.changeBatchAssistant(true)
    await vi.advanceTimersByTimeAsync(5000)
    component.cancelAssistantConfirmation()
    expect(component.batchDraft.value[0].ai_assistant_enabled).toBe(false)
    expect(component.batchDraft.value[0].token).toBe('draft')
    await component.changeBatchAssistant(true)
    expect(component.riskSeconds.value).toBe(5)
    expect(component.riskAcknowledged.value).toBe(false)
    expect(api.update_all_settings).not.toHaveBeenCalled()
  })

  it('cancelling the batch editor discards its acknowledgement and draft', async () => {
    await mount()
    await component.editBatch()
    await component.changeBatchAssistant(true)
    await vi.advanceTimersByTimeAsync(5000)
    component.riskAcknowledged.value = true
    component.confirmAssistantChange()
    component.editing.value = null
    await component.editBatch()
    expect(component.batchDraft.value[0].ai_assistant_enabled).toBe(false)
    expect(component.batchChanges.value).toEqual([])
    expect(component.batchAiRead.value).toBe(false)
    expect(api.update_all_settings).not.toHaveBeenCalled()
  })

  it.each(['added', 'renamed', 'moved'])(
    'cancels batch editing and reading if a target is %s',
    async (change) => {
      await mount()
      await component.editBatch()
      await component.changeBatchAssistant(true)
      if (change === 'added') rows.push({ ...stopped(), name: 'second', path: '/second' })
      else if (change === 'renamed') rows[0].name = 'other'
      else rows[0].path = '/other'
      await component.refresh()
      expect(component.editing.value).toBeNull()
      expect(component.assistantConfirmation.value).toBeNull()
      expect(component.error.value).toContain('实例列表已变化')
      await component.save()
      expect(api.update_all_settings).not.toHaveBeenCalled()
    }
  )

  it('keeps batch editing on process state changes so the backend can report skipped instances', async () => {
    await mount()
    await component.editBatch()
    component.batchDraft.value[0].token = 'edited-before-start'
    rows[0].editable = false
    rows[0].state = 'running'
    await component.refresh()
    expect(component.editing.value.kind).toBe('batch')
    await component.changeBatchAssistant(false)
    await component.save()
    expect(component.batchSummary.value).toBe('已更新 0 个，跳过 1 个，失败 0 个')
  })

  it('reports per-instance write failures without hiding completed updates', async () => {
    await mount()
    await component.editBatch()
    component.batchDraft.value[0].token = 'edit'
    api.update_all_settings.mockResolvedValueOnce({
      ok: true,
      results: [
        { idx: 0, name: 'first', status: 'updated', message: '已更新' },
        { idx: 1, name: 'second', status: 'failed', message: 'locked' }
      ]
    })
    await component.save()
    expect(component.batchSummary.value).toBe('已更新 1 个，跳过 0 个，失败 1 个')
    expect(component.batchResult.value.results[1].message).toBe('locked')
    expect(component.editing.value).toBeNull()
  })

  it.each(['bridge', 'invalid-result'])(
    'retains batch drafts after %s failure',
    async (failure) => {
      await mount()
      await component.editBatch()
      component.batchDraft.value[0].token = 'edit'
      if (failure === 'bridge')
        api.update_all_settings.mockRejectedValueOnce(new Error('bridge failed'))
      else api.update_all_settings.mockResolvedValueOnce({ ok: true })
      await component.save()
      expect(component.editing.value.kind).toBe('batch')
      expect(component.batchDraft.value[0].token).toBe('edit')
      expect(component.batchResult.value).toBeNull()
      expect(component.error.value).not.toBe('')
      expect(api.update_all_settings).toHaveBeenCalledOnce()
    }
  )

  it('clears a pending batch reading timer on unmount', async () => {
    await mount()
    await component.editBatch()
    await component.changeBatchAssistant(true)
    hooks.unmounted.forEach((callback) => callback())
    expect(vi.getTimerCount()).toBe(0)
    expect(component.assistantConfirmation.value).toBeNull()
    expect(api.update_all_settings).not.toHaveBeenCalled()
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
    expect(component.editing.value).toMatchObject({ idx: 0, kind: 'settings' })
    expect(component.error.value).toBe('write failed')
    expect(component.draft.value.port).toBe(58001)
    await component.save()
    expect(api.update_settings).toHaveBeenLastCalledWith(
      0,
      { token: 'new-secret', port: 58001 },
      { name: 'first', path: '/first' }
    )
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
