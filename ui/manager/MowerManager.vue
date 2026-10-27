<script setup>
import PlusIcon from '@vicons/ionicons5/es/Add'
import FolderIcon from '@vicons/ionicons5/es/FolderOpenOutline'
import PencilIcon from '@vicons/ionicons5/es/Pencil'
import PlayIcon from '@vicons/ionicons5/es/Play'
import StopIcon from '@vicons/ionicons5/es/Stop'
import SettingsIcon from '@vicons/ionicons5/es/SettingsOutline'
import TrashIcon from '@vicons/ionicons5/es/TrashOutline'
import WarningIcon from '@vicons/ionicons5/es/WarningOutline'
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { initializeManager, managerCall } from './bridge.js'

import BrowserIcon from '@vicons/ionicons5/es/GlobeOutline'
import CommonSettings from './CommonSettings.vue'
import ManagerTools from './ManagerTools.vue'
import DeviceSettingsEditor from './DeviceSettingsEditor.vue'

const toolsOpen = ref(false)
const deviceEditor = ref(null)
const preview = ref(null)
const previewLoading = ref(false)
const previewRevision = ref(0)
const instances = ref([])
const loading = ref(true)
const ready = ref(false)
const connected = ref(false)
const busy = ref(false)
const error = ref('')
const initializationError = ref('')
const confirmation = ref(null)
const pageOpening = ref(null)
const pageMode = ref('browser')
const rememberPageMode = ref(false)
const pageResult = ref(null)
const pageSummary = computed(() => {
  const count = (status) => (pageResult.value || []).filter((item) => item.status === status).length
  return `已派发 ${count('opened')} 个页面，跳过 ${count('skipped')} 个，失败 ${count('failed')} 个`
})
const deleting = ref(null)
const editing = ref(null)
const displayedEditing = ref(null)
// Keep the closing dialog's content and dimensions until its leave transition finishes.
watch(
  editing,
  (editor) => {
    if (editor) displayedEditing.value = editor
  },
  { flush: 'sync' }
)
const draft = ref({ name: '', token: '', port: null })
const batchDraft = ref([])
const batchAiRead = ref(false)
const batchBooleanColumns = [
  { key: 'ai_assistant_enabled', label: 'Mower AI 助手', change: changeBatchAssistant },
  { key: 'start_automatically', label: '启动后自动开始', change: changeBatchAutomatic },
  { key: 'extra_settings_visible', label: '更新与维护', change: changeBatchExtraSettings }
]
const batchSelection = computed(() => {
  const editableRows = batchDraft.value.filter((_, idx) => batchEditable(idx))
  return Object.fromEntries(
    batchBooleanColumns.map(({ key }) => {
      const selected = editableRows.filter((row) => row[key]).length
      return [
        key,
        {
          checked: editableRows.length > 0 && selected === editableRows.length,
          indeterminate: selected > 0 && selected < editableRows.length,
          disabled: unavailable.value || !!assistantConfirmation.value || !editableRows.length
        }
      ]
    })
  )
})
const batchResult = ref(null)
const commonDraft = ref({})
const commonOriginal = ref({})
const commonFields = ref([])
watch(
  commonDraft,
  () => {
    preview.value = null
    previewRevision.value += 1
  },
  { deep: true, flush: 'sync' }
)
const commonLoading = ref(false)
const commonError = ref('')
const commonChanged = computed(() => {
  const keys = new Set([...Object.keys(commonDraft.value), ...Object.keys(commonOriginal.value)])
  return [...keys].some(
    (key) => JSON.stringify(commonDraft.value[key]) !== JSON.stringify(commonOriginal.value[key])
  )
})
const batchChanges = computed(() => {
  if (displayedEditing.value?.kind !== 'batch') return []
  return batchDraft.value.flatMap((row, idx) => {
    const original = displayedEditing.value.originals[idx]
    const settings = Object.fromEntries(
      Object.entries(row).filter(([key, value]) => value !== original[key])
    )
    return Object.keys(settings).length ? [{ idx, settings }] : []
  })
})
const batchSummary = computed(() => {
  const results = batchResult.value?.results || []
  const count = (status) => results.filter((item) => item.status === status).length
  const prefix = batchResult.value?.common_saved ? '通用设置已保存。' : ''
  if (prefix && !results.length) return prefix
  return `${prefix}已更新 ${count('updated')} 个，跳过 ${count('skipped')} 个，失败 ${count('failed')} 个`
})
const assistantConfirmation = ref(null)
const riskAcknowledged = ref(false)
const riskSeconds = ref(5)
const unavailable = computed(() => loading.value || !ready.value || !connected.value || busy.value)
const riskReady = computed(
  () =>
    Boolean(assistantConfirmation.value) &&
    riskAcknowledged.value &&
    riskSeconds.value === 0 &&
    !unavailable.value
)
let timer
let riskTimer
let riskStartedAt = 0
let disposed = false
let refreshVersion = 0
const api = () => window.pywebview?.api
const statuses = { stopped: '已停止', starting: '启动中', running: '运行中', stopping: '停止中' }

async function refresh() {
  const version = ++refreshVersion
  const loaded = await managerCall(() => api().get_instances())
  if (!Array.isArray(loaded)) throw new Error('实例列表格式不正确')
  if (disposed || version !== refreshVersion) return
  acceptInstances(loaded)
}

function deviceSettingsAvailable() {
  return ['get_device_settings', 'update_device_settings', 'discover_device_settings'].every(
    (name) => typeof api()?.[name] === 'function'
  )
}

function editDevice(idx) {
  if (
    !deviceSettingsAvailable() ||
    unavailable.value ||
    !instances.value[idx]?.editable ||
    !instances.value[idx]?.path
  )
    return
  const { name, path } = instances.value[idx]
  deviceEditor.value = { idx, target: { name, path }, previousEditor: editing.value }
  editing.value = null
}

