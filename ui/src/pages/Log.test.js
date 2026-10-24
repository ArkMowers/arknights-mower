import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { effectScope, nextTick, onMounted, onUnmounted, ref } from 'vue'
import { createPinia, setActivePinia } from 'pinia'
import axios from 'axios'
import { readFileSync } from 'node:fs'
import { compileScript, parse } from '@vue/compiler-sfc'

import LogPage from './Log.vue'

const { descriptor } = parse(readFileSync(new URL('./Log.vue', import.meta.url), 'utf8'))
const script = compileScript(descriptor, { id: 'task-dialog-loading-test' })
const openDialogNode = script.scriptSetupAst.find((node) => node.id?.name === 'openTaskDialog')
const openDialogCode = descriptor.scriptSetup.content
  .slice(openDialogNode.start, openDialogNode.end)
  .replace("import('@/components/TaskDialog.vue')", 'loadTaskDialog()')
  .replaceAll('task_dialog_active', 'page.task_dialog_active')

function taskDialogHandler(component, loadTaskDialog, message) {
  return new Function(
    'loadTaskDialog',
    'TaskDialog',
    'task_dialog_loading',
    'show_task',
    'db_message',
    'page',
    `${openDialogCode}; return { openTaskDialog }`
  )(
    loadTaskDialog,
    component.TaskDialog,
    component.task_dialog_loading,
    component.show_task,
    message,
    component
  )
}

const state = vi.hoisted(() => ({
  client: null,
  mower: null,
  config: null,
  warning: null
}))

vi.mock('pinia', async (original) => {
  const pinia = await original()
  return { ...pinia, storeToRefs: (store) => store.refs ?? pinia.storeToRefs(store) }
})
vi.mock('axios', () => ({ default: { get: vi.fn() } }))
vi.mock('vue', async (original) => ({
  ...(await original()),
  useSSRContext: () => ({ modules: new Set() }),
  inject: (key) => (key === 'axios' ? state.client : ref(false)),
  onMounted: vi.fn(),
  onUnmounted: vi.fn(),
  provide: vi.fn()
}))
vi.mock('naive-ui', () => ({
  useDialog: () => ({ warning: state.warning }),
  useMessage: () => ({ error: vi.fn(), success: vi.fn() })
}))
vi.mock('@/stores/mower', () => ({ useMowerStore: () => state.mower }))
vi.mock('@/stores/config', () => ({ useConfigStore: () => state.config }))
vi.mock('@/utils/screenshotPreview', () => ({
  createScreenshotPreview: () => ({ start: vi.fn(), stop: vi.fn() })
}))

