<script setup>
defineOptions({ name: 'MowerLogPage' })

import { storeToRefs } from 'pinia'
import {
  computed,
  inject,
  nextTick,
  onBeforeUnmount,
  onMounted,
  onUnmounted,
  provide,
  ref,
  shallowRef,
  useId,
  watch
} from 'vue'
import { useDialog, useMessage } from 'naive-ui'
import { routeLocationKey, routerKey } from 'vue-router'

import { useMowerStore } from '@/stores/mower'
import { useGuiStore } from '@/stores/gui'
import { useLogBackgroundStore } from '@/stores/logBackground'
import { dailyStatusExpiry, useLogWorkspaceStore } from '@/stores/logWorkspace'
import { useConfigStore } from '@/stores/config'
import {
  clampScreenshotHeight,
  clampTaskHeight,
  fitRailLayout,
  logLayoutZoom,
  logMinHeight,
  RAIL_GAP,
  RAIL_LAYOUT_MIN_WIDTH,
  RAIL_LOG_MIN_WIDTH,
  RAIL_MAX_WIDTH,
  RAIL_MIN_WIDTH,
  RESIZER_HEIGHT
} from '@/utils/logLayout'
import { createScreenshotPreview } from '@/utils/screenshotPreview'
import StartSchedule from '@/components/StartSchedule.vue'
import LogOutput from '@/components/LogOutput.vue'
import LogOperator from '@/components/LogOperator.vue'
import TaskActionSubjects from '@/components/TaskActionSubjects.vue'
import mastery0 from '@/assets/growth/mastery-0.png?url&no-inline'
import mastery1 from '@/assets/growth/mastery-1.png?url&no-inline'
import mastery2 from '@/assets/growth/mastery-2.png?url&no-inline'
import mastery3 from '@/assets/growth/mastery-3.png?url&no-inline'
import { usePlanStore } from '@/stores/plan'
import { queueTaskRoom, queueTaskRows } from '@/utils/taskPresentation'
import { useResolvedTheme } from '@/composables/theme'
import { getDailyStatusItems, hasDailyStatusTasks } from '@/task-workflow/model'
const mower_store = useMowerStore()
const config_store = useConfigStore()
const logBackground = useLogBackgroundStore()
const workspace = useLogWorkspaceStore()
const startup_reveal = ref(!workspace.visited)
const page_visible = ref(!document.hidden)
const { taskQueueDisplay } = storeToRefs(useGuiStore())
const { operators, plan } = storeToRefs(usePlanStore())
const operator_names = computed(() => operators.value.map((operator) => operator.value))
const mastery_icons = [mastery0, mastery1, mastery2, mastery3]
const {
  running,
  status: worker_status,
  plan_condition,
  log_lines,
  task_list,
  waiting,
  stop_after_round,
  maintenance_pause
} = storeToRefs(mower_store)
const show_task_names = computed(() => taskQueueDisplay.value === 'names')
const task_rows = computed(() =>
  queueTaskRows(task_list.value, operator_names.value, plan.value, show_task_names.value)
)
const task_calendar_day = ref(browser_calendar_day())
const task_date_hint = ref(null)
watch(task_rows, (rows) => {
  if (task_date_hint.value !== null && !rows.some((row) => row.key === task_date_hint.value)) {
    task_date_hint.value = null
  }
})

function browser_calendar_day() {
  const now = new Date()
  const month = String(now.getMonth() + 1).padStart(2, '0')
  const day = String(now.getDate()).padStart(2, '0')
  return `${now.getFullYear()}-${month}-${day}`
}

function set_task_date_hint(key, show) {
  if (show) task_date_hint.value = key
  else if (task_date_hint.value === key) task_date_hint.value = null
}

const { clear_legacy_logs, get_tasks, get_running, start_task_polling, stop_task_polling } =
  mower_store
const axios = inject('axios')
const cancelling_pause = ref(false)
const pause_end = computed(() =>
  maintenance_pause.value?.end ? new Date(maintenance_pause.value.end).toLocaleTimeString() : ''
)

async function cancel_pause() {
  const id = maintenance_pause.value?.id
  if (!id || cancelling_pause.value) return
  cancelling_pause.value = true
  try {
    await mower_store.cancel_maintenance_pause(id)
  } catch (error) {
    db_message.error(error.response?.data?.error || '取消暂停失败，请重试')
    void get_running()
  } finally {
    cancelling_pause.value = false
  }
}
const mobile = inject('mobile')
const resizer_height = computed(() => (mobile.value ? 24 : RESIZER_HEIGHT))
const route = inject(routeLocationKey, null)
const router = inject(routerKey, null)

const auto_scroll = ref(true)
const log_concise = ref(localStorage.getItem('log_detail_mode') === 'concise')
watch(log_concise, (enabled) => {
  localStorage.setItem('log_detail_mode', enabled ? 'concise' : 'detailed')
})
const sc_preview = ref(true)
const sc_blob = ref('')
const has_screenshot = computed(() => sc_preview.value && Boolean(sc_blob.value))
const show_task_table = ref(localStorage.getItem('log_show_task_table') !== 'false')
const show_daily_tasks = ref(localStorage.getItem('log_show_daily_tasks') !== 'false')
watch(
  show_daily_tasks,
  (visible) => localStorage.setItem('log_show_daily_tasks', String(visible)),
  {
    flush: 'sync'
  }
)
const task_table_visible = computed(() => show_task_table.value && task_list.value.length > 0)
const screenshot_entry = use_panel_entry(has_screenshot)
const queue_entry = use_panel_entry(task_table_visible)
const log_layout = ref(null)
const action_bar = ref(null)
const show_view_controls = ref(false)
function dismiss_view_controls(event) {
  show_view_controls.value = false
  if (event.type === 'touchend') event.preventDefault()
}
const toolbar_id = useId()
const operator_hint = ref(null)
function operator_hint_name(name) {
  return !name || name === '_'
    ? 'Empty（留空）'
    : ({ Current: 'Current（保留当前干员）', Free: 'Free（自动选择干员）' }[name] ?? name)
}
function show_operator_hint(name, event) {
  const bounds = event.currentTarget.getBoundingClientRect()
  operator_hint.value = {
    name: operator_hint_name(name),
    x: (bounds.left + bounds.right) / 2,
    y: bounds.top - 4
  }
}
const task_queue = ref(null)
const layout_preference = { ...workspace.layout }
let layoutObserver
let restoring_log_layout = false
let cancel_layout_resize
let screenshot_aspect = workspace.screenshot?.aspect || 16 / 9
let mobile_screenshot_height = workspace.mobileScreenshotHeight
let railWidthReveal
let queueRevealAnimations = []
const STARTUP_REVEAL = { duration: 240, easing: 'ease' }
const startupReveal = `${STARTUP_REVEAL.duration}ms ${STARTUP_REVEAL.easing}`
let log_view_transition
let animate_next_screenshot = false
let animate_next_daily_status = false

function reduced_log_motion() {
  return globalThis.matchMedia?.('(prefers-reduced-motion: reduce)').matches
}

function use_panel_entry(visible) {
  const motion = ref('')
  let shown = false
  watch(
    [visible, startup_reveal, page_visible],
    ([present, firstVisit, active]) => {
      if (!present || !firstVisit || !active) {
        motion.value = ''
      } else if (!shown) {
        shown = true
        motion.value = reduced_log_motion() ? 'fade' : mobile.value ? '' : 'expand'
      }
    },
    { immediate: true, flush: 'sync' }
  )
  return motion
}

function cancel_log_entry_animations() {
  railWidthReveal?.cancel()
  railWidthReveal = undefined
  for (const animation of queueRevealAnimations) animation?.cancel()
  queueRevealAnimations = []
}

function finish_log_view_transition() {
  if (!log_view_transition) return
  const { transition, commit } = log_view_transition
  log_view_transition = undefined
  transition.skipTransition()
  void commit()
}

function transition_log_view(update, { panel } = {}) {
  finish_log_view_transition()
  const pane = log_layout.value
  const target = !panel && pane?.startViewTransition ? pane : document
  const reduced = reduced_log_motion()
  if (
    !pane ||
    !target.startViewTransition ||
    document.hidden ||
    (reduced && !panel) ||
    !globalThis.CSS?.supports('selector(:active-view-transition-type(mower-log))')
  ) {
    update()
    return
  }

  let committed = false
  function commit() {
    if (committed || log_layout.value !== pane) return
    committed = true
    update()
    return nextTick(apply_log_layout)
  }

  try {
    const types = ['mower-log']
    if (panel && !reduced) {
      types.push('mower-log-layout')
      const changesRail =
        panel === 'screenshot'
          ? !task_table_visible.value
          : !has_screenshot.value && task_list.value.length > 0
      if (rail_layout.value && changesRail) types.push('mower-log-rail')
    }
    const transition = target.startViewTransition({ update: commit, types })
    log_view_transition = { transition, commit }
    void transition.ready.catch(() => {})
    const release = () => {
      if (log_view_transition?.transition === transition) log_view_transition = undefined
    }
    void transition.finished.then(release, release)
    return transition.updateCallbackDone.catch(() => {})
  } catch {
    return commit()
  }
}

// 桌面宽屏仿照游戏主界面：截图和任务列表在右栏，日志占左侧。
const rail_layout = ref(workspace.wideLayout && !mobile.value)
const rail_active = computed(() => has_screenshot.value || task_table_visible.value)
const rail_mode = computed(() => rail_layout.value && rail_active.value && !mobile.value)
const rail_entry = use_panel_entry(rail_mode)

function apply_rail_layout(container) {
  const { width, height } = fitRailLayout(
    layout_preference.rail_width,
    layout_preference.screenshot_height ?? 270,
    container.clientWidth,
    container.getBoundingClientRect().height / logLayoutZoom(container),
    screenshot_aspect
  )
  container.style.setProperty('--log-rail-w', `${width}px`)
  if (has_screenshot.value) container.style.setProperty('--log-sc-h', `${height}px`)
  else container.style.removeProperty('--log-sc-h')
  container.style.removeProperty('--log-task-h')
}

function plan_condition_height(container, zoom) {
  return (container.querySelector('.plan-condition')?.getBoundingClientRect().height ?? 0) / zoom
}

// 上下排列时截图按当前宽度等比显示的高度；宽度未知时返回 0。
function stacked_screenshot_fit(container) {
  const width = container.querySelector('.log-screenshot')?.clientWidth || container.clientWidth
  return width > 0 ? Math.round(width / screenshot_aspect) : 0
}

function apply_log_layout() {
  const container = log_layout.value
  if (!container) return
  rail_layout.value = !mobile.value && container.clientWidth >= RAIL_LAYOUT_MIN_WIDTH
  if (rail_mode.value) return apply_rail_layout(container)
  container.style.removeProperty('--log-rail-w')
  const bounds = container.getBoundingClientRect()
  const zoom = logLayoutZoom(container)
  const paneHeight = bounds.height / zoom
  const logHeight = logMinHeight(paneHeight)
  const bottomReserve = logHeight + resizer_height.value
  const conditionHeight = plan_condition_height(container, zoom)
  container.style.setProperty('--log-min-h', `${logHeight}px`)
  let screenshotTrack = 0
  if (has_screenshot.value) {
    const fit = stacked_screenshot_fit(container)
    const fitMobile = mobile.value && mobile_screenshot_height === null && fit > 0
    const preferred = mobile.value
      ? (mobile_screenshot_height ?? 270)
      : (layout_preference.screenshot_height ?? 270)
    const height = fitMobile
      ? fit
      : clampScreenshotHeight(
          preferred,
          paneHeight,
          bottomReserve + conditionHeight,
          fit || Infinity,
          resizer_height.value
        )
    screenshotTrack = height + resizer_height.value
    container.style.setProperty('--log-sc-h', `${height}px`)
    container.style.setProperty('--log-sc-aspect', String(screenshot_aspect))
  } else {
    container.style.removeProperty('--log-sc-h')
  }

  if (layout_preference.task_height === null) {
    container.style.removeProperty('--log-task-h')
    return
  }
  const task = container.querySelector('.task-table-scroll')?.getBoundingClientRect()
  if (!task) {
    container.style.removeProperty('--log-task-h')
    return
  }
  // Use the final screenshot track while it is opening.
  const screenshotEntering = container
    .getAnimations?.()
    .some(
      (animation) =>
        animation.animationName?.startsWith('reveal-log-screenshot') &&
        animation.playState === 'running'
    )
  const availableHeight =
    screenshotTrack && screenshotEntering
      ? paneHeight + (container.scrollTop ?? 0) - screenshotTrack - conditionHeight
      : (bounds.bottom - task.top) / zoom
  const height = clampTaskHeight(layout_preference.task_height, availableHeight, bottomReserve)
  container.style.setProperty('--log-task-h', `${height}px`)
}