function closeDevice() {
  const previous = deviceEditor.value?.previousEditor
  deviceEditor.value = null
  if (!previous) return
  const current = instances.value[previous.idx]
  if (
    current?.editable &&
    current.name === previous.target.name &&
    current.path === previous.target.path
  )
    editing.value = previous
}

function deviceSaved() {
  closeDevice()
  void initialize()
}

function acceptInstances(loaded) {
  instances.value = loaded
  connected.value = true
  if (pageOpening.value) {
    const request = pageOpening.value
    const changed =
      request.kind === 'all'
        ? loaded.length !== request.targets.length ||
          loaded.some(
            (item, idx) =>
              item.name !== request.targets[idx].name || item.path !== request.targets[idx].path
          )
        : !loaded[request.idx]?.can_open_browser ||
          loaded[request.idx].name !== request.target.name ||
          loaded[request.idx].path !== request.target.path
    if (changed) {
      pageOpening.value = null
      error.value = '实例状态或列表已变化，请重新打开实例页面'
    }
  }
  if (deviceEditor.value) {
    const { idx, target } = deviceEditor.value
    const current = loaded[idx]
    if (!current?.editable || current.name !== target.name || current.path !== target.path)
      deviceEditor.value = null
  }
  if (editing.value?.kind === 'batch') {
    if (
      loaded.length !== editing.value.targets.length ||
      loaded.some(
        (item, idx) =>
          item.name !== editing.value.targets[idx].name ||
          item.path !== editing.value.targets[idx].path
      )
    ) {
      editing.value = null
      cancelAssistantConfirmation()
      error.value = '实例列表已变化，请重新打开配置管理'
    }
  } else if (editing.value) {
    const current = loaded[editing.value.idx]
    const { target } = editing.value
    if (!current?.editable || current.name !== target.name || current.path !== target.path) {
      editing.value = null
      cancelAssistantConfirmation()
    }
  }
  if (assistantConfirmation.value) {
    const target = assistantConfirmation.value
    if (target.kind === 'batch') {
      if (editing.value !== target.editor) cancelAssistantConfirmation()
    } else {
      const current = loaded[target.idx]
      if (
        editing.value !== target.editor ||
        !current?.editable ||
        current.name !== target.name ||
        current.path !== target.path ||
        (current.ai_assistant_enabled === true) !== target.original
      )
        cancelAssistantConfirmation()
    }
  }
  if (deleting.value) {
    const current = loaded[deleting.value.idx]
    if (
      !current?.editable ||
      current.name !== deleting.value.name ||
      current.path !== deleting.value.path
    )
      deleting.value = null
  }
}

async function initialize() {
  const version = ++refreshVersion
  loading.value = true
  initializationError.value = ''
  error.value = ''
  try {
    await initializeManager(async (loaded) => {
      if (disposed || version !== refreshVersion) return
      acceptInstances(loaded)
      ready.value = true
      await nextTick()
    })
  } catch (failure) {
    if (disposed || version !== refreshVersion) return
    connected.value = false
    initializationError.value = failure?.message || '无法加载实例列表，请重试'
  } finally {
    if (!disposed && version === refreshVersion) loading.value = false
  }
}

async function poll() {
  try {
    if (ready.value && !busy.value && !loading.value) await refresh()
  } catch (failure) {
    connected.value = false
    error.value = failure?.message || '无法读取实例状态，请稍后重试'
  } finally {
    if (!disposed) timer = setTimeout(poll, 1500)
  }
}

onMounted(async () => {
  await initialize()
  if (!disposed) timer = setTimeout(poll, 1500)
})
onUnmounted(() => {
  disposed = true
  clearTimeout(timer)
  cancelAssistantConfirmation()
})

async function execute(action, { waitForUser = false } = {}) {
  if (unavailable.value) return false
  busy.value = true
  error.value = ''
  let succeeded = false
  try {
    // A native dialog waits for the user; a frontend timeout cannot cancel it.
    const result = await (waitForUser ? action() : managerCall(action))
    if (result?.ok === false) throw new Error(result.message)
    succeeded = true
  } catch (failure) {
    error.value = failure?.message || '操作失败，请重试'
  } finally {
    try {
      await refresh()
    } catch (failure) {
      connected.value = false
      error.value = failure?.message || '无法读取实例状态，请稍后重试'
    }
    busy.value = false
  }
  return succeeded
}

function edit(idx, kind) {
  if (unavailable.value || !instances.value[idx]?.editable) return
  draft.value = {
    name: instances.value[idx].name,
    path: instances.value[idx].path,
    token: instances.value[idx].token,
    port: instances.value[idx].port,
    ai_assistant_enabled: instances.value[idx].ai_assistant_enabled === true,
    start_automatically: instances.value[idx].start_automatically === true,
    extra_settings_visible: instances.value[idx].extra_settings_visible === true
  }
  editing.value = {
    idx,
    kind,
    target: { name: draft.value.name, path: draft.value.path },
    originalAssistant: draft.value.ai_assistant_enabled,
    originalAutomatic: draft.value.start_automatically,
    originalExtraSettings: draft.value.extra_settings_visible
  }
}

function clearClosedEditor() {
  if (!editing.value) displayedEditing.value = null
}

async function editBatch() {
  if (unavailable.value) return
  error.value = ''
  const originals = instances.value.map((item) => ({
    token: item.token,
    port: item.port,
    ai_assistant_enabled: item.ai_assistant_enabled === true,
    start_automatically: item.start_automatically === true,
    extra_settings_visible: item.extra_settings_visible === true
  }))
  batchDraft.value = originals.map((row) => ({ ...row }))
  batchAiRead.value = false
  editing.value = {
    kind: 'batch',
    originals,
    targets: instances.value.map(({ name, path }) => ({ name, path }))
  }
  preview.value = null
  commonDraft.value = {}
  commonOriginal.value = {}
  commonError.value = ''
  await loadCommon()
}

