<script setup>
import { storeToRefs } from 'pinia'
import { computed, inject, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useDialog, useMessage } from 'naive-ui'

import { useMowerStore } from '@/stores/mower'
import {
  clampScreenshotHeight,
  clampTaskHeight,
  LOG_MIN_HEIGHT,
  RESIZER_HEIGHT
} from '@/utils/logLayout'
import { createScreenshotPreview } from '@/utils/screenshotPreview'
import StartSchedule from '@/components/StartSchedule.vue'
const mower_store = useMowerStore()
const { log, log_mobile, running, plan_condition, log_lines, task_list, waiting, get_task_id } =
  storeToRefs(mower_store)
const { get_tasks, get_running } = mower_store
const axios = inject('axios')
const mobile = inject('mobile')

const auto_scroll = ref(true)
const sc_preview = ref(true)
const sc_blob = ref('')
const log_layout = ref(null)
const layout_preference = {
  screenshot_height: null,
  task_height: null
}
let layoutObserver

function layout_bottom_reserve(container) {
  const conditionHeight =
    container.querySelector('.plan-condition')?.getBoundingClientRect().height ?? 0
  const actionHeight =
    container.querySelector('.action-container')?.getBoundingClientRect().height ?? 0
  return LOG_MIN_HEIGHT + RESIZER_HEIGHT + conditionHeight + actionHeight
}

function apply_log_layout() {
  const container = log_layout.value
  if (!container) return
  const bounds = container.getBoundingClientRect()
  const bottomReserve = layout_bottom_reserve(container)

  if (sc_preview.value) {
    const preferred = layout_preference.screenshot_height ?? 270
    const height = clampScreenshotHeight(preferred, bounds.height, bottomReserve)
    container.style.setProperty('--log-sc-h', `${height}px`)
  } else {
    container.style.removeProperty('--log-sc-h')
  }

  if (layout_preference.task_height === null) {
    container.style.removeProperty('--log-task-h')
    return
  }
  const task = container.querySelector('.task-table-scroll')?.getBoundingClientRect()
  if (!task) return
  const height = clampTaskHeight(
    layout_preference.task_height,
    bounds.bottom - task.top,
    bottomReserve
  )
  container.style.setProperty('--log-task-h', `${height}px`)
}

async function restore_log_layout() {
  try {
    const { data } = await axios.get(`${import.meta.env.VITE_HTTP_URL}/ui-state/log-layout`)
    layout_preference.screenshot_height = data?.screenshot_height ?? null
    layout_preference.task_height = data?.task_height ?? null
  } catch {}
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
      size = clampScreenshotHeight(moveEvent.clientY - bounds.top, bounds.height, bottomReserve)
    } else {
      const task = container.querySelector('.task-table-scroll')?.getBoundingClientRect()
      if (!task) return
      size = clampTaskHeight(moveEvent.clientY - task.top, bounds.bottom - task.top, bottomReserve)
    }
    savedSize = size
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

watch(
  plan_condition,
  () => {
    nextTick(apply_log_layout)
  },
  { deep: true }
)

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
onMounted(() => {
  get_tasks()
  get_running()
  runningTimer = setInterval(get_running, 5000)
  const savedPreviewState = localStorage.getItem('sc_preview')
  if (savedPreviewState !== null) {
    sc_preview.value = JSON.parse(savedPreviewState)
  }
  document.addEventListener('visibilitychange', updateScreenshotPreview)
  updateScreenshotPreview()
  layoutObserver = new ResizeObserver(apply_log_layout)
  if (log_layout.value) layoutObserver.observe(log_layout.value)
  restore_log_layout()
  db_load_stats()
})