function screenshot_loaded(event) {
  const image = event.target
  if (image?.naturalWidth > 0 && image?.naturalHeight > 0) {
    screenshot_aspect = image.naturalWidth / image.naturalHeight
    if (workspace.screenshot)
      workspace.screenshot = { ...workspace.screenshot, aspect: screenshot_aspect }
  }
  apply_log_layout()
}

async function restore_log_layout() {
  restoring_log_layout = true
  try {
    const { data } = await axios.get(`${import.meta.env.VITE_HTTP_URL}/ui-state/log-layout`)
    layout_preference.screenshot_height ??= data?.screenshot_height ?? null
    layout_preference.task_height ??= data?.task_height ?? null
    layout_preference.rail_width ??= data?.rail_width ?? null
  } catch {
    // Keep the default layout when saved preferences are unavailable.
  } finally {
    restoring_log_layout = false
  }
  await nextTick()
  apply_log_layout()
}

function listen_for_layout_resize(onMove, save) {
  cancel_layout_resize?.()
  const cancel = () => {
    document.removeEventListener('pointermove', onMove)
    document.removeEventListener('pointerup', onUp)
    document.removeEventListener('pointercancel', cancel)
    cancel_layout_resize = undefined
  }
  const onUp = () => {
    cancel()
    save()
  }
  cancel_layout_resize = cancel
  document.addEventListener('pointermove', onMove)
  document.addEventListener('pointerup', onUp)
  document.addEventListener('pointercancel', cancel)
}

function resize_log_pane(event, pane) {
  event.preventDefault()
  const container = log_layout.value
  if (!container) return
  railWidthReveal?.cancel()
  const variable = pane === 'screenshot' ? '--log-sc-h' : '--log-task-h'
  const stateKey = pane === 'screenshot' ? 'screenshot_height' : 'task_height'
  let savedSize = null
  let savedRailWidth = null
  const onMove = (moveEvent) => {
    const bounds = container.getBoundingClientRect()
    const zoom = logLayoutZoom(container)
    const paneHeight = bounds.height / zoom
    const bottomReserve = logMinHeight(paneHeight) + resizer_height.value
    let size
    if (pane === 'screenshot') {
      const screenshotTop =
        container.querySelector('.log-screenshot')?.getBoundingClientRect().top ?? bounds.top
      const dragged = (moveEvent.clientY - screenshotTop) / zoom
      if (rail_mode.value) {
        const fitted = fitRailLayout(
          null,
          dragged,
          container.clientWidth,
          paneHeight,
          screenshot_aspect
        )
        size = fitted.height
        if (restoring_log_layout || layout_preference.rail_width !== null) {
          savedRailWidth = fitted.width
          layout_preference.rail_width = fitted.width
        }
      } else {
        size = clampScreenshotHeight(
          dragged,
          paneHeight,
          bottomReserve + plan_condition_height(container, zoom),
          stacked_screenshot_fit(container) || Infinity,
          resizer_height.value
        )
      }
    } else {
      const task = container.querySelector('.task-table-scroll')?.getBoundingClientRect()
      if (!task) return
      size = clampTaskHeight(
        (moveEvent.clientY - task.top) / zoom,
        (bounds.bottom - task.top) / zoom,
        bottomReserve
      )
    }
    savedSize = size
    if (pane === 'screenshot' && mobile.value) mobile_screenshot_height = size
    layout_preference[stateKey] = size
    if (rail_mode.value) apply_rail_layout(container)
    else container.style.setProperty(variable, `${size}px`)
  }
  listen_for_layout_resize(onMove, () => {
    if (savedSize === null) return
    axios
      .post(`${import.meta.env.VITE_HTTP_URL}/ui-state/log-layout`, {
        [stateKey]: savedSize,
        ...(savedRailWidth !== null ? { rail_width: savedRailWidth } : {})
      })
      .catch(() => {})
  })
}

// 左右分栏时拖动日志与右栏之间的纵向分隔条，调整右栏宽度并保存。
function resize_rail_column(event) {
  event.preventDefault()
  const container = log_layout.value
  if (!container) return
  railWidthReveal?.cancel()
  let savedWidth = null
  const onMove = (moveEvent) => {
    const bounds = container.getBoundingClientRect()
    const paneWidth = container.clientWidth
    if (!bounds.width || !paneWidth) return
    const logRailMinWidth = Math.max(RAIL_LOG_MIN_WIDTH, Math.round(paneWidth * 0.4))
    const maxRailWidth = Math.min(RAIL_MAX_WIDTH, paneWidth - logRailMinWidth - RAIL_GAP)
    const dragged = ((bounds.right - moveEvent.clientX) * paneWidth) / bounds.width - RAIL_GAP / 2
    const width = Math.max(RAIL_MIN_WIDTH, Math.min(maxRailWidth, Math.round(dragged)))
    if (width <= 0) return
    savedWidth = width
    layout_preference.rail_width = width
    apply_rail_layout(container)
  }
  listen_for_layout_resize(onMove, () => {
    if (savedWidth === null) return
    axios
      .post(`${import.meta.env.VITE_HTTP_URL}/ui-state/log-layout`, { rail_width: savedWidth })
      .catch(() => {})
  })
}

let latest_screenshot_url = ''
const screenshotPreview = createScreenshotPreview({
  getCachedSnapshot: () => workspace.screenshot,
  cacheSnapshot: (snapshot) => {
    workspace.screenshot = snapshot
  },
  fetchSnapshot: (options) =>
    axios.get(`${import.meta.env.VITE_HTTP_URL}/screenshot/latest`, options),
  getFirstFrameAspect: async (url) => {
    const image = new Image()
    image.src = url
    await image.decode()
    return image.naturalWidth / image.naturalHeight
  },
  onChange: (url, aspect) => {
    if (aspect) screenshot_aspect = aspect
    latest_screenshot_url = url
    if (url && animate_next_screenshot) {
      animate_next_screenshot = false
      transition_log_view(
        () => {
          if (sc_preview.value && !document.hidden && latest_screenshot_url === url)
            sc_blob.value = url
        },
        { panel: 'screenshot' }
      )
    } else {
      sc_blob.value = url
    }
  }
})

function updateScreenshotPreview() {
  if (sc_preview.value && !document.hidden) screenshotPreview.start()
  else screenshotPreview.stop()
}

watch(
  sc_preview,
  (enabled) => {
    localStorage.setItem('sc_preview', JSON.stringify(enabled))
    if (!enabled) workspace.screenshot = null
    updateScreenshotPreview()
    nextTick(apply_log_layout)
  },
  { flush: 'sync' }
)

watch(sc_blob, (url, previous) => {
  if (!url) railWidthReveal?.cancel()
  const container = log_layout.value
  const oldWidth =
    screenshot_entry.value === 'expand' && url && !previous && rail_mode.value && container?.animate
      ? globalThis.getComputedStyle?.(container).getPropertyValue('--log-rail-track').trim()
      : null
  nextTick(() => {
    apply_log_layout()
    if (
      !oldWidth ||
      log_layout.value !== container ||
      screenshot_entry.value !== 'expand' ||
      !rail_mode.value ||
      reduced_log_motion()
    )
      return
    const width = container.style.getPropertyValue('--log-rail-w')
    if (width === oldWidth) return
    railWidthReveal?.cancel()
    railWidthReveal = container.animate(
      [{ '--log-rail-track': oldWidth }, { '--log-rail-track': width }],
      STARTUP_REVEAL
    )
  })
})

watch(
  plan_condition,
  () => {
    nextTick(apply_log_layout)
  },
  { deep: true }
)

watch(
  task_list,
  () => {
    operator_hint.value = null
    nextTick(apply_log_layout)
  },
  { deep: true }
)
watch(
  show_task_table,
  (visible) => {
    if (!visible) {
      operator_hint.value = null
      task_date_hint.value = null
    }
    nextTick(apply_log_layout)
  },
  { flush: 'sync' }
)
watch(rail_active, () => nextTick(apply_log_layout))
watch(
  task_queue,
  (table) => {
    if (!table) return
    nextTick(() => {
      if (task_queue.value !== table) return
      apply_log_layout()
      if (
        queue_entry.value !== 'expand' ||
        mobile.value ||
        !table.animate ||
        rail_mode.value ||
        reduced_log_motion()
      )
        return
      const height = table.getBoundingClientRect().height / logLayoutZoom(table)
      if (!height) return
      const handle = log_layout.value?.querySelector('.log-resizer-task')
      queueRevealAnimations = [
        table.animate([{ height: '0px' }, { height: `${height}px` }], STARTUP_REVEAL),
        handle?.animate?.([{ height: '0px' }, { height: `${RESIZER_HEIGHT}px` }], STARTUP_REVEAL)
      ]
    })
  },
  { flush: 'post' }
)
watch(mobile, () => {
  show_view_controls.value = false
  nextTick(apply_log_layout)
})

workspace.restoreDailyStatus()
const { dailyStatus: daily_status } = storeToRefs(workspace)
const daily_status_loading = ref(false)
const daily_view_selected = ref(workspace.dailyView)
const daily_status_always_visible = computed(() => rail_layout.value && !mobile.value)
const daily_toggle_available = computed(
  () =>
    show_daily_tasks.value &&
    running.value &&
    !daily_status_always_visible.value &&
    hasDailyStatusTasks(config_store)
)
const daily_view_visible = computed(() => daily_toggle_available.value && daily_view_selected.value)
const daily_slot = computed(() => (daily_view_visible.value ? 'alternate' : 'header'))
const daily_status_enabled = computed(
  () =>
    show_daily_tasks.value &&
    running.value &&
    (daily_status_always_visible.value || daily_view_visible.value)
)
watch(daily_toggle_available, (available) => {
  if (!available) daily_view_selected.value = false
})
const daily_items = computed(() =>
  daily_status_enabled.value && daily_status.value?.source === 'live'
    ? getDailyStatusItems(config_store, daily_status.value.records ?? {})
    : []
)
// 日志上方的日期取最新一条日志行的日期，而不是游戏日。
const log_date = computed(() => {
  for (let index = log_lines.value.length - 1; index >= 0; index -= 1) {
    const line = log_lines.value[index]
    const text = typeof line === 'string' ? line : line?.text
    const match = /^(\d{4}-\d{2}-\d{2})/u.exec(String(text ?? ''))
    if (match) return match[1]
  }
  return ''
})
let dailyStatusTimer
let dailyStatusExpiryTimer
let dailyStatusController
function schedule_daily_status_expiry() {
  clearTimeout(dailyStatusExpiryTimer)
  const now = Date.now()
  const expiry = dailyStatusExpiry(daily_status.value, now)
  if (expiry === null) {
    daily_status.value = null
    return
  }
  dailyStatusExpiryTimer = setTimeout(schedule_daily_status_expiry, expiry - now)
}
async function refresh_daily_status() {
  if (!daily_status_enabled.value || document.hidden) return
  schedule_daily_status_expiry()
  dailyStatusController?.abort()
  const controller = new AbortController()
  dailyStatusController = controller
  daily_status_loading.value = true
  try {
    const { data } = await axios.get(`${import.meta.env.VITE_HTTP_URL}/daily-status`, {
      signal: controller.signal,
      timeout: 10000
    })
    if (controller.signal.aborted) return
    const status = dailyStatusExpiry(data) === null ? null : data
    if (animate_next_daily_status && status?.source === 'live') {
      animate_next_daily_status = false
      await transition_log_view(() => {
        if (!controller.signal.aborted && daily_status_enabled.value && !document.hidden)
          daily_status.value = dailyStatusExpiry(status) === null ? null : status
      })
    } else {
      daily_status.value = status
    }
  } catch {
    if (!controller.signal.aborted) daily_status.value = null
  } finally {
    if (dailyStatusController === controller) {
      schedule_daily_status_expiry()
      dailyStatusController = undefined
      daily_status_loading.value = false
    }
  }
}
function stop_daily_status() {
  clearInterval(dailyStatusTimer)
  clearTimeout(dailyStatusExpiryTimer)
  dailyStatusTimer = undefined
  dailyStatusController?.abort()
  dailyStatusController = undefined
  daily_status_loading.value = false
}
function schedule_daily_status() {
  stop_daily_status()
  if (!daily_status_enabled.value || document.hidden) return
  void refresh_daily_status()
  dailyStatusTimer = setInterval(refresh_daily_status, 30000)
}
watch(daily_status_enabled, (enabled) => {
  if (!enabled) daily_status.value = null
  schedule_daily_status()
})
watch(worker_status, () => void refresh_daily_status())

