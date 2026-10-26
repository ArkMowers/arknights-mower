import { createPinia, setActivePinia } from 'pinia'
import axios from 'axios'
import { readFileSync } from 'node:fs'
import { compileScript, parse } from '@vue/compiler-sfc'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  compile,
  createRenderer,
  defineComponent,
  effectScope,
  h,
  nextTick,
  onMounted,
  onUnmounted,
  reactive,
  ref
} from 'vue'
import { routeLocationKey, routerKey } from 'vue-router'

import LogPage from './Log.vue'
import TaskConfiguration from '@/task-workflow/TaskConfiguration.vue'
import { useLogBackgroundStore } from '@/stores/logBackground'

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
  warning: null,
  error: null,
  taskVisibility: null,
  route: null,
  router: null,
  mobile: null,
  configurationMounts: 0
}))

vi.mock('pinia', async (original) => {
  const pinia = await original()
  return { ...pinia, storeToRefs: (store) => store.refs ?? pinia.storeToRefs(store) }
})
vi.mock('axios', () => ({ default: { get: vi.fn(), put: vi.fn(), delete: vi.fn() } }))
vi.mock('vue', async (original) => ({
  ...(await original()),
  useSSRContext: () => ({ modules: new Set() }),
  useId: () => 'log-toolbar',
  inject: (key) => {
    if (key === 'axios') return state.client
    if (key === routeLocationKey) return state.route
    if (key === routerKey) return state.router
    if (key === 'mobile') return state.mobile
    return ref(false)
  },
  onMounted: vi.fn(),
  onUnmounted: vi.fn(),
  provide: vi.fn((key, value) => {
    if (key === 'show_task') state.taskVisibility = value
  })
}))
vi.mock('naive-ui', () => ({
  useDialog: () => ({ warning: state.warning }),
  useMessage: () => ({ error: state.error, success: vi.fn() })
}))
vi.mock('@/stores/mower', () => ({ useMowerStore: () => state.mower }))
vi.mock('@/stores/config', () => ({ useConfigStore: () => state.config }))
vi.mock('@/components/TaskDialog.vue', () => ({
  default: { name: 'TaskDialog', render: () => h('div', { 'data-task-form': true }) }
}))
vi.mock('@/task-workflow/TaskConfiguration.vue', () => ({
  default: defineComponent({
    setup() {
      state.configurationMounts += 1
      return () => h('div', { 'data-task-configuration': true })
    }
  })
}))
vi.mock('@/utils/screenshotPreview', () => ({
  createScreenshotPreview: () => ({ start: vi.fn(), stop: vi.fn() })
}))