async function previewCommon() {
  const editor = editing.value
  const revision = previewRevision.value
  previewLoading.value = true
  try {
    const result = await managerCall(() =>
      api().preview_common_settings({ ...commonDraft.value }, editor.targets)
    )
    if (editing.value === editor && revision === previewRevision.value) preview.value = result
  } catch (failure) {
    error.value = failure?.message || '无法预览通用设置'
  } finally {
    previewLoading.value = false
  }
}
function changeBatchAutomatic(enabled) {
  if (unavailable.value || assistantConfirmation.value) return
  for (let idx = 0; idx < batchDraft.value.length; idx++)
    if (batchEditable(idx)) batchDraft.value[idx].start_automatically = enabled
}
function changeBatchExtraSettings(enabled, idx = null) {
  if (editing.value?.kind !== 'batch' || unavailable.value || assistantConfirmation.value) return
  for (const index of idx === null ? batchDraft.value.map((_, index) => index) : [idx]) {
    if (batchEditable(index)) batchDraft.value[index].extra_settings_visible = enabled
  }
}
async function loadCommon() {
  const editor = editing.value
  commonLoading.value = true
  commonError.value = ''
  try {
    const result = await managerCall(() => api().get_common_settings())
    if (editing.value !== editor) return
    if (!result?.values || !Array.isArray(result.fields)) throw new Error('通用设置格式不正确')
    commonOriginal.value = structuredClone(result.values)
    commonDraft.value = structuredClone(result.values)
    commonFields.value = result.fields
  } catch (failure) {
    if (editing.value === editor) commonError.value = failure?.message || '无法加载通用设置'
  } finally {
    if (editing.value === editor) commonLoading.value = false
  }
}

function browseCommon(key) {
  const editor = editing.value
  return execute(
    async () => {
      const selected = await api().select_common_path(key, commonDraft.value[key] || '')
      if (selected && editing.value === editor) commonDraft.value[key] = selected
    },
    { waitForUser: true }
  )
}

function selectPath(idx) {
  if (unavailable.value || !instances.value[idx]?.editable) return
  const { name, path } = instances.value[idx]
  return execute(() => api().select_path(idx, { name, path }), { waitForUser: true })
}

async function save() {
  if (!editing.value || unavailable.value || assistantConfirmation.value) return
  const { idx, kind, target, originalAssistant, originalAutomatic, originalExtraSettings } =
    editing.value
  if (kind === 'batch') {
    if (
      commonLoading.value ||
      commonError.value ||
      (!batchChanges.value.length && !commonChanged.value)
    )
      return
    const changes = batchChanges.value
    const targets = editing.value.targets
    const common = commonChanged.value
      ? { values: { ...commonDraft.value }, original: { ...commonOriginal.value } }
      : null
    const succeeded = await execute(async () => {
      const result = common
        ? await api().update_all_settings(changes, targets, common)
        : await api().update_all_settings(changes, targets)
      if (result?.ok !== false) {
        if (!Array.isArray(result?.results))
          throw new Error('配置管理结果格式不正确，请刷新后检查各实例')
        batchResult.value = result
      }
      return result
    })
    if (succeeded) editing.value = null
    return
  }
  if (kind === 'name') {
    const succeeded = await execute(() => api().rename(idx, draft.value.name, target))
    if (succeeded) editing.value = null
    return
  }
  const settings = { token: draft.value.token, port: draft.value.port }
  if (draft.value.ai_assistant_enabled !== originalAssistant)
    settings.ai_assistant_enabled = draft.value.ai_assistant_enabled
  if (draft.value.start_automatically !== originalAutomatic)
    settings.start_automatically = draft.value.start_automatically
  if (draft.value.extra_settings_visible !== originalExtraSettings)
    settings.extra_settings_visible = draft.value.extra_settings_visible
  const succeeded = await execute(() => api().update_settings(idx, settings, target))
  if (succeeded) editing.value = null
}

async function changeAssistant(enabled) {
  if (
    editing.value?.kind !== 'settings' ||
    unavailable.value ||
    assistantConfirmation.value ||
    enabled === draft.value.ai_assistant_enabled
  )
    return
  if (!enabled) {
    draft.value.ai_assistant_enabled = false
    return
  }
  const { idx } = editing.value
  const current = instances.value[idx]
  if (!current?.editable) return
  await readAssistantRisk({
    idx,
    name: current.name,
    path: current.path,
    original: current.ai_assistant_enabled === true,
    editor: editing.value
  })
}

function batchEditable(idx) {
  return Boolean(instances.value[idx]?.editable && instances.value[idx]?.path)
}

async function changeBatchAssistant(enabled, idx = null) {
  if (editing.value?.kind !== 'batch' || unavailable.value || assistantConfirmation.value) return
  const rows = (idx === null ? batchDraft.value.map((_, index) => index) : [idx]).filter(
    (index) => batchEditable(index) && batchDraft.value[index].ai_assistant_enabled !== enabled
  )
  if (!rows.length) return
  if (!enabled || batchAiRead.value) {
    for (const index of rows) batchDraft.value[index].ai_assistant_enabled = enabled
    return
  }
  await readAssistantRisk({
    kind: 'batch',
    rows,
    name: `全部 ${editing.value.targets.length} 个实例（运行中的实例跳过）`,
    editor: editing.value
  })
}