describe('log page', () => {
  let scope

  beforeEach(() => {
    vi.useFakeTimers()
    onMounted.mockClear()
    onUnmounted.mockClear()
    state.client = { get: vi.fn(), post: vi.fn() }
    axios.get.mockImplementation((...args) => state.client.get(...args))
    state.warning = vi.fn()
    state.mower = {
      refs: {
        log: ref(''),
        log_mobile: ref(''),
        running: ref(false),
        status_label: ref('已停止'),
        plan_condition: ref([]),
        log_lines: ref([]),
        task_list: ref([]),
        waiting: ref(false)
      },
      get_tasks: vi.fn(),
      get_running: vi.fn(),
      start_task_polling: vi.fn(),
      stop_task_polling: vi.fn()
    }
    state.config = { refs: { theme: ref('light') } }
    vi.stubGlobal('localStorage', { setItem: vi.fn(), getItem: vi.fn(() => null) })
    vi.stubGlobal(
      'document',
      Object.assign(new EventTarget(), { hidden: false, querySelector: vi.fn() })
    )
    vi.stubGlobal(
      'ResizeObserver',
      vi.fn(function () {
        this.observe = vi.fn()
        this.disconnect = vi.fn()
      })
    )
    scope = effectScope()
  })

  afterEach(() => {
    state.mower.$dispose?.()
    scope.stop()
    vi.clearAllTimers()
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })

  it('subscribes to task updates only while the log page is mounted', async () => {
    state.client.get.mockResolvedValue({ data: {} })
    const component = scope.run(() => LogPage.setup({}, { expose: vi.fn() }))
    onMounted.mock.lastCall[0]()
    expect(state.mower.start_task_polling).toHaveBeenCalledOnce()
    expect(state.mower.get_tasks).not.toHaveBeenCalled()
    expect(vi.getTimerCount()).toBe(1)

    component.start()
    expect(state.mower.get_tasks).toHaveBeenCalledOnce()
    onUnmounted.mock.lastCall[0]()
    expect(state.mower.stop_task_polling).toHaveBeenCalledOnce()
    expect(vi.getTimerCount()).toBe(0)
    await nextTick()
  })

  async function mountWithStore({ hidden = false } = {}) {
    const { useMowerStore } = await vi.importActual('@/stores/mower')
    setActivePinia(createPinia())
    state.mower = useMowerStore()
    document.hidden = hidden
    const component = scope.run(() => LogPage.setup({}, { expose: vi.fn() }))
    onMounted.mock.lastCall[0]()
    await vi.advanceTimersByTimeAsync(0)
    return component
  }

  function setHidden(hidden) {
    document.hidden = hidden
    document.dispatchEvent(new Event('visibilitychange'))
  }

  function callsTo(path) {
    return state.client.get.mock.calls.filter(([url]) => url.endsWith(path))
  }

  it('pauses hidden-page requests and refreshes immediately when visible again', async () => {
    let status = 'working'
    let tasks = [{ time: 'initial', plan: {} }]
    state.client.get.mockImplementation(async (url) => ({
      data: url.endsWith('/status')
        ? { status, plan_condition: [] }
        : url.endsWith('/task')
          ? tasks
          : {}
    }))
    await mountWithStore()
    expect(state.mower.task_list).toEqual(tasks)
    await vi.advanceTimersByTimeAsync(5000)
    expect(callsTo('/status')).toHaveLength(2)
    expect(callsTo('/task')).toHaveLength(2)

    setHidden(true)
    expect(vi.getTimerCount()).toBe(0)
    await vi.advanceTimersByTimeAsync(30000)
    expect(callsTo('/status')).toHaveLength(2)
    expect(callsTo('/task')).toHaveLength(2)

    status = 'recovering'
    tasks = [{ time: 'current', plan: {} }]
    setHidden(false)
    await vi.advanceTimersByTimeAsync(0)
    expect(callsTo('/status')).toHaveLength(3)
    expect(callsTo('/task')).toHaveLength(3)
    expect(state.mower.status).toBe('recovering')
    expect(state.mower.task_list).toEqual(tasks)
    expect(vi.getTimerCount()).toBe(2)

    onUnmounted.mock.lastCall[0]()
    setHidden(true)
    setHidden(false)
    await vi.advanceTimersByTimeAsync(30000)
    expect(callsTo('/status')).toHaveLength(3)
    expect(callsTo('/task')).toHaveLength(3)
    expect(vi.getTimerCount()).toBe(0)
  })

  it('starts no display polling when mounted hidden and reads current status on return', async () => {
    state.client.get.mockImplementation(async (url) => ({
      data: url.endsWith('/status') ? { status: 'starting', plan_condition: [] } : []
    }))
    await mountWithStore({ hidden: true })
    await vi.advanceTimersByTimeAsync(30000)
    expect(callsTo('/status')).toHaveLength(0)
    expect(callsTo('/task')).toHaveLength(0)

    setHidden(false)
    await vi.advanceTimersByTimeAsync(0)
    expect(callsTo('/status')).toHaveLength(1)
    expect(callsTo('/task')).toHaveLength(1)
    expect(state.mower.status_label).toBe('启动中')
    onUnmounted.mock.lastCall[0]()
  })

  it.each(['hide', 'unmount'])(
    'does not restart polling when pending responses finish after %s',
    async (action) => {
      let resolveStatus
      let resolveTasks
      let statusReads = 0
      state.client.get.mockImplementation((url) => {
        if (url.endsWith('/status')) {
          if (statusReads++ === 0) {
            return Promise.resolve({ data: { status: 'working', plan_condition: [] } })
          }
          return new Promise((resolve) => (resolveStatus = resolve))
        }
        if (url.endsWith('/task')) {
          return new Promise((resolve) => (resolveTasks = resolve))
        }
        return Promise.resolve({ data: {} })
      })
      await mountWithStore()
      await vi.advanceTimersByTimeAsync(5000)
      const signal = callsTo('/task')[0][1].signal
      if (action === 'hide') setHidden(true)
      else onUnmounted.mock.lastCall[0]()
      expect(signal.aborted).toBe(true)

      resolveStatus({ data: { status: 'working', plan_condition: [] } })
      resolveTasks({ data: [{ time: 'obsolete', plan: {} }] })
      await vi.advanceTimersByTimeAsync(30000)
      expect(state.mower.task_list).toEqual([])
      expect(callsTo('/status')).toHaveLength(2)
      expect(callsTo('/task')).toHaveLength(1)
      expect(vi.getTimerCount()).toBe(0)
      if (action === 'hide') onUnmounted.mock.lastCall[0]()
    }
  )

  it('preserves manual Start and Stop after returning from a hidden page', async () => {
    let status = 'stopped'
    state.client.get.mockImplementation(async (url) => {
      if (url.endsWith('/status')) return { data: { status, plan_condition: [] } }
      if (url.endsWith('/stop')) {
        status = 'stopped'
        return { data: true }
      }
      if (url.endsWith('/start/0')) status = 'working'
      return { data: url.endsWith('/task') ? [{ time: 'current', plan: {} }] : {} }
    })
    const component = await mountWithStore()
    setHidden(true)
    setHidden(false)
    await vi.advanceTimersByTimeAsync(0)
    component.start()
    await vi.advanceTimersByTimeAsync(0)
    expect(state.mower.running).toBe(true)
    expect(callsTo('/start/0')).toHaveLength(1)
    expect(state.mower.task_list).toHaveLength(1)

    component.stop()
    await vi.advanceTimersByTimeAsync(0)
    expect(state.mower.running).toBe(false)
    expect(state.mower.waiting).toBe(false)
    expect(state.mower.task_list).toEqual([])
    await vi.advanceTimersByTimeAsync(9000)
    expect(callsTo('/task')).toHaveLength(1)
    onUnmounted.mock.lastCall[0]()
  })

  it.each(['启动中', '等待设备恢复'])(
    'keeps Stop available during %s until the worker confirms exit',
    async (label) => {
      state.mower.refs.running.value = true
      state.mower.refs.status_label.value = label
      const component = scope.run(() => LogPage.setup({}, { expose: vi.fn() }))
      expect(component.running.value).toBe(true)
      expect(component.status_label.value).toBe(label)
      expect(component.waiting.value).toBe(false)

      state.client.get.mockResolvedValueOnce({ data: false })
      component.stop()
      expect(component.waiting.value).toBe(true)
      await nextTick()
      expect(state.client.get).toHaveBeenCalledWith('/stop')
      expect(component.running.value).toBe(true)
      expect(component.waiting.value).toBe(false)

      state.client.get.mockResolvedValueOnce({ data: true })
      component.stop()
      await nextTick()
      expect(component.running.value).toBe(false)
      expect(component.waiting.value).toBe(false)
    }
  )

  it('runs both process actions directly through ProcessControl', async () => {
    state.mower.refs.running.value = true
    const component = scope.run(() => LogPage.setup({}, { expose: vi.fn() }))
    const applySchedule = vi.fn()
    const restartResume = vi.fn()
    expect(component.stop_options.value[1].disabled).toBe(true)
    expect(component.stop_options.value[2].disabled).toBe(true)

    component.process_control.value = {
      canRunProcessAction: true,
      applySchedule,
      restartResume
    }
    await nextTick()
    expect(component.stop_options.value.map((option) => option.label)).toEqual([
      '停止MAA',
      '应用排班',
      '重启续接'
    ])
    expect(component.stop_options.value[1].disabled).toBe(false)
    expect(component.stop_options.value[2].disabled).toBe(false)

    component.select_stop_action('apply_schedule')
    component.select_stop_action('restart_resume')
    expect(applySchedule).toHaveBeenCalledOnce()
    expect(restartResume).toHaveBeenCalledOnce()
    expect(state.warning).not.toHaveBeenCalled()

    component.select_stop_action('maa')
    expect(state.client.get).toHaveBeenCalledWith('/stop-maa')
  })

  it('mounts the task form on first opening and retains it after closing', async () => {
    const component = scope.run(() => LogPage.setup({}, { expose: vi.fn() }))
    const dialog = { name: 'TaskForm' }
    const load = vi.fn().mockResolvedValue({ default: dialog })
    const { openTaskDialog } = taskDialogHandler(component, load, { error: vi.fn() })
    expect(component.TaskDialog.value).toBe(null)

    await Promise.all([openTaskDialog(), openTaskDialog()])
    expect(load).toHaveBeenCalledOnce()
    expect(component.TaskDialog.value).toBe(dialog)
    expect(component.show_task.value).toBe(true)

    component.show_task.value = false
    await nextTick()
    expect(component.TaskDialog.value).toBe(dialog)
    await openTaskDialog()
    expect(load).toHaveBeenCalledOnce()
    expect(component.show_task.value).toBe(true)
  })

  it('reports a failed task form load and retries only on the next user action', async () => {
    const component = scope.run(() => LogPage.setup({}, { expose: vi.fn() }))
    const dialog = { name: 'TaskForm' }
    const load = vi
      .fn()
      .mockRejectedValueOnce(new Error('offline'))
      .mockResolvedValueOnce({ default: dialog })
    const message = { error: vi.fn() }
    const { openTaskDialog } = taskDialogHandler(component, load, message)
    await openTaskDialog()
    expect(message.error).toHaveBeenCalledWith('新增任务表单加载失败，请点击「新增任务」重试')
    expect(component.task_dialog_loading.value).toBe(false)
    expect(component.TaskDialog.value).toBe(null)
    expect(component.show_task.value).toBe(false)
    await nextTick()
    expect(load).toHaveBeenCalledOnce()

    await openTaskDialog()
    expect(load).toHaveBeenCalledTimes(2)
    expect(component.TaskDialog.value).toBe(dialog)
    expect(component.show_task.value).toBe(true)
  })

  it.each([false, true])(
    'ignores a task form load after leaving the page (failure=%s)',
    async (fail) => {
      const component = scope.run(() => LogPage.setup({}, { expose: vi.fn() }))
      let resolve
      let reject
      const load = vi.fn(
        () =>
          new Promise((resolvePromise, rejectPromise) => {
            resolve = resolvePromise
            reject = rejectPromise
          })
      )
      const message = { error: vi.fn() }
      const { openTaskDialog } = taskDialogHandler(component, load, message)
      const loading = openTaskDialog()
      expect(component.task_dialog_loading.value).toBe(true)
      expect(component.TaskDialog.value).toBe(null)
      expect(component.show_task.value).toBe(false)
      expect(component.task_dialog_active).toBe(true)
      onUnmounted.mock.lastCall[0]()
      expect(component.task_dialog_active).toBe(false)
      if (fail) reject(new Error('offline'))
      else resolve({ default: { name: 'TaskForm' } })
      await loading
      expect(component.TaskDialog.value).toBe(null)
      expect(component.show_task.value).toBe(false)
      expect(message.error).not.toHaveBeenCalled()
    }
  )

  it('reclamps panes when plan conditions appear after the initial layout pass', async () => {
    let conditionHeight = 0
    const setProperty = vi.fn()
    const container = {
      getBoundingClientRect: () => ({ top: 0, bottom: 620, height: 620 }),
      querySelector: (selector) => {
        if (selector === '.plan-condition') {
          return conditionHeight
            ? { getBoundingClientRect: () => ({ height: conditionHeight }) }
            : null
        }
        if (selector === '.action-container') {
          return { getBoundingClientRect: () => ({ height: 52 }) }
        }
        if (selector === '.task-table-scroll') {
          return { getBoundingClientRect: () => ({ top: 258 }) }
        }
        return null
      },
      style: { setProperty, removeProperty: vi.fn() }
    }

    const component = scope.run(() => LogPage.setup({}, { expose: vi.fn() }))
    component.log_layout.value = container
    component.layout_preference.screenshot_height = 500
    component.layout_preference.task_height = 600
    component.apply_log_layout()
    const initialTaskHeight = setProperty.mock.calls.at(-1)[1]

    conditionHeight = 40
    state.mower.refs.plan_condition.value = ['副表一']
    await nextTick()
    await nextTick()

    expect(setProperty.mock.calls.length).toBeGreaterThan(2)
    expect(setProperty.mock.calls.at(-1)).toEqual(['--log-task-h', '142px'])
    expect(setProperty.mock.calls.at(-1)[1]).not.toBe(initialTaskHeight)
  })
})