describe('log page', () => {
  let scope
  let app

  beforeEach(() => {
    setActivePinia(createPinia())
    vi.useFakeTimers()
    onMounted.mockClear()
    onUnmounted.mockClear()
    state.client = { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() }
    axios.get.mockImplementation((...args) => state.client.get(...args))
    axios.put.mockImplementation((...args) => state.client.put(...args))
    axios.delete.mockImplementation((...args) => state.client.delete(...args))
    state.warning = vi.fn()
    state.error = vi.fn()
    state.mower = {
      refs: {
        log: ref(''),
        log_mobile: ref(''),
        running: ref(false),
        stop_after_round: ref(false),
        status_label: ref('已停止'),
        plan_condition: ref([]),
        log_lines: ref([]),
        task_list: ref([]),
        waiting: ref(false)
      },
      get_tasks: vi.fn(),
      get_running: vi.fn(),
      set_stop_after_round: vi.fn(),
      start_task_polling: vi.fn(),
      stop_task_polling: vi.fn()
    }
    state.config = { refs: { theme: ref('light') } }
    state.configurationMounts = 0
    state.taskVisibility = null
    state.route = reactive({ hash: '', query: {}, redirectedFrom: null })
    state.router = { push: vi.fn(), replace: vi.fn() }
    state.mobile = ref(false)
    vi.stubGlobal('localStorage', { setItem: vi.fn(), getItem: vi.fn(() => null) })
    const documentTarget = Object.assign(new EventTarget(), {
      hidden: false,
      querySelector: vi.fn()
    })
    documentTarget.addEventListener = vi.fn(documentTarget.addEventListener.bind(documentTarget))
    documentTarget.removeEventListener = vi.fn(
      documentTarget.removeEventListener.bind(documentTarget)
    )
    vi.stubGlobal('document', documentTarget)
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
    app?.unmount()
    app = null
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

  function mountWorkspace() {
    function node(tag, text = '') {
      return {
        tag,
        text,
        props: {},
        children: [],
        parent: null,
        scrollTop: 0,
        scrollIntoView: vi.fn(),
        style: { setProperty: vi.fn(), removeProperty: vi.fn() },
        querySelector: () => null,
        getBoundingClientRect: () => ({ top: 0, bottom: 600, height: 600 })
      }
    }
    const renderer = createRenderer({
      createElement: (tag) => node(tag),
      createText: (text) => node('#text', text),
      createComment: (text) => node('#comment', text),
      setText: (target, text) => (target.text = text),
      setElementText: (target, text) => (target.text = text),
      parentNode: (target) => target.parent,
      nextSibling: (target) => target.parent?.children[target.parent.children.indexOf(target) + 1],
      patchProp: (target, key, _previous, value) => (target.props[key] = value),
      insert(target, parent, anchor = null) {
        if (target.parent) target.parent.children.splice(target.parent.children.indexOf(target), 1)
        target.parent = parent
        const index = anchor ? parent.children.indexOf(anchor) : -1
        parent.children.splice(index < 0 ? parent.children.length : index, 0, target)
      },
      remove: (target) => target.parent.children.splice(target.parent.children.indexOf(target), 1)
    })
    const { descriptor } = parse(readFileSync(new URL('./Log.vue', import.meta.url), 'utf8'))
    app = renderer.createApp({
      ...LogPage,
      ssrRender: undefined,
      render: compile(descriptor.template.content, { hoistStatic: false }),
      setup: (props, context) => ({ ...LogPage.setup(props, context) })
    })
    const wrapper = {
      setup:
        (_, { slots }) =>
        () =>
          h('div', slots.default?.())
    }
    for (const name of [
      'NImage',
      'NTable',
      'NButton',
      'NIcon',
      'NText',
      'NSwitch',
      'NModal',
      'NCheckbox',
      'DropDown',
      'StartSchedule',
      'ProcessControl',
      'TaskDialog',
      'HelpText',
      'StopIcon',
      'AddIcon',
      'ServerOutlineIcon',
      'CollapseIcon',
      'ExpandIcon'
    ])
      app.component(name, wrapper)
    app.component('NPopover', {
      props: ['show'],
      emits: ['update:show'],
      setup:
        (props, { emit, slots }) =>
        () =>
          h('div', [
            h('div', { onClick: () => emit('update:show', !props.show) }, slots.trigger?.()),
            props.show ? slots.default?.() : null
          ])
    })
    app.component('NLog', { render: () => h('pre', { 'data-log-content': true }) })
    app.component('TaskConfiguration', TaskConfiguration)
    const root = node('root')
    app.mount(root)
    const all = (target = root) => [target, ...target.children.flatMap(all)]
    const find = (predicate) => {
      const target = all().find(predicate)
      expect(target).toBeTruthy()
      return target
    }
    return { root, find, all }
  }

  it('updates the mounted background immediately when shared settings change', async () => {
    const { find } = mountWorkspace()
    const layer = find((target) => target.props.class === 'log-bg')
    expect(layer.props.style.backgroundImage).toBe("url('/bg.webp')")
    const background = useLogBackgroundStore()
    background.customUrl = 'blob:custom-image'
    await nextTick()
    expect(layer.props.style.backgroundImage).toBe("url('blob:custom-image')")
    background.customUrl = ''
    await nextTick()
    expect(layer.props.style.backgroundImage).toBe("url('/bg.webp')")
  })

  it('keeps an empty queue compact without mounting task preparation or editors', () => {
    const { all } = mountWorkspace()
    expect(all().some((target) => target.props.class === 'log-screenshot')).toBe(false)
    expect(all().some((target) => target.props.class === 'log-resizer log-resizer-sc')).toBe(false)
    expect(all().some((target) => target.props.class === 'task-table-scroll')).toBe(false)
    expect(all().some((target) => target.props.class === 'log-resizer log-resizer-task')).toBe(
      false
    )
    expect(state.configurationMounts).toBe(0)
    expect(all().some((target) => target.props.title === '全部设置')).toBe(false)
    expect(all().some((target) => target.props.class === 'task-configuration-trigger')).toBe(false)
    expect(state.client.get).not.toHaveBeenCalled()
    expect(state.client.post).not.toHaveBeenCalled()
  })

  it('mounts screenshot and resizer only when screenshot preview is enabled and a frame is available', async () => {
    const { find, all } = mountWorkspace()
    const log = find((target) => target.props['data-log-content'])
    expect(all().some((target) => target.props.class === 'log-screenshot')).toBe(false)

    app._instance.setupState.sc_blob = 'blob:http://latest'
    await nextTick()

    const screenshot = find((target) => target.props.class === 'log-screenshot')
    expect(screenshot.parent).toBe(log.parent)
    expect(all(screenshot).some((target) => target.props.src === 'blob:http://latest')).toBe(true)
    expect(all().some((target) => target.props.class === 'log-resizer log-resizer-sc')).toBe(true)
  })

  it('fits the default mobile screenshot height to the loaded frame and current pane width', async () => {
    state.mobile.value = true
    const { find } = mountWorkspace()
    const page = app._instance.setupState
    const pane = find((target) => target.props['aria-label'] === '运行日志')
    pane.clientWidth = 360
    pane.getBoundingClientRect = () => ({ top: 0, bottom: 900, height: 900 })
    page.sc_blob = 'blob:http://latest'
    await nextTick()
    const image = find((target) => target.props.src === 'blob:http://latest')
    image.props.onLoad({ target: { naturalWidth: 1920, naturalHeight: 1080 } })
    await nextTick()
    const screenshotHeight = () =>
      pane.style.setProperty.mock.calls.filter(([key]) => key === '--log-sc-h').at(-1)?.[1]
    expect(screenshotHeight()).toBe('203px')

    pane.clientWidth = 640
    page.apply_log_layout()
    expect(screenshotHeight()).toBe('360px')

    pane.clientWidth = 360
    image.props.onLoad({ target: { naturalWidth: 1080, naturalHeight: 1920 } })
    await nextTick()
    expect(screenshotHeight()).toBe('640px')
    pane.clientWidth = 360
    pane.getBoundingClientRect = () => ({ top: 0, bottom: 220, height: 220 })
    image.props.onLoad({ target: { naturalWidth: 1920, naturalHeight: 1080 } })
    await nextTick()
    expect(screenshotHeight()).toBe('203px')
    expect(page.layout_preference.screenshot_height).toBeNull()
    expect(state.client.post).not.toHaveBeenCalled()
  })

  it('ignores a desktop screenshot height on mobile, keeps a mobile drag, and falls back without width', async () => {
    state.mobile.value = true
    const { find } = mountWorkspace()
    const page = app._instance.setupState
    const pane = find((target) => target.props['aria-label'] === '运行日志')
    pane.getBoundingClientRect = () => ({ top: 0, bottom: 900, height: 900 })
    pane.querySelector = (selector) =>
      selector === '.log-screenshot' ? { getBoundingClientRect: () => ({ top: 0 }) } : null
    page.sc_blob = 'blob:http://latest'
    await nextTick()
    const image = find((target) => target.props.src === 'blob:http://latest')
    image.props.onLoad({ target: { naturalWidth: 1920, naturalHeight: 1080 } })
    await nextTick()
    const screenshotHeight = () =>
      pane.style.setProperty.mock.calls.filter(([key]) => key === '--log-sc-h').at(-1)?.[1]
    expect(screenshotHeight()).toBe('270px')

    pane.clientWidth = 360
    page.layout_preference.screenshot_height = 500
    page.apply_log_layout()
    expect(screenshotHeight()).toBe('203px')
    const listeners = new Map()
    document.addEventListener.mockImplementation((name, handler) => listeners.set(name, handler))
    state.client.post.mockResolvedValue({})
    page.resize_log_pane({ preventDefault: vi.fn() }, 'screenshot')
    listeners.get('pointermove')({ clientY: 190 })
    listeners.get('pointerup')()
    image.props.onLoad({ target: { naturalWidth: 1080, naturalHeight: 1920 } })
    await nextTick()
    expect(screenshotHeight()).toBe('190px')
    expect(page.layout_preference.screenshot_height).toBe(190)
    expect(state.client.post).toHaveBeenCalledExactlyOnceWith('/ui-state/log-layout', {
      screenshot_height: 190
    })
  })

  it('restores grouped room rows and keeps backend order, task names and execution times', async () => {
    state.mower.refs.task_list.value = [
      {
        time: '2026-10-20T11:30:00.000',
        plan: { room_1_1: ['阿米娅', ''], dormitory_1: ['芬'] },
        type: { display_value: '换班' },
        emergency_staffing: true
      },
      {
        time: '2026-10-20T10:00:00.000',
        plan: {},
        type: { display_value: '默认任务名称' },
        display_name: '扫描仓库',
        meta_data: '全部物品'
      }
    ]
    const { find, all } = mountWorkspace()
    const queue = find((target) => target.props.class === 'task-table-scroll')
    const log = find((target) => target.props['data-log-content'])
    const text = (target) =>
      all(target)
        .filter((item) => item.tag !== '#comment')
        .map((item) => item.text)
        .join(' ')
        .replace(/\s+/g, ' ')
        .trim()
    const rows = () => all(queue).filter((target) => target.tag === 'tr')
    expect(queue.parent).toBe(log.parent)
    expect(rows().map(text)).toEqual([
      '时间 任务',
      '11:30:00 自动救急换班 room_1_1 阿米娅, _',
      'dormitory_1 芬',
      '10:00:00 扫描仓库 全部物品'
    ])
    expect(rows()[1].children.find((target) => target.tag === 'td').props.rowspan).toBe(2)
    expect(state.configurationMounts).toBe(0)

    state.mower.refs.task_list.value = [state.mower.refs.task_list.value[1]]
    await nextTick()
    expect(rows().map(text)).toEqual(['时间 任务', '10:00:00 扫描仓库 全部物品'])
    state.mower.refs.task_list.value = []
    await nextTick()
    expect(all().some((target) => target.props.class === 'task-table-scroll')).toBe(false)
    expect(find((target) => target.props['data-log-content'])).toBe(log)
    expect(state.client.post).not.toHaveBeenCalled()
  })

  it.each([
    ['emergency_recovery_release', '自动救急'],
    ['emergency_staffing', '自动救急换班'],
    ['emergency_dorm', '自动救急宿舍安排']
  ])('retains the %s label on a scheduled room task', (flag, label) => {
    state.mower.refs.task_list.value = [
      {
        time: '2026-10-20T11:30:00.000',
        plan: { dormitory_1: ['芬'] },
        [flag]: true
      }
    ]
    const { all } = mountWorkspace()
    expect(all().some((target) => target.text === label)).toBe(true)
  })

  it('keeps the saved task height and persists manual resizing', async () => {
    state.mower.refs.task_list.value = [
      {
        time: '2026-10-20T11:30:00.000',
        plan: {},
        type: { display_value: '跑单' }
      }
    ]
    const { find } = mountWorkspace()
    const queue = find((target) => target.props.class === 'task-table-scroll')
    const pane = queue.parent
    pane.getBoundingClientRect = () => ({ top: 0, bottom: 900, height: 900 })
    pane.querySelector = (selector) => (selector === '.task-table-scroll' ? queue : null)
    queue.getBoundingClientRect = () => ({ top: 278, bottom: 410, height: 132 })
    const page = app._instance.setupState
    page.layout_preference.task_height = 132
    page.apply_log_layout()
    const taskHeight = () =>
      pane.style.setProperty.mock.calls.filter(([name]) => name === '--log-task-h').at(-1)[1]
    expect(taskHeight()).toBe('132px')

    const listeners = new Map()
    document.addEventListener.mockImplementation((name, handler) => listeners.set(name, handler))
    state.client.post.mockResolvedValue({})
    page.resize_log_pane({ preventDefault: vi.fn() }, 'task')
    listeners.get('pointermove')({ clientY: 478 })
    listeners.get('pointerup')()
    page.apply_log_layout()
    expect(taskHeight()).toBe('200px')
    expect(state.client.post).toHaveBeenCalledExactlyOnceWith('/ui-state/log-layout', {
      task_height: 200
    })
  })

  it.each([
    '#task-devices',
    '#task-runtime',
    '#task-base',
    '#task-daily',
    '#task-long',
    '#task-accounts',
    '#task-maa'
  ])('redirects a direct legacy %s link to the task configuration page', (hash) => {
    state.route.hash = hash
    state.route.query = { profile: 'default' }
    mountWorkspace()
    expect(state.router.replace).toHaveBeenCalledExactlyOnceWith({
      name: 'task-settings',
      query: { profile: 'default' },
      hash
    })
    expect(state.configurationMounts).toBe(0)
    expect(state.client.get).not.toHaveBeenCalled()
    expect(state.client.post).not.toHaveBeenCalled()
  })

  it('ignores unknown hashes and redirects later legacy editor links', async () => {
    state.route.hash = '#task-unknown'
    const { find } = mountWorkspace()
    const log = find((target) => target.props['data-log-content'])
    log.scrollTop = 137
    expect(state.router.replace).not.toHaveBeenCalled()
    state.route.hash = '#task-base'
    await nextTick()
    expect(state.router.replace).toHaveBeenCalledExactlyOnceWith({
      name: 'task-settings',
      query: {},
      hash: '#task-base'
    })
    expect(log.scrollTop).toBe(137)
    expect(state.configurationMounts).toBe(0)
  })

  it('leaves the legacy settings path redirect to the router', () => {
    state.route.redirectedFrom = { name: 'maasettings' }
    mountWorkspace()
    expect(state.router.replace).not.toHaveBeenCalled()
    expect(state.configurationMounts).toBe(0)
  })

  it('locates the task queue on return without saving or running tasks', async () => {
    state.route.hash = '#task-queue'
    state.mower.refs.task_list.value = [
      {
        time: '2026-10-20T11:30:00.000',
        plan: {},
        type: { display_value: '跑单' }
      }
    ]
    const { find } = mountWorkspace()
    await nextTick()
    expect(
      find((target) => target.props.class === 'task-table-scroll').scrollIntoView
    ).toHaveBeenCalledExactlyOnceWith({ block: 'nearest' })
    expect(state.router.replace).not.toHaveBeenCalled()
    expect(state.client.get).not.toHaveBeenCalled()
    expect(state.client.post).not.toHaveBeenCalled()
    expect(state.mower.get_tasks).not.toHaveBeenCalled()
  })

  it('reveals a collapsed mobile task table when navigating to its queue hash', async () => {
    state.mobile.value = true
    state.mower.refs.task_list.value = [
      { time: '2026-10-20T11:30:00.000', plan: {}, type: { display_value: '跑单' } }
    ]
    const { find } = mountWorkspace()
    const collapse = find((target) => target.props.class === 'toggle-table-collapse-btn')
    const queue = find((target) => target.props.class === 'task-table-scroll')
    collapse.props.onClick()
    await nextTick()
    expect(queue.style.display).toBe('none')

    state.route.hash = '#task-queue'
    await nextTick()
    await nextTick()

    expect(queue.style.display).not.toBe('none')
    expect(collapse.props['aria-expanded']).toBe(true)
    expect(queue.scrollIntoView).toHaveBeenCalledExactlyOnceWith({ block: 'nearest' })
    expect(state.client.post).not.toHaveBeenCalled()
    expect(state.mower.get_tasks).not.toHaveBeenCalled()
  })
  it.each(['启动中', '等待设备恢复'])(
    'keeps Stop available during %s until the worker confirms exit',
    async (label) => {
      state.mower.refs.running.value = true
      state.mower.refs.status_label.value = label
      const component = scope.run(() => LogPage.setup({}, { expose: vi.fn() }))
      expect(component.running.value).toBe(true)
      expect(state.mower.refs.status_label.value).toBe(label)
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

  it('opens task creation and database management directly from colored toolbar buttons', async () => {
    const { find } = mountWorkspace()
    const addTask = find((target) => target.props.type === 'warning')
    const database = find((target) => target.props.type === 'info')
    const databaseModal = find(
      (target) => target.props.preset === 'card' && target.props.title !== '全部设置'
    )
    expect(state.taskVisibility.value).toBe(false)
    expect(databaseModal.props.show).toBe(false)

    await addTask.props.onClick()
    expect(state.taskVisibility.value).toBe(true)
    state.client.get.mockResolvedValueOnce({ data: {} })
    database.props.onClick()
    await nextTick()

    expect(databaseModal.props.show).toBe(true)
    expect(state.client.get).toHaveBeenCalledExactlyOnceWith('/db-admin/stats')
    expect(find((target) => target.props.label === '新增任务说明').parent).toBe(addTask.parent)
  })

  it('opens mobile controls from More, changes display options and closes More before database management', async () => {
    state.mobile.value = true
    const { find, all } = mountWorkspace()
    const trigger = find((target) => target.props.class === 'display-options-trigger')
    const page = app._instance.setupState
    expect(trigger.props['aria-label']).toBe('日志更多操作')
    expect(trigger.props['aria-haspopup']).toBe('dialog')
    expect(trigger.props['aria-expanded']).toBe(false)
    expect(all().some((target) => target.props.role === 'dialog')).toBe(false)

    trigger.parent.props.onClick()
    await nextTick()
    const panel = find((target) => target.props.role === 'dialog')
    expect(panel.props['aria-label']).toBe('日志更多操作')
    expect(panel.props.id).toBe(trigger.props['aria-controls'])
    expect(trigger.props['aria-expanded']).toBe(true)
    expect(all(panel).some((target) => target.tag === 'details')).toBe(true)
    expect(
      all(panel).some((target) => target.tag === 'summary' && target.text === '新增任务说明')
    ).toBe(true)
    const previewSwitch = all(panel).find((target) => target.props['aria-label'] === '预览截图')
    previewSwitch.props['onUpdate:value'](false)
    const scrollingSwitch = all(panel).find((target) => target.props['aria-label'] === '自动滚动')
    scrollingSwitch.props['onUpdate:value'](false)
    await nextTick()
    expect(page.sc_preview).toBe(false)
    expect(page.auto_scroll).toBe(false)
    expect(localStorage.setItem).toHaveBeenCalledWith('sc_preview', 'false')

    const desktopDatabase = find((target) => target.props.class === 'database-action')
    const mobileDatabase = find((target) => target.props.class === 'database-menu-action')
    expect(mobileDatabase).not.toBe(desktopDatabase)
    state.client.get.mockResolvedValueOnce({ data: {} })
    mobileDatabase.props.onClick()
    await nextTick()
    expect(page.show_display_options).toBe(false)
    expect(page.show_db_admin).toBe(true)
    expect(trigger.props['aria-expanded']).toBe(false)
    expect(all().some((target) => target.props.role === 'dialog')).toBe(false)
    expect(state.client.get).toHaveBeenCalledExactlyOnceWith('/db-admin/stats')
    expect(state.client.post).not.toHaveBeenCalled()
  })

  it.each(['已停止', '启动中', '运行中', '等待设备恢复'])(
    'omits the %s status label from the toolbar',
    (label) => {
      state.mower.refs.running.value = label !== '已停止'
      state.mower.refs.status_label.value = label
      const { find, all } = mountWorkspace()
      const toolbar = find((target) => target.props.class === 'action-container')
      expect(all(toolbar).some((target) => target.text.includes(label))).toBe(false)
      expect(state.mower.refs.status_label.value).toBe(label)
    }
  )

  it('sets and cancels round stop from the stop menu while retaining immediate Stop', async () => {
    state.mower.refs.running.value = true
    const { find, all } = mountWorkspace()
    const page = app._instance.setupState
    const menu = () => page.stop_options.find((option) => option.key === 'after_round')
    expect(menu().label).toBe('本轮结束后停止')
    await page.select_stop_action('after_round')
    expect(state.mower.set_stop_after_round).toHaveBeenCalledExactlyOnceWith(true)
    state.mower.refs.stop_after_round.value = true
    await nextTick()
    expect(menu().label).toBe('取消本轮结束后停止')
    expect(all().some((node) => node.text.includes('将在本轮结束后停止'))).toBe(true)
    expect(find((node) => node.props.onClick === page.stop).props.disabled).toBe(false)
    await page.select_stop_action('after_round')
    expect(state.mower.set_stop_after_round).toHaveBeenLastCalledWith(false)
  })

  it('blocks duplicate round-stop requests but keeps immediate Stop available', async () => {
    state.mower.refs.running.value = true
    let resolveRequest
    state.mower.set_stop_after_round.mockImplementation(
      () => new Promise((resolve) => (resolveRequest = resolve))
    )
    const page = scope.run(() => LogPage.setup({}, { expose: vi.fn() }))
    const request = page.select_stop_action('after_round')
    expect(page.stop_options.value[0].disabled).toBe(true)
    expect(state.mower.refs.waiting.value).toBe(false)
    await page.select_stop_action('after_round')
    expect(state.mower.set_stop_after_round).toHaveBeenCalledOnce()
    resolveRequest()
    await request
    expect(page.stop_options.value[0].disabled).toBe(false)
  })

  it('shows request errors and allows another attempt', async () => {
    state.mower.set_stop_after_round.mockRejectedValueOnce({
      response: { data: { error: '任务已经结束' } }
    })
    const page = scope.run(() => LogPage.setup({}, { expose: vi.fn() }))
    await page.select_stop_action('after_round')
    expect(state.error).toHaveBeenCalledExactlyOnceWith('任务已经结束')
    expect(page.round_stop_busy.value).toBe(false)
    expect(state.mower.refs.stop_after_round.value).toBe(false)
  })

  it('runs both process actions directly through ProcessControl', async () => {
    state.mower.refs.running.value = true
    const component = scope.run(() => LogPage.setup({}, { expose: vi.fn() }))
    const applySchedule = vi.fn()
    const restartResume = vi.fn()
    expect(
      component.stop_options.value.find((option) => option.key === 'apply_schedule').disabled
    ).toBe(true)
    expect(
      component.stop_options.value.find((option) => option.key === 'restart_resume').disabled
    ).toBe(true)

    component.process_control.value = {
      canRunProcessAction: true,
      applySchedule,
      restartResume
    }
    await nextTick()
    expect(component.stop_options.value.map((option) => option.label)).toEqual([
      '本轮结束后停止',
      '停止MAA',
      '应用排班',
      '重启续接'
    ])
    expect(
      component.stop_options.value.find((option) => option.key === 'apply_schedule').disabled
    ).toBe(false)
    expect(
      component.stop_options.value.find((option) => option.key === 'restart_resume').disabled
    ).toBe(false)

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
    component.sc_blob.value = 'blob:http://latest'
    component.layout_preference.screenshot_height = 500
    component.layout_preference.task_height = 600
    component.apply_log_layout()
    const initialTaskHeight = setProperty.mock.calls.at(-1)[1]

    conditionHeight = 40
    state.mower.refs.plan_condition.value = ['副表一']
    await nextTick()
    await nextTick()

    expect(setProperty.mock.calls.length).toBeGreaterThan(2)
    expect(setProperty.mock.calls.at(-1)).toEqual(['--log-task-h', '194px'])
    expect(setProperty.mock.calls.at(-1)[1]).not.toBe(initialTaskHeight)
  })

  it('sizes screenshot and task table while keeping the log readable', () => {
    const sizes = new Map()
    const container = {
      getBoundingClientRect: () => ({ top: 100, bottom: 1000, height: 900 }),
      querySelector: (selector) => {
        if (selector === '.log-screenshot') {
          return { getBoundingClientRect: () => ({ top: 100 }) }
        }
        if (selector === '.task-table-scroll') {
          return {
            getBoundingClientRect: () => ({
              top: 100 + parseInt(sizes.get('--log-sc-h'), 10) + 8
            })
          }
        }
        return null
      },
      style: {
        setProperty: (key, value) => sizes.set(key, value),
        removeProperty: (key) => sizes.delete(key)
      }
    }
    const component = scope.run(() => LogPage.setup({}, { expose: vi.fn() }))
    component.log_layout.value = container
    component.sc_blob.value = 'blob:http://latest'
    component.layout_preference.screenshot_height = 500
    component.layout_preference.task_height = 600

    component.apply_log_layout()

    const screenshotHeight = parseInt(sizes.get('--log-sc-h'), 10)
    const taskHeight = parseInt(sizes.get('--log-task-h'), 10)
    expect(screenshotHeight).toBe(495)
    expect(taskHeight).toBe(269)
    expect(screenshotHeight + 8 + taskHeight + 8 + 120).toBeLessThanOrEqual(900)
  })

  it('measures screenshot dragging from the screenshot top and saves only its height', () => {
    const setProperty = vi.fn()
    const listeners = new Map()
    document.addEventListener.mockImplementation((name, handler) => listeners.set(name, handler))
    state.client.post.mockResolvedValue({})
    const container = {
      getBoundingClientRect: () => ({ top: 80, bottom: 1080, height: 1000 }),
      querySelector: (selector) => {
        if (selector === '.log-screenshot') {
          return { getBoundingClientRect: () => ({ top: 320 }) }
        }
        if (selector === '.action-container') {
          return { getBoundingClientRect: () => ({ height: 52 }) }
        }
        return null
      },
      style: { setProperty, removeProperty: vi.fn() }
    }
    const component = scope.run(() => LogPage.setup({}, { expose: vi.fn() }))
    component.log_layout.value = container
    const event = { preventDefault: vi.fn() }

    component.resize_log_pane(event, 'screenshot')
    listeners.get('pointermove')({ clientY: 510 })
    listeners.get('pointerup')()

    expect(event.preventDefault).toHaveBeenCalledOnce()
    expect(setProperty).toHaveBeenLastCalledWith('--log-sc-h', '190px')
    expect(component.layout_preference.screenshot_height).toBe(190)
    expect(state.client.post).toHaveBeenCalledExactlyOnceWith('/ui-state/log-layout', {
      screenshot_height: 190
    })
    expect(document.removeEventListener).toHaveBeenCalledWith(
      'pointermove',
      listeners.get('pointermove')
    )
    expect(document.removeEventListener).toHaveBeenCalledWith(
      'pointerup',
      listeners.get('pointerup')
    )
  })

  it('uses the natural table height until the user saves a resized height', async () => {
    const setProperty = vi.fn()
    const container = {
      getBoundingClientRect: () => ({ top: 0, bottom: 620, height: 620 }),
      querySelector: (selector) => {
        if (selector === '.action-container') {
          return { getBoundingClientRect: () => ({ height: 52 }) }
        }
        if (selector === '.task-table-scroll') {
          return { getBoundingClientRect: () => ({ top: 370 }) }
        }
        return null
      },
      style: { setProperty, removeProperty: vi.fn() }
    }
    const component = scope.run(() => LogPage.setup({}, { expose: vi.fn() }))
    component.log_layout.value = container
    component.apply_log_layout()
    expect(container.style.removeProperty).toHaveBeenCalledWith('--log-task-h')
    expect(setProperty.mock.calls.some(([key]) => key === '--log-task-h')).toBe(false)
    expect(component.layout_preference.task_height).toBeNull()
    setProperty.mockClear()

    state.mower.refs.task_list.value = [{ time: '2026-10-17T12:00:00', plan: {} }]
    await nextTick()
    await nextTick()

    expect(setProperty.mock.calls.some(([key]) => key === '--log-task-h')).toBe(false)
    component.layout_preference.task_height = 600
    component.apply_log_layout()
    expect(setProperty).toHaveBeenCalledWith('--log-task-h', '122px')
    expect(122 + 120 + 8).toBeLessThanOrEqual(620 - 370)
    expect(component.layout_preference.task_height).toBe(600)
    expect(state.client.post).not.toHaveBeenCalled()
  })

  it('collapses the complete mobile queue and resizer inside the log pane without losing their state', async () => {
    state.mobile.value = true
    state.mower.refs.task_list.value = [
      {
        time: '2026-10-20T11:30:00.000',
        plan: {},
        type: { display_value: '跑单' }
      }
    ]
    const { find, all } = mountWorkspace()
    const collapseBtn = find((target) => target.props.class === 'toggle-table-collapse-btn')
    const queue = find((target) => target.props.class === 'task-table-scroll')
    const resizer = find((target) => target.props.class === 'log-resizer log-resizer-task')
    const log = find((target) => target.props['data-log-content'])
    const pane = queue.parent
    const page = app._instance.setupState
    expect(page.show_task_table).toBe(true)
    expect(collapseBtn.parent).toBe(pane)
    expect(collapseBtn.props['aria-expanded']).toBe(true)
    expect(collapseBtn.props['aria-label']).toBe('收起任务列表')
    expect(collapseBtn.props['aria-controls']).toBe(queue.props.id)
    expect(queue.props.id).toBeTruthy()
    page.layout_preference.task_height = 132

    collapseBtn.props.onClick()
    await nextTick()
    expect(page.show_task_table).toBe(false)
    expect(queue.style.display).toBe('none')
    expect(resizer.style.display).toBe('none')
    expect(pane.props.class.split(' ')).not.toContain('has-tasks')
    expect(collapseBtn.props['aria-expanded']).toBe(false)
    expect(collapseBtn.props['aria-label']).toBe('展开任务列表')
    expect(all().filter((target) => target.props.class === 'task-table-scroll')).toEqual([queue])
    expect(find((target) => target.props['data-log-content'])).toBe(log)

    collapseBtn.props.onClick()
    await nextTick()
    expect(page.show_task_table).toBe(true)
    expect(queue.style.display).not.toBe('none')
    expect(resizer.style.display).not.toBe('none')
    expect(pane.props.class.split(' ')).toContain('has-tasks')
    expect(page.layout_preference.task_height).toBe(132)
    expect(state.client.get).not.toHaveBeenCalled()
    expect(state.client.post).not.toHaveBeenCalled()

    state.mower.refs.task_list.value = []
    await nextTick()
    expect(all().some((target) => target.props.class === 'toggle-table-collapse-btn')).toBe(false)
  })

  it('keeps the desktop queue visible and omits mobile folding even after the mobile table was hidden', async () => {
    state.mower.refs.task_list.value = [
      { time: '2026-10-20T11:30:00.000', plan: {}, type: { display_value: '跑单' } }
    ]
    const { find, all } = mountWorkspace()
    const queue = find((target) => target.props.class === 'task-table-scroll')
    const page = app._instance.setupState
    page.show_task_table = false
    await nextTick()
    expect(queue.style.display).not.toBe('none')
    expect(queue.parent.props.class.split(' ')).toContain('has-tasks')
    expect(all().some((target) => target.props.class === 'toggle-table-collapse-btn')).toBe(false)
    state.mobile.value = true
    await nextTick()
    expect(queue.style.display).toBe('none')
    expect(
      find((target) => target.props.class === 'toggle-table-collapse-btn').props['aria-expanded']
    ).toBe(false)
    state.mobile.value = false
    await nextTick()
    expect(queue.style.display).not.toBe('none')
    expect(all().some((target) => target.props.class === 'toggle-table-collapse-btn')).toBe(false)
  })
})