async function readAssistantRisk(target) {
  assistantConfirmation.value = target
  const pending = assistantConfirmation.value
  riskAcknowledged.value = false
  riskSeconds.value = 5
  await nextTick()
  if (assistantConfirmation.value !== pending) return
  riskStartedAt = performance.now()
  riskTimer = setInterval(() => {
    riskSeconds.value = Math.max(0, Math.ceil((5000 - (performance.now() - riskStartedAt)) / 1000))
    if (riskSeconds.value === 0) clearInterval(riskTimer)
  }, 100)
}

function cancelAssistantConfirmation() {
  clearInterval(riskTimer)
  assistantConfirmation.value = null
  riskAcknowledged.value = false
  riskSeconds.value = 5
}

function confirmAssistantChange() {
  if (!riskReady.value || performance.now() - riskStartedAt < 5000) return false
  const target = assistantConfirmation.value
  if (target.kind === 'batch' && editing.value === target.editor) {
    batchAiRead.value = true
    for (const idx of target.rows) {
      if (batchEditable(idx)) batchDraft.value[idx].ai_assistant_enabled = true
    }
  } else if (editing.value?.kind === 'settings' && editing.value === target.editor)
    draft.value.ai_assistant_enabled = true
  cancelAssistantConfirmation()
  return false
}

function confirmBulk(action) {
  if (unavailable.value) return
  confirmation.value = action
}

async function applyBulk() {
  const action = confirmation.value
  confirmation.value = null
  await execute(() => api()[action === 'start' ? 'start_all' : 'stop_all']())
}

function lifecycle(idx) {
  const instance = instances.value[idx]
  if (instance.state === 'stopped' ? !instance.can_start : !instance.can_stop) return
  const target = { name: instance.name, path: instance.path }
  execute(() => api()[instance.state === 'stopped' ? 'start' : 'stop'](idx, target))
}

function openInstancePage(idx) {
  const instance = instances.value[idx]
  if (unavailable.value || pageOpening.value || !instance?.can_open_browser) return
  const target = { name: instance.name, path: instance.path }
  return dispatchPages({ kind: 'one', idx, target })
}

function openAllInstancePages() {
  if (
    unavailable.value ||
    pageOpening.value ||
    !instances.value.some((item) => item.can_open_browser)
  )
    return
  const targets = instances.value.map(({ name, path }) => ({ name, path }))
  return dispatchPages({ kind: 'all', targets })
}

function dispatchPages(request, mode, remember = false) {
  pageResult.value = null
  return execute(async () => {
    const result =
      request.kind === 'all'
        ? await api().open_instance_pages(request.targets, ...(mode ? [mode, remember] : []))
        : await api().open_instance_page(
            request.idx,
            request.target,
            ...(mode ? [mode, remember] : [])
          )
    if (result?.needs_mode && !mode) {
      pageMode.value = 'browser'
      rememberPageMode.value = false
      pageOpening.value = request
      return { ok: true }
    }
    if (Array.isArray(result?.results)) pageResult.value = result.results
    if (result?.ok === false && result?.results && !result.message)
      return { ...result, message: '部分页面未能打开，请查看逐实例结果' }
    return result
  })
}

function confirmPageMode() {
  if (unavailable.value || !pageOpening.value) return false
  const request = pageOpening.value
  pageOpening.value = null
  void dispatchPages(request, pageMode.value, rememberPageMode.value)
  return false
}

function confirmDelete(idx) {
  if (unavailable.value || !instances.value[idx].editable) return
  const { name, path } = instances.value[idx]
  deleting.value = { idx, name, path }
}

async function applyDelete() {
  const target = deleting.value
  deleting.value = null
  if (!target) return
  await execute(() => api().remove(target.idx, { name: target.name, path: target.path }))
}

function addInstance() {
  return execute(() => api().add('新实例', ''))
}
</script>