let runningTimer
function refresh_visible_status() {
  const day = browser_calendar_day()
  if (day !== task_calendar_day.value) task_date_hint.value = null
  task_calendar_day.value = day
  void get_running()
}

function updatePageVisibility(event) {
  if (event && document.hidden) {
    startup_reveal.value = false
    animate_next_screenshot = false
    animate_next_daily_status = false
    cancel_log_entry_animations()
    finish_log_view_transition()
  }
  page_visible.value = !document.hidden
  updateScreenshotPreview()
  clearInterval(runningTimer)
  schedule_daily_status()
  if (document.hidden) {
    task_date_hint.value = null
    stop_task_polling()
    return
  }
  start_task_polling()
  refresh_visible_status()
  runningTimer = setInterval(refresh_visible_status, 5000)
}

onMounted(() => {
  workspace.visited = true
  void logBackground.load()
  const savedPreviewState = localStorage.getItem('sc_preview')
  if (savedPreviewState !== null) {
    sc_preview.value = JSON.parse(savedPreviewState)
  }
  document.addEventListener('visibilitychange', updatePageVisibility)
  updatePageVisibility()
  apply_log_layout()
  layoutObserver = new ResizeObserver(apply_log_layout)
  if (log_layout.value) layoutObserver.observe(log_layout.value)
  if (action_bar.value) layoutObserver.observe(action_bar.value)
  restore_log_layout()
  db_load_stats()
})

onBeforeUnmount(finish_log_view_transition)
onUnmounted(() => {
  workspace.layout = { ...layout_preference }
  workspace.wideLayout = rail_layout.value
  workspace.mobileScreenshotHeight = mobile_screenshot_height
  workspace.dailyView = daily_view_visible.value
  if (!daily_status_enabled.value) daily_status.value = null
  task_dialog_active = false
  cancel_layout_resize?.()
  cancel_log_entry_animations()
  stop_task_polling()
  clearInterval(runningTimer)
  stop_daily_status()
  document.removeEventListener('visibilitychange', updatePageVisibility)
  layoutObserver?.disconnect()
  screenshotPreview.stop()
})

function start(value) {
  running.value = true
  clear_legacy_logs()
  if (value == undefined) {
    value = '0'
  }
  axios.get(`${import.meta.env.VITE_HTTP_URL}/start/${value}`)
  get_tasks()
}

function stop() {
  waiting.value = true
  axios.get(`${import.meta.env.VITE_HTTP_URL}/stop`).then((response) => {
    running.value = !response.data
    waiting.value = false
  })
}

import StopIcon from '@vicons/ionicons5/es/StopCircleOutline'
import PlayIcon from '@vicons/ionicons5/es/PlayOutline'
import AddIcon from '@vicons/ionicons5/es/AddCircleOutline'
import LayersOutlineIcon from '@vicons/ionicons5/es/LayersOutline'
import ScreenshotIcon from '@vicons/tabler/es/Photo'
import FollowLogIcon from '@/components/FollowLogIcon.vue'
import DetailedLogIcon from '@vicons/tabler/es/ListDetails'
import ConciseLogIcon from '@vicons/tabler/es/List'
import TaskListIcon from '@vicons/tabler/es/ListNumbers'
import DailyTasksIcon from '@vicons/tabler/es/ListCheck'
import MoreIcon from '@vicons/tabler/es/Dots'
import DailyDoneIcon from '@vicons/ionicons5/es/CheckmarkCircle'
import DailyAttemptedIcon from '@vicons/ionicons5/es/AlertCircleOutline'
import DailyPendingIcon from '@vicons/ionicons5/es/EllipseOutline'
import DailyViewSwitchIcon from '@vicons/ionicons5/es/SwapHorizontalOutline'

const log_view_options = [
  {
    className: 'log-detail-mode-toggle',
    label: '简洁日志',
    state: log_concise,
    icon: DetailedLogIcon,
    activeIcon: ConciseLogIcon,
    enableTitle: '切换到简洁日志',
    disableTitle: '切换到详细日志'
  },
  {
    className: 'task-table-toggle',
    label: '任务列表',
    state: show_task_table,
    icon: TaskListIcon,
    enableTitle: '显示任务列表',
    disableTitle: '隐藏任务列表'
  },
  {
    className: 'daily-tasks-toggle',
    label: '今日任务',
    state: show_daily_tasks,
    icon: DailyTasksIcon,
    enableTitle: '显示今日任务',
    disableTitle: '隐藏今日任务'
  },
  {
    className: 'screenshot-toggle',
    label: '预览截图',
    state: sc_preview,
    icon: ScreenshotIcon,
    enableTitle: '显示截图预览',
    disableTitle: '隐藏截图预览'
  },
  {
    className: 'scroll-toggle',
    label: '跟随最新日志',
    state: auto_scroll,
    icon: FollowLogIcon,
    enableTitle: '跟随最新日志',
    disableTitle: '停止跟随最新日志'
  }
]

function toggle_log_view({ className, state }) {
  finish_log_view_transition()
  const enabled = !state.value
  const update = () => {
    if (className === 'screenshot-toggle' || className === 'task-table-toggle')
      startup_reveal.value = false
    state.value = enabled
    if (className === 'task-table-toggle')
      localStorage.setItem('log_show_task_table', String(enabled))
  }
  if (className === 'screenshot-toggle') {
    animate_next_screenshot = enabled
    if (!enabled && has_screenshot.value) transition_log_view(update, { panel: 'screenshot' })
    else update()
  } else if (
    className === 'task-table-toggle' &&
    (task_list.value.length || plan_condition.value.length)
  ) {
    transition_log_view(update, { panel: 'queue' })
  } else if (className === 'daily-tasks-toggle') {
    const wide = daily_status_always_visible.value
    const available = running.value && hasDailyStatusTasks(config_store)
    animate_next_daily_status = enabled && wide && available
    if (daily_items.value.length || (!wide && available)) transition_log_view(update)
    else update()
  } else update()
}

function toggle_daily_view() {
  transition_log_view(() => (daily_view_selected.value = !daily_view_selected.value))
}

const daily_states = {
  done: { icon: DailyDoneIcon, label: '今日已处理（按调度记录）', summary: '已处理' },
  attempted: { icon: DailyAttemptedIcon, label: '今日已尝试，尚未完成', summary: '已尝试' },
  pending: { icon: DailyPendingIcon, label: '今日尚未完成', summary: '未处理' }
}
const dailyState = (state) =>
  Object.hasOwn(daily_states, state)
    ? daily_states[state]
    : { icon: DailyPendingIcon, label: '处理结果未确认', summary: '未确认' }