onUnmounted(() => {
  clearTimeout(get_task_id.value)
  clearInterval(runningTimer)
  document.removeEventListener('visibilitychange', updateScreenshotPreview)
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

const show_feedback = ref(false)

import StopIcon from '@vicons/ionicons5/Stop'
import AddIcon from '@vicons/ionicons5/Add'
import ServerOutlineIcon from '@vicons/ionicons5/ServerOutline'
import ChatbubbleIcon from '@vicons/ionicons5/ChatbubbleEllipsesOutline'
import CollapseIcon from '@vicons/fluent/PanelTopContract20Regular'
import ExpandIcon from '@vicons/fluent/PanelTopExpand20Regular'

const show_task_table = ref(true)
const show_task = ref(false)
const add_task = ref(true)
provide('show_task', show_task)
provide('show_feedback', show_feedback)
provide('add_task', add_task)
import { useConfigStore } from '@/stores/config'
const config_store = useConfigStore()
const { theme } = storeToRefs(config_store)

const bg_opacity = computed(() => {
  return theme.value == 'light' ? 0.2 : 0.3
})

function stop_maa() {
  axios.get(`${import.meta.env.VITE_HTTP_URL}/stop-maa`)
}

const process_control = ref(null)
const stop_options = computed(() => [
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
  <div
    ref="log_layout"
    class="home-container"
    :class="{ 'with-screenshot': sc_preview, 'has-tasks': task_list.length > 0 }"
  >
    <div class="log-bg"></div>
    <n-image
      v-if="sc_preview"
      width="100%"
      class="sc"
      :src="sc_blob == '' ? '/bg2.webp' : sc_blob"
      object-fit="scale-down"
    />
    <div
      v-if="sc_preview"
      class="log-resizer log-resizer-sc"
      @pointerdown="(event) => resize_log_pane(event, 'screenshot')"
    ></div>

    <div v-if="task_list.length > 0" class="task-table-scroll">
      <n-table class="task-table" size="small" :single-line="false">
        <thead>
          <tr>
            <th>时间</th>
            <th :colspan="2">任务</th>
          </tr>
        </thead>
        <tbody v-show="!mobile || show_task_table">
          <template v-for="task in task_list">
            <template v-if="Object.keys(task.plan).length">
              <tr v-for="(value, key, idx) in task.plan">
                <td v-if="idx == 0" :rowspan="Object.keys(task.plan).length">
                  {{ task.time.split('T')[1].split('.')[0] }}
                </td>
                <td>{{ key }}</td>
                <td>
                  {{ value.map((x) => x || '_').join(', ') }}
                </td>
              </tr>
            </template>
            <tr v-else>
              <td>
                {{ task.time.split('T')[1].split('.')[0] }}
              </td>
              <td :colspan="2">
                {{ task.type.display_value }}{{ task.meta_data ? ' ' + task.meta_data : '' }}
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
      class="log-resizer log-resizer-task"
      @pointerdown="(event) => resize_log_pane(event, 'task')"
    ></div>
    <n-log
      class="log"
      :log="mobile ? log_mobile : log"
      language="mower"
      style="user-select: text"
    />
    <div class="action-container">
      <drop-down
        v-if="running"
        :select="select_stop_action"
        :options="stop_options"
        type="error"
        :up="true"
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
      <start-schedule
        v-if="!running"
        :start="start"
        :start-options="start_options"
        :waiting="waiting"
      />
      <ProcessControl ref="process_control" compact :running="running" />
      <task-dialog />
      <n-button type="warning" @click="show_task = true">
        <template #icon>
          <n-icon>
            <add-icon />
          </n-icon>
        </template>
        <span class="btn-text">新增任务</span>
      </n-button>
      <help-text class="help-btn">
        <div>目前只糊了一个勉强能用的版本，其他功能敬请期待</div>
        <div>支持空任务、专精、加工材料、分解所有重复家具、仓库扫描和线索任务</div>
        <div>只能增，不能删！！写错了可以【载入心情数据】启动</div>
        <div>新增加工材料或分解家具任务会唤醒调度器，按任务时间执行</div>
        <div>其他新增任务不会主动唤醒调度器，休眠期间添加的任务可能延后执行</div>
        <div>添加完任务可以【载入心情任务】启动</div>
        <div>空任务，请确保任务房间名字，干员数量正确（没有判定）</div>
        <div>专精任务，UI有详细说明；新增完毕，UI上面的表会实时反馈</div>
        <div>线索任务，到点跑一次完整的会客室流程（信息板、领线索、摆线索、送线索）</div>
        <div>在Q群或者频道提以上问题，看心情踢人</div>
      </help-text>
      <n-button type="error" @click="show_feedback = true">
        <template #icon>
          <n-icon>
            <chatbubble-icon />
          </n-icon>
        </template>
        <span class="btn-text">反馈问题</span>
      </n-button>
      <feedback />
      <n-button type="info" @click="db_toggle_panel">
        <template #icon>
          <n-icon>
            <server-outline-icon />
          </n-icon>
        </template>
        <span class="btn-text">数据库管理</span>
      </n-button>
      <div class="expand"></div>
      <div class="scroll-container">
        <n-checkbox v-model:checked="sc_preview">
          <span class="btn-text">预览截图</span>
          <span class="btn-text-short">截图</span>
        </n-checkbox>
        <n-switch v-model:value="auto_scroll" />
        <span class="scroll-label">自动滚动</span>
      </div>
    </div>
    <n-button
      class="toggle-table-collapse-btn"
      size="small"
      @click="show_task_table = !show_task_table"
      :focusable="false"
      v-if="mobile"
    >
      <template #icon>
        <n-icon>
          <collapse-icon v-if="show_task_table" />
          <expand-icon v-else />
        </n-icon>
      </template>
    </n-button>
    <n-modal
      v-model:show="show_db_admin"
      preset="card"
      transform-origin="center"
      style="width: 480px"
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
  grid-template-rows: 0 0 0 auto 0 minmax(120px, 1fr) auto;
  gap: 0;
  min-height: 0;
  overflow: hidden;
  position: relative;

  &.with-screenshot {
    grid-template-rows: var(--log-sc-h, 270px) 8px 0 auto 0 minmax(120px, 1fr) auto;
  }

  &.has-tasks {
    grid-template-rows: 0 0 auto auto 8px minmax(120px, 1fr) auto;

    &.with-screenshot {
      grid-template-rows: var(--log-sc-h, 270px) 8px auto auto 8px minmax(120px, 1fr) auto;
    }
  }
}

.sc {
  grid-row: 1;
  justify-self: start;
  align-self: start;
  height: 100%;
  min-height: 0;
  max-height: min(45vh, 500px);

  :deep(img) {
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
  height: auto;
  min-height: 0;
  max-height: var(--log-task-h, min(600px, 36vh));
  overflow: auto;
  scrollbar-gutter: stable;
  justify-self: start;
}

.task-table {
  width: 100%;

  :deep(thead th) {
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
  grid-row: 7;
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  min-width: 0;

  :deep(.n-button) {
    white-space: nowrap;
    flex-shrink: 0;
  }

  :deep(.n-checkbox) {
    white-space: nowrap;
  }
}

.expand {
  flex-grow: 1;
  flex-basis: 0;
  min-width: 0;
}

.scroll-container {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  white-space: nowrap;
  flex-shrink: 0;
  margin-left: auto;
}

.scroll-label {
  white-space: nowrap;
}

.btn-text-short {
  display: none;
}

@container main-content (max-width: 500px) {
  .btn-text {
    display: none;
  }
  .btn-text-short {
    display: inline;
  }
  .scroll-label,
  .help-btn {
    display: none;
  }
}

@supports not (container-type: inline-size) {
  @media (max-width: 500px) {
    .btn-text {
      display: none;
    }
    .btn-text-short {
      display: inline;
    }
    .scroll-label,
    .help-btn {
      display: none;
    }
  }
}

.toggle-table-collapse-btn {
  position: absolute;
  top: 12px;
  right: 12px;
}

.log-bg {
  content: '';
  width: 100%;
  height: 100%;
  position: absolute;
  top: 0;
  left: 0;
  opacity: v-bind(bg_opacity);
  background-image: url(/bg.webp);
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
.sc {
  max-width: 480px;
  max-height: 270px;
  border-radius: 6px;
  z-index: 15;
}
</style>