<template>
  <div class="mower-list" :data-manager-ready="ready">
    <div v-if="initializationError || error || batchResult || pageResult" class="manager-feedback">
      <n-alert v-if="initializationError" type="error">
        <div>{{ initializationError }}</div>
        <n-button size="small" @click="initialize">重新加载</n-button>
      </n-alert>
      <n-alert v-if="error" type="warning" closable @close="error = ''">{{ error }}</n-alert>
      <n-alert
        v-if="pageResult"
        :title="pageSummary"
        :type="pageResult.some((item) => item.status === 'failed') ? 'error' : 'info'"
        closable
        @close="pageResult = null"
      >
        <ul v-if="pageResult.some((item) => item.status !== 'opened')" class="batch-results">
          <li v-for="item in pageResult.filter((item) => item.status !== 'opened')" :key="item.idx">
            {{ item.name }}：{{ item.message }}
          </li>
        </ul>
      </n-alert>
      <n-alert
        v-if="batchResult"
        :title="batchSummary"
        :type="
          batchResult.results.some((item) => item.status === 'failed')
            ? 'error'
            : batchResult.results.some((item) => item.status === 'skipped')
              ? 'warning'
              : 'success'
        "
        closable
        @close="batchResult = null"
      >
        <ul
          v-if="batchResult.results.some((item) => item.status !== 'updated')"
          class="batch-results"
        >
          <li
            v-for="item in batchResult.results.filter((item) => item.status !== 'updated')"
            :key="item.idx"
          >
            {{ item.name }}：{{ item.message }}
          </li>
        </ul>
      </n-alert>
    </div>
    <div class="manager-heading">
      <div>
        <h1>多开管理器</h1>
        <p v-if="ready">
          {{ instances.length }} 个实例 ·
          {{ instances.filter((item) => item.state === 'running').length }} 个运行中
        </p>
        <p v-else>{{ loading ? '正在加载实例列表…' : '实例列表未加载' }}</p>
      </div>
    </div>
    <div class="bulk-actions">
      <n-button
        :disabled="unavailable || !instances.some((i) => i.can_start)"
        @click="confirmBulk('start')"
      >
        <template #icon
          ><n-icon><play-icon /></n-icon></template
        >全部打开
      </n-button>
      <n-button
        :disabled="unavailable || !instances.some((i) => i.can_open_browser)"
        @click="openAllInstancePages"
      >
        <template #icon
          ><n-icon><browser-icon /></n-icon
        ></template>
        一键开启页面
      </n-button>
      <n-button
        :disabled="unavailable || !instances.some((i) => i.can_stop)"
        @click="confirmBulk('stop')"
      >
        <template #icon
          ><n-icon><stop-icon /></n-icon></template
        >全部关闭
      </n-button>
      <n-button :disabled="unavailable" @click="editBatch">
        <template #icon
          ><n-icon><settings-icon /></n-icon></template
        >配置管理
      </n-button>
      <n-button :disabled="unavailable" @click="toolsOpen = true">维护工具</n-button>
    </div>
    <n-empty
      v-if="ready && !instances.length"
      description="添加实例，或先在配置管理中设置通用参数"
    />
    <n-skeleton v-if="loading" :height="140" />
    <n-card v-for="(instance, idx) in instances" :key="idx" size="small">
      <div class="instance-heading">
        <div class="instance-identity">
          <strong class="instance-name">{{ instance.name }}</strong>
          <n-button
            text
            size="small"
            class="instance-page-action"
            type="primary"
            :disabled="unavailable || !instance.can_open_browser"
            :aria-label="`${instance.name} 打开实例页面`"
            @click="openInstancePage(idx)"
          >
            <template #icon
              ><n-icon><browser-icon /></n-icon
            ></template>
            打开实例页面
          </n-button>
        </div>
        <n-tag size="small" :type="instance.state === 'running' ? 'success' : 'default'">{{
          statuses[instance.state]
        }}</n-tag>
        <n-button
          :type="instance.state === 'stopped' ? 'primary' : 'error'"
          size="small"
          :disabled="
            unavailable || (instance.state === 'stopped' ? !instance.can_start : !instance.can_stop)
          "
          @click="lifecycle(idx)"
        >
          <template #icon
            ><n-icon><play-icon v-if="instance.state === 'stopped'" /><stop-icon v-else /></n-icon
          ></template>
          {{ instance.state === 'stopped' ? '启动' : '停止' }}
        </n-button>
      </div>
      <div class="instance-toolbar">
        <div class="instance-tools">
          <n-button
            v-if="instance.can_open_browser"
            size="tiny"
            :disabled="unavailable"
            @click="execute(() => api().start(idx, { name: instance.name, path: instance.path }))"
            >打开窗口</n-button
          >
          <n-button
            size="tiny"
            title="修改实例名称"
            aria-label="修改实例名称"
            :disabled="unavailable || !instance.editable"
            @click="edit(idx, 'name')"
            ><template #icon
              ><n-icon><pencil-icon /></n-icon></template
          ></n-button>
          <n-button
            size="tiny"
            title="实例配置"
            aria-label="实例配置"
            :disabled="unavailable || !instance.editable || !instance.path"
            @click="edit(idx, 'settings')"
            ><template #icon
              ><n-icon><settings-icon /></n-icon></template
          ></n-button>
          <n-button
            size="tiny"
            title="选择保存目录"
            aria-label="选择保存目录"
            :disabled="unavailable || !instance.editable"
            @click="selectPath(idx)"
            ><template #icon
              ><n-icon><folder-icon /></n-icon></template
          ></n-button>
          <n-button
            size="tiny"
            type="error"
            ghost
            title="删除实例"
            aria-label="删除实例"
            :disabled="unavailable || !instance.editable"
            @click="confirmDelete(idx)"
            ><template #icon
              ><n-icon><trash-icon /></n-icon></template
          ></n-button>
        </div>
      </div>
      <code class="folder-content">{{ instance.path || '未选择保存目录' }}</code>
      <div class="connection-info">
        <span>端口：{{ instance.port || '随机' }}</span
        ><span>Token：{{ instance.token ? '已设置' : '未设置' }}</span
        ><span>自动开始任务：{{ instance.start_automatically ? '开' : '关' }}</span>
      </div>
      <div v-if="instance.reason && instance.state === 'stopped'" class="reason">
        {{ instance.reason }}
      </div>
    </n-card>
    <n-button v-if="ready" dashed :disabled="unavailable" @click="addInstance"
      ><template #icon
        ><n-icon><plus-icon /></n-icon></template
      >添加实例</n-button
    >
    <n-modal
      :show="!!deviceEditor"
      preset="card"
      :title="`${deviceEditor?.target.name || ''} · 连接与启动`"
      :style="{ width: 'min(800px, calc(100vw - 24px))' }"
      @update:show="
        (show) => {
          if (!show) closeDevice()
        }
      "
    >
      <device-settings-editor
        v-if="deviceEditor"
        :key="`${deviceEditor.target.name}:${deviceEditor.target.path}`"
        :api="api()"
        :idx="deviceEditor.idx"
        :target="deviceEditor.target"
        @saved="deviceSaved"
      />
    </n-modal>
    <n-modal
      :show="toolsOpen"
      preset="card"
      title="维护工具"
      :style="{ width: 'min(840px, calc(100vw - 24px))' }"
      @update:show="(show) => (toolsOpen = show)"
    >
      <div class="settings-content"><manager-tools v-if="toolsOpen" :api="api()" /></div>
    </n-modal>
    <n-modal
      :show="!!confirmation"
      preset="dialog"
      :title="confirmation === 'start' ? '打开全部可启动实例？' : '关闭全部运行实例？'"
      positive-text="确认"
      negative-text="取消"
      @positive-click="applyBulk"
      @negative-click="confirmation = null"
      @close="confirmation = null"
      @update:show="
        (show) => {
          if (!show) confirmation = null
        }
      "
    >
      {{
        confirmation === 'start'
          ? '仅启动当前允许启动的实例；运行中、未选择目录或端口不可用的实例不会启动。'
          : '运行中的实例将退出，正在进行的自动化也会停止。'
      }}
    </n-modal>
    <n-modal
      :show="!!deleting"
      preset="dialog"
      type="error"
      title="删除实例"
      positive-text="删除"
      negative-text="取消"
      @positive-click="applyDelete"
      @negative-click="deleting = null"
      @close="deleting = null"
      @update:show="
        (show) => {
          if (!show) deleting = null
        }
      "
    >
      <p class="delete-notice">是否确认删除“{{ deleting?.name }}”？</p>
      <p>仅从多开管理器移除该实例，不删除保存目录中的文件。</p>
    </n-modal>
    <n-modal
      :show="!!editing"
      preset="card"
      :title="
        displayedEditing?.kind === 'name'
          ? '实例名称'
          : displayedEditing?.kind === 'batch'
            ? '配置管理'
            : '实例配置'
      "
      class="settings-dialog"
      :style="{
        width:
          displayedEditing?.kind === 'batch'
            ? 'min(920px, calc(100vw - 24px))'
            : 'min(420px, calc(100vw - 24px))',
        borderRadius: '6px'
      }"
      :mask-closable="!busy && !assistantConfirmation"
      :closable="!busy && !assistantConfirmation"
      @after-leave="clearClosedEditor"
      @update:show="
        (show) => {
          if (!show) editing = null
        }
      "
    >
      <div class="settings-content">
        <n-alert v-if="error" type="error" class="dialog-error">{{ error }}</n-alert>
        <n-form v-if="displayedEditing" label-placement="top">
          <n-form-item v-if="displayedEditing.kind === 'name'" label="实例名称"
            ><n-input v-model:value="draft.name" :disabled="unavailable"
          /></n-form-item>
          <template v-else-if="displayedEditing.kind === 'batch'">
            <n-skeleton v-if="commonLoading" :height="44" />
            <n-alert v-else-if="commonError" type="error">
              {{ commonError }}
              <template #action><n-button @click="loadCommon">重新加载</n-button></template>
            </n-alert>
            <common-settings
              v-if="!commonLoading && !commonError"
              v-model:values="commonDraft"
              :fields="commonFields"
              :disabled="unavailable || !!assistantConfirmation"
              @browse="browseCommon"
            />
            <div class="preview-section">
              <n-button
                :disabled="unavailable || commonLoading || !!commonError || previewLoading"
                :loading="previewLoading"
                @click="previewCommon"
                >预览生效范围</n-button
              >
              <span>当前 {{ displayedEditing.targets.length }} 个实例及以后新增的实例</span>
              <div v-if="preview" class="preview-results" aria-live="polite">
                <p>
                  以下通用值在下次受管理启动时生效；独立配置保留本实例的连接和页面等待参数，已运行实例保留当前值。
                </p>
                <details v-for="row in preview.rows" :key="row.idx" :open="row.warnings.length > 0">
                  <summary>
                    {{ row.name }} · {{ row.fields.length }} 项<span v-if="row.warnings.length">
                      · 需要检查</span
                    >
                  </summary>
                  <p v-for="message in row.warnings" :key="message" class="reason">{{ message }}</p>
                  <ul>
                    <li v-for="field in row.fields" :key="field.label">
                      {{ field.label }}：{{ field.before ?? '实例默认值' }} → {{ field.after }}
                    </li>
                  </ul>
                </details>
              </div>
            </div>
            <h2 class="section-title">逐实例配置</h2>
            <p class="section-description">
              共
              {{ displayedEditing.targets.length }}
              个实例。勾选表头可批量设置可编辑实例；只保存修改过的单元格，运行中的实例会跳过。
            </p>
            <p class="section-description">
              “更新与维护”在下次启动时生效，控制实例页面的“网络与更新”和“数据与维护”两组及对应操作权限。关闭后隐藏这两组并禁止对应操作，管理器仍可执行维护。
            </p>
            <div class="batch-table-scroll">
              <table class="batch-table">
                <colgroup>
                  <col class="batch-name-col" />
                  <col class="batch-token-col" />
                  <col class="batch-port-col" />
                  <col class="batch-ai-col" />
                  <col class="batch-updates-col" />
                  <col class="batch-updates-col" />
                </colgroup>
                <thead>
                  <tr>
                    <th scope="col">实例名称</th>
                    <th scope="col">Token</th>
                    <th scope="col">端口</th>
                    <th v-for="column in batchBooleanColumns" :key="column.key" scope="col">
                      <n-checkbox
                        :checked="batchSelection[column.key].checked"
                        :indeterminate="batchSelection[column.key].indeterminate"
                        :disabled="batchSelection[column.key].disabled"
                        :aria-label="`批量设置${column.label}`"
                        @update:checked="(enabled) => column.change(enabled)"
                        >{{ column.label }}</n-checkbox
                      >
                    </th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(row, idx) in batchDraft" :key="idx">
                    <th scope="row">
                      <span class="batch-instance-name">{{
                        displayedEditing.targets[idx].name
                      }}</span>
                      <n-tag size="small" :type="batchEditable(idx) ? 'default' : 'warning'">{{
                        statuses[instances[idx]?.state] || '不可编辑'
                      }}</n-tag>
                    </th>
                    <td>
                      <n-input
                        v-model:value="row.token"
                        type="password"
                        show-password-on="click"
                        placeholder="未设置"
                        :disabled="unavailable || !batchEditable(idx)"
                        :aria-label="`${displayedEditing.targets[idx].name} Token`"
                      />
                    </td>
                    <td>
                      <n-input-number
                        v-model:value="row.port"
                        :min="1"
                        :max="65535"
                        :precision="0"
                        placeholder="随机"
                        clearable
                        :disabled="unavailable || !batchEditable(idx)"
                        :aria-label="`${displayedEditing.targets[idx].name} 端口`"
                      />
                    </td>
                    <td>
                      <n-checkbox
                        :checked="row.ai_assistant_enabled"
                        :disabled="unavailable || !batchEditable(idx) || !!assistantConfirmation"
                        :aria-disabled="
                          unavailable || !batchEditable(idx) || !!assistantConfirmation
                        "
                        :aria-label="`${displayedEditing.targets[idx].name} AI 助手`"
                        @update:checked="(enabled) => changeBatchAssistant(enabled, idx)"
                      />
                    </td>
                    <td>
                      <n-checkbox
                        v-model:checked="row.start_automatically"
                        :disabled="unavailable || !batchEditable(idx) || !!assistantConfirmation"
                        :aria-label="`${displayedEditing.targets[idx].name} 启动后自动开始任务`"
                      />
                    </td>
                    <td>
                      <n-checkbox
                        :checked="row.extra_settings_visible"
                        :disabled="unavailable || !batchEditable(idx) || !!assistantConfirmation"
                        :aria-label="`${displayedEditing.targets[idx].name} 更新与维护`"
                        @update:checked="(enabled) => changeBatchExtraSettings(enabled, idx)"
                      />
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </template>
          <template v-else>
            <n-form-item label="Token"
              ><n-input
                v-model:value="draft.token"
                type="password"
                show-password-on="click"
                placeholder="未设置"
                :disabled="unavailable"
            /></n-form-item>
            <n-form-item label="端口"
              ><n-input-number
                v-model:value="draft.port"
                :min="1"
                :max="65535"
                :precision="0"
                placeholder="随机"
                clearable
                :disabled="unavailable"
            /></n-form-item>
            <n-form-item label="Mower AI 助手">
              <n-switch
                :value="draft.ai_assistant_enabled"
                aria-label="Mower AI 助手"
                :disabled="unavailable || !!assistantConfirmation"
                @update:value="changeAssistant"
              />
            </n-form-item>
            <n-form-item label="启动后自动开始任务"
              ><n-switch
                v-model:value="draft.start_automatically"
                aria-label="启动后自动开始任务"
                :disabled="unavailable || !!assistantConfirmation"
            /></n-form-item>
            <n-form-item label="更新与维护">
              <n-space vertical>
                <n-switch
                  v-model:value="draft.extra_settings_visible"
                  aria-label="更新与维护"
                  :disabled="unavailable || !!assistantConfirmation"
                />
                <n-text depth="3">
                  下次启动时生效。开启后，实例页面显示“网络与更新”和“数据与维护”，并允许对应操作；关闭后隐藏这两组并禁止对应操作。管理器仍可执行维护。
                </n-text>
              </n-space>
            </n-form-item>
            <n-form-item v-if="deviceSettingsAvailable()" label="连接与启动">
              <n-button
                :disabled="unavailable || !!assistantConfirmation"
                @click="editDevice(displayedEditing.idx)"
                >配置连接、启动与运行参数</n-button
              >
            </n-form-item>
            <n-alert v-if="draft.token" type="warning"
              >设置 Token 后将允许远程连接，请妥善保管。</n-alert
            >
          </template>
        </n-form>
      </div>
      <template #footer
        ><div class="dialog-actions">
          <span v-if="displayedEditing?.kind === 'batch'" class="batch-change-count"
            >{{ commonChanged ? '通用设置已修改；' : '' }}已修改
            {{ batchChanges.length }} 个实例</span
          >
          <n-button :disabled="busy" @click="editing = null">取消</n-button
          ><n-button
            type="primary"
            :disabled="
              unavailable ||
              !!assistantConfirmation ||
              (displayedEditing?.kind === 'batch' &&
                (commonLoading || !!commonError || (!batchChanges.length && !commonChanged)))
            "
            :loading="busy"
            @click="save"
            >{{ displayedEditing?.kind === 'batch' ? '保存修改' : '保存' }}</n-button
          >
        </div></template
      >
    </n-modal>
    <n-modal
      :show="!!pageOpening"
      preset="dialog"
      title="选择实例页面打开方式"
      positive-text="打开"
      negative-text="取消"
      :positive-button-props="{ disabled: unavailable }"
      @positive-click="confirmPageMode"
      @negative-click="pageOpening = null"
      @close="pageOpening = null"
      @update:show="
        (show) => {
          if (!show) pageOpening = null
        }
      "
    >
      <p>请选择本次打开方式。勾选“记住我的选择”后，下次直接使用，也可在“配置管理”中修改。</p>
      <n-radio-group v-model:value="pageMode" aria-label="实例页面打开方式">
        <n-space vertical>
          <n-radio value="browser">外部默认浏览器</n-radio>
          <n-radio value="webview">内置 WebView</n-radio>
        </n-space>
      </n-radio-group>
      <n-checkbox v-model:checked="rememberPageMode" class="remember-page-mode"
        >记住我的选择</n-checkbox
      >
    </n-modal>
    <n-modal
      :show="!!assistantConfirmation"
      preset="dialog"
      type="warning"
      :title="
        assistantConfirmation?.kind === 'batch'
          ? '批量开启 Mower AI 助手前请阅读'
          : '开启 Mower AI 助手前请阅读'
      "
      :positive-text="riskSeconds > 0 ? `同意开启（${riskSeconds} 秒）` : '同意开启'"
      negative-text="取消"
      :positive-button-props="{ disabled: !riskReady }"
      @positive-click="confirmAssistantChange"
      @negative-click="cancelAssistantConfirmation"
      @close="cancelAssistantConfirmation"
      @update:show="
        (show) => {
          if (!show) cancelAssistantConfirmation()
        }
      "
    >
      <div class="ai-risk-content">
        <p>
          {{ assistantConfirmation?.kind === 'batch' ? '范围' : '实例' }}：{{
            assistantConfirmation?.name
          }}
        </p>
        <n-alert type="error" title="数据与隐私风险" class="ai-risk-notice">
          <template #icon
            ><n-icon><warning-icon /></n-icon
          ></template>
          <p>
            Mower AI
            助手可通过工具读取日志、配置、排班等本地信息，并将对话内容及工具读取结果发送至已配置的模型服务。
          </p>
          <p>
            多开实例不等同于数据隔离。工具访问范围或权限限制不当时，可能泄露当前实例、其他实例或他人的敏感信息，请仅向可信用户开放。
          </p>
        </n-alert>
        <p>对话可能产生模型调用费用；助手支持数据查询和部分配置操作，请人工核对回答及操作结果。</p>
        <p>此选择仅影响当前实例的助手对话，不影响模型服务配置、诊断分析或验证码处理。</p>
      </div>
      <n-checkbox v-model:checked="riskAcknowledged">我已阅读并了解上述风险</n-checkbox>
    </n-modal>
  </div>
