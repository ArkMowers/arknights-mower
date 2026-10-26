<script setup>
defineOptions({ name: 'MowerLogPage' })

import { storeToRefs } from 'pinia'
import {
  computed,
  inject,
  nextTick,
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
import { useLogBackgroundStore } from '@/stores/logBackground'
import {
  clampScreenshotHeight,
  clampTaskHeight,
  LOG_MIN_HEIGHT,
  RESIZER_HEIGHT
} from '@/utils/logLayout'
import { createScreenshotPreview } from '@/utils/screenshotPreview'
import StartSchedule from '@/components/StartSchedule.vue'
import { useResolvedTheme } from '@/composables/theme'
const mower_store = useMowerStore()
const logBackground = useLogBackgroundStore()
const {
  log,
  log_mobile,
  running,
  plan_condition,
  log_lines,
  task_list,
  waiting,
  stop_after_round
} = storeToRefs(mower_store)
const { get_tasks, get_running, start_task_polling, stop_task_polling } = mower_store
const axios = inject('axios')
const mobile = inject('mobile')
const route = inject(routeLocationKey, null)
const router = inject(routerKey, null)

const auto_scroll = ref(true)
const sc_preview = ref(true)
const sc_blob = ref('')
const has_screenshot = computed(() => sc_preview.value && Boolean(sc_blob.value))
const show_task_table = ref(true)
const task_table_visible = computed(
  () => task_list.value.length > 0 && (!mobile.value || show_task_table.value)
)
const log_layout = ref(null)
const action_bar = ref(null)
const show_display_options = ref(false)
const toolbar_id = useId()
const task_queue = ref(null)
const layout_preference = {
  screenshot_height: null,
  task_height: null
}
let layoutObserver
let screenshot_aspect = 16 / 9
let mobile_screenshot_height = null

function layout_bottom_reserve(container) {
  const conditionHeight =
    container.querySelector('.plan-condition')?.getBoundingClientRect().height ?? 0
  return LOG_MIN_HEIGHT + RESIZER_HEIGHT + conditionHeight
}

function apply_log_layout() {
  if (
    show_display_options.value &&
    action_bar.value?.querySelector('.display-options-trigger')?.getClientRects().length === 0
  )
    show_display_options.value = false
  const container = log_layout.value
  if (!container) return
  const bounds = container.getBoundingClientRect()
  const bottomReserve = layout_bottom_reserve(container)
  if (has_screenshot.value) {
    const fitMobile = mobile.value && mobile_screenshot_height === null && container.clientWidth > 0
    const preferred = mobile.value
      ? (mobile_screenshot_height ?? 270)
      : (layout_preference.screenshot_height ?? 270)
    const height = fitMobile
      ? Math.round(container.clientWidth / screenshot_aspect)
      : clampScreenshotHeight(preferred, bounds.height, bottomReserve)
    container.style.setProperty('--log-sc-h', `${height}px`)
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
  const height = clampTaskHeight(
    layout_preference.task_height,
    bounds.bottom - task.top,
    bottomReserve
  )
  container.style.setProperty('--log-task-h', `${height}px`)
}

function screenshot_loaded(event) {
  const image = event.target
  if (image?.naturalWidth > 0 && image?.naturalHeight > 0)
    screenshot_aspect = image.naturalWidth / image.naturalHeight
  apply_log_layout()
}

async function restore_log_layout() {
  try {
    const { data } = await axios.get(`${import.meta.env.VITE_HTTP_URL}/ui-state/log-layout`)
    layout_preference.screenshot_height = data?.screenshot_height ?? null
    layout_preference.task_height = data?.task_height ?? null
  } catch {
    // Keep the default layout when saved preferences are unavailable.
  }
  await nextTick()
  apply_log_layout()
}

function resize_log_pane(event, pane) {
  event.preventDefault()
  const container = log_layout.value
  if (!container) return
  const variable = pane === 'screenshot' ? '--log-sc-h' : '--log-task-h'
  const stateKey = pane === 'screenshot' ? 'screenshot_height' : 'task_height'
  let savedSize = null
  const onMove = (moveEvent) => {
    const bounds = container.getBoundingClientRect()
    const bottomReserve = layout_bottom_reserve(container)
    let size
    if (pane === 'screenshot') {
      const screenshotTop =
        container.querySelector('.log-screenshot')?.getBoundingClientRect().top ?? bounds.top
      size = clampScreenshotHeight(moveEvent.clientY - screenshotTop, bounds.height, bottomReserve)
    } else {
      const task = container.querySelector('.task-table-scroll')?.getBoundingClientRect()
      if (!task) return
      size = clampTaskHeight(moveEvent.clientY - task.top, bounds.bottom - task.top, bottomReserve)
    }
    savedSize = size
    if (pane === 'screenshot' && mobile.value) mobile_screenshot_height = size
    layout_preference[stateKey] = size
    container.style.setProperty(variable, `${size}px`)
  }
  const onUp = () => {
    document.removeEventListener('pointermove', onMove)
    document.removeEventListener('pointerup', onUp)
    if (savedSize === null) return
    axios
      .post(`${import.meta.env.VITE_HTTP_URL}/ui-state/log-layout`, { [stateKey]: savedSize })
      .catch(() => {})
  }
  document.addEventListener('pointermove', onMove)
  document.addEventListener('pointerup', onUp)
}

const screenshotPreview = createScreenshotPreview({
  fetchSnapshot: (options) =>
    axios.get(`${import.meta.env.VITE_HTTP_URL}/screenshot/latest`, options),
  onChange: (url) => {
    sc_blob.value = url
  }
})

function updateScreenshotPreview() {
  if (sc_preview.value && !document.hidden) screenshotPreview.start()
  else screenshotPreview.stop()
}

watch(sc_preview, (enabled) => {
  localStorage.setItem('sc_preview', JSON.stringify(enabled))
  updateScreenshotPreview()
  nextTick(apply_log_layout)
})

watch(sc_blob, () => {
  nextTick(apply_log_layout)
})

watch(
  plan_condition,
  () => {
    nextTick(apply_log_layout)
  },
  { deep: true }
)

watch(task_list, () => nextTick(apply_log_layout), { deep: true })
watch(show_task_table, () => nextTick(apply_log_layout))
watch(mobile, () => nextTick(apply_log_layout))

function scroll_last_line() {
  nextTick(() => {
    const container = document.querySelector('.log .n-scrollbar-container')
    if (container) container.scrollTop = container.scrollHeight
  })
}

function scroll_log() {
  if (auto_scroll.value) {
    scroll_last_line()
  }
}

watch(
  () => [log, task_list],
  () => {
    scroll_log()
  },
  { deep: true }
)

let runningTimer
function updatePageVisibility() {
  updateScreenshotPreview()
  clearInterval(runningTimer)
  if (document.hidden) {
    stop_task_polling()
    return
  }
  start_task_polling()
  get_running()
  runningTimer = setInterval(get_running, 5000)
}

onMounted(() => {
  void logBackground.load()
  const savedPreviewState = localStorage.getItem('sc_preview')
  if (savedPreviewState !== null) {
    sc_preview.value = JSON.parse(savedPreviewState)
  }
  document.addEventListener('visibilitychange', updatePageVisibility)
  updatePageVisibility()
  layoutObserver = new ResizeObserver(apply_log_layout)
  if (log_layout.value) layoutObserver.observe(log_layout.value)
  if (action_bar.value) layoutObserver.observe(action_bar.value)
  restore_log_layout()
  db_load_stats()
})

onUnmounted(() => {
  task_dialog_active = false
  stop_task_polling()
  clearInterval(runningTimer)
  document.removeEventListener('visibilitychange', updatePageVisibility)
  layoutObserver?.disconnect()
  screenshotPreview.stop()
})

function start(value) {
  running.value = true
  log_lines.value = []
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

import StopIcon from '@vicons/ionicons5/es/Stop'
import AddIcon from '@vicons/ionicons5/es/Add'
import ServerOutlineIcon from '@vicons/ionicons5/es/ServerOutline'
import CollapseIcon from '@vicons/fluent/es/PanelTopContract20Regular'
import ExpandIcon from '@vicons/fluent/es/PanelTopExpand20Regular'
import MoreIcon from '@vicons/fluent/es/MoreHorizontal20Regular'

const task_help = [
  '目前只糊了一个勉强能用的版本，其他功能敬请期待',
  '支持空任务、专精、加工材料、分解所有重复家具、仓库扫描和线索任务',
  '只能增，不能删！！写错了可以【载入心情数据】启动',
  '新增加工材料或分解家具任务会唤醒调度器，按任务时间执行',
  '其他新增任务不会主动唤醒调度器，休眠期间添加的任务可能延后执行',
  '添加完任务可以【载入心情任务】启动',
  '空任务，请确保任务房间名字，干员数量正确（没有判定）',
  '专精任务，UI有详细说明；新增完毕，UI上面的表会实时反馈',
  '线索任务，到点跑一次完整的会客室流程（信息板、领线索、摆线索、送线索）',
  '在Q群或者频道提以上问题，看心情踢人'
]

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
import { useConfigStore } from '@/stores/config'
const config_store = useConfigStore()
const { theme: themePreference } = storeToRefs(config_store)
const theme = useResolvedTheme(themePreference)
function revealTaskQueue() {
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
      router?.replace({ name: 'task-settings', query: route?.query, hash })
    else if (hash === '#task-queue') revealTaskQueue()
  },
  { immediate: true }
)

const bg_opacity = computed(() => {
  return theme.value == 'light' ? 0.2 : 0.3
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
    disabled: !process_control.value?.canRunProcessAction,
    props: { title: '保存配置并重启当前实例，保留心情和位置，按当前排班重新生成任务。' }
  },
  {
    label: '重启续接',
    key: 'restart_resume',
    disabled: !process_control.value?.canRunProcessAction,
    props: { title: '保存配置并重启当前实例，保留原任务队列继续运行。' }
  }
])

function select_stop_action(key) {
  if (key === 'after_round') return toggle_round_stop()
  if (key === 'maa') return stop_maa()
  if (!process_control.value?.canRunProcessAction) return
  if (key === 'apply_schedule') return process_control.value.applySchedule()
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

function db_load_stats() {
  axios
    .get(`${import.meta.env.VITE_HTTP_URL}/db-admin/stats`)
    .then((resp) => {
      db_stats.value = resp.data || {}
    })
    .catch(() => {}) // 后端未启动/接口不可用时静默（卡片仍显示 0 条）
}
function db_toggle_panel() {
  show_display_options.value = false
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
  try {
    await axios.post(`${import.meta.env.VITE_HTTP_URL}/db-admin/delete`, { categories: keys })
    db_load_stats()
    keys.forEach((k) => (db_sel.value[k] = false))
    db_message.success('删除成功')
  } catch (e) {
    db_message.error(`删除失败：${e?.response?.data?.error || e.message || ''}`)
  }
}
</script>

<template>
  <div class="home-container" :class="{ 'home-container--mobile': mobile }">
    <div
      class="log-bg"
      :style="{ backgroundImage: `url('${logBackground.url}')` }"
      aria-hidden="true"
    ></div>
    <section
      ref="log_layout"
      class="log-pane"
      :class="{ 'with-screenshot': has_screenshot, 'has-tasks': task_table_visible }"
      aria-label="运行日志"
    >
      <n-image
        v-if="has_screenshot"
        width="100%"
        class="log-screenshot"
        :src="sc_blob"
        object-fit="contain"
        @load="screenshot_loaded"
      />
      <n-button
        v-if="mobile && task_list.length > 0"
        class="toggle-table-collapse-btn"
        :aria-label="show_task_table ? '收起任务列表' : '展开任务列表'"
        :aria-expanded="show_task_table"
        :aria-controls="`${toolbar_id}-queue`"
        :title="show_task_table ? '收起任务列表' : '展开任务列表'"
        @click="show_task_table = !show_task_table"
      >
        <template #icon>
          <n-icon>
            <collapse-icon v-if="show_task_table" />
            <expand-icon v-else />
          </n-icon>
        </template>
      </n-button>
      <div
        v-if="has_screenshot"
        class="log-resizer log-resizer-sc"
        @pointerdown="(event) => resize_log_pane(event, 'screenshot')"
      ></div>

      <div
        v-if="task_list.length > 0"
        v-show="task_table_visible"
        :id="`${toolbar_id}-queue`"
        ref="task_queue"
        class="task-table-scroll"
        role="region"
        aria-label="任务列表"
      >
        <n-table class="task-table" size="small" :single-line="false">
          <thead>
            <tr>
              <th>时间</th>
              <th :colspan="2">任务</th>
            </tr>
          </thead>
          <tbody>
            <template v-for="(task, task_index) in task_list" :key="task_index">
              <template v-if="Object.keys(task.plan).length">
                <tr v-for="(value, key, idx) in task.plan" :key="key">
                  <td v-if="idx == 0" :rowspan="Object.keys(task.plan).length">
                    {{ task.time.split('T')[1].split('.')[0] }}
                    <div v-if="task.emergency_recovery_release">自动救急</div>
                    <div v-else-if="task.emergency_staffing">自动救急换班</div>
                    <div v-else-if="task.emergency_dorm">自动救急宿舍安排</div>
                  </td>
                  <td>{{ key }}</td>
                  <td>{{ value.map((x) => x || '_').join(', ') }}</td>
                </tr>
              </template>
              <tr v-else>
                <td>{{ task.time.split('T')[1].split('.')[0] }}</td>
                <td :colspan="2">
                  {{ task.display_name || task.type.display_value
                  }}{{ task.meta_data ? ' ' + task.meta_data : '' }}
                </td>
              </tr>
            </template>
          </tbody>
        </n-table>
      </div>
      <div v-if="plan_condition.length > 0" class="plan-condition" style="display: flex; gap: 10px">
        <span>当前激活的副表为： </span>
        <span v-for="(x, index) in plan_condition" :key="index" style="color: green">
          {{ x }}
        </span>
      </div>
      <div
        v-if="task_list.length > 0"
        v-show="task_table_visible"
        class="log-resizer log-resizer-task"
        @pointerdown="(event) => resize_log_pane(event, 'task')"
      ></div>
      <n-log
        class="log"
        :log="mobile ? log_mobile : log"
        language="mower"
        style="user-select: text"
      />
    </section>
    <div ref="action_bar" class="action-container">
      <div class="action-buttons" role="group" aria-label="运行操作">
        <div class="execution-control">
          <drop-down
            v-if="running"
            :select="select_stop_action"
            :options="stop_options"
            type="error"
            :up="true"
            menu-label="停止选项"
            :disabled="waiting"
          >
            <n-button type="error" @click="stop" :loading="waiting" :disabled="waiting">
              <template #icon>
                <n-icon>
                  <stop-icon />
                </n-icon>
              </template>
              <span class="btn-text">立即停止</span>
            </n-button>
          </drop-down>
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
          <help-text v-if="!mobile" label="新增任务说明">
            <div v-for="line in task_help" :key="line">{{ line }}</div>
          </help-text>
        </div>
        <n-button class="database-action" type="info" @click="db_toggle_panel">
          <template #icon>
            <n-icon>
              <server-outline-icon />
            </n-icon>
          </template>
          <span class="btn-text">数据库管理</span>
        </n-button>
      </div>
      <div class="toolbar-options">
        <div class="view-options" role="group" aria-label="日志显示选项">
          <div class="view-option">
            <span>预览截图</span>
            <n-switch v-model:value="sc_preview" aria-label="预览截图" />
          </div>
          <div class="view-option">
            <span>自动滚动</span>
            <n-switch v-model:value="auto_scroll" aria-label="自动滚动" />
          </div>
        </div>
        <n-popover
          v-model:show="show_display_options"
          trigger="click"
          placement="top-end"
          :show-arrow="false"
          :internal-trap-focus="true"
        >
          <template #trigger>
            <n-button
              class="display-options-trigger"
              :aria-label="mobile ? '日志更多操作' : '日志显示选项'"
              :title="mobile ? '更多操作' : '日志显示选项'"
              aria-haspopup="dialog"
              :aria-expanded="show_display_options"
              :aria-controls="`${toolbar_id}-display`"
            >
              <template v-if="mobile" #icon><n-icon :component="MoreIcon" /></template>
              <span v-if="!mobile">显示</span>
            </n-button>
          </template>
          <div
            :id="`${toolbar_id}-display`"
            class="log-display-panel"
            :class="{ 'log-display-panel--mobile': mobile }"
            role="dialog"
            :aria-label="mobile ? '日志更多操作' : '日志显示选项'"
          >
            <n-button
              v-if="mobile"
              class="database-menu-action"
              type="info"
              @click="db_toggle_panel"
            >
              <template #icon><n-icon :component="ServerOutlineIcon" /></template>
              数据库管理
            </n-button>
            <div class="view-option">
              <span>预览截图</span>
              <n-switch v-model:value="sc_preview" aria-label="预览截图" />
            </div>
            <div class="view-option">
              <span>自动滚动</span>
              <n-switch v-model:value="auto_scroll" aria-label="自动滚动" />
            </div>
            <details v-if="mobile" class="log-task-help">
              <summary>新增任务说明</summary>
              <div v-for="line in task_help" :key="line">{{ line }}</div>
            </details>
          </div>
        </n-popover>
      </div>
      <div class="process-status" aria-live="polite">
        <ProcessControl ref="process_control" compact :running="running" />
      </div>
    </div>
    <component :is="TaskDialog" v-if="TaskDialog" />
    <n-modal
      v-model:show="show_db_admin"
      preset="card"
      transform-origin="center"
      style="width: min(480px, calc(100vw - 32px))"
    >
      <template #header>
        <div>数据库管理</div>
      </template>
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
            :disabled="!db_any_selected"
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
.home-container {
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
  grid-row: 1;
  z-index: 1;
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  grid-template-rows: 0 0 0 auto 0 minmax(120px, 1fr);
  min-height: 0;
  min-width: 0;
  overflow: auto;
  position: relative;

  &.with-screenshot {
    grid-template-rows: var(--log-sc-h, 270px) 8px 0 auto 0 minmax(120px, 1fr);
  }

  &.has-tasks {
    grid-template-rows: 0 0 auto auto 8px minmax(120px, 1fr);

    &.with-screenshot {
      grid-template-rows: var(--log-sc-h, 270px) 8px auto auto 8px minmax(120px, 1fr);
    }
  }
}

.log-screenshot {
  grid-row: 1;
  width: 100%;
  max-width: 480px;
  justify-self: start;
  align-self: start;
  height: 100%;
  min-height: 0;
  max-height: min(45vh, 500px);
  border-radius: 6px;
  z-index: 15;

  :deep(img) {
    height: 100%;
    object-position: left top !important;
  }
}

.log-resizer {
  width: 100%;
  height: 8px;
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
    background: rgb(24 160 88 / 0%);
    transition: background-color 0.15s ease;
  }

  &:hover::after {
    background: rgb(24 160 88 / 45%);
  }
}

.log-resizer-sc {
  grid-row: 2;
}

.task-table-scroll {
  grid-row: 3;
  width: 100%;
  max-width: 600px;
  min-width: 0;
  min-height: 0;
  max-height: var(--log-task-h, min(600px, 36vh));
  overflow: auto;
  scrollbar-gutter: stable;
  justify-self: start;
}

.task-table {
  width: 100%;
  background: transparent;

  :deep(th),
  :deep(td) {
    background: transparent !important;
  }

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

.plan-condition {
  grid-row: 4;
  min-height: 0;
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

.action-container {
  grid-row: 2;
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

.round-stop-notice {
  position: absolute;
  top: calc(100% + 2px);
  left: 50%;
  transform: translateX(-50%);
  font-size: 10px;
  line-height: 10px;
  white-space: nowrap;
}

.toolbar-options {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-left: auto;
  flex: none;
}

.view-options {
  display: flex;
  align-items: center;
  gap: 20px;
  margin-right: 8px;
}

.view-option {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  min-height: 36px;
  white-space: nowrap;
}

.display-options-trigger {
  display: none;
}

.log-display-panel {
  display: grid;
  gap: 8px;
  min-width: min(200px, calc(100dvw / var(--mower-zoom, 1) - 48px));
  max-width: min(300px, calc(100dvw / var(--mower-zoom, 1) - 48px));
  max-height: min(420px, calc(100dvh / var(--mower-zoom, 1) - 140px));
  overflow-y: auto;
  overscroll-behavior: contain;
}

.log-display-panel .view-option {
  justify-content: space-between;
}

.log-display-panel--mobile .view-option,
.database-menu-action {
  min-height: 44px;
}

.log-task-help summary {
  display: flex;
  align-items: center;
  min-height: 44px;
  cursor: pointer;
}

.log-task-help > div {
  margin-block: 8px;
  max-width: 260px;
  line-height: 1.65;
  overflow-wrap: anywhere;
}

.home-container--mobile {
  width: 100%;
  height: 100%;
  padding: 0 0 8px;
  box-sizing: border-box;

  .log-screenshot {
    max-width: none;
    max-height: none;
    border-radius: 0;
  }

  .action-container {
    flex-wrap: nowrap;
    gap: 8px;
    margin-inline: 8px;
    padding-top: 8px;
  }

  .action-buttons {
    flex-wrap: nowrap;
  }

  .action-container :deep(.n-button) {
    min-height: 44px;
  }

  .database-action,
  .view-options,
  .add-task-action .btn-text {
    display: none;
  }

  .add-task-action,
  .display-options-trigger {
    display: inline-flex;
    width: 44px;
    padding-inline: 0;

    :deep(.n-button__icon) {
      margin: 0;
    }
  }
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

@container main-content (max-width: 760px) {
  .view-options {
    display: none;
  }
  .display-options-trigger {
    display: inline-flex;
  }
}

@supports not (container-type: inline-size) {
  @media (max-width: 760px) {
    .view-options {
      display: none;
    }
    .display-options-trigger {
      display: inline-flex;
    }
  }
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

.toggle-table-collapse-btn {
  position: absolute;
  top: 8px;
  right: 8px;
  z-index: 30;
  width: 44px;
  height: 44px;
  padding: 0;
  border-radius: 10px;
  background: color-mix(in srgb, var(--mower-surface) 94%, transparent);
}
</style>

<style>
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
