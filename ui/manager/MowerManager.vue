<script setup>
import {
  Add as PlusIcon,
  FolderOpenOutline as FolderIcon,
  Pencil as PencilIcon,
  Play as PlayIcon,
  Stop as StopIcon,
  SettingsOutline as SettingsIcon,
  TrashOutline as TrashIcon,
  WarningOutline as WarningIcon
} from '@vicons/ionicons5'
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue'
import { initializeManager, managerCall } from './bridge.js'

const instances = ref([])
const loading = ref(true)
const ready = ref(false)
const connected = ref(false)
const busy = ref(false)
const error = ref('')
const initializationError = ref('')
const confirmation = ref(null)
const deleting = ref(null)
const editing = ref(null)
const draft = ref({ name: '', token: '', port: null })
const assistantConfirmation = ref(null)
const riskAcknowledged = ref(false)
const riskSeconds = ref(5)
const unavailable = computed(() => !ready.value || !connected.value || busy.value)
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
const api = () => window.pywebview.api
const statuses = { stopped: '已停止', starting: '启动中', running: '运行中', stopping: '停止中' }

async function refresh() {
  const version = ++refreshVersion
  const loaded = await managerCall(() => api().get_instances())
  if (!Array.isArray(loaded)) throw new Error('实例列表格式不正确')
  if (disposed || version !== refreshVersion) return
  instances.value = loaded
  connected.value = true
  if (editing.value && !loaded[editing.value.idx]?.editable) editing.value = null
  if (assistantConfirmation.value) {
    const target = assistantConfirmation.value
    const current = loaded[target.idx]
    if (
      !current?.editable ||
      current.name !== target.name ||
      current.path !== target.path ||
      (current.ai_assistant_enabled === true) !== target.original
    )
      cancelAssistantConfirmation()
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
  loading.value = true
  initializationError.value = ''
  try {
    await initializeManager(async (loaded) => {
      instances.value = loaded
      ready.value = true
      connected.value = true
      await nextTick()
    })
  } catch (failure) {
    connected.value = false
    initializationError.value = failure?.message || '无法加载实例列表，请重试'
  } finally {
    loading.value = false
  }
}

async function poll() {
  try {
    if (ready.value && !busy.value) await refresh()
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
  if (unavailable.value || !instances.value[idx].editable) return
  draft.value = {
    ...instances.value[idx],
    ai_assistant_enabled: instances.value[idx].ai_assistant_enabled === true
  }
  editing.value = { idx, kind }
}

function selectPath(idx) {
  return execute(() => api().select_path(idx), { waitForUser: true })
}

async function save() {
  if (!editing.value || unavailable.value || assistantConfirmation.value) return
  const { idx, kind } = editing.value
  if (kind === 'name') {
    const succeeded = await execute(() => api().rename(idx, draft.value.name))
    if (succeeded) editing.value = null
    return
  }
  const settings = { token: draft.value.token, port: draft.value.port }
  const current = instances.value[idx]
  if (draft.value.ai_assistant_enabled !== (current.ai_assistant_enabled === true))
    settings.ai_assistant_enabled = draft.value.ai_assistant_enabled
  const succeeded = await execute(() => api().update_settings(idx, settings))
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
  assistantConfirmation.value = {
    idx,
    name: current.name,
    path: current.path,
    original: current.ai_assistant_enabled === true
  }
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
  if (editing.value?.kind === 'settings' && editing.value.idx === target.idx)
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
  await execute(() => window.pywebview.api[action === 'start' ? 'start_all' : 'stop_all']())
}

function lifecycle(idx) {
  const instance = instances.value[idx]
  if (instance.state === 'stopped' ? !instance.can_start : !instance.can_stop) return
  execute(() => window.pywebview.api[instance.state === 'stopped' ? 'start' : 'stop'](idx))
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
  await execute(() => api().remove(target.idx))
}
</script>

<template>
  <div class="mower-list" :data-manager-ready="ready">
    <n-alert v-if="initializationError" type="error">
      {{ initializationError }}
      <template #action><n-button @click="initialize">重新加载</n-button></template>
    </n-alert>
    <n-alert v-if="error" type="warning" closable @close="error = ''">{{ error }}</n-alert>
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
        :disabled="unavailable || !instances.some((i) => i.can_stop)"
        @click="confirmBulk('stop')"
      >
        <template #icon
          ><n-icon><stop-icon /></n-icon></template
        >全部关闭
      </n-button>
    </div>
    <n-skeleton v-if="loading" :height="140" />
    <n-card v-for="(instance, idx) in instances" :key="idx" size="small">
      <div class="instance-heading">
        <strong class="instance-name">{{ instance.name }}</strong>
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
      <div class="instance-tools">
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
      <code class="folder-content">{{ instance.path || '未选择保存目录' }}</code>
      <div class="connection-info">
        <span>端口：{{ instance.port || '随机' }}</span
        ><span>Token：{{ instance.token ? '已设置' : '未设置' }}</span>
      </div>
      <div v-if="instance.reason && instance.state === 'stopped'" class="reason">
        {{ instance.reason }}
      </div>
    </n-card>
    <n-button
      v-if="ready"
      dashed
      :disabled="unavailable"
      @click="execute(() => api().add('新实例', ''))"
      ><template #icon
        ><n-icon><plus-icon /></n-icon></template
      >添加实例</n-button
    >
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
      :title="editing?.kind === 'name' ? '实例名称' : '实例配置'"
      class="settings-dialog"
      :mask-closable="!busy && !assistantConfirmation"
      :closable="!busy && !assistantConfirmation"
      @update:show="
        (show) => {
          if (!show) editing = null
        }
      "
    >
      <n-form v-if="editing" label-placement="top">
        <n-form-item v-if="editing.kind === 'name'" label="实例名称"
          ><n-input v-model:value="draft.name" :disabled="unavailable"
        /></n-form-item>
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
          <n-alert v-if="draft.token" type="warning"
            >设置 Token 后将允许远程连接，请妥善保管。</n-alert
          >
        </template>
      </n-form>
      <template #footer
        ><div class="dialog-actions">
          <n-button :disabled="busy" @click="editing = null">取消</n-button
          ><n-button type="primary" :disabled="unavailable" :loading="busy" @click="save"
            >保存</n-button
          >
        </div></template
      >
    </n-modal>
    <n-modal
      :show="!!assistantConfirmation"
      preset="dialog"
      type="warning"
      title="开启 Mower AI 助手前请阅读"
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
        <p>实例：{{ assistantConfirmation?.name }}</p>
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
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.bulk-actions,
.instance-heading,
.instance-tools,
.connection-info,
.dialog-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}
.bulk-actions {
  flex-wrap: wrap;
}
.instance-heading {
  min-height: 32px;
}
.instance-name {
  min-width: 0;
  flex: 1;
  overflow-wrap: anywhere;
  font-size: 15px;
}
.instance-tools {
  margin: 10px 0;
}
.folder-content {
  display: block;
  overflow-wrap: anywhere;
  color: #555;
  font-size: 12px;
}
.connection-info {
  flex-wrap: wrap;
  margin-top: 8px;
  color: #666;
  font-size: 12px;
}
.reason {
  margin-top: 8px;
  color: #a15812;
  font-size: 12px;
  overflow-wrap: anywhere;
}
.settings-dialog {
  width: min(420px, calc(100vw - 24px));
  border-radius: 6px;
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
.dialog-actions {
  justify-content: flex-end;
}
</style>