const show_task = ref(false)
const TaskDialog = shallowRef(null)
const task_dialog_loading = ref(false)
let task_dialog_active = true
async function openTaskDialog() {
  if (task_dialog_loading.value) return
  if (TaskDialog.value) {
    show_task.value = true
    return
  }
  task_dialog_loading.value = true
  try {
    const { default: component } = await import('@/components/TaskDialog.vue')
    if (!task_dialog_active) return
    TaskDialog.value = component
    show_task.value = true
  } catch {
    if (task_dialog_active) db_message.error('新增任务表单加载失败，请点击「新增任务」重试')
  } finally {
    if (task_dialog_active) task_dialog_loading.value = false
  }
}
const add_task = ref(true)
provide('show_task', show_task)
provide('add_task', add_task)
const { theme: themePreference } = storeToRefs(config_store)
const theme = useResolvedTheme(themePreference)
function revealTaskQueue() {
  finish_log_view_transition()
  show_task_table.value = true
  nextTick(() => {
    apply_log_layout()
    task_queue.value?.scrollIntoView?.({ block: 'nearest' })
  })
}
watch(
  () => route?.hash,
  (hash) => {
    if (/^#task-(devices|runtime|base|daily|long|accounts|maa)$/.test(hash || ''))
      router?.replace({ name: 'settings', query: route?.query, hash })
    else if (hash === '#task-queue') revealTaskQueue()
  },
  { immediate: true }
)

// 深色背景上的浅色立绘更显眼，透明度略低于浅色主题，避免干扰日志文字。
const bg_opacity = computed(() => {
  const opacity = theme.value === 'light' ? 0.2 : 0.16
  return mobile.value ? opacity * 0.6 : opacity
})

function stop_maa() {
  axios.get(`${import.meta.env.VITE_HTTP_URL}/stop-maa`)
}

const process_control = ref(null)
const round_stop_busy = ref(false)
async function toggle_round_stop() {
  if (round_stop_busy.value || waiting.value) return
  round_stop_busy.value = true
  try {
    await mower_store.set_stop_after_round(!stop_after_round.value)
  } catch (error) {
    db_message.error(error.response?.data?.error || '设置本轮结束后停止失败')
  } finally {
    round_stop_busy.value = false
  }
}
const stop_options = computed(() => [
  ...(maintenance_pause.value
    ? [{ label: '立即停止', key: 'immediate', disabled: waiting.value }]
    : []),
  {
    label: stop_after_round.value ? '取消本轮结束后停止' : '本轮结束后停止',
    key: 'after_round',
    disabled: round_stop_busy.value || waiting.value,
    props: { title: '完成本轮操作，在正常休息前停止；已在正常休息时直接停止。' }
  },
  {
    label: '停止MAA',
    key: 'maa'
  },
  {
    label: '应用排班',
    key: 'apply_schedule',
    disabled: !process_control.value?.canApplySchedule,
    props: { title: '保存配置并停止当前任务，保留心情和位置，按当前排班重新生成任务。' }
  },
  {
    label: '重启续接',
    key: 'restart_resume',
    disabled: !process_control.value?.canRunProcessAction,
    props: { title: '保存配置并重启当前实例，保留原任务队列继续运行。' }
  }
])

function select_stop_action(key) {
  if (key === 'immediate') return stop()
  if (key === 'after_round') return toggle_round_stop()
  if (key === 'maa') return stop_maa()
  if (key === 'apply_schedule') {
    if (process_control.value?.canApplySchedule) return process_control.value.applySchedule()
    return
  }
  if (!process_control.value?.canRunProcessAction) return
  if (key === 'restart_resume') return process_control.value.restartResume()
}
const start_options = [
  {
    label: '载入心情任务',
    key: '0',
    props: { title: '继续上次任务：保留心情、位置和原任务队列。' }
  },
  {
    label: '载入心情数据',
    key: '1',
    props: {
      title: '按当前排班重排：保留心情、位置，清空旧任务后重新生成任务。修改排班后使用。'
    }
  },
  {
    label: '缓存清零重启',
    key: '2',
    props: { title: '重新读取现场：不使用旧运行缓存，重新读取心情和位置。' }
  }
]

// --- 数据库管理：按类删除不需要的数据（只删行，绝不动表结构） ---
const db_groups = [
  {
    key: 'mastery',
    label: '全自动专精',
    items: ['mastery_plan', 'mastery_route', 'mastery_notify']
  },
  {
    key: 'record',
    label: '运行数据',
    items: [
      'log',
      'agent_action',
      'operation_history',
      'trading_history',
      'inventory',
      'saved_state'
    ]
  }
]
const db_cat_labels = {
  mastery_plan: '专精计划',
  mastery_route: '专精路线配置',
  mastery_notify: '专精通知记录',
  log: '错误日志',
  agent_action: '干员心情记录',
  operation_history: '刷图记录',
  trading_history: '跑单记录',
  inventory: '仓库库存',
  saved_state: '运行缓存'
}
const db_stats = ref({})
const db_sel = ref({})
const db_dialog = useDialog()
const db_message = useMessage()
const show_db_admin = ref(false)
const db_maintenance = ref(null)
const db_limit = ref(null)
const db_busy = ref(false)
const db_loading = ref(false)
const db_error = ref('')
const db_result = ref('')
for (const g of db_groups) for (const k of g.items) db_sel.value[k] = false
const db_group = computed(() => {
  const out = {}
  for (const g of db_groups) {
    const vals = g.items.map((k) => db_sel.value[k])
    out[g.key] = {
      checked: vals.every(Boolean),
      indeterminate: vals.some(Boolean) && !vals.every(Boolean)
    }
  }
  return out
})
const db_all = computed(() => {
  const vals = Object.values(db_sel.value)
  return { checked: vals.every(Boolean), indeterminate: vals.some(Boolean) && !vals.every(Boolean) }
})
const db_any_selected = computed(() => Object.values(db_sel.value).some(Boolean))

async function db_load_stats() {
  if (db_loading.value) return
  db_loading.value = true
  db_error.value = ''
  try {
    const [counts, maintenance] = await Promise.all([
      axios.get(`${import.meta.env.VITE_HTTP_URL}/db-admin/stats`),
      axios.get(`${import.meta.env.VITE_HTTP_URL}/db-admin/maintenance`)
    ])
    db_stats.value = counts.data || {}
    db_maintenance.value = maintenance.data
    db_limit.value = maintenance.data.backup_limit_mib
  } catch (e) {
    db_maintenance.value = null
    db_error.value = `读取数据库信息失败：${e?.response?.data?.message || e.message || ''}`
  } finally {
    db_loading.value = false
  }
}
function db_format_size(bytes) {
  return `${(bytes / (1024 * 1024)).toFixed(2)} MiB`
}
async function db_maintain(operation) {
  if (db_busy.value || db_loading.value) return
  db_busy.value = true
  db_error.value = ''
  db_result.value = ''
  try {
    const base = `${import.meta.env.VITE_HTTP_URL}/db-admin`
    const options = { headers: { 'X-Mower-Settings': '1' } }
    const { data } =
      operation === 'compact'
        ? await axios.post(`${base}/compact`, {}, options)
        : await axios.put(`${base}/backup-limit`, { backup_limit_mib: db_limit.value }, options)
    db_maintenance.value = data
    db_limit.value = data.backup_limit_mib
    db_result.value =
      operation === 'compact'
        ? `整理完成：${db_format_size(data.before_bytes)} → ${db_format_size(data.after_bytes)}`
        : `备份大小上限已保存为 ${data.backup_limit_mib} MiB`
  } catch (e) {
    db_error.value = e?.response?.data?.message || e.message || '数据库维护失败，请重试'
  } finally {
    db_busy.value = false
  }
}
function db_toggle_panel() {
  show_view_controls.value = false
  show_db_admin.value = !show_db_admin.value
  if (show_db_admin.value) db_load_stats() // 打开时刷新条数
}
function db_toggle_group(gkey, value) {
  db_groups.find((g) => g.key === gkey).items.forEach((k) => (db_sel.value[k] = value))
}
function db_toggle_all(value) {
  Object.keys(db_sel.value).forEach((k) => (db_sel.value[k] = value))
}
function db_selected_keys() {
  return Object.keys(db_sel.value).filter((k) => db_sel.value[k])
}
function db_confirm_delete() {
  const keys = db_selected_keys()
  if (!keys.length) return
  const active = keys.includes('mastery_plan') ? db_stats.value.mastery_plan_active || 0 : 0
  const content =
    active > 0
      ? `确定删除选中的 ${keys.length} 类数据？其中专精计划有 ${active} 条正在训练，会一起删掉（练完可能收到一条「训练室占用」提醒）。`
      : `确定删除选中的 ${keys.length} 类数据？删除后不可恢复。`
  db_dialog.warning({
    title: '删除确认',
    content,
    positiveText: '删除',
    negativeText: '取消',
    onPositiveClick: () => db_delete(keys)
  })
}
async function db_delete(keys) {
  if (db_busy.value) return
  db_busy.value = true
  try {
    await axios.post(`${import.meta.env.VITE_HTTP_URL}/db-admin/delete`, { categories: keys })
    await db_load_stats()
    keys.forEach((k) => (db_sel.value[k] = false))
    db_message.success('删除成功')
  } catch (e) {
    db_message.error(`删除失败：${e?.response?.data?.error || e.message || ''}`)
  } finally {
    db_busy.value = false
  }
}
</script>

<template>
  <div
    class="home-container"
    :class="{
      'home-container--mobile': mobile,
      'home-container--rail': rail_mode
    }"
  >
    <div
      class="log-bg"
      :style="{ backgroundImage: `url('${logBackground.url}')` }"
      aria-hidden="true"
    ></div>
    <section
      ref="log_layout"
      class="log-pane"
      :class="{
        'with-screenshot': has_screenshot,
        'has-tasks': task_table_visible,
        'log-pane--rail': rail_mode,
        'log-pane--reveal-screenshot': screenshot_entry,
        'log-pane--expand-screenshot': screenshot_entry === 'expand',
        'log-pane--reveal-queue': queue_entry,
        'log-pane--expand-rail': rail_entry === 'expand'
      }"
      aria-label="运行日志"
      @animationend.self="apply_log_layout"
    >
      <n-image
        v-if="has_screenshot"
        class="log-screenshot"
        :src="sc_blob"
        object-fit="contain"
        @load="screenshot_loaded"
      />
      <div
        v-if="has_screenshot"
        class="log-resizer log-resizer-sc"
        @pointerdown="(event) => resize_log_pane(event, 'screenshot')"
      ></div>

      <div v-if="show_task_table && plan_condition.length > 0" class="plan-condition">
        <span class="plan-condition-label">当前激活的副表为： </span>
        <span v-for="(x, index) in plan_condition" :key="index" class="plan-condition-name">
          {{ x }}
        </span>
      </div>
      <div
        v-if="task_list.length > 0"
        v-show="task_table_visible"
        :id="`${toolbar_id}-queue`"
        ref="task_queue"
        class="task-table-scroll"
        role="region"
        aria-label="任务列表"
      >
        <n-table
          class="task-table"
          :class="{ 'task-table--names': show_task_names }"
          size="small"
          :bordered="show_task_names"
          :single-line="!show_task_names"
        >
          <thead>
            <tr>
              <th class="task-time"><span class="task-time-label">时间</span></th>
              <th :colspan="show_task_names ? 2 : undefined">任务</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="{
                task,
                clock,
                day,
                heading,
                mastery,
                actions,
                roomEntries,
                roomId,
                roomAgents,
                roomIndex = 0,
                refreshTargets,
                key
              } in task_rows"
              :key="key"
              class="task-group-start"
            >
              <td
                v-if="roomIndex === 0"
                class="task-time"
                :rowspan="show_task_names && roomEntries.length ? roomEntries.length : undefined"
              >
                <n-popover
                  v-if="day && day !== task_calendar_day"
                  :show="task_date_hint === key"
                  trigger="click"
                  placement="top"
                  @update:show="set_task_date_hint(key, $event)"
                >
                  <template #trigger>
                    <button
                      type="button"
                      class="task-date-trigger"
                      :aria-label="`${day} ${clock}`"
                      :aria-expanded="task_date_hint === key"
                      @pointerenter="
                        $event.pointerType === 'mouse' && set_task_date_hint(key, true)
                      "
                      @pointerleave="
                        $event.pointerType === 'mouse' && set_task_date_hint(key, false)
                      "
                      @keydown.esc.stop="set_task_date_hint(key, false)"
                    >
                      <time :datetime="task.time">{{ clock }}</time>
                    </button>
                  </template>
                  {{ day }} {{ clock }}
                </n-popover>
                <time v-else :datetime="task.time" :title="day">{{ clock }}</time>
                <template v-if="show_task_names && roomEntries.length">
                  <div v-if="task.emergency_recovery_release">自动救急</div>
                  <div v-else-if="task.emergency_staffing">自动救急换班</div>
                  <div v-else-if="task.emergency_dorm">自动救急宿舍安排</div>
                </template>
              </td>
              <template v-if="show_task_names">
                <template v-if="roomIndex < roomEntries.length">
                  <td>{{ roomId }}</td>
                  <td>
                    {{
                      Array.isArray(roomAgents)
                        ? roomAgents.map((name) => name || '_').join(', ')
                        : ''
                    }}
                  </td>
                </template>
                <td v-else colspan="2">
                  {{
                    task.display_name ||
                    (typeof task.type === 'string' ? task.type : task.type?.display_value)
                  }}{{ task.meta_data ? ' ' + task.meta_data : '' }}
                </td>
              </template>
              <td v-else class="task-content">
                <div class="task-heading">
                  <TaskActionSubjects
                    v-if="actions.length"
                    :actions="actions"
                    :facility-plan="plan"
                    :size="24"
                  />
                  <template v-for="(token, index) in heading" :key="index">
                    <button
                      v-if="!actions.length && token.type === 'operator'"
                      type="button"
                      class="task-operator-button"
                      :class="{ 'task-operator-button--named': token.showName }"
                      :aria-label="token.name"
                      :title="token.name"
                      @click="show_operator_hint(token.name, $event)"
                      @focus="show_operator_hint(token.name, $event)"
                      @blur="operator_hint = null"
                      @keydown.esc="operator_hint = null"
                    >
                      <log-operator
                        :name="token.name"
                        :show-name="token.showName"
                        :size="24"
                        :tabindex="-1"
                      />
                    </button>
                    <span
                      v-else-if="!actions.length && token.type === 'group'"
                      class="task-subject"
                      >{{ token.text }}</span
                    >
                    <span v-else-if="!actions.length">{{ token.text }}</span>
                  </template>
                </div>
                <div v-if="task.emergency_recovery_release" class="task-flag">自动救急</div>
                <div v-else-if="task.emergency_staffing" class="task-flag">自动救急换班</div>
                <div v-else-if="task.emergency_dorm" class="task-flag">自动救急宿舍安排</div>
                <div v-if="mastery" class="task-facilities">
                  <div v-if="mastery.room" class="task-room-label" :title="mastery.room">
                    {{ mastery.label }}
                  </div>
                  <div
                    class="task-mastery-detail"
                    :class="{ 'task-mastery-detail--unplaced': !mastery.room }"
                  >
                    <template v-for="(token, index) in mastery.tokens" :key="index">
                      <button
                        v-if="token.type === 'operator'"
                        type="button"
                        class="task-operator-button"
                        :aria-label="token.name"
                        :title="token.name"
                        @click="show_operator_hint(token.name, $event)"
                        @focus="show_operator_hint(token.name, $event)"
                        @blur="operator_hint = null"
                        @keydown.esc="operator_hint = null"
                      >
                        <log-operator :name="token.name" :size="24" :tabindex="-1" />
                      </button>
                      <span
                        v-else-if="token.type === 'mastery'"
                        class="task-mastery"
                        role="img"
                        :aria-label="token.text"
                        :title="token.text"
                        ><template v-for="(level, position) in token.levels" :key="position"
                          ><span v-if="position" aria-hidden="true"> → </span
                          ><img
                            :src="mastery_icons[level]"
                            width="20"
                            height="18"
                            alt=""
                            aria-hidden="true" /></template
                      ></span>
                      <span v-else>{{ token.text }}</span>
                    </template>
                  </div>
                </div>
                <div v-if="roomEntries.length" class="task-facilities">
                  <div v-for="[key, value] in roomEntries" :key="key" class="task-facility">
                    <div class="task-room-label" :title="key">
                      {{ queueTaskRoom(task, key, plan) }}
                    </div>
                    <div class="task-operators">
                      <button
                        v-for="(name, index) in value"
                        :key="index"
                        type="button"
                        class="task-operator-button"
                        :aria-label="operator_hint_name(name)"
                        :title="operator_hint_name(name)"
                        @click="show_operator_hint(name, $event)"
                        @focus="show_operator_hint(name, $event)"
                        @blur="operator_hint = null"
                        @keydown.esc="operator_hint = null"
                      >
                        <log-operator :name="name || '_'" :size="24" :tabindex="-1" />
                      </button>
                    </div>
                  </div>
                </div>
                <div v-if="refreshTargets.length" class="task-refresh-targets">
                  <div
                    v-for="(target, index) in refreshTargets"
                    :key="`${target.id}:${index}`"
                    class="task-room-label"
                    :title="target.id"
                  >
                    {{ target.label }}
                  </div>
                </div>
              </td>
            </tr>
          </tbody>
        </n-table>
      </div>
      <div
        v-if="task_list.length > 0"
        v-show="task_table_visible"
        class="log-resizer log-resizer-task"
        @pointerdown="(event) => resize_log_pane(event, 'task')"
      ></div>
      <log-output
        class="log"
        :lines="log_lines"
        :operator-names="operator_names"
        :facility-plan="plan"
        :compact="mobile"
        :concise="log_concise"
        :running="running"
        :auto-scroll="auto_scroll"
        :show-alternate-view="daily_view_visible"
      >
        <template v-if="daily_toggle_available" #title>
          <button
            class="log-daily-toggle"
            type="button"
            :aria-label="
              daily_view_visible ? '今日任务，切换到运行日志' : '运行日志，切换到今日任务'
            "
            @click="toggle_daily_view"
          >
            {{ daily_view_visible ? '今日任务' : '运行日志' }}
            <DailyViewSwitchIcon aria-hidden="true" />
          </button>
        </template>
        <template v-if="daily_view_visible || daily_items.length" #[daily_slot]>
          <div
            class="daily-status"
            :class="{ 'daily-status--view': daily_view_visible }"
            :role="daily_view_visible ? 'region' : 'group'"
            :aria-label="daily_view_visible ? '今日任务' : '任务状态'"
            :tabindex="daily_view_visible ? 0 : undefined"
            :title="
              daily_items.length
                ? `游戏日 ${daily_status.game_day}，北京时间每日凌晨 4 点开始新的游戏日`
                : undefined
            "
          >
            <p v-if="!daily_view_visible && log_date" class="daily-status__date">
              {{ log_date }}
            </p>
            <ul v-if="daily_items.length" class="daily-status__items" aria-label="任务概览">
              <li
                v-for="item in daily_items"
                :key="item.id"
                class="daily-status__item"
                :class="`daily-status__item--${item.state}`"
                :title="`${item.title}：${dailyState(item.state).label}`"
              >
                <n-icon
                  class="daily-status__icon"
                  :component="dailyState(item.state).icon"
                  aria-hidden="true"
                />
                <span class="daily-status__title">{{ item.title }}</span>
                <span class="daily-status__state">，{{ dailyState(item.state).label }}</span>
                <span v-if="daily_view_visible" class="daily-status__summary" aria-hidden="true">
                  {{ dailyState(item.state).summary }}
                </span>
              </li>
            </ul>
            <p v-else class="daily-status__empty" role="status">
              {{ daily_status_loading ? '正在读取今日任务…' : '暂无今日任务状态' }}
            </p>
          </div>
        </template>
      </log-output>
      <div
        v-if="rail_mode"
        class="log-resizer log-resizer-rail"
        role="separator"
        aria-orientation="vertical"
        aria-label="调整日志与右侧栏宽度"
        @pointerdown="resize_rail_column"
      ></div>
    </section>
    <n-popover
      v-if="operator_hint"
      :show="true"
      trigger="manual"
      placement="top"
      :x="operator_hint.x"
      :y="operator_hint.y"
      :show-arrow="false"
      @clickoutside="operator_hint = null"
    >
      {{ operator_hint.name }}
    </n-popover>
    <div class="log-toolbar">
      <div
        ref="action_bar"
        class="action-container"
        :class="{ 'action-container--paused': running && maintenance_pause }"
      >
        <div class="action-buttons" role="group" aria-label="运行操作">
          <div class="execution-control">
            <drop-down
              v-if="running"
              glass-menu
              :select="select_stop_action"
              :options="stop_options"
              :type="maintenance_pause ? 'warning' : 'error'"
              :up="true"
              menu-label="停止选项"
              :disabled="waiting"
            >
              <n-button
                v-if="maintenance_pause"
                type="warning"
                @click="cancel_pause"
                :loading="cancelling_pause"
                :disabled="waiting || cancelling_pause"
              >
                <template #icon>
                  <n-icon><play-icon /></n-icon>
                </template>
                <span class="btn-text">取消暂停</span>
              </n-button>
              <n-button v-else type="error" @click="stop" :loading="waiting" :disabled="waiting">
                <template #icon>
                  <n-icon>
                    <stop-icon />
                  </n-icon>
                </template>
                <span class="btn-text">立即停止</span>
              </n-button>
            </drop-down>
            <div v-if="running && maintenance_pause" class="maintenance-pause-notice" role="status">
              <n-text type="warning">计划暂停中，设定结束时间 {{ pause_end }}</n-text>
            </div>
            <n-text
              v-if="running && stop_after_round"
              type="warning"
              class="round-stop-notice"
              role="status"
            >
              将在本轮结束后停止
            </n-text>
            <start-schedule
              v-if="!running"
              glass-menu
              :start="start"
              :start-options="start_options"
              :waiting="waiting"
            />
          </div>
          <div class="task-action">
            <n-button
              class="add-task-action"
              type="warning"
              aria-label="新增任务"
              title="新增任务"
              :loading="task_dialog_loading"
              @click="openTaskDialog"
            >
              <template #icon>
                <n-icon>
                  <add-icon />
                </n-icon>
              </template>
              <span class="btn-text">新增任务</span>
            </n-button>
          </div>
          <n-button
            class="database-action"
            type="info"
            aria-label="数据库管理"
            title="数据库管理"
            @click="db_toggle_panel"
          >
            <template #icon>
              <n-icon>
                <layers-outline-icon />
              </n-icon>
            </template>
            <span v-if="!mobile" class="btn-text">数据库管理</span>
          </n-button>
        </div>
        <div class="process-status" aria-live="polite">
          <ProcessControl ref="process_control" compact :running="running" />
        </div>
      </div>
      <div class="log-view-controls" role="group" aria-label="日志显示选项">
        <div v-if="!mobile" class="view-toggle-island">
          <n-button
            v-for="option in log_view_options"
            :key="option.className"
            text
            class="view-toggle"
            :class="option.className"
            :aria-label="option.label"
            :aria-pressed="option.state.value"
            :aria-controls="
              option.className === 'task-table-toggle' && task_list.length
                ? `${toolbar_id}-queue`
                : undefined
            "
            :title="option.state.value ? option.disableTitle : option.enableTitle"
            @click="toggle_log_view(option)"
          >
            <template #icon>
              <span :class="{ 'view-toggle-icon': !option.activeIcon }">
                <n-icon :component="(option.state.value && option.activeIcon) || option.icon" />
              </span>
            </template>
          </n-button>
        </div>
        <n-popover
          v-else
          v-model:show="show_view_controls"
          trigger="click"
          placement="top-end"
          :show-arrow="false"
          :internal-trap-focus="true"
          @clickoutside="dismiss_view_controls"
          :theme-overrides="{
            padding: '4px',
            borderRadius: '999px',
            color: theme === 'dark' ? 'rgba(38, 40, 46, 0.96)' : 'rgba(255, 255, 255, 0.96)'
          }"
          style="backdrop-filter: blur(20px) saturate(1.1)"
        >
          <template #trigger>
            <div class="view-options-anchor">
              <n-button
                text
                class="view-options-trigger"
                aria-label="日志显示选项"
                title="日志显示选项"
                aria-haspopup="dialog"
                :aria-expanded="show_view_controls"
                :aria-controls="`${toolbar_id}-view-controls`"
              >
                <template #icon><n-icon :component="MoreIcon" /></template>
              </n-button>
            </div>
          </template>
          <div
            :id="`${toolbar_id}-view-controls`"
            class="log-view-actions"
            role="dialog"
            aria-label="日志显示选项"
          >
            <n-button
              v-for="option in log_view_options"
              :key="option.className"
              text
              class="view-toggle"
              :class="option.className"
              :aria-label="option.label"
              :aria-pressed="option.state.value"
              :aria-controls="
                option.className === 'task-table-toggle' && task_list.length
                  ? `${toolbar_id}-queue`
                  : undefined
              "
              :title="option.state.value ? option.disableTitle : option.enableTitle"
              @click="toggle_log_view(option)"
            >
              <template #icon>
                <span :class="{ 'view-toggle-icon': !option.activeIcon }">
                  <n-icon :component="(option.state.value && option.activeIcon) || option.icon" />
                </span>
              </template>
            </n-button>
          </div>
        </n-popover>
      </div>
    </div>
    <component :is="TaskDialog" v-if="TaskDialog" />
    <n-modal
      v-model:show="show_db_admin"
      preset="card"
      transform-origin="center"
      style="width: min(480px, calc(100vw - 32px)); max-height: calc(100dvh - 48px)"
      content-style="overflow: auto"
    >
      <template #header>
        <div>数据库管理</div>
      </template>
      <div class="db-maintenance">
        <template v-if="db_maintenance">
          <p>
            数据库 {{ db_format_size(db_maintenance.database_bytes) }}， 空闲页
            {{ db_format_size(db_maintenance.reclaimable_bytes) }}。
          </p>
          <p>
            删除记录后可整理数据库以回收空闲空间，保留现有记录。请先停止任务，整理可能需要一分钟。
          </p>
          <n-button
            :loading="db_busy"
            :disabled="db_busy || db_loading || running || db_maintenance.busy"
            @click="db_maintain('compact')"
            >整理数据库</n-button
          >
          <label class="db-limit-label" for="db-backup-limit">备份大小上限（MiB）</label>
          <div class="db-limit-actions">
            <n-input-number
              v-model:value="db_limit"
              :input-props="{ id: 'db-backup-limit' }"
              :min="1"
              :max="db_maintenance.max_backup_limit_mib"
              :precision="0"
              :disabled="db_busy || db_loading || running || db_maintenance.busy"
            />
            <n-button
              :loading="db_busy"
              :disabled="
                db_busy ||
                db_loading ||
                running ||
                db_maintenance.busy ||
                !db_limit ||
                db_limit === db_maintenance.backup_limit_mib
              "
              @click="db_maintain('limit')"
              >保存上限</n-button
            >
          </div>
          <p>
            默认 16 MiB，可设为 1–{{ db_maintenance.max_backup_limit_mib }} MiB。 同时限制
            ZIP、解压后的配置与数据总量，以及恢复前备份；调大上限会增加内存占用。
            设置仅用于当前实例，恢复备份或切换档案后仍保留。
          </p>
          <p v-if="running || db_maintenance.busy">
            请等待任务和其他维护操作结束后再整理或调整上限。
          </p>
        </template>
        <n-alert v-if="db_result" type="success" aria-live="polite">{{ db_result }}</n-alert>
        <n-alert v-if="db_error" type="error" aria-live="polite">{{ db_error }}</n-alert>
        <n-button :loading="db_loading" :disabled="db_busy || db_loading" @click="db_load_stats"
          >刷新数据库信息</n-button
        >
      </div>
      <div class="db-admin-body">
        <div class="db-admin-group" v-for="g in db_groups" :key="g.key">
          <n-checkbox
            :checked="db_group[g.key].checked"
            :indeterminate="db_group[g.key].indeterminate"
            @update:checked="(v) => db_toggle_group(g.key, v)"
          >
            {{ g.label }}
          </n-checkbox>
          <div class="db-admin-items">
            <div class="db-admin-item" v-for="k in g.items" :key="k">
              <n-checkbox :checked="db_sel[k]" @update:checked="(v) => (db_sel[k] = v)">
                {{ db_cat_labels[k] }}
              </n-checkbox>
              <span class="db-cat-count">{{ db_stats[k] ?? 0 }} 条</span>
            </div>
          </div>
        </div>
      </div>
      <template #footer>
        <div class="db-admin-footer">
          <n-checkbox
            :checked="db_all.checked"
            :indeterminate="db_all.indeterminate"
            @update:checked="db_toggle_all"
          >
            全选
          </n-checkbox>
          <n-button
            type="error"
            size="small"
            :disabled="db_busy || db_loading || !db_any_selected"
            @click="db_confirm_delete"
          >
            删除选中
          </n-button>
        </div>
      </template>
    </n-modal>
  </div>
