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
  onBeforeUnmount,
  onMounted,
  onUnmounted,
  reactive,
  ref,
  shallowReactive
} from 'vue'
import { routeLocationKey, routerKey } from 'vue-router'

import LogPage from './Log.vue'
import LogDailyStatus from '@/components/LogDailyStatus.vue'
import TaskConfiguration from '@/task-workflow/TaskConfiguration.vue'
import { useLogBackgroundStore } from '@/stores/logBackground'
import { useGuiStore } from '@/stores/gui'

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
  plan: null,
  config: null,
  warning: null,
  error: null,
  taskVisibility: null,
  route: null,
  router: null,
  mobile: null,
  chatPanelVisible: null,
  preview: null,
  previewOptions: null,
  realPreview: false,
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
    if (key === 'chat_panel_visible') return state.chatPanelVisible
    return ref(false)
  },
  onBeforeUnmount: vi.fn(),
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
vi.mock('@/stores/plan', () => ({ usePlanStore: () => state.plan }))
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
vi.mock('@/utils/screenshotPreview', async (original) => {
  const actual = await original()
  return {
    createScreenshotPreview: (options) => {
      state.previewOptions = options
      return state.realPreview ? actual.createScreenshotPreview(options) : state.preview
    }
  }
})

describe('log page', () => {
  let scope
  let app

  beforeEach(() => {
    setActivePinia(createPinia())
    vi.useFakeTimers()
    onBeforeUnmount.mockClear()
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
        status: ref('stopped'),
        stop_after_round: ref(false),
        maintenance_pause: ref(null),
        status_label: ref('已停止'),
        plan_condition: ref([]),
        log_lines: ref([]),
        task_list: ref([]),
        waiting: ref(false)
      },
      clear_legacy_logs: vi.fn(),
      get_tasks: vi.fn(),
      get_running: vi.fn(),
      set_stop_after_round: vi.fn(),
      cancel_maintenance_pause: vi.fn(),
      start_task_polling: vi.fn(),
      stop_task_polling: vi.fn()
    }
    state.config = shallowReactive({ refs: { theme: ref('light') } })
    state.plan = {
      refs: {
        operators: ref([{ value: '阿米娅' }, { value: '芬' }]),
        plan: ref({ room_1_1: { name: '贸易站' } })
      }
    }
    state.configurationMounts = 0
    state.taskVisibility = null
    state.route = reactive({ hash: '', query: {}, redirectedFrom: null })
    state.router = { push: vi.fn(), replace: vi.fn() }
    state.mobile = ref(false)
    state.chatPanelVisible = ref(false)
    state.preview = { start: vi.fn(), stop: vi.fn() }
    state.realPreview = false
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
    expect(state.mower.clear_legacy_logs).toHaveBeenCalledOnce()
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
      'NModal',
      'NCheckbox',
      'DropDown',
      'StartSchedule',
      'ProcessControl',
      'TaskDialog',
      'HelpText',
      'StopIcon',
      'PlayIcon',
      'AddIcon',
      'LayersOutlineIcon',
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
    app.component('LogOutput', {
      props: [
        'lines',
        'operatorNames',
        'facilityPlan',
        'compact',
        'concise',
        'autoScroll',
        'showAlternateView'
      ],
      setup:
        (props, { slots }) =>
        () =>
          h('pre', { 'data-log-content': true, ...props }, [
            slots.title?.(),
            props.showAlternateView ? slots.alternate?.() : slots.header?.()
          ])
    })
    const dailyStatusTemplate = parse(
      readFileSync(new URL('../components/LogDailyStatus.vue', import.meta.url), 'utf8')
    ).descriptor.template.content
    app.component('LogDailyStatus', {
      ...LogDailyStatus,
      ssrRender: undefined,
      render: compile(dailyStatusTemplate),
      setup: (props, context) => ({ ...LogDailyStatus.setup(props, context) })
    })
    app.component('LogOperator', {
      props: ['name', 'showName'],
      setup: (props) => () =>
        h(
          'span',
          { 'data-operator-name': props.name, 'data-show-name': props.showName },
          props.name
        )
    })
    app.component('TaskActionSubjects', {
      props: ['actions', 'facilityPlan', 'size'],
      setup: (props) => () =>
        h(
          'span',
          { 'data-task-action-subjects': true, ...props },
          props.actions.map((action) => action.subject + action.action).join('；')
        )
    })
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

  async function openViewOptions(find) {
    const trigger = find((target) => target.props.class === 'view-options-trigger')
    expect(trigger.props['aria-expanded']).toBe(false)
    let triggerHost = trigger.parent
    while (triggerHost && !triggerHost.props.onClick) triggerHost = triggerHost.parent
    expect(triggerHost).toBeTruthy()
    triggerHost.props.onClick()
    await nextTick()
    expect(trigger.props['aria-expanded']).toBe(true)
    const panel = find((target) => target.props.id === trigger.props['aria-controls'])
    expect(panel.props.role).toBe('dialog')
    return trigger
  }

  function viewControl(find, label) {
    return find(
      (target) =>
        target.props['aria-label'] === label && typeof target.props['aria-pressed'] === 'boolean'
    )
  }

  it('updates the mounted background immediately when shared settings change', async () => {
    const { find } = mountWorkspace()
    const layer = find((target) => target.props.class?.split(' ').includes('log-bg'))
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

  it('keeps the last decoded screenshot and layout through repeated invalid frames', async () => {
    state.realPreview = true
    const frames = ['A', 'B', 'C', 'D'].map((name) => ({
      status: 200,
      data: new Blob([name], { type: 'image/jpeg' }),
      headers: { etag: `"${name}"` }
    }))
    const requests = vi.fn()
    for (const frame of frames) requests.mockResolvedValueOnce(frame)
    requests.mockResolvedValue({ status: 304, headers: {} })
    state.client.get.mockImplementation(async (url, options) =>
      url.endsWith('/screenshot/latest') ? requests(options) : { data: {} }
    )
    vi.stubGlobal(
      'Image',
      class {
        naturalWidth = 1600

        async decode() {
          if (this.src === 'blob:B' || this.src === 'blob:C') throw new Error('Invalid JPEG')
          this.naturalHeight = this.src === 'blob:A' ? 900 : 1200
        }
      }
    )
    const createUrl = vi
      .spyOn(URL, 'createObjectURL')
      .mockReturnValueOnce('blob:A')
      .mockReturnValueOnce('blob:B')
      .mockReturnValueOnce('blob:C')
      .mockReturnValueOnce('blob:D')
    const debug = vi.spyOn(console, 'debug').mockImplementation(() => {})
    const { find, page, sizes } = mountWidePane()
    const getScreenshot = () => find((target) => target.props.class === 'log-screenshot')
    const getResizer = () => find((target) => target.props.class === 'log-resizer log-resizer-sc')
    const released = []
    const revokeUrl = vi.spyOn(URL, 'revokeObjectURL').mockImplementation((url) => {
      released.push([url, getScreenshot()?.props.src])
    })

    try {
      onMounted.mock.lastCall[0]()
      await vi.advanceTimersByTimeAsync(0)
      const screenshot = getScreenshot()
      const resizer = getResizer()
      const cached = { blob: frames[0].data, etag: '"A"', aspect: 16 / 9 }
      expect(screenshot.props.src).toBe('blob:A')
      expect(resizer).toBeDefined()
      expect(sizes()['--log-rail-w']).toBe('480px')
      expect(sizes()['--log-sc-h']).toBe('270px')
      expect(page.workspace.screenshot).toEqual(cached)
      expect(requests.mock.lastCall[0].headers).toEqual({})

      for (const [index, invalid] of ['blob:B', 'blob:C'].entries()) {
        await vi.advanceTimersByTimeAsync(999)
        expect(requests).toHaveBeenCalledTimes(index + 1)
        await vi.advanceTimersByTimeAsync(1)
        expect(requests).toHaveBeenCalledTimes(index + 2)
        expect(requests.mock.lastCall[0].headers).toEqual({ 'If-None-Match': '"A"' })
        expect(getScreenshot()).toBe(screenshot)
        expect(screenshot.props.src).toBe('blob:A')
        expect(getResizer()).toBe(resizer)
        expect(sizes()['--log-rail-w']).toBe('480px')
        expect(sizes()['--log-sc-h']).toBe('270px')
        expect(page.workspace.screenshot).toEqual(cached)
        expect(released.at(-1)).toEqual([invalid, 'blob:A'])
        expect(revokeUrl).not.toHaveBeenCalledWith('blob:A')
      }

      await vi.advanceTimersByTimeAsync(1000)
      expect(requests).toHaveBeenCalledTimes(4)
      expect(requests.mock.lastCall[0].headers).toEqual({ 'If-None-Match': '"A"' })
      expect(getScreenshot()).toBe(screenshot)
      expect(screenshot.props.src).toBe('blob:D')
      expect(getResizer()).toBe(resizer)
      expect(sizes()['--log-rail-w']).toBe('360px')
      expect(sizes()['--log-sc-h']).toBe('270px')
      expect(page.workspace.screenshot).toEqual({
        blob: frames[3].data,
        etag: '"D"',
        aspect: 4 / 3
      })
      expect(released).toContainEqual(['blob:A', 'blob:D'])

      await vi.advanceTimersByTimeAsync(1000)
      expect(requests).toHaveBeenCalledTimes(5)
      expect(requests.mock.lastCall[0].headers).toEqual({ 'If-None-Match': '"D"' })
      expect(screenshot.props.src).toBe('blob:D')
      expect(createUrl).toHaveBeenCalledTimes(4)
    } finally {
      onUnmounted.mock.lastCall[0]()
      createUrl.mockRestore()
      revokeUrl.mockRestore()
      debug.mockRestore()
    }
  })

  async function publishScreenshot(url, aspect) {
    await state.previewOptions.onChange(url, aspect)
    await nextTick()
  }

  it('fits the default mobile screenshot height to the loaded frame and current pane width', async () => {
    state.mobile.value = true
    const { find } = mountWorkspace()
    const page = app._instance.setupState
    const pane = find((target) => target.props['aria-label'] === '运行日志')
    pane.clientWidth = 360
    pane.getBoundingClientRect = () => ({ top: 0, bottom: 900, height: 900 })
    await publishScreenshot('blob:http://latest', 16 / 9)
    const screenshot = find((target) => target.props.class === 'log-screenshot')
    pane.querySelector = (selector) => (selector === '.log-screenshot' ? screenshot : null)
    const screenshotHeight = () =>
      pane.style.setProperty.mock.calls.filter(([key]) => key === '--log-sc-h').at(-1)?.[1]
    expect(screenshotHeight()).toBe('203px')

    pane.clientWidth = 640
    page.apply_log_layout()
    expect(screenshotHeight()).toBe('360px')

    screenshot.clientWidth = 240
    page.apply_log_layout()
    expect(screenshotHeight()).toBe('135px')

    screenshot.clientWidth = 0
    pane.clientWidth = 360
    await publishScreenshot('blob:http://portrait', 9 / 16)
    expect(screenshotHeight()).toBe('640px')
    pane.clientWidth = 360
    pane.getBoundingClientRect = () => ({ top: 0, bottom: 220, height: 220 })
    await publishScreenshot('blob:http://landscape', 16 / 9)
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
    await publishScreenshot('blob:http://latest', 16 / 9)
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
    await publishScreenshot('blob:http://portrait', 9 / 16)
    expect(screenshotHeight()).toBe('190px')
    expect(page.layout_preference.screenshot_height).toBe(190)
    expect(state.client.post).toHaveBeenCalledExactlyOnceWith('/ui-state/log-layout', {
      screenshot_height: 190
    })
  })

  it('keeps each task in one row with an independent time cell and ordered facilities', async () => {
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
      '11:30:00 换班 自动救急换班 宿舍1 芬 贸易站 B101 阿米娅 _',
      '10:00:00 扫描仓库 全部物品'
    ])
    const timeCell = rows()[1].children.find((target) => target.tag === 'td')
    expect(text(timeCell)).toBe('11:30:00')
    expect(all(rows()[1]).filter((target) => target.props.class === 'task-facility')).toHaveLength(
      2
    )
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

  it('shows readable target rooms and backend action titles without splitting a task', () => {
    state.plan.refs.plan.value.room_2_1 = { name: '贸易站' }
    state.mower.refs.task_list.value = [
      {
        time: '2026-11-04T16:05:19',
        plan: {},
        display_name: '刷新跑单时间',
        meta_data: 'room_2_1'
      },
      {
        time: '2026-11-04T18:11:29',
        plan: { room_3_3: ['Current', '阿米娅'], dormitory_2: ['芬'] },
        type: { display_value: '下班' },
        presentation: {
          title: '甲组上班、乙组下班',
          rooms: [
            { id: 'room_3_3', label: '发电站 B303', agents: ['Current', '阿米娅'] },
            { id: 'dormitory_2', label: '宿舍2', agents: ['芬'] }
          ],
          targets: [],
          backups: []
        }
      }
    ]
    const { find, all } = mountWorkspace()
    const queue = find((target) => target.props.class === 'task-table-scroll')
    const text = (target) =>
      all(target)
        .filter((entry) => entry.tag !== '#comment')
        .map((entry) => entry.text)
        .join(' ')
        .replace(/\s+/g, ' ')
        .trim()
    expect(text(queue)).toContain('刷新跑单时间 贸易站 B201')
    const refreshHeading = all(queue).find((entry) => entry.props.class === 'task-heading')
    expect(text(refreshHeading)).toBe('刷新跑单时间')
    const refreshTargets = all(queue).find((entry) => entry.props.class === 'task-refresh-targets')
    expect(text(refreshTargets)).toBe('贸易站 B201')
    expect(text(queue)).not.toContain('room_2_1')
    expect(text(queue)).toContain('甲组上班、乙组下班')
    expect(text(queue)).toContain('发电站 B303')
    const rows = all(queue).filter((entry) => entry.tag === 'tr')
    expect(rows).toHaveLength(3)
    const cells = all(queue).filter((entry) => entry.tag === 'td')
    expect(cells.filter((entry) => entry.props.class === 'task-time').map(text)).toEqual([
      '16:05:19',
      '18:11:29'
    ])
    expect(
      all(rows[2])
        .filter((entry) => entry.props.class === 'task-room-label')
        .map(text)
    ).toEqual(['宿舍2', '发电站 B303'])
  })

  it('shows full dates from non-today times on desktop hover or touch', async () => {
    vi.setSystemTime(new Date(2026, 10, 6, 20))
    state.mower.refs.task_list.value = [
      { time: '2026-11-06T17:38:57', plan: {}, type: { display_value: '上班' } },
      { time: '2026-11-07T13:26:26', plan: {}, type: { display_value: '线索交流' } },
      { time: '2026-11-07T16:00:00', plan: {}, type: { display_value: '安排干员' } },
      { time: '2026-11-06T20:07:41', plan: {}, type: { display_value: '刷新跑单时间' } }
    ]
    const { root, all } = mountWorkspace()
    const pageText = () =>
      all(root)
        .map((entry) => entry.text)
        .join('')
    const times = all().filter((entry) => entry.tag === 'time')
    expect(times.map((entry) => entry.text)).toEqual([
      '17:38:57',
      '13:26:26',
      '16:00:00',
      '20:07:41'
    ])
    const triggers = all().filter((entry) => entry.props.class === 'task-date-trigger')
    expect(triggers.map((entry) => entry.props['aria-label'])).toEqual([
      '2026-11-07 13:26:26',
      '2026-11-07 16:00:00'
    ])
    expect(times[1].props.datetime).toBe('2026-11-07T13:26:26')
    expect(pageText()).not.toContain('2026-11-07')

    triggers[0].props.onPointerenter({ pointerType: 'mouse' })
    await nextTick()
    expect(pageText()).toContain('2026-11-07 13:26:26')
    triggers[0].props.onPointerleave({ pointerType: 'mouse' })
    await nextTick()
    expect(pageText()).not.toContain('2026-11-07 13:26:26')

    triggers[1].props.onPointerenter({ pointerType: 'touch' })
    await nextTick()
    expect(triggers[1].props['aria-expanded']).toBe(false)
    triggers[1].parent.props.onClick()
    await nextTick()
    expect(triggers[1].props['aria-expanded']).toBe(true)
    expect(pageText()).toContain('2026-11-07 16:00:00')
    triggers[1].props.onKeydown({ key: 'Escape', stopPropagation: vi.fn() })
    await nextTick()
    expect(pageText()).not.toContain('2026-11-07 16:00:00')

    triggers[1].parent.props.onClick()
    await nextTick()
    const tasks = state.mower.refs.task_list.value
    state.mower.refs.task_list.value = tasks.filter((_, index) => index !== 2)
    await nextTick()
    state.mower.refs.task_list.value = tasks
    await nextTick()
    expect(pageText()).not.toContain('2026-11-07 16:00:00')
  })

  it('switches the task list to the alpha text columns and retains date and backup display', async () => {
    vi.setSystemTime(new Date(2026, 10, 6, 20))
    state.mower.refs.plan_condition.value = ['停服更新']
    state.mower.refs.task_list.value = [
      {
        time: '2026-11-07T13:26:26',
        plan: { room_3_3: ['Current', '阿米娅', ''], dormitory_2: ['芬'] },
        type: { display_value: '下班' },
        emergency_staffing: true
      },
      {
        time: '2026-11-06T20:07:41',
        plan: {},
        display_name: '刷新跑单时间',
        meta_data: 'room_2_1'
      }
    ]
    const { all, find } = mountWorkspace()
    const gui = useGuiStore()
    const queue = find((target) => target.props.class === 'task-table-scroll')
    const backup = find((target) => target.props.class === 'plan-condition')
    const rows = () => all(queue).filter((target) => target.tag === 'tr')
    const cells = (row) => row.children.filter((target) => target.tag === 'td')
    const text = (target) =>
      all(target)
        .filter((entry) => entry.tag !== '#comment')
        .map((entry) => entry.text)
        .join('')
        .trim()
    expect(rows()).toHaveLength(3)
    expect(all(queue).some((target) => target.props['data-operator-name'] === '阿米娅')).toBe(true)

    gui.taskQueueDisplay = 'names'
    await nextTick()
    expect(rows()).toHaveLength(4)
    expect(cells(rows()[1]).map(text)).toEqual([
      '13:26:26自动救急换班',
      'room_3_3',
      'Current, 阿米娅, _'
    ])
    expect(cells(rows()[1])[0].props.rowspan).toBe(2)
    expect(cells(rows()[2]).map(text)).toEqual(['dormitory_2', '芬'])
    expect(cells(rows()[3]).map(text)).toEqual(['20:07:41', '刷新跑单时间 room_2_1'])
    expect(cells(rows()[3])[1].props.colspan).toBe('2')
    expect(all(queue).some((target) => target.props['data-operator-name'])).toBe(false)
    expect(
      all(queue).find((target) => target.props.class === 'task-date-trigger').props['aria-label']
    ).toBe('2026-11-07 13:26:26')
    expect(all().indexOf(backup)).toBeLessThan(all().indexOf(queue))
    expect(text(backup)).toContain('停服更新')

    gui.taskQueueDisplay = 'portraits'
    await nextTick()
    expect(rows()).toHaveLength(3)
  })

  it('refreshes the non-today indication after local midnight while the log stays open', async () => {
    vi.setSystemTime(new Date(2026, 10, 6, 23, 59, 59))
    state.client.get.mockResolvedValue({ data: {} })
    state.mower.refs.task_list.value = [
      { time: '2026-11-06T23:59:59', plan: {}, type: { display_value: '上班' } },
      { time: '2026-11-07T13:26:26', plan: {}, type: { display_value: '线索交流' } }
    ]
    const { all } = mountWorkspace()
    onMounted.mock.lastCall[0]()
    const markedTimes = () =>
      all()
        .filter((entry) => entry.props.class === 'task-date-trigger')
        .map((entry) => entry.props['aria-label'])
    expect(markedTimes()).toEqual(['2026-11-07 13:26:26'])
    await vi.advanceTimersByTimeAsync(5000)
    expect(markedTimes()).toEqual(['2026-11-06 23:59:59'])
    onUnmounted.mock.lastCall[0]()
  })

  it('places same-instant refresh facilities below one heading without changing the backend tasks', () => {
    state.plan.refs.plan.value.room_2_1 = { name: '贸易站' }
    const tasks = Object.freeze([
      Object.freeze({
        time: '2026-11-05T16:05:19.000',
        plan: {},
        display_name: '刷新跑单时间',
        meta_data: 'room_2_1'
      }),
      Object.freeze({
        time: '2026-11-05T16:05:19.000',
        plan: {},
        display_name: '刷新跑单时间',
        meta_data: 'room_1_1'
      })
    ])
    state.mower.refs.task_list.value = tasks
    const { find, all } = mountWorkspace()
    const queue = find((entry) => entry.props.class === 'task-table-scroll')
    const content = (entry) =>
      all(entry)
        .filter((item) => item.tag !== '#comment')
        .map((item) => item.text)
        .join('')
        .trim()
    expect(all(queue).filter((entry) => entry.tag === 'tr')).toHaveLength(2)
    const heading = all(queue).find((entry) => entry.props.class === 'task-heading')
    const facilities = all(queue).find((entry) => entry.props.class === 'task-refresh-targets')
    expect(content(heading)).toBe('刷新跑单时间')
    expect(
      all(facilities)
        .filter((entry) => entry.props.class === 'task-room-label')
        .map(content)
    ).toEqual(['贸易站 B201', '贸易站 B101'])
    expect(heading.parent.children.indexOf(heading)).toBeLessThan(
      heading.parent.children.indexOf(facilities)
    )
    expect(
      all(queue)
        .filter((entry) => entry.tag === 'time')
        .map(content)
    ).toEqual(['16:05:19'])
    expect(all(heading.parent).filter((entry) => entry.tag === 'button')).toHaveLength(0)
    expect(state.mower.refs.task_list.value).toBe(tasks)
    expect(state.client.post).not.toHaveBeenCalled()
  })

  it('retains separate refresh rows when fractional timestamps differ', () => {
    state.plan.refs.plan.value.room_2_1 = { name: '贸易站' }
    state.mower.refs.task_list.value = [
      {
        time: '2026-11-05T16:05:19.001',
        plan: {},
        display_name: '刷新跑单时间',
        meta_data: 'room_1_1'
      },
      {
        time: '2026-11-05T16:05:19.002',
        plan: {},
        display_name: '刷新跑单时间',
        meta_data: 'room_2_1'
      }
    ]
    const { find, all } = mountWorkspace()
    const queue = find((entry) => entry.props.class === 'task-table-scroll')
    expect(all(queue).filter((entry) => entry.tag === 'tr')).toHaveLength(3)
    expect(
      all(queue)
        .filter((entry) => entry.tag === 'time')
        .map((entry) => entry.props.datetime)
    ).toEqual(['2026-11-05T16:05:19.001', '2026-11-05T16:05:19.002'])
    expect(all(queue).filter((entry) => entry.props.class === 'task-refresh-targets')).toHaveLength(
      2
    )
  })

  it('reuses the correct task row across equivalent polls and insertions while changing real content keys', async () => {
    const task = {
      time: '2026-11-05T18:11:29.000',
      plan: { room_1_1: ['Current', '阿米娅', 'Free'], dormitory_1: ['芬'] },
      type: { display_value: '上班' }
    }
    state.mower.refs.task_list.value = [task]
    const { find, all } = mountWorkspace()
    const taskRow = () => {
      let entry = find((node) => node.tag === 'time' && node.props.datetime === task.time)
      while (entry.tag !== 'tr') entry = entry.parent
      return entry
    }
    const original = taskRow()
    const portraitNames = (row) =>
      all(row)
        .filter((entry) => entry.props['data-operator-name'])
        .map((entry) => entry.props['data-operator-name'])
    expect(portraitNames(original)).toEqual(['芬', 'Current', '阿米娅', 'Free'])
    state.mower.refs.task_list.value = [JSON.parse(JSON.stringify(task))]
    await nextTick()
    expect(taskRow()).toBe(original)
    state.mower.refs.task_list.value = [
      { time: '2026-11-05T17:00:00.000', plan: {}, display_name: '扫描仓库' },
      JSON.parse(JSON.stringify(task))
    ]
    await nextTick()
    expect(taskRow()).toBe(original)
    expect(portraitNames(taskRow())).toEqual(['芬', 'Current', '阿米娅', 'Free'])
    state.mower.refs.task_list.value[1].plan.room_1_1[0] = '芬'
    await nextTick()
    expect(taskRow()).not.toBe(original)
    expect(portraitNames(taskRow())).toEqual(['芬', '芬', '阿米娅', 'Free'])
  })

  it('keeps the automatic mastery heading separate from the training row with existing mastery icons', () => {
    state.plan.refs.operators.value = [{ value: '焰狐龙梓兰' }, { value: '逻各斯' }]
    state.mower.refs.task_list.value = [
      {
        time: '2026-11-04T19:42:00',
        plan: {},
        type: { display_value: '换协助位' },
        meta_data: '焰狐龙梓兰 二技能·飞翔瞪射 专二 → 专三 换入逻各斯'
      },
      {
        time: '2026-11-04T19:43:00',
        plan: {},
        type: { display_value: '空任务' },
        presentation: { title: '', rooms: [], targets: [], backups: [] }
      },
      {
        time: '2026-11-04T19:44:00',
        plan: {},
        display_name: '替班心情检查：白面鸮',
        meta_data: '替班心情检查：白面鸮'
      }
    ]
    const { find, all } = mountWorkspace()
    const queue = find((entry) => entry.props.class === 'task-table-scroll')
    const text = all(queue)
      .map((entry) => entry.text)
      .join(' ')
    expect(text).toContain('二技能·飞翔瞪射')
    expect(text).toContain('训练室')
    expect(text).toContain('换入')
    expect(text).toContain('空任务')
    expect(text.match(/替班心情检查：白面鸮/gu)).toHaveLength(1)
    expect(
      all(queue)
        .filter((entry) => entry.props['data-operator-name'])
        .map((entry) => entry.props['data-operator-name'])
    ).toEqual(['焰狐龙梓兰', '逻各斯'])
    expect(
      all(queue)
        .filter((entry) => entry.props.class === 'task-mastery')
        .map((entry) => entry.props['aria-label'])
    ).toEqual(['专二 → 专三'])
    const headings = all(queue).filter((entry) => entry.props.class === 'task-heading')
    expect(
      all(headings[0])
        .filter((entry) => entry.tag !== '#comment')
        .map((entry) => entry.text)
        .join('')
    ).toBe('自动专精换协助位')
    expect(
      all(queue)
        .filter((entry) => entry.tag === 'img' && /mastery-[0-3]\.png/u.test(entry.props.src ?? ''))
        .map((entry) => entry.props.src.match(/mastery-([0-3])\.png/u)[1])
    ).toEqual(['2', '3'])
  })

  it.each(['下班', '转为空闲'])('passes %s actions once with their full identities', (action) => {
    const actions = [
      ...(action === '转为空闲'
        ? [{ kind: 'operator', subject: '桑葚', action: '休息' }]
        : [{ kind: 'group', subject: '感知', action: '上班', members: ['阿米娅', '凯尔希'] }]),
      ...['芬', '红', '陈', '赫默'].map((subject) => ({
        kind: 'operator',
        subject,
        action
      }))
    ]
    state.mower.refs.task_list.value = [
      {
        time: '2026-11-04T19:42:00',
        plan: {},
        presentation: {
          title: `${action === '转为空闲' ? '桑葚休息' : '感知上班'}；芬、红、陈、赫默${action}`,
          actions
        }
      }
    ]
    const { find, all } = mountWorkspace()
    const subjects = find((entry) => entry.props['data-task-action-subjects'])
    expect(subjects.props.actions).toEqual(actions)
    expect(subjects.props.size).toBe(24)
    const heading = all().find((entry) => entry.props.class === 'task-heading')
    expect(all(heading).filter((entry) => entry.props['data-operator-name'])).toHaveLength(0)
    expect(all(heading).filter((entry) => entry.props['data-task-action-subjects'])).toHaveLength(1)
  })

  it('passes original logs, known operators and the main facility plan across compact layout changes', async () => {
    const rawLines = Object.freeze([
      '2026-10-31 14:12:03,456 INFO 阿米娅进入 room_1_1',
      '  File "scheduler.py", line 72, in arrange\nValueError: 芬仍在训练室'
    ])
    state.mower.refs.log_lines.value = rawLines
    state.mower.refs.log.value = '<span>legacy desktop formatting</span>'
    state.mower.refs.log_mobile.value = 'legacy compact formatting'
    const taskPlan = Object.freeze({
      room_1_1: Object.freeze(['阿米娅']),
      room_1_2: Object.freeze(['芬']),
      unknown_room: Object.freeze(['Free'])
    })
    state.mower.refs.task_list.value = [
      { time: '2026-10-31T14:20:00.000', plan: taskPlan, type: { display_value: '换班' } }
    ]
    const facilityPlan = state.plan.refs.plan.value
    const { find, all } = mountWorkspace()
    const output = find((target) => target.props['data-log-content'])
    const roomLabel = (room) => {
      const cell = find(
        (target) => target.props.class === 'task-room-label' && target.props.title === room
      )
      return all(cell)
        .filter((target) => target.tag !== '#comment')
        .map((target) => target.text)
        .join('')
        .trim()
    }
    expect(all().filter((target) => target.props['data-log-content'])).toHaveLength(1)
    expect(output.props.lines).toBe(rawLines)
    expect(output.props.operatorNames).toEqual(['阿米娅', '芬'])
    expect(output.props.facilityPlan).toBe(facilityPlan)
    expect(output.props.compact).toBe(false)
    expect(roomLabel('room_1_1')).toBe('贸易站 B101')
    expect(roomLabel('room_1_2')).toBe('B102')
    expect(roomLabel('unknown_room')).toBe('unknown_room')

    state.mobile.value = true
    state.plan.refs.operators.value = [{ value: '阿米娅' }, { value: '芬' }, { value: '令' }]
    facilityPlan.room_1_1.name = '制造站'
    facilityPlan.room_1_2 = { name: '未知设施' }
    facilityPlan.unknown_room = { name: '贸易站' }
    await nextTick()
    expect(find((target) => target.props['data-log-content'])).toBe(output)
    expect(output.props.compact).toBe(true)
    expect(output.props.lines).toBe(rawLines)
    expect(output.props.operatorNames).toEqual(['阿米娅', '芬', '令'])
    expect(output.props.facilityPlan).toBe(facilityPlan)
    expect(roomLabel('room_1_1')).toBe('制造站 B101')
    expect(roomLabel('room_1_2')).toBe('B102')
    expect(roomLabel('unknown_room')).toBe('unknown_room')
    expect(state.mower.refs.task_list.value[0].plan).toBe(taskPlan)
    expect(Object.keys(taskPlan)).toEqual(['room_1_1', 'room_1_2', 'unknown_room'])
    expect(state.mower.refs.log_lines.value).toBe(rawLines)
    expect(state.mower.refs.log_lines.value[0]).toBe(
      '2026-10-31 14:12:03,456 INFO 阿米娅进入 room_1_1'
    )
    expect(state.mower.refs.log_lines.value[1]).toBe(
      '  File "scheduler.py", line 72, in arrange\nValueError: 芬仍在训练室'
    )
    expect(state.client.post).not.toHaveBeenCalled()
  })

  it.each([false, true])(
    'shows the charging target portrait and name in the heading (mobile=%s)',
    (mobile) => {
      state.mobile.value = mobile
      const task = {
        time: '2026-10-31T14:02:37.000',
        display_name: '肥鸭',
        meta_data: '砾',
        plan: { dormitory_1: ['砾', '菲亚梅塔'] }
      }
      state.mower.refs.task_list.value = [
        { ...task, presentation: { title: '肥鸭 充 砾' } },
        { ...task, presentation: { title: '肥鸭' } }
      ]
      const { find, all } = mountWorkspace()
      const queue = find((target) => target.props.class === 'task-table-scroll')
      const [charging, fallback] = all(queue).filter(
        (target) => target.props.class === 'task-heading'
      )
      const content = (target) =>
        all(target)
          .filter((entry) => entry.tag !== '#comment')
          .map((entry) => entry.text)
          .join('')
          .replace(/\s+/g, '')
      expect(content(charging)).toBe('菲亚梅塔充能砾')
      const portrait = all(charging).find((target) => target.props['data-operator-name'] === '砾')
      expect(portrait.props['data-show-name']).toBe(true)
      expect(portrait.parent.props['aria-label']).toBe('砾')
      expect(content(fallback)).toBe('菲亚梅塔充能')
      expect(content(queue)).not.toContain('充能对象')
      expect(
        all(queue)
          .filter((target) => target.props.class === 'task-facilities')
          .map((facility) =>
            all(facility)
              .map((target) => target.props['data-operator-name'])
              .filter(Boolean)
          )
      ).toEqual([
        ['砾', '菲亚梅塔'],
        ['砾', '菲亚梅塔']
      ])
    }
  )

  it('shares one task portrait hint across touch and keyboard without replacing the queue or log', async () => {
    state.mobile.value = true
    const originalPlan = { room_1_1: ['阿米娅', '芬', ''] }
    state.mower.refs.task_list.value = [
      { time: '2026-10-31T14:20:00.000', plan: originalPlan, type: { display_value: '换班' } }
    ]
    const { find, all } = mountWorkspace()
    const queue = find((target) => target.props.class === 'task-table-scroll')
    const output = find((target) => target.props['data-log-content'])
    const buttons = all(queue).filter((target) => target.props.class === 'task-operator-button')
    const hints = () => all().filter((target) => target.props.trigger === 'manual')
    const content = (target) =>
      all(target)
        .filter((element) => element.tag !== '#comment')
        .map((element) => element.text)
        .join('')
        .trim()
    const eventFor = (button, left) => {
      button.getBoundingClientRect = () => ({ left, right: left + 28, top: 80 })
      return { currentTarget: button }
    }
    expect(buttons).toHaveLength(3)
    expect(hints()).toHaveLength(0)
    expect(queue.parent).toBe(output.parent)

    buttons[0].props.onClick(eventFor(buttons[0], 100))
    await nextTick()
    const hint = hints()[0]
    expect(hints()).toHaveLength(1)
    expect(content(hint)).toBe('阿米娅')
    expect(hint.props.x).toBe(114)
    expect(hint.props.y).toBe(76)

    buttons[1].props.onFocus(eventFor(buttons[1], 140))
    await nextTick()
    expect(hints()).toHaveLength(1)
    expect(hints()[0]).toBe(hint)
    expect(content(hint)).toBe('芬')
    expect(hint.props.x).toBe(154)
    buttons[1].props.onBlur()
    await nextTick()
    expect(hints()).toHaveLength(0)

    buttons[0].props.onFocus(eventFor(buttons[0], 100))
    await nextTick()
    expect(hints()).toHaveLength(1)
    buttons[0].props.onKeydown({ key: 'Escape' })
    await nextTick()
    expect(hints()).toHaveLength(0)

    buttons[2].props.onClick(eventFor(buttons[2], 180))
    await nextTick()
    expect(hints()).toHaveLength(1)
    expect(content(hints()[0])).toBe('Empty（留空）')
    state.mower.refs.task_list.value[0].time = '2026-10-31T14:25:00.000'
    await nextTick()
    expect(hints()).toHaveLength(0)
    expect(find((target) => target.props.class === 'task-table-scroll')).toBe(queue)
    expect(find((target) => target.props['data-log-content'])).toBe(output)
    expect(queue.parent).toBe(output.parent)
    expect(state.mower.refs.task_list.value[0].plan).toEqual({ room_1_1: ['阿米娅', '芬', ''] })
    expect(originalPlan).toEqual({ room_1_1: ['阿米娅', '芬', ''] })
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

  it.each([false, true])(
    'opens the first task queue at its saved height with mobile=%s',
    async (mobile) => {
      state.mobile.value = mobile
      state.mower.refs.task_list.value = [
        { time: '2026-10-20T11:30:00.000', plan: {}, type: '跑单' }
      ]
      const component = scope.run(() => LogPage.setup({}, { expose: vi.fn() }))
      const styles = new Map()
      const queueReveal = { cancel: vi.fn() }
      const handleReveal = { cancel: vi.fn() }
      const queue = {
        animate: vi.fn(() => queueReveal),
        getBoundingClientRect: () => ({
          top: 0,
          height: parseInt(styles.get('--log-task-h') ?? '240px', 10)
        })
      }
      const handle = { animate: vi.fn(() => handleReveal) }
      component.log_layout.value = {
        clientWidth: 720,
        getBoundingClientRect: () => ({ top: 0, bottom: 720, height: 720 }),
        querySelector: (selector) =>
          ({ '.task-table-scroll': queue, '.log-resizer-task': handle })[selector] ?? null,
        style: {
          setProperty: (name, value) => styles.set(name, value),
          removeProperty: (name) => styles.delete(name)
        }
      }
      state.client.get.mockResolvedValue({ data: {} })
      onMounted.mock.lastCall[0]()
      component.layout_preference.task_height = 132
      component.task_queue_elements.value = [queue]
      await nextTick()
      await nextTick()

      expect(styles.get('--log-task-h')).toBe('132px')
      if (mobile) {
        expect(queue.animate).not.toHaveBeenCalled()
        expect(handle.animate).not.toHaveBeenCalled()
      } else {
        expect(queue.animate).toHaveBeenCalledExactlyOnceWith(
          [{ height: '0px' }, { height: '132px' }],
          expect.objectContaining({ duration: expect.any(Number) })
        )
        expect(handle.animate).toHaveBeenCalledOnce()

        setHidden(true)
        setHidden(false)
        await nextTick()
        expect(queueReveal.cancel).toHaveBeenCalledOnce()
        expect(handleReveal.cancel).toHaveBeenCalledOnce()
        expect(queue.animate).toHaveBeenCalledOnce()
        expect(handle.animate).toHaveBeenCalledOnce()
      }
      onUnmounted.mock.lastCall[0]()
    }
  )

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
    const pane = queue.parent.parent
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
      name: 'settings',
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
      name: 'settings',
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

  it.each([false, true])(
    'reveals a hidden task list through its queue hash (mobile=%s)',
    async (mobile) => {
      state.mobile.value = mobile
      state.mower.refs.task_list.value = [
        { time: '2026-10-20T11:30:00.000', plan: {}, type: { display_value: '跑单' } }
      ]
      const { find } = mountWorkspace()
      if (mobile) await openViewOptions(find)
      const toggle = viewControl(find, '任务列表')
      const queue = find((target) => target.props.class === 'task-table-scroll')
      toggle.props.onClick()
      await nextTick()
      expect(queue.style.display).toBe('none')

      state.route.hash = '#task-queue'
      await nextTick()
      await nextTick()

      expect(queue.style.display).not.toBe('none')
      expect(toggle.props['aria-pressed']).toBe(true)
      expect(queue.scrollIntoView).toHaveBeenCalledExactlyOnceWith({ block: 'nearest' })
      expect(localStorage.setItem).toHaveBeenCalledExactlyOnceWith('log_show_task_table', 'false')
      expect(state.client.post).not.toHaveBeenCalled()
      expect(state.mower.get_tasks).not.toHaveBeenCalled()
    }
  )
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
    const { find, all } = mountWorkspace()
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
    expect(state.client.get).toHaveBeenCalledWith('/db-admin/stats')
    expect(state.client.get).toHaveBeenCalledWith('/db-admin/maintenance')
    expect(all().some((target) => target.props.label === '新增任务说明')).toBe(false)
  })

  it('refreshes database size after compaction and saves the selected backup limit', async () => {
    const page = scope.run(() => LogPage.setup({}, { expose: vi.fn() }))
    const info = {
      database_bytes: 200 * 1024 * 1024,
      reclaimable_bytes: 199 * 1024 * 1024,
      backup_limit_mib: 16,
      max_backup_limit_mib: 1024,
      busy: false
    }
    state.client.get.mockImplementation(async (url) => ({
      data: url.endsWith('/maintenance') ? info : { log: 10 }
    }))
    await page.db_load_stats()
    expect(page.db_limit.value).toBe(16)
    state.client.post.mockResolvedValueOnce({
      data: {
        ...info,
        database_bytes: 1024 * 1024,
        reclaimable_bytes: 0,
        before_bytes: 200 * 1024 * 1024,
        after_bytes: 1024 * 1024
      }
    })
    await page.db_maintain('compact')
    expect(state.client.post).toHaveBeenCalledExactlyOnceWith(
      '/db-admin/compact',
      {},
      {
        headers: { 'X-Mower-Settings': '1' }
      }
    )
    expect(page.db_maintenance.value.database_bytes).toBe(1024 * 1024)
    expect(page.db_result.value).toContain('200.00 MiB → 1.00 MiB')
    page.db_limit.value = 256
    state.client.put.mockResolvedValueOnce({ data: { ...info, backup_limit_mib: 256 } })
    await page.db_maintain('limit')
    expect(state.client.put).toHaveBeenCalledExactlyOnceWith(
      '/db-admin/backup-limit',
      { backup_limit_mib: 256 },
      { headers: { 'X-Mower-Settings': '1' } }
    )
    expect(page.db_result.value).toContain('256 MiB')
    expect(page.db_busy.value).toBe(false)
  })

  it('shows a maintenance failure and permits an explicit retry without changing the saved limit', async () => {
    const page = scope.run(() => LogPage.setup({}, { expose: vi.fn() }))
    page.db_maintenance.value = { backup_limit_mib: 16 }
    page.db_limit.value = 64
    state.client.put.mockRejectedValueOnce({ response: { data: { message: '请先停止 Mower' } } })
    await page.db_maintain('limit')
    expect(page.db_error.value).toBe('请先停止 Mower')
    expect(page.db_maintenance.value.backup_limit_mib).toBe(16)
    expect(page.db_limit.value).toBe(64)
    expect(page.db_busy.value).toBe(false)
    expect(page.db_result.value).toBe('')
  })

  it.each([false, true])(
    'toggles screenshot preview and log following from desktop controls or mobile options (mobile=%s)',
    async (mobile) => {
      state.mobile.value = mobile
      const { find, all } = mountWorkspace()
      const page = app._instance.setupState
      page.sc_blob = 'blob:preview'
      await nextTick()
      if (mobile) {
        expect(all().some((target) => target.props['aria-label'] === '预览截图')).toBe(false)
        expect(all().some((target) => target.props['aria-label'] === '跟随最新日志')).toBe(false)
        await openViewOptions(find)
      } else {
        expect(all().some((target) => target.props.class === 'view-options-trigger')).toBe(false)
      }
      const preview = find((target) => target.props['aria-label'] === '预览截图')
      const scrolling = viewControl(find, '跟随最新日志')
      const controls = find(
        (target) => target.props.role === 'group' && target.props['aria-label'] === '日志显示选项'
      )
      expect(all(controls)).toContain(preview)
      expect(all(controls)).toContain(scrolling)
      expect(
        all(controls)
          .filter((target) => typeof target.props['aria-pressed'] === 'boolean')
          .map((target) => target.props['aria-label'])
      ).toEqual(['简洁日志', '任务列表', '今日任务', '预览截图', '跟随最新日志'])
      expect(preview.props['aria-pressed']).toBe(true)
      expect(scrolling.props['aria-pressed']).toBe(true)
      expect(all().some((target) => target.props.class === 'log-screenshot')).toBe(true)

      preview.props.onClick()
      await nextTick()
      expect(preview.props['aria-pressed']).toBe(false)
      expect(preview.props.title).toBe('显示截图预览')
      expect(state.preview.stop).toHaveBeenCalledOnce()
      expect(localStorage.setItem).toHaveBeenLastCalledWith('sc_preview', 'false')
      expect(all().some((target) => target.props.class === 'log-screenshot')).toBe(false)
      expect(scrolling.props['aria-pressed']).toBe(true)

      const output = find((target) => target.props['data-log-content'])
      expect(output.props.autoScroll).toBe(true)
      scrolling.props.onClick()
      await nextTick()
      expect(scrolling.props['aria-pressed']).toBe(false)
      expect(output.props.autoScroll).toBe(false)
      state.mower.refs.log_lines.value = ['line while following is disabled']
      await nextTick()
      expect(document.querySelector).not.toHaveBeenCalledWith('.log .n-scrollbar-container')

      preview.props.onClick()
      scrolling.props.onClick()
      await nextTick()
      state.mower.refs.log_lines.value = ['line while following is enabled']
      await nextTick()
      expect(output.props.autoScroll).toBe(true)
      expect(output.props.lines).toEqual(['line while following is enabled'])
      expect(document.querySelector).not.toHaveBeenCalledWith('.log .n-scrollbar-container')
      expect(preview.props['aria-pressed']).toBe(true)
      expect(scrolling.props['aria-pressed']).toBe(true)
      expect(state.preview.start).toHaveBeenCalledOnce()
      expect(localStorage.setItem).toHaveBeenLastCalledWith('sc_preview', 'true')
      expect(all().some((target) => target.props.class === 'log-screenshot')).toBe(true)
      expect(state.client.post).not.toHaveBeenCalled()
    }
  )

  it.each([false, true])(
    'restores and switches the log display mode (mobile=%s)',
    async (mobile) => {
      state.mobile.value = mobile
      localStorage.getItem.mockImplementation((key) =>
        key === 'log_detail_mode' ? 'concise' : null
      )
      const { find } = mountWorkspace()
      if (mobile) await openViewOptions(find)
      const toggle = find((entry) => entry.props['aria-label'] === '简洁日志')
      const output = find((entry) => entry.props['data-log-content'])
      expect(toggle.props['aria-pressed']).toBe(true)
      expect(output.props.concise).toBe(true)

      toggle.props.onClick()
      await nextTick()
      expect(toggle.props['aria-pressed']).toBe(false)
      expect(output.props.concise).toBe(false)
      expect(output.props.compact).toBe(mobile)
      expect(localStorage.setItem).toHaveBeenCalledWith('log_detail_mode', 'detailed')
      expect(state.client.post).not.toHaveBeenCalled()
    }
  )

  it.each(['touchend', 'mouseup'])(
    'dismisses mobile view options on %s and consumes only the closing touch',
    async (type) => {
      state.mobile.value = true
      const { find, all } = mountWorkspace()
      const trigger = await openViewOptions(find)
      const outside = find((target) => typeof target.props.onClickoutside === 'function')
      const event = { type, preventDefault: vi.fn() }
      outside.props.onClickoutside(event)
      await nextTick()
      expect(trigger.props['aria-expanded']).toBe(false)
      expect(all().some((target) => target.props.class === 'log-view-actions')).toBe(false)
      expect(event.preventDefault).toHaveBeenCalledTimes(type === 'touchend' ? 1 : 0)
    }
  )

  it('keeps narrow database access direct, then restores the wide label', async () => {
    state.mobile.value = true
    const { find, all } = mountWorkspace()
    const page = app._instance.setupState
    const database = find((target) => target.props.class === 'database-action')
    expect(database.props['aria-label']).toBe('数据库管理')
    expect(database.props.title).toBe('数据库管理')
    expect(all(database).some((target) => target.text === '数据库管理')).toBe(false)
    expect(all().some((target) => target.props.label === '新增任务说明')).toBe(false)
    expect(all().some((target) => target.props.class === 'display-options-trigger')).toBe(false)
    await openViewOptions(find)
    expect(page.show_view_controls).toBe(true)

    state.client.get.mockResolvedValueOnce({ data: {} })
    database.props.onClick()
    await nextTick()
    expect(page.show_db_admin).toBe(true)
    expect(page.show_view_controls).toBe(false)
    expect(
      all().some(
        (target) => target.props.role === 'dialog' && target.props['aria-label'] === '日志显示选项'
      )
    ).toBe(false)
    expect(state.client.get).toHaveBeenCalledWith('/db-admin/stats')
    expect(state.client.get).toHaveBeenCalledWith('/db-admin/maintenance')
    expect(state.client.post).not.toHaveBeenCalled()

    page.show_db_admin = false
    await openViewOptions(find)
    expect(page.show_view_controls).toBe(true)
    state.mobile.value = false
    await nextTick()
    expect(page.show_view_controls).toBe(false)
    expect(
      all().some(
        (target) => target.props.role === 'dialog' && target.props['aria-label'] === '日志显示选项'
      )
    ).toBe(false)
    expect(find((target) => target.props.class === 'database-action')).toBe(database)
    expect(all(database).some((target) => target.text === '数据库管理')).toBe(true)
    expect(all().some((target) => target.props.label === '新增任务说明')).toBe(false)
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

  it('replaces the Stop button with cancellation and keeps immediate Stop in the menu', async () => {
    state.mower.refs.running.value = true
    state.mower.refs.maintenance_pause.value = {
      id: 'current-window',
      end: '2026-10-26T18:00:00+08:00'
    }
    let resolveCancel
    state.mower.cancel_maintenance_pause.mockImplementation(
      () => new Promise((resolve) => (resolveCancel = resolve))
    )
    const { find, all } = mountWorkspace()
    const page = app._instance.setupState
    expect(all().some((node) => node.text.includes('计划暂停中'))).toBe(true)
    const button = find((node) => node.props.onClick === page.cancel_pause)
    expect(all().filter((node) => node.props.onClick === page.cancel_pause)).toHaveLength(1)
    expect(all().some((node) => node.props.onClick === page.stop)).toBe(false)
    expect(page.stop_options.find((option) => option.key === 'immediate').label).toBe('立即停止')
    const request = button.props.onClick()
    await nextTick()
    await page.cancel_pause()
    expect(state.mower.cancel_maintenance_pause).toHaveBeenCalledExactlyOnceWith('current-window')
    expect(button.props.disabled).toBe(true)
    expect(page.stop_options.find((option) => option.key === 'immediate').disabled).toBe(false)
    resolveCancel()
    await request
    state.mower.refs.maintenance_pause.value = null
    await nextTick()
    expect(all().some((node) => node.text.includes('计划暂停中'))).toBe(false)
    expect(find((node) => node.props.onClick === page.stop).props.disabled).toBe(false)
    expect(page.stop_options.some((option) => option.key === 'immediate')).toBe(false)
  })

  it('keeps the flash pause visible and reports a failed cancellation', async () => {
    state.mower.refs.running.value = true
    state.mower.refs.maintenance_pause.value = {
      id: 'current-window',
      end: '2026-10-26T18:00:00+08:00'
    }
    state.mower.cancel_maintenance_pause.mockRejectedValueOnce({
      response: { data: { error: '无法取消' } }
    })
    const page = scope.run(() => LogPage.setup({}, { expose: vi.fn() }))
    await page.cancel_pause()
    expect(state.error).toHaveBeenCalledWith('无法取消')
    expect(state.mower.refs.maintenance_pause.value.id).toBe('current-window')
    expect(page.cancelling_pause.value).toBe(false)
  })

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
      canApplySchedule: true,
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

  it('allows applying a plan when desktop process control is unavailable', async () => {
    state.mower.refs.running.value = true
    const component = scope.run(() => LogPage.setup({}, { expose: vi.fn() }))
    const applySchedule = vi.fn()
    component.process_control.value = {
      canApplySchedule: true,
      canRunProcessAction: false,
      applySchedule
    }
    await nextTick()
    expect(
      component.stop_options.value.find((option) => option.key === 'apply_schedule').disabled
    ).toBe(false)
    expect(
      component.stop_options.value.find((option) => option.key === 'restart_resume').disabled
    ).toBe(true)
    component.select_stop_action('apply_schedule')
    expect(applySchedule).toHaveBeenCalledOnce()
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
          return { getBoundingClientRect: () => ({ top: 258 + conditionHeight }) }
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
    // 620 高的日志区给日志留 207（三分之一），再扣分隔条和 40 高的副表说明。
    expect(setProperty.mock.calls.at(-1)).toEqual(['--log-task-h', '107px'])
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
    expect(sizes.get('--log-min-h')).toBe('300px')
    expect(screenshotHeight).toBe(494)
    expect(taskHeight).toBe(90)
    expect(screenshotHeight + 8 + taskHeight + 8 + 300).toBeLessThanOrEqual(900)
  })

  it('stops the stacked screenshot row at the frame height and gives the rest to the task table', () => {
    const sizes = new Map()
    const container = {
      clientWidth: 866,
      getBoundingClientRect: () => ({ top: 100, bottom: 1000, height: 900 }),
      querySelector: (selector) => {
        if (selector === '.log-screenshot') {
          return { clientWidth: 480, getBoundingClientRect: () => ({ top: 100 }) }
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

    expect(sizes.get('--log-sc-h')).toBe('270px')
    expect(sizes.get('--log-task-h')).toBe('314px')
    expect(component.layout_preference.screenshot_height).toBe(500)
  })

  it.each([
    { mobile: false, width: 1000, imageWidth: 480, shot: 90 },
    { mobile: true, width: 366, imageWidth: 360, shot: 640 }
  ])('retains the panels in a short explicit single layout (mobile=$mobile)', (fixture) => {
    const { mobile, width, imageWidth, shot } = fixture
    state.mobile.value = mobile
    useGuiStore().runningLogLayout = 'custom:single:log,daily,tasks,screenshot'
    const sizes = new Map()
    const component = scope.run(() => LogPage.setup({}, { expose: vi.fn() }))
    component.sc_blob.value = 'blob:preview'
    component.layout_preference.task_height = 132
    component.log_layout.value = {
      clientWidth: width,
      getBoundingClientRect: () => ({ top: 0, bottom: 250, height: 250 }),
      querySelector: (selector) => {
        if (selector === '.log-screenshot') return { clientWidth: imageWidth }
        if (selector === '.log-daily-module')
          return { getBoundingClientRect: () => ({ height: 64 }) }
        if (selector === '.task-table-scroll')
          return { getBoundingClientRect: () => ({ top: 184 }) }
        return null
      },
      style: { setProperty: (key, value) => sizes.set(key, value), removeProperty: vi.fn() }
    }
    component.screenshot_aspect = mobile ? 360 / 640 : 16 / 9
    component.apply_log_layout()
    expect(sizes.get('--log-sc-h')).toBe(`${shot}px`)
    expect(sizes.get('--log-task-h')).toBe('90px')
    expect(sizes.get('--log-min-h')).toBe('120px')
  })

  it('retains the saved task height below the log when the other column has no screenshot', async () => {
    useGuiStore().runningLogLayout = 'custom:split:log,tasks,daily|screenshot'
    state.mower.refs.task_list.value = [{ time: '2026-11-01T14:20:00', plan: {}, type: '跑单' }]
    const { classes, find, page, pane, sizes } = mountWidePane()
    const queue = find((target) => target.props.class === 'task-table-scroll')
    pane.getBoundingClientRect = () => ({ top: 0, bottom: 600, height: 600 })
    pane.querySelector = (selector) => (selector === '.task-table-scroll' ? queue : null)
    queue.getBoundingClientRect = () => ({ top: 460 })
    page.layout_preference.task_height = 132
    page.apply_log_layout()
    await nextTick()

    expect(classes(pane)).not.toContain('log-pane--rail')
    expect(sizes()['--log-task-h']).toBe('132px')
  })

  it.each([1, 0.8, 1.25])(
    'saves the screenshot drag height in layout pixels at zoom %s',
    (zoom) => {
      const setProperty = vi.fn()
      const listeners = new Map()
      document.addEventListener.mockImplementation((name, handler) => listeners.set(name, handler))
      state.client.post.mockResolvedValue({})
      const container = {
        ownerDocument: { documentElement: { style: { zoom } } },
        getBoundingClientRect: () => ({ top: 80 * zoom, bottom: 1080 * zoom, height: 1000 * zoom }),
        querySelector: (selector) => {
          if (selector === '.log-screenshot') {
            return { getBoundingClientRect: () => ({ top: 320 * zoom }) }
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
      listeners.get('pointermove')({ clientY: 510 * zoom })
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
    }
  )

  it('applies the stacked log height constraints and saves task dragging at 80% zoom', () => {
    const sizes = new Map()
    const listeners = new Map()
    document.addEventListener.mockImplementation((name, handler) => listeners.set(name, handler))
    state.client.post.mockResolvedValue({})
    const component = scope.run(() => LogPage.setup({}, { expose: vi.fn() }))
    component.log_layout.value = {
      ownerDocument: { documentElement: { style: { zoom: 0.8 } } },
      clientWidth: 800,
      getBoundingClientRect: () => ({ top: 0, bottom: 576, height: 576 }),
      querySelector: (selector) =>
        selector === '.task-table-scroll' ? { getBoundingClientRect: () => ({ top: 80 }) } : null,
      style: { setProperty: (key, value) => sizes.set(key, value), removeProperty: vi.fn() }
    }
    component.layout_preference.task_height = 600
    component.apply_log_layout()

    expect(sizes.get('--log-min-h')).toBe('240px')
    expect(sizes.get('--log-task-h')).toBe('372px')

    component.resize_log_pane({ preventDefault: vi.fn() }, 'task')
    listeners.get('pointermove')({ clientY: 280 })
    listeners.get('pointerup')()

    expect(sizes.get('--log-task-h')).toBe('250px')
    expect(state.client.post).toHaveBeenCalledExactlyOnceWith('/ui-state/log-layout', {
      task_height: 250
    })
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
    expect(setProperty).toHaveBeenCalledWith('--log-task-h', '35px')
    // 620 高的日志区给日志留 207（三分之一）和一条分隔条。
    expect(35 + 207 + 8).toBeLessThanOrEqual(620 - 370)
    expect(component.layout_preference.task_height).toBe(600)
    expect(state.client.post).not.toHaveBeenCalled()
  })

  it.each([
    ['screenshot', 'pointercancel'],
    ['task', 'pointercancel'],
    ['rail', 'pointercancel'],
    ['screenshot', 'unmount'],
    ['task', 'unmount'],
    ['rail', 'unmount']
  ])('ends %s dragging after %s without saving or changing detached layout', (pane, ending) => {
    const setProperty = vi.fn()
    state.client.post.mockResolvedValue({})
    const component = scope.run(() => LogPage.setup({}, { expose: vi.fn() }))
    component.log_layout.value = {
      clientWidth: 1290,
      getBoundingClientRect: () => ({ top: 0, bottom: 800, height: 800, width: 1290, right: 1290 }),
      querySelector: (selector) =>
        ['.log-screenshot', '.task-table-scroll'].includes(selector)
          ? { getBoundingClientRect: () => ({ top: 0 }) }
          : null,
      style: { setProperty, removeProperty: vi.fn() }
    }
    const pointer = (type, x, y) =>
      document.dispatchEvent(Object.assign(new Event(type), { clientX: x, clientY: y }))
    if (pane === 'rail') component.resize_rail_column({ preventDefault: vi.fn() })
    else component.resize_log_pane({ preventDefault: vi.fn() }, pane)
    pointer('pointermove', 800, 180)
    expect(setProperty).toHaveBeenCalled()
    setProperty.mockClear()

    if (ending === 'unmount') onUnmounted.mock.lastCall[0]()
    else pointer('pointercancel')
    pointer('pointermove', 700, 240)
    pointer('pointerup')

    expect(setProperty).not.toHaveBeenCalled()
    expect(state.client.post).not.toHaveBeenCalled()
  })

  it.each([false, true])(
    'hides the queue, backup banner and resizer without losing the queue or layout (mobile=%s)',
    async (mobile) => {
      state.mobile.value = mobile
      state.mower.refs.plan_condition.value = ['副表一']
      const task = { time: '2026-10-20T11:30:00.000', plan: {}, type: { display_value: '跑单' } }
      state.mower.refs.task_list.value = [task]
      const { find, all, pane, page, classes } = mountWidePane(mobile ? 390 : 800)
      if (mobile) await openViewOptions(find)
      const toggle = viewControl(find, '任务列表')
      const daily = viewControl(find, '今日任务')
      const queue = find((target) => target.props.class === 'task-table-scroll')
      const resizer = find((target) => target.props.class === 'log-resizer log-resizer-task')
      const log = find((target) => target.props['data-log-content'])
      page.layout_preference.task_height = 132
      expect(toggle.props['aria-pressed']).toBe(true)
      expect(toggle.props['aria-controls']).toBe(queue.props.id)
      expect(queue.props.id).toBeTruthy()

      toggle.props.onClick()
      await nextTick()
      expect(toggle.props['aria-pressed']).toBe(false)
      expect(toggle.props.title).toBe('显示任务列表')
      expect(queue.style.display).toBe('none')
      expect(resizer.style.display).toBe('none')
      expect(classes(pane)).not.toContain('has-tasks')
      expect(all().some((target) => target.props.class === 'plan-condition')).toBe(false)
      expect(find((target) => target.props['data-log-content'])).toBe(log)
      expect(daily.props['aria-pressed']).toBe(true)
      expect(localStorage.setItem).toHaveBeenLastCalledWith('log_show_task_table', 'false')
      expect(state.mower.refs.task_list.value).toEqual([task])

      toggle.props.onClick()
      await nextTick()
      expect(toggle.props['aria-pressed']).toBe(true)
      expect(queue.style.display).not.toBe('none')
      expect(resizer.style.display).not.toBe('none')
      expect(classes(pane)).toContain('has-tasks')
      expect(find((target) => target.props.class === 'plan-condition')).toBeTruthy()
      expect(page.layout_preference.task_height).toBe(132)
      expect(localStorage.setItem).toHaveBeenLastCalledWith('log_show_task_table', 'true')
      expect(state.client.get).not.toHaveBeenCalled()
      expect(state.client.post).not.toHaveBeenCalled()

      state.mower.refs.task_list.value = []
      await nextTick()
      expect(viewControl(find, '任务列表')).toBe(toggle)
    }
  )

  function deferViewTransitions({ holdAnimation = false } = {}) {
    vi.stubGlobal('CSS', { supports: () => true })
    const skipTransition = vi.fn()
    const callbacks = []
    const finishAnimations = []
    document.startViewTransition = vi.fn(({ update }) => {
      const completion = Promise.withResolvers()
      const animation = holdAnimation ? Promise.withResolvers() : completion
      callbacks.push(async () => {
        await update()
        completion.resolve()
      })
      finishAnimations.push(animation.resolve)
      return {
        ready: Promise.resolve(),
        updateCallbackDone: completion.promise,
        finished: animation.promise,
        skipTransition
      }
    })
    return { callbacks, finishAnimations, skipTransition }
  }

  it('applies document-wide log changes directly while the assistant is visible', async () => {
    state.mower.refs.task_list.value = [{ time: '2026-10-20T11:30:00.000', plan: {}, type: '跑单' }]
    const { callbacks } = deferViewTransitions()
    state.chatPanelVisible.value = true
    const { find } = mountWidePane()
    const task = viewControl(find, '任务列表')
    task.props.onClick()
    await nextTick()
    expect(task.props['aria-pressed']).toBe(false)
    expect(localStorage.setItem).toHaveBeenLastCalledWith('log_show_task_table', 'false')
    expect(document.startViewTransition).not.toHaveBeenCalled()

    state.chatPanelVisible.value = false
    task.props.onClick()
    expect(document.startViewTransition).toHaveBeenCalledOnce()
    await callbacks[0]()
    expect(task.props['aria-pressed']).toBe(true)
  })

  it('finishes a document transition and applies queued selections when opening the assistant', async () => {
    state.mower.refs.task_list.value = [{ time: '2026-10-20T11:30:00.000', plan: {}, type: '跑单' }]
    const { callbacks, finishAnimations, skipTransition } = deferViewTransitions({
      holdAnimation: true
    })
    const { find, page } = mountWidePane()
    page.sc_blob = 'blob:initial-frame'
    page.apply_log_layout()
    await nextTick()
    const screenshot = viewControl(find, '预览截图')
    const task = viewControl(find, '任务列表')
    screenshot.props.onClick()
    await callbacks[0]()
    task.props.onClick()
    expect(callbacks).toHaveLength(1)

    state.chatPanelVisible.value = true
    expect(skipTransition).toHaveBeenCalledOnce()
    await nextTick()
    expect(screenshot.props['aria-pressed']).toBe(false)
    expect(task.props['aria-pressed']).toBe(false)
    expect(localStorage.setItem).toHaveBeenLastCalledWith('log_show_task_table', 'false')
    expect(document.startViewTransition).toHaveBeenCalledOnce()
    finishAnimations[0]()
    await nextTick()
    expect(document.startViewTransition).toHaveBeenCalledOnce()
    expect(state.client.post).not.toHaveBeenCalled()
  })

  it.each([
    [false, ['mower-log', 'mower-log-layout', 'mower-log-rail']],
    [true, ['mower-log']]
  ])(
    'uses the selected motion for task and screenshot controls (reduced=%s)',
    async (reduced, types) => {
      vi.stubGlobal('matchMedia', () => ({ matches: reduced }))
      state.realPreview = true
      state.mower.refs.task_list.value = [
        { time: '2026-10-20T11:30:00.000', plan: {}, type: '跑单' }
      ]
      localStorage.getItem.mockImplementation((key) => (key === 'sc_preview' ? 'false' : null))
      const decoding = Promise.withResolvers()
      vi.stubGlobal(
        'Image',
        class {
          naturalWidth = 4
          naturalHeight = 3
          decode() {
            return decoding.promise
          }
        }
      )
      state.client.get.mockImplementation(async (url) =>
        url.endsWith('/screenshot/latest')
          ? { status: 200, data: new Blob(['frame']), headers: {} }
          : { data: {} }
      )
      const { callbacks } = deferViewTransitions()
      const { find, page } = mountWidePane()
      onMounted.mock.lastCall[0]()

      const closingTypes = reduced ? types : [...types, 'mower-log-collapse']
      const task = viewControl(find, '任务列表')
      task.props.onClick()
      expect(document.startViewTransition).toHaveBeenLastCalledWith({
        update: expect.any(Function),
        types: closingTypes
      })
      await callbacks[0]()
      expect(task.props['aria-pressed']).toBe(false)

      const screenshot = viewControl(find, '预览截图')
      screenshot.props.onClick()
      await vi.advanceTimersByTimeAsync(0)
      expect(document.startViewTransition).toHaveBeenCalledTimes(1)
      expect(page.sc_blob).toBe('')
      decoding.resolve()
      await vi.advanceTimersByTimeAsync(0)
      expect(document.startViewTransition).toHaveBeenLastCalledWith({
        update: expect.any(Function),
        types
      })
      await callbacks[1]()
      expect(page.sc_blob).toMatch(/^blob:/)

      screenshot.props.onClick()
      expect(document.startViewTransition).toHaveBeenCalledTimes(3)
      expect(document.startViewTransition).toHaveBeenLastCalledWith({
        update: expect.any(Function),
        types: closingTypes
      })
      await callbacks[2]()
      expect(page.sc_blob).toBe('')

      screenshot.props.onClick()
      setHidden(true)
      setHidden(false)
      await vi.advanceTimersByTimeAsync(0)
      expect(page.sc_blob).toMatch(/^blob:/)
      expect(document.startViewTransition).toHaveBeenCalledTimes(3)
      onUnmounted.mock.lastCall[0]()
    }
  )

  it('settles rapid task toggles after the visible transition without skipping its animation', async () => {
    state.mower.refs.task_list.value = [{ time: '2026-10-20T11:30:00.000', plan: {}, type: '跑单' }]
    const { callbacks, finishAnimations, skipTransition } = deferViewTransitions({
      holdAnimation: true
    })
    const { find, page } = mountWidePane()
    page.apply_log_layout()
    await nextTick()
    const toggle = viewControl(find, '任务列表')
    const queue = find((target) => target.props.class === 'task-table-scroll')

    toggle.props.onClick()
    toggle.props.onClick()
    toggle.props.onClick()
    expect(callbacks).toHaveLength(1)
    expect(skipTransition).not.toHaveBeenCalled()
    await callbacks[0]()
    expect(queue.style.display).toBe('none')
    expect(toggle.props['aria-pressed']).toBe(false)
    expect(localStorage.setItem).toHaveBeenCalledExactlyOnceWith('log_show_task_table', 'false')

    toggle.props.onClick()
    expect(callbacks).toHaveLength(1)
    expect(skipTransition).not.toHaveBeenCalled()
    expect(queue.style.display).toBe('none')
    finishAnimations[0]()
    await nextTick()
    expect(callbacks).toHaveLength(2)
    expect(queue.style.display).toBe('none')
    await callbacks[1]()
    expect(queue.style.display).not.toBe('none')
    expect(toggle.props['aria-pressed']).toBe(true)
    expect(localStorage.setItem).toHaveBeenLastCalledWith('log_show_task_table', 'true')

    toggle.props.onClick()
    expect(callbacks).toHaveLength(2)
    onBeforeUnmount.mock.lastCall[0]()
    expect(localStorage.setItem).toHaveBeenLastCalledWith('log_show_task_table', 'false')
    expect(skipTransition).toHaveBeenCalledOnce()
    finishAnimations[1]()
    await nextTick()
    expect(callbacks).toHaveLength(2)
  })

  it('retains the queued task change when two screenshot clicks cancel each other', async () => {
    state.mower.refs.task_list.value = [{ time: '2026-10-20T11:30:00.000', plan: {}, type: '跑单' }]
    const { callbacks, finishAnimations, skipTransition } = deferViewTransitions({
      holdAnimation: true
    })
    const { find, page } = mountWidePane()
    page.sc_blob = 'blob:initial-frame'
    page.apply_log_layout()
    await nextTick()
    const screenshot = viewControl(find, '预览截图')
    const task = viewControl(find, '任务列表')
    const queue = find((target) => target.props.class === 'task-table-scroll')

    screenshot.props.onClick()
    await callbacks[0]()
    expect(screenshot.props['aria-pressed']).toBe(false)
    task.props.onClick()
    screenshot.props.onClick()
    screenshot.props.onClick()
    expect(callbacks).toHaveLength(1)
    expect(queue.style.display).not.toBe('none')

    finishAnimations[0]()
    await nextTick()
    expect(callbacks).toHaveLength(2)
    await callbacks[1]()
    expect(queue.style.display).toBe('none')
    expect(screenshot.props['aria-pressed']).toBe(false)
    expect(localStorage.setItem).toHaveBeenLastCalledWith('log_show_task_table', 'false')

    finishAnimations[1]()
    await nextTick()
    expect(callbacks).toHaveLength(2)
    expect(skipTransition).not.toHaveBeenCalled()
    expect(screenshot.props['aria-pressed']).toBe(false)
    expect(state.preview.start).not.toHaveBeenCalled()
  })

  it('discards a queued first screenshot when the preview is turned off before it appears', async () => {
    state.mower.refs.task_list.value = [{ time: '2026-10-20T11:30:00.000', plan: {}, type: '跑单' }]
    const { callbacks, finishAnimations, skipTransition } = deferViewTransitions({
      holdAnimation: true
    })
    const { find, page } = mountWidePane()
    const screenshot = viewControl(find, '预览截图')
    const task = viewControl(find, '任务列表')

    task.props.onClick()
    await callbacks[0]()
    state.previewOptions.onChange('blob:queued-frame')
    expect(page.sc_blob).toBe('')
    screenshot.props.onClick()

    finishAnimations[0]()
    await vi.advanceTimersByTimeAsync(0)
    expect(callbacks).toHaveLength(1)
    expect(skipTransition).not.toHaveBeenCalled()
    expect(screenshot.props['aria-pressed']).toBe(false)
    expect(page.sc_blob).toBe('')
    expect(state.preview.stop).toHaveBeenCalledOnce()
  })

  it('reveals the linked task list after a pending hide without changing the saved preference', async () => {
    state.mower.refs.task_list.value = [{ time: '2026-10-20T11:30:00.000', plan: {}, type: '跑单' }]
    const { callbacks } = deferViewTransitions()
    const { find } = mountWidePane()
    const toggle = viewControl(find, '任务列表')
    const queue = find((target) => target.props.class === 'task-table-scroll')

    toggle.props.onClick()
    state.route.hash = '#task-queue'
    await nextTick()
    await callbacks[0]()
    await nextTick()

    expect(queue.style.display).not.toBe('none')
    expect(toggle.props['aria-pressed']).toBe(true)
    expect(queue.scrollIntoView).toHaveBeenCalledExactlyOnceWith({ block: 'nearest' })
    expect(localStorage.setItem).toHaveBeenCalledExactlyOnceWith('log_show_task_table', 'false')
  })

  it.each([
    ['log_show_task_table', false, true],
    ['log_show_daily_tasks', true, false]
  ])(
    'restores the saved %s setting independently across desktop and mobile',
    async (hiddenKey, taskVisible, dailyVisible) => {
      localStorage.getItem.mockImplementation((key) => (key === hiddenKey ? 'false' : null))
      state.mower.refs.task_list.value = [
        { time: '2026-10-20T11:30:00.000', plan: {}, type: { display_value: '跑单' } }
      ]
      const { find, all } = mountWorkspace()
      const queue = find((target) => target.props.class === 'task-table-scroll')
      const expectVisibility = () => {
        expect(queue.style.display !== 'none').toBe(taskVisible)
        expect(viewControl(find, '任务列表').props['aria-pressed']).toBe(taskVisible)
        expect(viewControl(find, '今日任务').props['aria-pressed']).toBe(dailyVisible)
      }
      expectVisibility()

      state.mobile.value = true
      await nextTick()
      await openViewOptions(find)
      expectVisibility()

      state.mobile.value = false
      await nextTick()
      expect(all().some((target) => target.props.class === 'log-view-actions')).toBe(false)
      expectVisibility()
      expect(localStorage.setItem).not.toHaveBeenCalled()
    }
  )

  function mountWidePane(width = 1290) {
    const workspace = mountWorkspace()
    const pane = workspace.find((target) => target.props['aria-label'] === '运行日志')
    pane.clientWidth = width
    pane.getBoundingClientRect = () => ({ top: 0, bottom: 800, height: 800 })
    const sizes = () => Object.fromEntries(pane.style.setProperty.mock.calls)
    const classes = (target) => (target.props.class ?? '').split(' ')
    return { ...workspace, page: app._instance.setupState, pane, sizes, classes }
  }

  it.each([
    { width: 1290, mobile: false, rail: true },
    { width: 800, mobile: false, rail: false },
    { width: 390, mobile: true, rail: false }
  ])('places the active backup above the queue at $width px', async ({ width, mobile, rail }) => {
    state.mobile.value = mobile
    state.mower.refs.plan_condition.value = ['副表一']
    state.mower.refs.task_list.value = [{ time: '2026-10-31T14:20:00', plan: {}, type: '跑单' }]
    const { find, page, pane, classes } = mountWidePane(width)
    page.sc_blob = 'blob:http://latest'
    page.apply_log_layout()
    await nextTick()

    expect(classes(pane).includes('log-pane--rail')).toBe(rail)
    const screenshot = find((target) => target.props.src === 'blob:http://latest')
    const condition = find((target) => target.props.class === 'plan-condition')
    const queue = find((target) => target.props.class === 'task-table-scroll')
    const column = condition.parent
    expect(column.parent).toBe(pane)
    expect(screenshot.parent).toBe(column)
    expect(queue.parent).toBe(column)
    expect(column.children.indexOf(screenshot)).toBeLessThan(column.children.indexOf(condition))
    expect(column.children.indexOf(condition)).toBeLessThan(column.children.indexOf(queue))
  })

  it('places the screenshot above the task list in a right column on a wide desktop pane', async () => {
    state.mower.refs.task_list.value = [
      {
        time: '2026-10-31T14:20:00.000',
        plan: { room_1_1: ['阿米娅'] },
        type: { display_value: '换班' }
      }
    ]
    const { find, page, pane, sizes, classes } = mountWidePane()
    page.sc_blob = 'blob:http://latest'
    await nextTick()
    page.apply_log_layout()
    await nextTick()

    expect(classes(pane)).toContain('log-pane--rail')
    expect(classes(pane.parent)).toContain('home-container--rail')
    const queue = find((target) => target.props.class === 'task-table-scroll')
    const columns = pane.children.filter((target) => classes(target).includes('log-column'))
    expect(queue.parent).toBe(columns[1])
    expect(find((target) => target.props['data-log-content']).parent).toBe(columns[0])
    expect(sizes()['--log-rail-w']).toBe('480px')
    expect(sizes()['--log-sc-h']).toBe('270px')
    expect(pane.style.removeProperty).toHaveBeenCalledWith('--log-task-h')

    await publishScreenshot('blob:http://next', 4 / 3)
    expect(sizes()['--log-rail-w']).toBe('360px')
    expect(sizes()['--log-sc-h']).toBe('270px')

    pane.clientWidth = 880
    page.apply_log_layout()
    await nextTick()
    expect(classes(pane)).not.toContain('log-pane--rail')
    expect(classes(pane.parent)).not.toContain('home-container--rail')
    expect(pane.style.removeProperty).toHaveBeenCalledWith('--log-rail-w')
    expect(state.client.post).not.toHaveBeenCalled()
  })

  it('moves real panels into the saved order and retains the log across rearrangement', async () => {
    vi.setSystemTime(new Date('2026-11-01T05:00:00Z'))
    state.mower.refs.running.value = true
    state.config.report_enable = true
    state.mower.refs.task_list.value = [{ time: '2026-11-01T14:20:00', plan: {}, type: '跑单' }]
    mockDailyStatus(() => ({
      game_day: '2026-11-01',
      source: 'live',
      records: { report: 'done' }
    }))
    const gui = useGuiStore()
    const { pane, page, classes, find, all } = mountWidePane()
    const log = find((target) => target.props['data-log-content'])
    const panelOrder = () =>
      pane.children
        .filter(
          (target) => classes(target).includes('log-column') && target.style.display !== 'none'
        )
        .map((column) =>
          column.children.flatMap((target) =>
            classes(target).filter((name) =>
              ['log', 'log-screenshot', 'task-table-scroll', 'log-daily-module'].includes(name)
            )
          )
        )
    page.sc_blob = 'blob:preview'
    page.apply_log_layout()
    await vi.advanceTimersByTimeAsync(0)
    expect(panelOrder()).toEqual([['log'], ['log-screenshot', 'task-table-scroll']])
    expect(all(log).some((target) => classes(target).includes('daily-status'))).toBe(true)

    gui.runningLogLayout = 'custom:split:tasks,screenshot|log,daily'
    await nextTick()
    expect(panelOrder()).toEqual([
      ['task-table-scroll', 'log-screenshot'],
      ['log', 'log-daily-module']
    ])
    expect(find((target) => target.props['data-log-content'])).toBe(log)

    gui.runningLogLayout = 'right_rail_log'
    await nextTick()
    expect(panelOrder()).toEqual([
      ['log-daily-module', 'task-table-scroll'],
      ['log-screenshot', 'log']
    ])
    expect(find((target) => target.props['data-log-content'])).toBe(log)

    state.mobile.value = true
    await nextTick()
    expect(panelOrder()).toEqual([['log-screenshot', 'task-table-scroll', 'log']])
    expect(find((target) => classes(target).includes('log-daily-toggle'))).toBeTruthy()

    gui.runningLogLayout = 'custom:single:log,daily,tasks,screenshot'
    await vi.advanceTimersByTimeAsync(0)
    expect(panelOrder()).toEqual([
      ['log', 'log-daily-module', 'task-table-scroll', 'log-screenshot']
    ])
    expect(all().some((target) => classes(target).includes('log-daily-toggle'))).toBe(false)
    expect(find((target) => target.props['data-log-content'])).toBe(log)
  })

  it('reveals the task queue through its hash after moving it into the log column', async () => {
    state.mower.refs.task_list.value = [{ time: '2026-11-01T14:20:00', plan: {}, type: '跑单' }]
    const { find, page } = mountWidePane()
    page.sc_blob = 'blob:preview'
    page.apply_log_layout()
    await nextTick()
    const original = find((target) => target.props.class === 'task-table-scroll')

    useGuiStore().runningLogLayout = 'custom:split:tasks,daily,log|screenshot'
    await nextTick()
    const queue = find((target) => target.props.class === 'task-table-scroll')
    expect(queue).not.toBe(original)

    state.route.hash = '#task-queue'
    await nextTick()
    await nextTick()
    expect(queue.scrollIntoView).toHaveBeenCalledExactlyOnceWith({ block: 'nearest' })
    expect(original.scrollIntoView).not.toHaveBeenCalled()
  })

  it.each([false, true])(
    'keeps the resized right-column screenshot with pending restore %s',
    async (pending) => {
      const { page, pane, sizes } = mountWidePane()
      pane.querySelector = (selector) =>
        selector === '.log-screenshot' ? { getBoundingClientRect: () => ({ top: 0 }) } : null
      page.sc_blob = 'blob:http://latest'
      await nextTick()
      page.apply_log_layout()
      await nextTick()
      const listeners = new Map()
      document.addEventListener.mockImplementation((name, handler) => listeners.set(name, handler))
      state.client.post.mockResolvedValue({})
      let restoreLayout
      let resolveLayout
      if (pending) {
        state.client.get.mockImplementationOnce(
          () => new Promise((resolve) => (resolveLayout = resolve))
        )
        restoreLayout = page.restore_log_layout()
      }

      page.resize_log_pane({ preventDefault: vi.fn() }, 'screenshot')
      listeners.get('pointermove')({ clientY: 360 })
      listeners.get('pointerup')()

      if (pending) {
        resolveLayout({ data: { rail_width: 360, task_height: 100 } })
        await restoreLayout
        expect(page.layout_preference.task_height).toBe(100)
      }
      expect(sizes()['--log-rail-w']).toBe('640px')
      expect(sizes()['--log-sc-h']).toBe('360px')
      expect(page.layout_preference.screenshot_height).toBe(360)
      expect(state.client.post).toHaveBeenCalledExactlyOnceWith('/ui-state/log-layout', {
        screenshot_height: 360,
        ...(pending ? { rail_width: 640 } : {})
      })
    }
  )

  it.each([
    { pending: false, zoom: 1 },
    { pending: true, zoom: 1 },
    { pending: false, zoom: 0.9 }
  ])(
    'saves the new right-column width at zoom $zoom with pending restore $pending',
    async ({ pending, zoom }) => {
      const { page, pane, sizes } = mountWidePane()
      pane.getBoundingClientRect = () => ({
        top: 0,
        bottom: 800,
        height: 800,
        width: 1290 * zoom,
        right: 1290 * zoom,
        left: 0
      })
      page.sc_blob = 'blob:http://latest'
      await nextTick()
      page.apply_log_layout()
      await nextTick()
      const listeners = new Map()
      document.addEventListener.mockImplementation((name, handler) => listeners.set(name, handler))
      state.client.post.mockResolvedValue({})
      let restoreLayout
      let resolveLayout
      if (pending) {
        state.client.get.mockImplementationOnce(
          () => new Promise((resolve) => (resolveLayout = resolve))
        )
        restoreLayout = page.restore_log_layout()
      }

      page.resize_rail_column({ preventDefault: vi.fn() })
      listeners.get('pointermove')({ clientX: 800 * zoom })
      listeners.get('pointerup')()

      if (pending) {
        resolveLayout({ data: { rail_width: 360, task_height: 100 } })
        await restoreLayout
        expect(page.layout_preference.task_height).toBe(100)
      }
      expect(sizes()['--log-rail-w']).toBe('478px')
      expect(page.layout_preference.rail_width).toBe(478)
      expect(state.client.post).toHaveBeenCalledExactlyOnceWith('/ui-state/log-layout', {
        rail_width: 478
      })
    }
  )

  it('grows a widened screenshot vertically with its actual aspect and contains the full frame', async () => {
    const { find, page, sizes } = mountWidePane()
    page.sc_blob = 'blob:http://latest'
    page.layout_preference.rail_width = 640
    page.layout_preference.screenshot_height = 180
    await nextTick()

    page.apply_log_layout()
    expect(sizes()['--log-rail-w']).toBe('640px')
    expect(sizes()['--log-sc-h']).toBe('360px')
    const screenshot = find((target) => target.props.src === 'blob:http://latest')
    expect(screenshot.props['object-fit']).toBe('contain')

    await publishScreenshot('blob:http://next', 4 / 3)
    expect(sizes()['--log-sc-h']).toBe('480px')
  })

  it('keeps screenshot dragging proportional after a saved rail-width adjustment', async () => {
    const { page, pane, sizes } = mountWidePane()
    pane.querySelector = (selector) =>
      selector === '.log-screenshot' ? { getBoundingClientRect: () => ({ top: 0 }) } : null
    page.sc_blob = 'blob:http://latest'
    page.layout_preference.rail_width = 640
    await nextTick()
    page.apply_log_layout()
    const listeners = new Map()
    document.addEventListener.mockImplementation((name, handler) => listeners.set(name, handler))
    state.client.post.mockResolvedValue({})

    page.resize_log_pane({ preventDefault: vi.fn() }, 'screenshot')
    listeners.get('pointermove')({ clientY: 180 })
    listeners.get('pointerup')()

    expect(sizes()['--log-rail-w']).toBe('320px')
    expect(sizes()['--log-sc-h']).toBe('180px')
    expect(state.client.post).toHaveBeenCalledExactlyOnceWith('/ui-state/log-layout', {
      screenshot_height: 180,
      rail_width: 320
    })
  })

  it('keeps the task list in the right column without a screenshot and stacks on mobile', async () => {
    state.mower.refs.task_list.value = [
      { time: '2026-10-31T14:20:00.000', plan: {}, type: { display_value: '跑单' } }
    ]
    const { find, page, pane, classes } = mountWidePane()
    page.apply_log_layout()
    await nextTick()
    expect(classes(pane)).toContain('log-pane--rail')
    expect(classes(pane)).toContain('log-pane--reveal-queue')
    expect(pane.style.setProperty).toHaveBeenCalledWith('--log-rail-w', '480px')
    expect(pane.style.removeProperty).toHaveBeenCalledWith('--log-sc-h')

    const toggle = viewControl(find, '任务列表')
    toggle.props.onClick()
    await nextTick()
    expect(classes(pane)).not.toContain('log-pane--rail')
    expect(state.mower.refs.task_list.value).toHaveLength(1)
    toggle.props.onClick()
    await nextTick()
    expect(classes(pane)).toContain('log-pane--rail')

    state.mobile.value = true
    await nextTick()
    page.apply_log_layout()
    await nextTick()
    expect(classes(pane)).not.toContain('log-pane--rail')
    expect(classes(pane.parent)).toContain('home-container--mobile')
    expect(classes(pane)).not.toContain('log-pane--reveal-queue')

    state.mobile.value = false
    state.mower.refs.task_list.value = []
    await nextTick()
    page.apply_log_layout()
    await nextTick()
    expect(classes(pane)).not.toContain('log-pane--rail')
    expect(state.client.post).not.toHaveBeenCalled()
  })

  function mockDailyStatus(response) {
    state.client.get.mockImplementation(async (url) => ({
      data: url.endsWith('/daily-status') ? response() : {}
    }))
  }

  it('reveals each panel only on its first appearance in the initial visit', async () => {
    state.mobile.value = true
    let reduced = false
    vi.stubGlobal('matchMedia', () => ({ matches: reduced }))
    const { classes, pane, page } = mountWidePane(390)
    page.sc_blob = 'blob:preview'
    await nextTick()
    expect(classes(pane)).not.toContain('log-pane--reveal-screenshot')

    reduced = true
    const task = { time: '2026-10-20T11:30:00.000', plan: {}, type: '跑单' }
    state.mower.refs.task_list.value = [task]
    await nextTick()
    expect(classes(pane)).toContain('log-pane--reveal-queue')
    expect(classes(pane)).not.toContain('log-pane--reveal-screenshot')

    page.sc_blob = ''
    state.mower.refs.task_list.value = []
    await nextTick()
    page.sc_blob = 'blob:next-frame'
    state.mower.refs.task_list.value = [task]
    await nextTick()
    expect(classes(pane)).not.toContain('log-pane--reveal-queue')
    expect(classes(pane)).not.toContain('log-pane--reveal-screenshot')
  })

  it('animates the first visible visit but restores a screenshot without replay after hiding', async () => {
    state.realPreview = true
    document.hidden = true
    vi.stubGlobal(
      'Image',
      class {
        naturalWidth = 4
        naturalHeight = 3
        async decode() {}
      }
    )
    state.client.get.mockImplementation(async (url) =>
      url.endsWith('/screenshot/latest')
        ? { status: 200, data: new Blob(['frame']), headers: {} }
        : { data: {} }
    )
    const { classes, pane, page } = mountWidePane()
    onMounted.mock.lastCall[0]()
    expect(page.sc_blob).toBe('')

    setHidden(false)
    await vi.advanceTimersByTimeAsync(0)
    expect(page.sc_blob).toMatch(/^blob:/)
    expect(classes(pane)).toContain('log-pane--reveal-screenshot')

    setHidden(true)
    expect(page.sc_blob).toBe('')
    setHidden(false)
    expect(page.sc_blob).toMatch(/^blob:/)
    await nextTick()
    expect(classes(pane)).not.toContain('log-pane--reveal-screenshot')
    onUnmounted.mock.lastCall[0]()
  })

  it.each([false, true])(
    'restores the whole log workspace before refresh replies after a route return (mobile=%s)',
    async (mobile) => {
      vi.setSystemTime(new Date('2026-11-08T05:00:00Z'))
      state.realPreview = true
      state.mobile.value = mobile
      state.mower.refs.running.value = true
      state.config.report_enable = true
      state.mower.refs.task_list.value = [{ time: '2026-11-08T14:20:00', plan: {}, type: '跑单' }]
      vi.stubGlobal(
        'Image',
        class {
          naturalWidth = 4
          naturalHeight = 3
          decode() {
            return Promise.resolve()
          }
        }
      )
      const createUrl = vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:first-frame')
      const revokeUrl = vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {})
      state.client.get.mockImplementation(async (url) =>
        url.endsWith('/screenshot/latest')
          ? { status: 200, data: new Blob(['frame']), headers: { etag: 'first' } }
          : {
              data: url.endsWith('/daily-status')
                ? { game_day: '2026-11-08', source: 'live', records: { report: 'done' } }
                : {}
            }
      )
      const first = mountWidePane(mobile ? 390 : 1290)
      onMounted.mock.lastCall[0]()
      first.page.apply_log_layout()
      if (mobile) first.page.daily_view_selected = true
      await vi.advanceTimersByTimeAsync(0)
      expect(dailyStrip(first).items()).toEqual([['读取基报', 'done']])
      expect(callsTo('/screenshot/latest')).toHaveLength(1)
      expect(first.page.sc_blob).toBe('blob:first-frame')
      onUnmounted.mock.lastCall[0]()
      app.unmount()
      expect(revokeUrl).toHaveBeenCalledWith('blob:first-frame')
      state.client.get.mockImplementation(() => new Promise(() => {}))

      const returned = mountWidePane(mobile ? 390 : 1290)
      onMounted.mock.lastCall[0]()
      returned.page.apply_log_layout()
      await nextTick()

      expect(returned.all().some((target) => target.props.src === 'blob:first-frame')).toBe(true)
      expect(returned.all().some((target) => target.props.class === 'task-table-scroll')).toBe(true)
      expect(dailyStrip(returned).items()).toEqual([['读取基报', 'done']])
      expect(returned.classes(returned.pane)).not.toContain('log-pane--reveal-screenshot')
      expect(returned.classes(returned.pane)).not.toContain('log-pane--reveal-queue')
      expect(state.mower.start_task_polling).toHaveBeenCalledTimes(2)
      expect(state.mower.stop_task_polling).toHaveBeenCalledOnce()
      returned.page.sc_preview = false
      await nextTick()
      expect(returned.page.workspace.screenshot).toBeNull()
      expect(returned.all().some((target) => target.props.class === 'log-screenshot')).toBe(false)
      onUnmounted.mock.lastCall[0]()
      createUrl.mockRestore()
      revokeUrl.mockRestore()
    }
  )

  function dailyStrip(workspace) {
    const strip = () =>
      workspace
        .all()
        .find(
          (target) =>
            target.props['aria-label'] === '任务状态' ||
            (target.props['aria-label'] === '今日任务' && target.props.role === 'region')
        )
    const items = () =>
      workspace
        .all(strip())
        .filter((target) => target.tag === 'li')
        .map((target) => [
          target.props.title.split('：')[0],
          target.props.class.split(' ')[1].replace('daily-status__item--', '')
        ])
    return { strip, items }
  }

  it.each([false, true])(
    'opens and closes the wide daily overview only when its visibility changes (reduced=%s)',
    async (reduced) => {
      vi.setSystemTime(new Date('2026-11-08T05:00:00Z'))
      vi.stubGlobal('matchMedia', () => ({ matches: reduced }))
      state.mower.refs.running.value = true
      state.config.report_enable = true
      let report = 'done'
      mockDailyStatus(() => ({
        game_day: '2026-11-08',
        source: 'live',
        records: { report }
      }))
      const { callbacks } = deferViewTransitions()
      const workspace = mountWidePane()
      const { strip, items } = dailyStrip(workspace)
      onMounted.mock.lastCall[0]()
      await vi.advanceTimersByTimeAsync(0)
      const types = ['mower-log', 'mower-log-layout', 'mower-log-daily']
      if (reduced) {
        expect(callbacks).toHaveLength(0)
      } else {
        expect(strip()).toBeUndefined()
        expect(document.startViewTransition).toHaveBeenLastCalledWith({
          update: expect.any(Function),
          types
        })
        await callbacks[0]()
      }
      expect(items()).toEqual([['读取基报', 'done']])

      report = 'attempted'
      await vi.advanceTimersByTimeAsync(30000)
      expect(items()).toEqual([['读取基报', 'attempted']])
      expect(callbacks).toHaveLength(reduced ? 0 : 1)

      state.mower.refs.running.value = false
      await nextTick()
      if (!reduced) {
        expect(document.startViewTransition).toHaveBeenLastCalledWith({
          update: expect.any(Function),
          types: [...types, 'mower-log-collapse']
        })
        await callbacks[1]()
      }
      expect(strip()).toBeUndefined()
      onUnmounted.mock.lastCall[0]()
    }
  )

  it('applies a daily status reply without replaying the interrupted reveal after tab return', async () => {
    vi.setSystemTime(new Date('2026-11-08T05:00:00Z'))
    state.mower.refs.running.value = true
    state.config.report_enable = true
    localStorage.getItem.mockImplementation((key) =>
      key === 'log_show_daily_tasks' ? 'false' : null
    )
    const replies = []
    state.client.get.mockImplementation((url, options) => {
      if (!url.endsWith('/daily-status')) return Promise.resolve({ data: {} })
      const reply = Promise.withResolvers()
      replies.push({ ...reply, signal: options.signal })
      return reply.promise
    })
    deferViewTransitions()
    const workspace = mountWidePane()
    onMounted.mock.lastCall[0]()
    viewControl(workspace.find, '今日任务').props.onClick()
    await nextTick()
    expect(replies).toHaveLength(1)

    setHidden(true)
    expect(replies[0].signal.aborted).toBe(true)
    setHidden(false)
    expect(replies).toHaveLength(2)
    replies[1].resolve({
      data: { game_day: '2026-11-08', source: 'live', records: { report: 'done' } }
    })
    await vi.advanceTimersByTimeAsync(0)
    expect(dailyStrip(workspace).items()).toEqual([['读取基报', 'done']])
    expect(document.startViewTransition).not.toHaveBeenCalled()
    onUnmounted.mock.lastCall[0]()
  })

  it.each([false, true])(
    'clears cached daily status when leaving during a hide transition (mobile=%s)',
    async (mobile) => {
      vi.setSystemTime(new Date('2026-11-08T05:00:00Z'))
      state.mobile.value = mobile
      state.mower.refs.running.value = true
      state.config.report_enable = true
      mockDailyStatus(() => ({
        game_day: '2026-11-08',
        source: 'live',
        records: { report: 'done' }
      }))
      const first = mountWidePane(mobile ? 390 : 1290)
      const { find, page } = first
      onMounted.mock.lastCall[0]()
      const control = mobile
        ? find((target) => target.props.class === 'log-daily-toggle')
        : viewControl(find, '今日任务')
      if (mobile) control.props.onClick()
      await vi.advanceTimersByTimeAsync(0)
      expect(dailyStrip(first).items()).toEqual([['读取基报', 'done']])

      const { callbacks, skipTransition } = deferViewTransitions()
      control.props.onClick()
      await nextTick()
      expect(callbacks).toHaveLength(1)
      onBeforeUnmount.mock.lastCall[0]()
      app.unmount()
      app = null
      onUnmounted.mock.lastCall[0]()

      expect(skipTransition).toHaveBeenCalledOnce()
      expect(page.workspace.dailyStatus).toBeNull()
      await callbacks[0]()
      expect(page.workspace.dailyStatus).toBeNull()
    }
  )

  it.each([false, true])(
    'hides daily status and cancels its refresh independently of the task list (mobile=%s)',
    async (mobile) => {
      vi.setSystemTime(new Date('2026-11-01T05:00:00Z'))
      state.mobile.value = mobile
      state.mower.refs.running.value = true
      state.mower.refs.task_list.value = [
        { time: '2026-11-01T14:20:00.000', plan: {}, type: { display_value: '跑单' } }
      ]
      state.config.report_enable = true
      const replies = []
      state.client.get.mockImplementation((url) =>
        url.endsWith('/daily-status')
          ? new Promise((resolve) => replies.push(resolve))
          : Promise.resolve({ data: {} })
      )
      const response = (report) => ({
        data: { game_day: '2026-11-01', source: 'live', records: { report } }
      })
      const workspace = mountWidePane(mobile ? 390 : 1290)
      const { find, all, page } = workspace
      const { strip, items } = dailyStrip(workspace)
      const titleToggle = () => all().find((target) => target.props.class === 'log-daily-toggle')
      const log = find((target) => target.props['data-log-content'])
      const queue = find((target) => target.props.class === 'task-table-scroll')
      onMounted.mock.lastCall[0]()
      page.apply_log_layout()
      await nextTick()
      if (mobile) {
        await openViewOptions(find)
        titleToggle().props.onClick()
      }
      const daily = viewControl(find, '今日任务')
      const tasks = viewControl(find, '任务列表')
      await vi.advanceTimersByTimeAsync(0)
      expect(callsTo('/daily-status')).toHaveLength(1)
      replies[0](response('done'))
      await vi.advanceTimersByTimeAsync(0)
      expect(items()).toEqual([['读取基报', 'done']])

      await vi.advanceTimersByTimeAsync(30000)
      const { signal } = callsTo('/daily-status')[1][1]
      expect(signal.aborted).toBe(false)
      daily.props.onClick()
      await nextTick()
      expect(daily.props['aria-pressed']).toBe(false)
      expect(localStorage.setItem).toHaveBeenCalledWith('log_show_daily_tasks', 'false')
      expect(strip()).toBeUndefined()
      expect(titleToggle()).toBeUndefined()
      expect(log.props.showAlternateView).toBe(false)
      expect(tasks.props['aria-pressed']).toBe(true)
      expect(queue.style.display).not.toBe('none')
      expect(signal.aborted).toBe(true)

      replies[1](response('pending'))
      await vi.advanceTimersByTimeAsync(60000)
      expect(callsTo('/daily-status')).toHaveLength(2)
      expect(strip()).toBeUndefined()

      daily.props.onClick()
      await vi.advanceTimersByTimeAsync(0)
      expect(daily.props['aria-pressed']).toBe(true)
      expect(localStorage.setItem).toHaveBeenCalledWith('log_show_daily_tasks', 'true')
      expect(log.props.showAlternateView).toBe(false)
      if (mobile) {
        expect(titleToggle().props['aria-label']).toBe('运行日志，切换到今日任务')
        expect(callsTo('/daily-status')).toHaveLength(2)
      } else {
        expect(callsTo('/daily-status')).toHaveLength(3)
      }
      onUnmounted.mock.lastCall[0]()
    }
  )

  it.each(['stop and restart', 'new game day', 'failed refresh', 'saved response'])(
    'invalidates restored daily status after %s',
    async (reason) => {
      vi.setSystemTime(new Date('2026-11-08T05:00:00Z'))
      state.mower.refs.running.value = true
      state.config.report_enable = true
      mockDailyStatus(() => ({
        game_day: '2026-11-08',
        source: 'live',
        records: { report: 'done' }
      }))
      const first = mountWidePane()
      onMounted.mock.lastCall[0]()
      await vi.advanceTimersByTimeAsync(0)
      expect(dailyStrip(first).items()).toEqual([['读取基报', 'done']])
      onUnmounted.mock.lastCall[0]()
      app.unmount()
      if (reason === 'stop and restart') {
        state.mower.refs.running.value = false
        state.mower.refs.running.value = true
      } else if (reason === 'new game day') {
        vi.setSystemTime(new Date('2026-11-08T20:00:00Z'))
      }
      let resolveDaily, rejectDaily
      state.client.get.mockImplementation((url) =>
        url.endsWith('/daily-status')
          ? new Promise((resolve, reject) => {
              resolveDaily = resolve
              rejectDaily = reject
            })
          : Promise.resolve({ data: {} })
      )
      const returned = mountWidePane()
      onMounted.mock.lastCall[0]()
      await nextTick()
      if (['stop and restart', 'new game day'].includes(reason)) {
        expect(dailyStrip(returned).strip()).toBeUndefined()
      } else {
        expect(dailyStrip(returned).items()).toEqual([['读取基报', 'done']])
        if (reason === 'failed refresh') rejectDaily(new Error('synthetic failure'))
        else resolveDaily({ data: { source: 'saved', records: { report: 'done' } } })
        await vi.advanceTimersByTimeAsync(0)
        expect(dailyStrip(returned).strip()).toBeUndefined()
      }
      onUnmounted.mock.lastCall[0]()
    }
  )

  it('expires the visible checklist at game-day rollover and discards an in-flight old response', async () => {
    vi.setSystemTime(new Date('2026-11-08T19:59:20Z'))
    state.mower.refs.running.value = true
    state.config.report_enable = true
    const replies = []
    state.client.get.mockImplementation((url) =>
      url.endsWith('/daily-status')
        ? new Promise((resolve) => replies.push(resolve))
        : Promise.resolve({ data: {} })
    )
    const response = (game_day, report) => ({
      data: { game_day, source: 'live', records: { report } }
    })
    const workspace = mountWidePane()
    onMounted.mock.lastCall[0]()
    const { strip, items } = dailyStrip(workspace)
    await nextTick()
    replies[0](response('2026-11-08', 'done'))
    await vi.advanceTimersByTimeAsync(39999)
    expect(items()).toEqual([['读取基报', 'done']])
    expect(replies).toHaveLength(2)

    await vi.advanceTimersByTimeAsync(1)
    expect(strip()).toBeUndefined()
    expect(replies).toHaveLength(2)
    replies[1](response('2026-11-08', 'done'))
    await vi.advanceTimersByTimeAsync(0)
    expect(strip()).toBeUndefined()

    await vi.advanceTimersByTimeAsync(20000)
    replies[2](response('2026-11-09', 'pending'))
    await vi.advanceTimersByTimeAsync(0)
    expect(items()).toEqual([['读取基报', 'pending']])
    onUnmounted.mock.lastCall[0]()
  })

  it('drops the previous game-day checklist before refreshing a visible page', async () => {
    vi.setSystemTime(new Date('2026-11-08T19:59:59Z'))
    state.mower.refs.running.value = true
    state.config.report_enable = true
    mockDailyStatus(() => ({
      game_day: '2026-11-08',
      source: 'live',
      records: { report: 'done' }
    }))
    const workspace = mountWidePane()
    onMounted.mock.lastCall[0]()
    await vi.advanceTimersByTimeAsync(0)
    expect(dailyStrip(workspace).items()).toEqual([['读取基报', 'done']])

    setHidden(true)
    vi.setSystemTime(new Date('2026-11-08T20:00:00Z'))
    state.client.get.mockImplementation((url) =>
      url.endsWith('/daily-status') ? new Promise(() => {}) : Promise.resolve({ data: {} })
    )
    setHidden(false)
    await nextTick()
    expect(dailyStrip(workspace).strip()).toBeUndefined()
    expect(callsTo('/daily-status')).toHaveLength(2)
    onUnmounted.mock.lastCall[0]()
  })

  it('returns to the running log when the worker stops while its mobile daily view is away', async () => {
    vi.setSystemTime(new Date('2026-11-08T05:00:00Z'))
    state.mobile.value = true
    state.mower.refs.running.value = true
    state.config.report_enable = true
    mockDailyStatus(() => ({
      game_day: '2026-11-08',
      source: 'live',
      records: { report: 'done' }
    }))
    const first = mountWidePane(390)
    onMounted.mock.lastCall[0]()
    first.page.daily_view_selected = true
    await vi.advanceTimersByTimeAsync(0)
    expect(first.page.daily_view_visible).toBe(true)
    onUnmounted.mock.lastCall[0]()
    app.unmount()
    state.mower.refs.running.value = false
    state.mower.refs.running.value = true
    const returned = mountWidePane(390)
    onMounted.mock.lastCall[0]()
    await nextTick()
    expect(returned.page.daily_view_selected).toBe(false)
    expect(returned.page.daily_view_visible).toBe(false)
    expect(returned.page.daily_status).toBeNull()
    onUnmounted.mock.lastCall[0]()
  })

  it('hides the entire checklist without an enabled task that has a daily record', async () => {
    state.mower.refs.running.value = true
    Object.assign(state.config, {
      recruit_enable: true,
      stage_plan_enable: true,
      report_enable: true
    })
    mockDailyStatus(() => ({
      game_day: '2026-11-05',
      source: 'live',
      records: { mail: 'done' },
      activities: {
        recruit: {
          last_checked_at: '2026-11-05T09:30:00+08:00',
          next_eligible_at: '2026-11-05T10:00:00+08:00'
        },
        'stage-plan': {
          last_observation: { at: '2026-11-05T09:32:00+08:00', runner: 'mower', outcome: 'running' }
        }
      }
    }))
    const workspace = mountWidePane()
    workspace.page.apply_log_layout()
    await vi.advanceTimersByTimeAsync(0)
    expect(dailyStrip(workspace).strip()).toBeUndefined()
    expect(callsTo('/daily-status')).toHaveLength(1)
  })

  it('hides saved daily records while the worker starts', async () => {
    state.mower.refs.running.value = true
    Object.assign(state.config, { report_enable: true, recruit_enable: true })
    mockDailyStatus(() => ({
      game_day: '2026-11-05',
      source: 'saved',
      records: { report: 'done' },
      activities: {
        recruit: {
          last_observation: {
            at: '2026-11-05T09:30:00+08:00',
            outcome: 'running'
          }
        }
      }
    }))
    const workspace = mountWidePane()
    workspace.page.apply_log_layout()
    await vi.advanceTimersByTimeAsync(0)
    expect(dailyStrip(workspace).strip()).toBeUndefined()
    expect(workspace.page.daily_items).toEqual([])
  })

  it('keeps the latest completion state when daily-status replies arrive out of order', async () => {
    vi.setSystemTime(new Date('2026-11-05T05:00:00Z'))
    state.mower.refs.running.value = true
    state.config.report_enable = true
    const replies = []
    state.client.get.mockImplementation((url) =>
      url.endsWith('/daily-status')
        ? new Promise((resolve) => replies.push(resolve))
        : Promise.resolve({ data: {} })
    )
    const workspace = mountWidePane()
    workspace.page.apply_log_layout()
    await vi.advanceTimersByTimeAsync(0)
    state.mower.refs.status.value = 'working'
    await vi.advanceTimersByTimeAsync(0)
    expect(callsTo('/daily-status')[0][1].signal.aborted).toBe(true)
    expect(callsTo('/daily-status')[1][1].signal.aborted).toBe(false)
    const response = (status) => ({
      data: {
        source: 'live',
        game_day: '2026-11-05',
        records: { report: status }
      }
    })
    const { items } = dailyStrip(workspace)
    replies[1](response('done'))
    await vi.advanceTimersByTimeAsync(0)
    expect(items()).toEqual([['读取基报', 'done']])
    replies[0](response('pending'))
    await vi.advanceTimersByTimeAsync(0)
    expect(items()).toEqual([['读取基报', 'done']])
  })

  it.each(['hide', 'unmount', 'stop'])('cancels a pending daily request on %s', async (action) => {
    state.mower.refs.running.value = true
    let reply
    state.client.get.mockImplementation((url) =>
      url.endsWith('/daily-status')
        ? new Promise((resolve) => (reply = resolve))
        : Promise.resolve({ data: {} })
    )
    const { page } = mountWidePane()
    onMounted.mock.lastCall[0]()
    page.apply_log_layout()
    await vi.advanceTimersByTimeAsync(0)
    const { signal, timeout } = callsTo('/daily-status')[0][1]
    expect(timeout).toBe(10000)
    expect(signal.aborted).toBe(false)

    if (action === 'hide') setHidden(true)
    else if (action === 'unmount') onUnmounted.mock.lastCall[0]()
    else state.mower.refs.running.value = false
    await nextTick()
    expect(signal.aborted).toBe(true)
    reply({ data: { source: 'live', records: { report: 'done' } } })
    await vi.advanceTimersByTimeAsync(30000)
    expect(page.daily_status).toBe(null)
    expect(callsTo('/daily-status')).toHaveLength(1)
    if (action !== 'unmount') onUnmounted.mock.lastCall[0]()
  })

  it('shows the enabled daily tasks in a non-expandable checklist above the wide desktop log', async () => {
    vi.setSystemTime(new Date('2026-11-01T05:00:00Z'))
    state.mower.refs.running.value = true
    Object.assign(state.config, {
      skland_enable: true,
      check_mail_enable: true,
      event_sign_in_enable: true,
      report_enable: true,
      visit_friend_enable: true,
      maa_credit_fight: true,
      maa_mail: true,
      maa_recruit: true,
      maa_orundum: true,
      recruit_enable: true
    })
    mockDailyStatus(() => ({
      game_day: '2026-11-01',
      source: 'live',
      records: {
        skland: 'done',
        mail: 'pending',
        event_sign_in: 'done',
        report: 'done',
        visit_friend: 'attempted',
        maa_credit_fight: 'done',
        maa_recruit: 'done',
        maa_orundum: 'pending',
        maa_mining: 'done'
      },
      activities: { recruit: { last_checked_at: '2026-11-01T09:30:00+08:00' } }
    }))
    const workspace = mountWidePane()
    const { strip, items } = dailyStrip(workspace)
    workspace.page.apply_log_layout()
    await vi.advanceTimersByTimeAsync(0)

    expect(callsTo('/daily-status')).toHaveLength(1)
    expect(strip().parent.props['data-log-content']).toBe(true)
    expect(strip().props.class).toBe('daily-status')
    expect(workspace.all(strip().parent).some((target) => target.tag === 'button')).toBe(false)
    state.mower.refs.log_lines.value = [
      {
        id: 1,
        at: Date.now(),
        text: '2026-11-02 20:00:00,000 INFO 测试日志',
        group: null,
        room: null,
        agents: null
      }
    ]
    await nextTick()
    const date = workspace.all().find((target) => target.props.class === 'daily-status__date')
    expect(date).toBeDefined()
    const dateText = workspace
      .all(date)
      .map((node) => node.text)
      .join('')
    expect(dateText).toBe('2026-11-02')
    expect(items()).toEqual([
      ['森空岛签到', 'done'],
      ['领取邮件', 'pending'],
      ['活动签到', 'done'],
      ['读取基报', 'done'],
      ['访问好友', 'attempted'],
      ['信用作战', 'done'],
      ['MAA 领取奖励', 'pending']
    ])

    state.config.maa_orundum = false
    await nextTick()
    expect(items().at(-1)).toEqual(['MAA 领取奖励', 'done'])
    state.config.maa_recruit = false
    await nextTick()
    expect(items().some(([title]) => title === 'MAA 领取奖励')).toBe(false)
    Object.assign(state.config, {
      skland_enable: false,
      check_mail_enable: false,
      event_sign_in_enable: false,
      report_enable: false,
      visit_friend_enable: false,
      maa_credit_fight: false
    })
    await nextTick()
    expect(strip()).toBeUndefined()
    expect(callsTo('/daily-status')).toHaveLength(1)
  })

  it('shows task status only after live records arrive and hides it across stop and restart', async () => {
    vi.setSystemTime(new Date('2026-11-01T05:00:00Z'))
    Object.assign(state.config, { report_enable: true, recruit_enable: true })
    let response = {
      game_day: '2026-11-01',
      source: 'saved',
      records: { report: 'done' },
      activities: { recruit: { last_checked_at: '2026-11-01T09:30:00+08:00' } }
    }
    mockDailyStatus(() => response)
    const workspace = mountWidePane()
    const { strip, items } = dailyStrip(workspace)
    workspace.page.apply_log_layout()
    await vi.advanceTimersByTimeAsync(0)
    expect(strip()).toBeUndefined()
    expect(callsTo('/daily-status')).toHaveLength(0)

    response = { game_day: '2026-11-01', source: 'none', records: {}, activities: {} }
    state.mower.refs.running.value = true
    await vi.advanceTimersByTimeAsync(0)
    expect(strip()).toBeUndefined()
    expect(callsTo('/daily-status')).toHaveLength(1)

    response = {
      game_day: '2026-11-01',
      source: 'live',
      records: { report: 'done' },
      activities: { recruit: { last_checked_at: '2026-11-01T09:30:00+08:00' } }
    }
    await vi.advanceTimersByTimeAsync(30000)
    expect(strip().props.class).toBe('daily-status')
    expect(items()).toEqual([['读取基报', 'done']])

    state.mower.refs.running.value = false
    await nextTick()
    expect(strip()).toBeUndefined()
    expect(workspace.page.daily_status).toBe(null)
    await vi.advanceTimersByTimeAsync(30000)
    expect(callsTo('/daily-status')).toHaveLength(2)

    response = { game_day: '2026-11-01', source: 'none', records: {}, activities: {} }
    state.mower.refs.running.value = true
    await nextTick()
    expect(strip()).toBeUndefined()
    await vi.advanceTimersByTimeAsync(0)
    expect(workspace.page.daily_items).toEqual([])
    expect(callsTo('/daily-status')).toHaveLength(3)
  })

  it('refreshes daily records on load, every 30 seconds, on return and on worker status changes', async () => {
    state.mower.refs.running.value = true
    state.config.report_enable = true
    mockDailyStatus(() => ({
      game_day: '2026-11-01',
      source: 'live',
      records: { report: 'pending' }
    }))
    const { page, pane } = mountWidePane()
    onMounted.mock.lastCall[0]()
    page.apply_log_layout()
    await vi.advanceTimersByTimeAsync(0)
    expect(callsTo('/daily-status')).toHaveLength(1)
    await vi.advanceTimersByTimeAsync(30000)
    expect(callsTo('/daily-status')).toHaveLength(2)

    setHidden(true)
    await vi.advanceTimersByTimeAsync(60000)
    expect(callsTo('/daily-status')).toHaveLength(2)
    setHidden(false)
    await vi.advanceTimersByTimeAsync(0)
    expect(callsTo('/daily-status')).toHaveLength(3)

    state.mower.refs.status.value = 'working'
    await vi.advanceTimersByTimeAsync(0)
    expect(callsTo('/daily-status')).toHaveLength(4)

    pane.clientWidth = 880
    page.apply_log_layout()
    await vi.advanceTimersByTimeAsync(30000)
    state.mower.refs.status.value = 'sleeping'
    await vi.advanceTimersByTimeAsync(30000)
    expect(callsTo('/daily-status')).toHaveLength(4)
    expect(page.daily_items).toEqual([])

    onUnmounted.mock.lastCall[0]()
    expect(vi.getTimerCount()).toBe(0)
  })

  it.each([
    ['a narrow pane', 880, false],
    ['mobile', 1290, true]
  ])('switches between the log and live daily task views on %s', async (_, width, mobile) => {
    vi.setSystemTime(new Date('2026-11-01T05:00:00Z'))
    state.mower.refs.running.value = true
    state.mobile.value = mobile
    Object.assign(state.config, { report_enable: true, recruit_enable: true })
    const replies = []
    state.client.get.mockImplementation((url) =>
      url.endsWith('/daily-status')
        ? new Promise((resolve) => replies.push(resolve))
        : Promise.resolve({ data: {} })
    )
    const response = (status) => ({
      data: {
        game_day: '2026-11-01',
        source: 'live',
        records: { report: status },
        activities: { recruit: { last_checked_at: '2026-11-01T09:30:00+08:00' } }
      }
    })
    const workspace = mountWidePane(width)
    const { strip, items } = dailyStrip(workspace)
    const findLog = () => workspace.find((target) => target.props['data-log-content'])
    workspace.page.apply_log_layout()
    state.mower.refs.status.value = 'working'
    await vi.advanceTimersByTimeAsync(60000)
    const log = findLog()
    const toggle = workspace.find((target) => target.props.class === 'log-daily-toggle')
    const title = () =>
      workspace
        .all(toggle)
        .filter((node) => node.tag !== '#comment')
        .map((node) => node.text)
        .join('')
        .trim()
    expect(toggle.tag).toBe('button')
    expect(toggle.props['aria-expanded']).toBeUndefined()
    expect(toggle.props['aria-label']).toBe('运行日志，切换到今日任务')
    expect(title()).toBe('运行日志')
    expect(log.props.showAlternateView).toBe(false)
    expect(callsTo('/daily-status')).toHaveLength(0)
    expect(strip()).toBeUndefined()

    toggle.props.onClick()
    await vi.advanceTimersByTimeAsync(0)
    expect(toggle.props['aria-label']).toBe('今日任务，切换到运行日志')
    expect(title()).toBe('今日任务')
    expect(log.props.showAlternateView).toBe(true)
    expect(callsTo('/daily-status')).toHaveLength(1)
    expect(strip().props.role).toBe('region')
    expect(items()).toEqual([])
    expect(workspace.all(strip()).some((node) => node.text.trim() === '正在读取今日任务…')).toBe(
      true
    )
    replies[0](response('done'))
    await vi.advanceTimersByTimeAsync(0)
    expect(items()).toEqual([['读取基报', 'done']])
    expect(findLog()).toBe(log)

    await vi.advanceTimersByTimeAsync(30000)
    expect(callsTo('/daily-status')).toHaveLength(2)
    const { signal } = callsTo('/daily-status')[1][1]
    expect(signal.aborted).toBe(false)
    toggle.props.onClick()
    await nextTick()
    expect(title()).toBe('运行日志')
    expect(log.props.showAlternateView).toBe(false)
    expect(signal.aborted).toBe(true)
    expect(strip()).toBeUndefined()
    replies[1](response('pending'))
    await vi.advanceTimersByTimeAsync(60000)
    expect(callsTo('/daily-status')).toHaveLength(2)
    expect(strip()).toBeUndefined()
    expect(findLog()).toBe(log)

    toggle.props.onClick()
    await vi.advanceTimersByTimeAsync(0)
    expect(callsTo('/daily-status')).toHaveLength(3)
    expect(items()).toEqual([])
    replies[2](response('pending'))
    await vi.advanceTimersByTimeAsync(0)
    expect(items()).toEqual([['读取基报', 'pending']])

    await vi.advanceTimersByTimeAsync(30000)
    replies[3]({ data: { game_day: '2026-11-01', source: 'live', records: {} } })
    await vi.advanceTimersByTimeAsync(0)
    expect(log.props.showAlternateView).toBe(true)
    expect(items()).toEqual([])
    expect(workspace.all(strip()).some((node) => node.text.trim() === '暂无今日任务状态')).toBe(
      true
    )
  })

  it('only offers the compact checklist while running with a recordable daily task enabled', async () => {
    vi.setSystemTime(new Date('2026-11-01T05:00:00Z'))
    state.mobile.value = true
    Object.assign(state.config, { maa_mail: true, recruit_enable: true })
    mockDailyStatus(() => ({
      game_day: '2026-11-01',
      source: 'live',
      records: { maa_recruit: 'done' }
    }))
    const workspace = mountWidePane(390)
    const titleToggle = () =>
      workspace.all().find((target) => target.props.class === 'log-daily-toggle')
    workspace.page.apply_log_layout()
    state.mower.refs.running.value = true
    await nextTick()
    expect(titleToggle()).toBeUndefined()

    state.config.maa_recruit = true
    await nextTick()
    expect(titleToggle().props['aria-label']).toBe('运行日志，切换到今日任务')
    expect(callsTo('/daily-status')).toHaveLength(0)
    titleToggle().props.onClick()
    await vi.advanceTimersByTimeAsync(0)
    expect(dailyStrip(workspace).items()).toEqual([['MAA 领取奖励', 'done']])

    state.config.maa_recruit = false
    await nextTick()
    expect(titleToggle()).toBeUndefined()
    expect(dailyStrip(workspace).strip()).toBeUndefined()
    state.config.maa_recruit = true
    await nextTick()
    expect(titleToggle().props['aria-label']).toBe('运行日志，切换到今日任务')
    expect(callsTo('/daily-status')).toHaveLength(1)

    state.mower.refs.running.value = false
    await nextTick()
    expect(titleToggle()).toBeUndefined()
  })
})