</template>

<style scoped>
.mower-list {
  box-sizing: border-box;
  width: 100%;
  padding: 20px;
  -webkit-font-smoothing: antialiased;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.manager-feedback {
  display: grid;
  gap: 10px;
}
.remember-page-mode {
  display: flex;
  margin-top: 16px;
}
.bulk-actions,
.instance-heading,
.instance-toolbar,
.instance-tools,
.connection-info,
.dialog-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}
.manager-heading h1 {
  margin: 0;
  font-size: 21px;
  font-weight: 600;
  text-wrap: balance;
}
.manager-heading p {
  margin: 6px 0 12px;
  color: #666;
  font-variant-numeric: tabular-nums;
}
.section-title {
  font-size: 16px;
  margin: 20px 0 6px;
}
.section-description {
  margin: 0 0 14px;
  color: #666;
}
.preview-section {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
}
.preview-section > span {
  color: #666;
  font-size: 12px;
}
.preview-results {
  width: 100%;
  padding: 12px;
  background: #f7f8fa;
  border-radius: 8px;
  overflow-wrap: anywhere;
}
.preview-results summary {
  cursor: pointer;
  padding: 10px 0;
}
.instance-tools :deep(.n-button) {
  min-height: 40px;
  min-width: 40px;
}
.connection-info,
.batch-change-count {
  font-variant-numeric: tabular-nums;
}
.bulk-actions {
  flex-wrap: wrap;
}
.instance-heading {
  min-height: 32px;
}
.instance-identity {
  display: flex;
  align-items: center;
  flex: 1;
  min-width: 0;
  flex-wrap: wrap;
  gap: 12px;
}
.instance-name {
  min-width: 0;
  overflow-wrap: anywhere;
  font-size: 15px;
}
.instance-toolbar {
  flex-wrap: wrap;
  margin: 10px 0;
}
.instance-page-action {
  flex-shrink: 0;
}
.folder-content {
  display: block;
  overflow-wrap: anywhere;
  color: inherit;
  opacity: 0.7;
  font-size: 12px;
}
.connection-info {
  flex-wrap: wrap;
  margin-top: 8px;
  color: inherit;
  opacity: 0.65;
  font-size: 12px;
}
.reason {
  margin-top: 8px;
  color: #a15812;
  font-size: 12px;
  overflow-wrap: anywhere;
}
.delete-notice {
  overflow-wrap: anywhere;
}
.ai-risk-content {
  max-height: min(320px, calc(100dvh - 240px));
  overflow-y: auto;
  overflow-wrap: anywhere;
}
.ai-risk-notice p:first-child {
  margin-top: 0;
}
.ai-risk-notice p:last-child {
  margin-bottom: 0;
}
.batch-change-count {
  margin-right: auto;
  font-size: 13px;
  color: inherit;
  opacity: 0.65;
}
.batch-table-scroll {
  max-height: min(440px, calc(100dvh - 260px));
  overflow: auto;
  border: 1px solid var(--n-border-color, #e5e7eb);
}
.settings-content {
  max-height: calc(100dvh - 200px);
  overflow-y: auto;
}
.dialog-error {
  margin-bottom: 12px;
}
.batch-table {
  width: 100%;
  min-width: 960px;
  table-layout: fixed;
  border-spacing: 0;
  font-size: 13px;
}
.batch-name-col {
  width: 160px;
}
.batch-token-col {
  width: 220px;
}
.batch-port-col {
  width: 180px;
}
.batch-ai-col {
  width: 140px;
}
.batch-updates-col {
  width: 120px;
}
.batch-table th,
.batch-table td {
  padding: 10px;
  text-align: left;
  border-bottom: 1px solid var(--n-border-color, #e5e7eb);
  background: var(--n-color, #fff);
}
.batch-table thead th {
  position: sticky;
  top: 0;
  z-index: 2;
  background: var(--n-action-color, #f5f6f8);
  font-weight: 500;
}
.batch-table th:first-child {
  position: sticky;
  left: 0;
  z-index: 1;
  border-right: 1px solid var(--n-border-color, #e5e7eb);
}
.batch-table thead th:first-child {
  z-index: 3;
}
.batch-instance-name {
  display: block;
  overflow-wrap: anywhere;
  margin-bottom: 6px;
  font-weight: 500;
}
.batch-results {
  max-height: 240px;
  overflow-y: auto;
  overflow-wrap: anywhere;
  padding-left: 20px;
  margin: 0;
}
.dialog-actions {
  justify-content: flex-end;
}
</style>