</template>

<style scoped lang="scss">
@property --log-screenshot-entry {
  syntax: '<number>';
  inherits: false;
  initial-value: 1;
}

@property --log-rail-entry {
  syntax: '<number>';
  inherits: false;
  initial-value: 1;
}

@property --log-rail-track {
  syntax: '<length>';
  inherits: true;
  initial-value: 0px;
}

@keyframes reveal-log-screenshot {
  from {
    --log-screenshot-entry: 0;
  }
}

@keyframes reveal-log-rail {
  from {
    --log-rail-entry: 0;
  }
}

@keyframes reveal-log-preview {
  from {
    overflow: clip;
    opacity: 0.55;
  }
  to {
    overflow: clip;
    opacity: 1;
  }
}

@keyframes reveal-log-queue {
  from {
    opacity: 0.72;
  }
}

.home-container {
  /* 与 logLayout.js 的 RAIL_GAP 保持一致。 */
  --log-rail-gap: 24px;
  --log-stack-max-width: 480px;
  --log-stack-shot-max-height: min(45vh, 500px);
  --log-mono-font:
    'Cascadia Mono', Consolas, 'Microsoft YaHei', 'SF Mono', 'Menlo', 'PingFang SC', monospace;
  --log-rule: rgb(128 128 128 / 18%);
  --log-shot-shadow: 0 10px 28px -14px rgba(24, 25, 28, 0.45), 0 2px 6px rgba(24, 25, 28, 0.08);
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  grid-template-rows: minmax(120px, 1fr) auto;
  gap: 0;
  min-height: 0;
  overflow: hidden;
  position: relative;
  isolation: isolate;
}

.log-pane {
  --log-startup-reveal: v-bind(startupReveal);
  --log-resizer-size: 8px;
  --log-screenshot-tracks: 0px 0px;
  --log-task-row: 0px;
  --log-task-handle: 0px;
  grid-row: 1;
  z-index: 1;
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  grid-template-rows:
    var(--log-screenshot-tracks) auto var(--log-task-row) var(--log-task-handle)
    minmax(var(--log-min-h, 120px), 1fr);
  min-height: 0;
  min-width: 0;
  overflow: auto;
  position: relative;

  &.with-screenshot {
    --log-screenshot-tracks: calc(var(--log-sc-h, 270px) * var(--log-screenshot-entry, 1))
      calc(var(--log-resizer-size) * var(--log-screenshot-entry, 1));
  }

  &.has-tasks {
    --log-task-row: auto;
    --log-task-handle: auto;
  }
  &.log-pane--expand-screenshot {
    animation: reveal-log-screenshot var(--log-startup-reveal);
  }

  &.log-pane--expand-rail {
    animation: reveal-log-rail var(--log-startup-reveal);

    &.log-pane--expand-screenshot {
      animation:
        reveal-log-screenshot var(--log-startup-reveal),
        reveal-log-rail var(--log-startup-reveal);
    }
  }
}

.log-pane--reveal-screenshot .log-screenshot {
  animation: reveal-log-preview var(--log-startup-reveal);
}

.log-pane--reveal-queue .task-table-scroll {
  animation: reveal-log-queue var(--log-startup-reveal);
}

/* 宽屏右栏：截图在上，任务列表铺满下方，日志占左侧整列。 */
.home-container .log-pane.log-pane--rail {
  --log-rail-track: calc(var(--log-rail-w, 480px) * var(--log-rail-entry, 1));
  --log-rail-spacing: calc(var(--log-rail-gap) * var(--log-rail-entry, 1));
  grid-template-columns: minmax(0, 1fr) var(--log-rail-track);
  grid-template-rows: var(--log-screenshot-tracks) auto minmax(0, auto) minmax(0, 1fr);
  column-gap: var(--log-rail-spacing);
  overflow: hidden;

  .log-screenshot,
  .log-resizer-sc,
  .plan-condition,
  .task-table-scroll {
    grid-column: 2;
  }

  .plan-condition {
    padding: 2px 4px 6px;
  }

  .task-table-scroll {
    width: 100%;
    max-width: none;
    max-height: none;
  }

  .log-resizer-task {
    display: none;
  }

  .log {
    grid-column: 1;
    grid-row: 1 / -1;
  }

  .log-screenshot {
    justify-self: stretch;
    max-width: none;
    max-height: none;

    :deep(img) {
      width: var(--log-rail-w, 480px);
      height: var(--log-sc-h, 270px);
      max-width: none;
      max-height: none;
    }
  }
}

.home-container:not(.home-container--mobile) .log-pane:not(.log-pane--rail) {
  --log-stacked-task-width: min(100%, var(--log-stack-max-width));

  &.with-screenshot {
    --log-stacked-task-width: min(
      100%,
      var(--log-stack-max-width),
      calc(
        min(var(--log-sc-h, 270px), var(--log-stack-shot-max-height)) *
          var(--log-sc-aspect, calc(16 / 9))
      )
    );
  }

  .task-table-scroll,
  .log-resizer-task {
    max-width: var(--log-stacked-task-width);
  }
}

.log-screenshot {
  grid-row: 1;
  width: 100%;
  max-width: min(var(--log-stack-max-width), 100%);
  justify-self: start;
  align-self: start;
  height: 100%;
  min-height: 0;
  max-height: var(--log-stack-shot-max-height);
  border-radius: 8px;
  z-index: 15;

  :deep(img) {
    display: block;
    flex: none;
    align-self: flex-start;
    width: auto;
    height: auto;
    max-width: 100%;
    max-height: min(var(--log-sc-h, 270px), var(--log-stack-shot-max-height));
    border-radius: inherit;
    box-shadow: var(--log-shot-shadow);
  }
}

.log-resizer {
  width: 100%;
  height: var(--log-resizer-size);
  cursor: row-resize;
  position: relative;
  z-index: 25;
  touch-action: none;
  user-select: none;

  &::after {
    content: '';
    position: absolute;
    left: 0;
    right: 0;
    top: 50%;
    height: 1px;
    background: transparent;
    transition: background-color 0.15s ease;
  }

  &:active::after {
    background: color-mix(in srgb, var(--lg-focus) 45%, transparent);
  }
}

@media (hover: hover) and (pointer: fine) {
  .log-resizer:hover::after {
    background: color-mix(in srgb, var(--lg-focus) 45%, transparent);
  }
}

.log-resizer-sc {
  grid-row: 2;
  height: 100%;
}

/* 左右分栏时日志与右栏之间的纵向拖动手柄。 */
.log-resizer-rail {
  position: absolute;
  top: 0;
  right: calc(var(--log-rail-track) + (var(--log-rail-spacing) - 8px) / 2);
  bottom: 0;
  z-index: 30;
  width: 8px;
  height: auto;
  cursor: col-resize;

  &::after {
    top: 0;
    right: auto;
    bottom: 0;
    left: 50%;
    width: 1px;
    height: auto;
  }
}

.task-table-scroll {
  grid-row: 4;
  width: 100%;
  max-width: 100%;
  min-width: 0;
  min-height: 0;
  max-height: var(--log-task-h, min(240px, 28vh));
  overflow: auto;
  scrollbar-width: thin;
  justify-self: start;
}

/* 任务列表不预留滚动条空间；能悬停的设备只在悬停或键盘聚焦时显示滚动条。 */
@media (hover: hover) and (pointer: fine) {
  .task-table-scroll {
    scrollbar-color: transparent transparent;
  }

  .task-table-scroll:is(:hover, :focus-within) {
    scrollbar-color: var(--window-shell-scrollbar-thumb) transparent;
  }
}

.task-table {
  width: 100%;
  background: transparent;

  :deep(th),
  :deep(td) {
    background: transparent !important;
  }
}

.task-table--names {
  th {
    padding: 2px 16px;
  }

  td {
    height: 24px;
    padding: 2px 8px;

    &:last-child {
      width: 100%;
    }
  }
}

/* 头像列表只保留表头下沿和任务之间的细线，不画竖线和外框。 */
.task-table:not(.task-table--names) {
  table-layout: fixed;

  :deep(th),
  :deep(td) {
    border: 0 !important;
  }

  th {
    padding: 2px 8px 6px;
    color: var(--mower-text-muted, #8a9099);
    font-size: 12px;
    font-weight: 600;
    letter-spacing: 0.06em;
    border-bottom: 1px solid var(--log-rule) !important;
  }

  .task-time-label {
    position: relative;
    display: inline-block;

    &::before {
      content: '';
      position: absolute;
      inset-inline-start: -7px;
      top: 50%;
      width: 3px;
      height: 0.9em;
      border-radius: 1px;
      background: var(--lg-primary);
      transform: translateY(-50%);
    }
  }

  td {
    height: auto;
    padding: 4px 8px;
    line-height: 22px;
  }

  tbody tr.task-group-start:not(:first-child) td {
    border-top: 1px solid var(--log-rule) !important;
  }
}

.task-table:not(.task-table--names) .task-time {
  width: 64px;
  text-align: start;
  vertical-align: top;
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
}

.task-date-trigger {
  padding: 0;
  border: 0;
  background: none;
  color: inherit;
  font: inherit;
  cursor: pointer;
  text-decoration: underline dotted color-mix(in srgb, currentColor 35%, transparent);
  text-underline-offset: 3px;
}

.task-date-trigger:focus-visible {
  outline: 1px solid var(--mower-primary);
  outline-offset: 2px;
}

.task-content {
  min-width: 0;
  vertical-align: top;
}

.task-heading {
  font-size: 14px;
  font-weight: 600;
  line-height: 22px;
  overflow-wrap: anywhere;
}

.task-heading :deep(.task-action-subjects__people) {
  gap: 1px;
}

.task-heading :deep(.task-action-subjects__count) {
  margin-inline-start: 0;
  padding-inline: 2px;
}

.task-heading .task-operator-button {
  vertical-align: middle;
}

.task-heading .task-operator-button--named {
  margin-inline-start: 4px;
  border-radius: 4px;
}

.task-subject {
  color: var(--lg-primary);
  font-weight: 600;
}

.task-mastery {
  display: inline-flex;
  align-items: center;
  vertical-align: middle;
  white-space: nowrap;
}

.task-mastery img {
  width: 20px;
  height: 18px;
  object-fit: contain;
}

.task-mastery-detail {
  min-width: 0;
  overflow-wrap: anywhere;
}

.task-mastery-detail .task-operator-button {
  vertical-align: middle;
}

.task-mastery-detail--unplaced {
  grid-column: 1 / -1;
}

.task-facilities {
  display: grid;
  grid-template-columns: max-content minmax(0, 1fr);
  gap: 4px 8px;
  align-items: center;
  margin-top: 2px;
}

.task-refresh-targets {
  display: grid;
  gap: 4px;
  margin-top: 2px;
}

.task-facility {
  display: contents;
}

.task-flag {
  color: var(--lg-btn-warning-label);
  font-size: 12px;
  line-height: 16px;
}

.plan-condition {
  grid-row: 3;
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 4px 10px;
  min-height: 0;
  font-size: 13px;
}

.plan-condition-label {
  color: var(--mower-text-muted, #8a9099);
}

.plan-condition-name {
  color: var(--lg-primary);
}

.task-operators {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px;
}

.task-room-label {
  white-space: nowrap;
  font-size: 13px;
  line-height: 24px;
  font-weight: 400;
  color: var(--mower-text-muted, #8a9099);
}

.task-operator-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 24px;
  height: 24px;
  padding: 0;
  border: 0;
  border-radius: 50%;
  background: transparent;
  color: inherit;
  font: inherit;
  cursor: pointer;
  touch-action: manipulation;
}

.task-operator-button :deep(.log-operator) {
  display: inline-flex;
  align-items: center;
  line-height: 1;
}

.task-operator-button:focus-visible {
  outline: 2px solid var(--mower-primary, #18a058);
  outline-offset: 2px;
}

.log-resizer-task {
  grid-row: 5;
}

.log {
  grid-row: 6;
  height: 100% !important;
  min-height: 0;
  overflow: hidden;
}

.log-daily-toggle {
  display: inline-flex;
  flex: 0 0 var(--log-gutter);
  align-items: center;
  gap: 2px;
  min-height: 24px;
  padding: 0;
  border: 0;
  border-radius: 4px;
  background: transparent;
  color: inherit;
  font: inherit;
  font-size: 12px;
  white-space: nowrap;
  cursor: pointer;
  pointer-events: auto;
}

.log-daily-toggle:focus-visible {
  outline: 2px solid var(--lg-focus);
  outline-offset: -2px;
}

.log-daily-toggle svg {
  width: 12px;
  height: 12px;
  color: var(--mower-text-muted);
}

/* 日志上方的日期与今日任务：整体居中，透明波点底在四周浅出。 */
.daily-status {
  position: relative;
  display: flex;
  width: 100%;
  max-width: 100%;
  box-sizing: border-box;
  flex-direction: column;
  flex-shrink: 0;
  align-items: center;
  gap: 4px;
  margin-inline: auto;
  padding: 6px 24px 8px;
  border-radius: 10px;
  font-size: 12px;
  line-height: 18px;
}

.daily-status::before {
  content: '';
  position: absolute;
  inset: -8px -40px;
  background-image: radial-gradient(
    circle,
    color-mix(in srgb, currentColor 9%, transparent) 1px,
    transparent 1.2px
  );
  background-size: 12px 12px;
  -webkit-mask-image: radial-gradient(ellipse 55% 110% at 50% 50%, #000 25%, transparent 100%);
  mask-image: radial-gradient(ellipse 55% 110% at 50% 50%, #000 25%, transparent 100%);
  pointer-events: none;
}

.daily-status > * {
  position: relative;
  z-index: 1;
}

.daily-status__date {
  margin: 0;
  color: var(--mower-text-muted, #8a9099);
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.12em;
  font-variant-numeric: tabular-nums;
}

.daily-status__items {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 6px;
  max-height: 58px;
  width: 100%;
  overflow: hidden;
  margin: 0;
  padding: 0;
  list-style: none;
}

.daily-status--view {
  align-items: stretch;
  height: 100%;
  padding: 0 var(--log-scroll-padding) 8px var(--log-inset);
  overflow: auto;
  overscroll-behavior: contain;
}

.daily-status--view::before {
  content: none;
}

.daily-status--view .daily-status__items {
  display: block;
  max-height: none;
  overflow: visible;
}

.daily-status--view .daily-status__item {
  display: flex;
  gap: 8px;
  height: auto;
  min-height: 36px;
  padding: 6px 0;
  border: 0;
  border-bottom: 1px solid var(--log-rule);
  border-radius: 0;
  background: none;
  box-shadow: none;
  backdrop-filter: none;
  -webkit-backdrop-filter: none;
}

.daily-status__summary {
  margin-inline-start: auto;
  font-size: 11px;
}

.daily-status__empty {
  margin: 8px 0;
  color: var(--mower-text-muted);
}

.daily-status__item {
  --lg-btn-label: var(--lg-btn-neutral-label);
  --lg-btn-line: var(--lg-btn-neutral-line);
  --lg-btn-bg: var(--lg-btn-neutral-bg);
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  box-sizing: border-box;
  height: 26px;
  max-width: 100%;
  flex-shrink: 0;
  padding: 2px 9px 2px 6px;
  border: 0.5px solid var(--lg-btn-line);
  border-radius: 999px;
  color: var(--lg-btn-label);
  background-image: var(--lg-btn-sheen), var(--lg-btn-bg);
  backdrop-filter: blur(20px) saturate(1.1);
  -webkit-backdrop-filter: blur(20px) saturate(1.1);
  box-shadow: var(--lg-btn-shadow);
  white-space: nowrap;
}

.daily-status__item--done {
  --lg-btn-label: var(--lg-btn-primary-label);
  --lg-btn-line: var(--lg-btn-primary-line);
  --lg-btn-bg: var(--lg-btn-primary-bg);
}

.daily-status__item--attempted {
  --lg-btn-label: var(--lg-btn-warning-label);
  --lg-btn-line: var(--lg-btn-warning-line);
  --lg-btn-bg: var(--lg-btn-warning-bg);
}

.daily-status__item--pending,
.daily-status__item--unknown {
  .daily-status__icon {
    color: var(--mower-text-muted, #8a9099);
  }
}

.daily-status__title {
  overflow: hidden;
  text-overflow: ellipsis;
}

.daily-status__icon {
  font-size: 14px;
}

/* 状态文字只给读屏软件，视觉上由图标和颜色区分。 */
.daily-status__state {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
}

/* 操作按钮在左，截图预览与自动滚动开关在同一行右端，不再盖住右上角的截图。 */
.log-toolbar {
  grid-row: 2;
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.log-toolbar .action-container {
  flex: 1 1 auto;
}

.action-container {
  z-index: 1;
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
  min-width: 0;
  padding-top: 12px;
  margin-bottom: 4px;
  border-top: 1px solid rgb(128 128 128 / 16%);
  position: relative;

  :deep(.n-button) {
    white-space: nowrap;
    flex-shrink: 0;
  }
}

.action-buttons {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  min-width: 0;
}

.execution-control,
.task-action {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.execution-control :deep(.start-label) {
  display: inline;
}

.execution-control {
  position: relative;
}

.maintenance-pause-notice {
  position: absolute;
  bottom: calc(100% + 6px);
  left: 0;
  white-space: nowrap;
  font-size: 12px;
  line-height: 16px;
}

.round-stop-notice {
  position: absolute;
  top: calc(100% + 2px);
  left: 50%;
  transform: translateX(-50%);
  font-size: 10px;
  line-height: 10px;
  white-space: nowrap;
}

.log-view-controls,
.log-view-actions {
  --view-control-color: #5b5f66;
  --view-control-muted: #9298a1;
  --view-control-hover-bg: rgba(40, 37, 35, 0.07);
  --view-control-pressed-bg: rgba(40, 37, 35, 0.12);
}

.log-view-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px;
  max-width: calc(100vw - 32px);
}

.log-view-actions :deep(.n-button) {
  flex: 0 0 44px;
  min-width: 44px;
  min-height: 44px;
}

.log-view-controls {
  position: relative;
  z-index: 30;
  display: flex;
  flex: 0 0 auto;
  align-items: center;
  gap: 8px;
  margin-left: auto;
  padding-block: 6px 4px;
}

.view-toggle-island {
  display: inline-flex;
  align-items: center;
  gap: 0;
  padding: 3px;
  overflow: hidden;
}

.view-options-anchor {
  position: relative;
  display: inline-flex;
}

.view-options-anchor::before {
  content: '';
  position: absolute;
  inset: 4px;
  pointer-events: none;
}

.view-toggle-island,
.view-options-anchor::before {
  border: 0.5px solid rgba(24, 25, 28, 0.08);
  border-radius: 999px;
  background: linear-gradient(145deg, var(--lg-surface-top), var(--lg-surface-bottom));
  box-shadow: 0 3px 12px -4px rgba(24, 25, 28, 0.16);
}

html[data-mower-theme='dark'] .log-view-controls,
html[data-window-shell-theme='dark'] .log-view-controls,
html[data-mower-theme='dark'] .log-view-actions,
html[data-window-shell-theme='dark'] .log-view-actions {
  --view-control-color: #c1c5cc;
  --view-control-muted: #858b95;
  --view-control-hover-bg: rgba(255, 255, 255, 0.08);
  --view-control-pressed-bg: rgba(255, 255, 255, 0.13);
}

html[data-mower-theme='dark'] .view-toggle-island,
html[data-window-shell-theme='dark'] .view-toggle-island,
html[data-mower-theme='dark'] .view-options-anchor::before,
html[data-window-shell-theme='dark'] .view-options-anchor::before {
  border-color: rgba(244, 240, 229, 0.1);
  box-shadow: 0 3px 12px -4px rgba(0, 0, 0, 0.4);
}

.view-toggle-icon {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
}

.view-toggle[aria-pressed='false'] .view-toggle-icon::after {
  content: '';
  position: absolute;
  top: 50%;
  left: 50%;
  width: 1.5px;
  height: 26px;
  border-radius: 1px;
  background: currentColor;
  transform: translate(-50%, -50%) rotate(-45deg);
  pointer-events: none;
}

.home-container--mobile {
  --log-row-inset: 10px;
  --log-compact-time-column: 68px;
  width: 100%;
  height: 100%;
  padding: 0 16px 12px;
  box-sizing: border-box;

  .log-pane {
    --log-resizer-size: 24px;
  }

  .task-table :is(th, td) {
    padding-inline-start: var(--log-row-inset);
  }

  .task-table .task-time {
    box-sizing: border-box;
    width: var(--log-compact-time-column);
    min-width: var(--log-compact-time-column);
    max-width: var(--log-compact-time-column);
    padding-inline-end: 2px;
    text-align: start;
    vertical-align: top;
    white-space: normal;
    overflow-wrap: anywhere;
  }

  .task-time :is(time, .task-date-trigger) {
    font-family: var(--log-mono-font);
    font-size: 11px;
  }

  .task-table--names {
    border-inline-width: 0;
  }

  .log-resizer {
    color: var(--mower-text-muted, #8a9099);

    &::after {
      background: var(--log-rule);
    }

    &::before {
      content: '';
      position: absolute;
      z-index: 1;
      top: 50%;
      left: 50%;
      width: 28px;
      height: 3px;
      border-radius: 2px;
      background: currentColor;
      transform: translate(-50%, -50%);
    }

    &:active::before {
      color: var(--lg-primary);
    }
  }

  .log-screenshot {
    max-width: 100%;
    max-height: none;
    border-radius: 6px;

    :deep(img) {
      max-height: var(--log-sc-h, 270px);
    }
  }

  .log-toolbar {
    display: flex;
    flex-wrap: nowrap;
    align-items: center;
    gap: 8px;
  }

  .action-container {
    flex: 1 1 auto;
    gap: 8px;
    margin-inline: 0;
    padding-top: 8px;
  }

  .action-buttons {
    flex-wrap: nowrap;
  }

  .execution-control :deep(.n-button),
  .add-task-action,
  .database-action {
    min-height: 44px;
  }

  .add-task-action .btn-text {
    display: none;
  }

  .add-task-action,
  .database-action {
    display: inline-flex;
    width: 44px;
    padding-inline: 0;

    :deep(.n-button__icon) {
      margin: 0;
    }
  }

  .log-view-controls {
    position: static;
    padding-block: 8px 2px;
  }

  .log-view-controls :deep(.view-options-trigger) {
    min-width: 44px;
    min-height: 44px;
  }
}

@container main-content (max-width: 400px) {
  .home-container--mobile {
    padding-inline: 12px;

    .action-buttons {
      gap: 4px;
    }
  }
}

@container main-content (max-width: 380px) {
  .home-container--mobile {
    .log-toolbar,
    .action-buttons,
    .task-action {
      gap: 2px;
    }

    .add-task-action,
    .database-action {
      width: 30px;
      min-height: 38px;
    }
  }
}

.action-container.action-container--paused {
  padding-top: 28px;
}

.process-status {
  position: absolute;
  z-index: 5;
  bottom: calc(100% + 8px);
  left: 0;
  right: 0;
  max-height: min(50vh, 240px);
  overflow: auto;
  overflow-wrap: anywhere;

  &:empty {
    display: none;
  }

  &:not(:empty) {
    padding: 10px 12px;
    border: 1px solid var(--mower-border);
    border-radius: 8px;
    color: var(--mower-text);
    background: var(--mower-surface);
  }
}

/* 右栏布局时提示只盖住左侧日志：宽度不超过 logLayout.js 的 RAIL_LOG_MIN_WIDTH。 */
.home-container--rail .process-status {
  right: auto;
  width: max-content;
  max-width: min(100%, 440px);
}

.log-bg {
  content: '';
  width: 100%;
  height: 100%;
  position: absolute;
  z-index: 0;
  top: 0;
  left: 0;
  opacity: v-bind(bg_opacity);
  background-repeat: no-repeat;
  background-size: cover;
  background-position: 65% 50%;
  pointer-events: none;
}

/* 右栏布局时立绘只铺在左侧日志区，向截图和任务列表一侧渐隐。 */
.home-container--rail .log-bg {
  width: 74%;
  background-position: 50% 50%;
  -webkit-mask-image: linear-gradient(90deg, #000 58%, transparent);
  mask-image: linear-gradient(90deg, #000 58%, transparent);
}

.db-admin-body {
  .db-admin-group {
    display: flex;
    flex-direction: column;
    gap: 4px;
    padding: 4px 0;
  }

  .db-admin-items {
    display: flex;
    flex-direction: column;
    gap: 2px;
    padding-left: 24px;
  }

  .db-admin-item {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
  }

  .db-cat-count {
    opacity: 0.55;
    font-size: 12px;
    flex-shrink: 0;
  }
}

.db-admin-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.db-maintenance {
  display: grid;
  gap: 12px;
  margin-bottom: 20px;

  p {
    margin: 0;
    color: var(--mower-text-muted);
    font-size: 12px;
    line-height: 1.65;
  }
}

.db-limit-label {
  font-size: 14px;
}

.db-limit-actions {
  display: flex;
  gap: 12px;

  .n-input-number {
    flex: 1;
    min-width: 0;
  }
}

.action-container {
  margin-bottom: 0;
  padding: 6px 0 4px;
  border-top: 0;
}

.home-container--mobile .action-container {
  gap: 8px;
  margin: 0;
  padding: 8px 0 2px;
}

.home-container {
  --lg-focus: #18a058;
  --lg-surface-top: rgba(255, 255, 255, 0.96);
  --lg-surface-bottom: rgba(249, 250, 252, 0.94);
  --lg-action-surface: #fafbfc;
  --lg-line-base: #ffffff;
  --lg-primary: #18a058;
  --lg-error: #d03050;
  --lg-warning: #f0a020;
  --lg-info: #2080f0;
  --lg-btn-shadow:
    inset 0 0.5px 0 rgba(255, 255, 255, 0.55), 0 4px 12px -8px rgba(24, 25, 28, 0.24);
  --lg-btn-sheen: linear-gradient(
    115deg,
    rgba(255, 255, 255, 0) 30%,
    rgba(255, 255, 255, 0.08) 47%,
    rgba(255, 255, 255, 0) 66%
  );
  --lg-btn-neutral-bg: linear-gradient(145deg, var(--lg-surface-top), var(--lg-surface-bottom));
  --lg-btn-neutral-line: rgba(24, 25, 28, 0.08);
  --lg-btn-neutral-label: #1b1c20;
  --lg-btn-primary-bg: linear-gradient(
    145deg,
    color-mix(in srgb, var(--lg-primary) 6%, var(--lg-surface-top)),
    color-mix(in srgb, var(--lg-primary) 3%, var(--lg-surface-bottom))
  );
  --lg-btn-primary-line: color-mix(in srgb, var(--lg-primary) 22%, var(--lg-line-base));
  --lg-btn-primary-label: #0e7140;
  --lg-btn-error-line: color-mix(in srgb, var(--lg-error) 22%, var(--lg-line-base));
  --lg-btn-error-label: #a5203e;
  --lg-btn-warning-bg: linear-gradient(
    145deg,
    color-mix(in srgb, var(--lg-warning) 6%, var(--lg-surface-top)),
    color-mix(in srgb, var(--lg-warning) 3%, var(--lg-surface-bottom))
  );
  --lg-btn-warning-line: color-mix(in srgb, var(--lg-warning) 22%, var(--lg-line-base));
  --lg-btn-warning-label: #8c5800;
  --lg-btn-info-line: color-mix(in srgb, var(--lg-info) 22%, var(--lg-line-base));
  --lg-btn-info-label: #135f9e;
}

html[data-mower-theme='dark'] .home-container,
html[data-window-shell-theme='dark'] .home-container {
  --lg-focus: #7fe0b0;
  --lg-surface-top: rgba(38, 40, 46, 0.96);
  --lg-surface-bottom: rgba(29, 31, 36, 0.94);
  --lg-action-surface: #24262c;
  --lg-line-base: #24262c;
  --lg-primary: #7fe0b0;
  --lg-error: #ffb3c2;
  --lg-warning: #f8d794;
  --lg-info: #b3def7;
  --lg-btn-shadow: inset 0 0.5px 0 rgba(244, 240, 229, 0.08), 0 4px 12px -8px rgba(0, 0, 0, 0.45);
  --lg-btn-sheen: linear-gradient(
    115deg,
    rgba(244, 240, 229, 0) 30%,
    rgba(244, 240, 229, 0.04) 47%,
    rgba(244, 240, 229, 0) 66%
  );
  --lg-btn-neutral-line: rgba(244, 240, 229, 0.1);
  --lg-btn-neutral-label: #f4f0e5;
  --lg-btn-primary-label: #7fe0b0;
  --lg-btn-error-label: #ffb3c2;
  --lg-btn-warning-label: #f8d794;
  --lg-btn-info-label: #b3def7;
  --log-rule: rgb(244 240 229 / 12%);
  --log-shot-shadow: 0 12px 30px -14px rgba(0, 0, 0, 0.7), 0 0 0 1px rgba(244, 240, 229, 0.06);
}

.execution-control :deep(.n-button),
.action-container :deep(.n-button:is(.add-task-action, .database-action)) {
  --lg-action-accent: var(--lg-action-surface);
  --lg-action-tint: 6%;
  --n-color: color-mix(
    in srgb,
    var(--lg-action-accent) var(--lg-action-tint),
    var(--lg-action-surface)
  );
  --n-color-hover: var(--n-color);
  --n-color-pressed: var(--n-color);
  --n-color-focus: var(--n-color);
  --n-color-disabled: var(--n-color);
  --n-text-color: var(--lg-btn-label);
  --n-text-color-hover: var(--lg-btn-label);
  --n-text-color-pressed: var(--lg-btn-label);
  --n-text-color-focus: var(--lg-btn-label);
  --n-text-color-disabled: var(--lg-btn-neutral-label);
  --n-border: 0.5px solid var(--lg-btn-line);
  --n-border-hover: 0.5px solid var(--lg-btn-line);
  --n-border-pressed: 0.5px solid var(--lg-btn-line);
  --n-border-focus: 0.5px solid var(--lg-btn-line);
  --n-border-disabled: 0.5px solid var(--lg-btn-neutral-line);
  --n-border-radius: 10px;
  --n-height: 34px;
  --n-ripple-color: transparent;
  --n-opacity-disabled: 0.5;
  --lg-btn-label: var(--lg-btn-neutral-label);
  --lg-btn-line: var(--lg-btn-neutral-line);
  font-weight: 600;
  box-shadow: none;
  transition:
    transform 0.16s ease,
    background-color 0.16s ease,
    opacity 0.16s ease,
    color 0.16s ease;
}

.log-view-controls :deep(.n-button),
.log-view-actions :deep(.n-button) {
  --view-toggle-ink: var(--view-control-muted);
  --n-text-color: var(--view-toggle-ink);
  --n-text-color-hover: var(--view-toggle-ink);
  --n-text-color-pressed: var(--view-toggle-ink);
  --n-text-color-focus: var(--view-toggle-ink);
  width: 32px;
  height: 32px;
  padding-inline: 0;
  box-shadow: none !important;
  border-radius: 6px;

  .n-button__icon {
    margin: 0;
    z-index: 1;
  }
}

.log-view-controls :deep(.n-button)::before,
.log-view-actions :deep(.n-button)::before {
  content: '';
  position: absolute;
  z-index: 0;
  top: 50%;
  left: 50%;
  width: calc(100% - 4px);
  height: calc(100% - 4px);
  border-radius: 999px;
  transform: translate(-50%, -50%);
  pointer-events: none;
}

.log-view-controls :deep(.n-button:active:not(.n-button--disabled)),
.log-view-actions :deep(.n-button:active:not(.n-button--disabled)),
.log-view-controls :deep(.n-button:hover:not(.n-button--disabled)),
.log-view-actions :deep(.n-button:hover:not(.n-button--disabled)) {
  background: transparent;
}

@media (hover: hover) and (pointer: fine) {
  .log-view-controls :deep(.n-button:hover:not(.n-button--disabled))::before,
  .log-view-actions :deep(.n-button:hover:not(.n-button--disabled))::before {
    background: var(--view-control-hover-bg);
  }
}

.log-view-controls :deep(.n-button:active:not(.n-button--disabled))::before,
.log-view-actions :deep(.n-button:active:not(.n-button--disabled))::before {
  background: var(--view-control-pressed-bg);
}

.log-view-controls :deep(.view-toggle[aria-pressed='true']),
.log-view-actions :deep(.view-toggle[aria-pressed='true']) {
  --view-toggle-ink: var(--view-control-color);
}

.log-view-controls :deep(.n-button:focus-visible),
.log-view-actions :deep(.n-button:focus-visible) {
  outline: none !important;
}

.log-view-controls :deep(.n-button:focus-visible)::before,
.log-view-actions :deep(.n-button:focus-visible)::before {
  outline: 2px solid color-mix(in srgb, var(--view-control-color) 45%, transparent) !important;
  outline-offset: -2px;
}

.execution-control :deep(.n-button--primary-type) {
  --lg-action-accent: var(--lg-primary);
  --lg-btn-label: var(--lg-btn-primary-label);
  --lg-btn-line: var(--lg-btn-primary-line);
}

.execution-control :deep(.n-button--error-type) {
  --lg-action-accent: var(--lg-error);
  --lg-btn-label: var(--lg-btn-error-label);
  --lg-btn-line: var(--lg-btn-error-line);
}

.execution-control :deep(.n-button--warning-type),
.execution-control :deep(.halloween-start .n-button),
.action-container :deep(.n-button.add-task-action) {
  --lg-action-accent: var(--lg-warning);
  --lg-btn-label: var(--lg-btn-warning-label);
  --lg-btn-line: var(--lg-btn-warning-line);
}

.action-container :deep(.n-button.database-action) {
  --lg-action-accent: var(--lg-info);
  --lg-btn-label: var(--lg-btn-info-label);
  --lg-btn-line: var(--lg-btn-info-line);
}

.execution-control :deep(.split-dropdown > .n-button:first-child) {
  border-radius: 10px 0 0 10px;
}

.execution-control :deep(.split-dropdown > .n-button:last-child) {
  border-radius: 0 10px 10px 0;
}

.execution-control :deep(.split-dropdown > .n-button:first-child .n-button__border),
.execution-control :deep(.split-dropdown > .n-button:first-child .n-button__state-border) {
  border-right-width: 0 !important;
}

.execution-control :deep(.split-dropdown > .n-button:last-child .n-button__border),
.execution-control :deep(.split-dropdown > .n-button:last-child .n-button__state-border) {
  border-left-width: 0 !important;
}

.execution-control :deep(.split-dropdown > .n-button:last-child)::before {
  content: '';
  position: absolute;
  top: 8px;
  bottom: 8px;
  left: 0;
  width: 1px;
  border-radius: 1px;
  background: var(--lg-btn-line);
  pointer-events: none;
}

.log-view-controls :deep(.view-options-trigger)::before {
  width: calc(100% - 8px);
  height: calc(100% - 8px);
}

@media (hover: hover) and (pointer: fine) {
  .execution-control :deep(.n-button:hover:not(.n-button--disabled):not(.n-button--loading)),
  .action-container
    :deep(
      .n-button:is(.add-task-action, .database-action):hover:not(.n-button--disabled):not(
          .n-button--loading
        )
    ) {
    --lg-action-tint: 10%;
  }
}

.execution-control :deep(.n-button:active:not(.n-button--disabled):not(.n-button--loading)),
.action-container
  :deep(
    .n-button:is(.add-task-action, .database-action):active:not(.n-button--disabled):not(
        .n-button--loading
      )
  ) {
  --lg-action-tint: 14%;
  transform: translateY(0) scale(0.99);
}

.execution-control :deep(.n-button:focus-visible),
.action-container :deep(.n-button:is(.add-task-action, .database-action):focus-visible) {
  outline: 2px solid var(--lg-focus) !important;
  outline-offset: 2px;
}

.execution-control :deep(.n-button--disabled),
.action-container :deep(.n-button--disabled:is(.add-task-action, .database-action)) {
  transform: none !important;
}

.execution-control :deep(.n-button--loading),
.action-container :deep(.n-button--loading:is(.add-task-action, .database-action)) {
  cursor: wait;
}
</style>

<style>
html:active-view-transition-type(mower-log) {
  view-transition-name: none;
}

.log-pane:active-view-transition-type(mower-log),
html:active-view-transition-type(mower-log) .log-pane {
  view-transition-name: mower-log-pane;
}

html:active-view-transition-type(mower-log-layout) .log-pane {
  view-transition-name: none;

  & .log {
    view-transition-name: mower-log-content;
  }

  & .log-screenshot {
    view-transition-name: mower-log-preview;
  }

  & .task-table-scroll {
    view-transition-name: mower-log-queue;
  }

  & :is(.plan-condition, .log-resizer) {
    view-transition-name: match-element;
  }
}

html:active-view-transition-type(mower-log-layout) {
  &::view-transition-group(*) {
    animation-duration: 240ms;
    animation-timing-function: ease;
  }

  &::view-transition-image-pair(*) {
    overflow: clip;
  }

  &::view-transition-old(*) {
    display: none;
    animation: none;
  }

  &::view-transition-new(*) {
    animation: none;
    mix-blend-mode: normal;
    height: 100%;
    object-fit: none;
    object-position: left top;
  }

  &::view-transition-new(*):only-child {
    animation: mower-log-panel-open 240ms ease both;
  }

  &::view-transition-old(*):only-child {
    display: block;
    animation: mower-log-panel-open 240ms ease reverse both;
  }
}

html:active-view-transition-type(mower-log-rail) {
  &::view-transition-new(*),
  &::view-transition-old(*) {
    --log-panel-closed: inset(0 0 0 100%);
  }
}

@keyframes mower-log-panel-open {
  from {
    clip-path: var(--log-panel-closed, inset(0 0 100% 0));
  }

  to {
    clip-path: inset(0);
  }
}

:is(html, .log-pane):active-view-transition-type(mower-log)::view-transition {
  pointer-events: none;
}

:is(html, .log-pane):active-view-transition-type(mower-log)::view-transition-group(mower-log-pane) {
  animation-name: none;
  animation-duration: 240ms;
  animation-timing-function: ease;
}

html:active-view-transition-type(mower-log) .n-popover:has(.log-view-actions) {
  view-transition-name: mower-log-actions;
}

html:active-view-transition-type(mower-log)::view-transition-group(mower-log-actions) {
  z-index: 1;
  animation: none;
}

html:active-view-transition-type(mower-log)::view-transition-old(mower-log-actions) {
  display: none;
}

html:active-view-transition-type(mower-log)::view-transition-new(mower-log-actions) {
  animation: none;
  mix-blend-mode: normal;
}

.hljs-date {
  color: #f0a020 !important;
  font-weight: bold;
}

.hljs-time {
  color: #2080f0 !important;
  font-weight: bold;
}

.hljs-room {
  color: #18a058 !important;
  font-weight: bold;
}

.hljs-operator {
  color: #d03050 !important;
}

.hljs-info {
  font-weight: bold;
}

.hljs-warning {
  color: #f0a020 !important;
  font-weight: bold;
}

.hljs-error {
  color: #d03050 !important;
  font-weight: bold;
}

.hljs-scene {
  font-style: italic;
}
</style>
