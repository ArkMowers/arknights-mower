<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { managerCall } from './bridge'

const props = defineProps({ api: { type: Object, required: true }, disabled: Boolean })
const info = ref(null)
const channel = ref('stable')
const background = ref(false)
const checked = ref(null)
const confirmation = ref(null)
const job = ref({ status: 'idle' })
const busy = ref(false)
const error = ref('')
const running = computed(() => job.value.status === 'running')
const blocked = computed(() => !info.value || info.value.blockers.length > 0)
const channels = computed(() =>
  (info.value?.channels || []).map((item) => ({
    ...item,
    disabled:
      item.value === 'dev' && info.value.deployment !== 'source' && info.value.platform !== 'win32'
  }))
)
let timer
let disposed = false
let deadline = 0
async function run(action, timeout = 15000) {
  if (busy.value) return
  busy.value = true
  error.value = ''
  try {
    return await managerCall(action, timeout)
  } catch (failure) {
    if (!disposed) error.value = failure?.message || '操作失败，请重试'
  } finally {
    busy.value = false
  }
}
async function poll() {
  clearTimeout(timer)
  const result = await managerCall(() => props.api.get_mower_update_status())
  if (disposed) return
  job.value = result
  if (result.status === 'running') {
    if (performance.now() >= deadline) throw new Error('更新仍在进行，请刷新状态')
    timer = setTimeout(
      () =>
        poll().catch((failure) => {
          if (!disposed) error.value = failure.message
        }),
      2000
    )
  }
}
async function load() {
  await run(async () => {
    const result = await props.api.get_mower_update_info()
    if (disposed) return
    if (!info.value) {
      channel.value = result.settings.channel
      background.value = result.settings.background
    }
    info.value = result
    deadline = performance.now() + 2700000
    await poll()
  })
}
async function check() {
  checked.value = null
  await run(async () => {
    const result = await props.api.check_mower_update(channel.value)
    if (!disposed) checked.value = result
  }, 120000)
}
function requestInstall() {
  if (props.disabled || busy.value || running.value || blocked.value || !checked.value?.available)
    return
  confirmation.value = { ...checked.value, background: background.value }
}
async function install() {
  const target = confirmation.value
  confirmation.value = null
  if (!target || props.disabled) return
  await run(async () => {
    await props.api.start_mower_update(target.check_id, target.background)
    checked.value = null
    deadline = performance.now() + 2700000
    await poll()
  }, 120000)
}
async function cancel() {
  await run(async () => {
    await props.api.cancel_mower_update(job.value.id)
    await poll()
  })
}
watch(channel, () => {
  checked.value = null
})
onMounted(load)
onUnmounted(() => {
  disposed = true
  clearTimeout(timer)
})
</script>

<template>
  <div class="software-update" :aria-busy="busy">
    <p class="description">
      更新此安装目录下的 Mower，并重启管理器及原本运行的实例。实例 Web 中仍可使用原有软件更新功能。
    </p>
    <n-alert v-if="error" type="error" role="alert">{{ error }}</n-alert>
    <n-alert v-for="message in info?.blockers || []" :key="message" type="warning">{{
      message
    }}</n-alert>
    <p>
      当前版本：{{ info?.version || '—'
      }}<span v-if="info"
        >（{{ info.deployment === 'source' ? '源码部署' : 'Release 独立包' }}）</span
      >
    </p>
    <n-form label-placement="top">
      <n-form-item label="本次更新渠道">
        <n-select
          v-model:value="channel"
          :options="channels"
          :disabled="busy || running || disabled || !info"
          :consistent-menu-width="false"
        />
      </n-form-item>
      <p class="description">{{ channels.find((item) => item.value === channel)?.description }}</p>
      <n-checkbox v-model:checked="background" :disabled="busy || running || disabled"
        >更新后后台静默重启</n-checkbox
      >
    </n-form>
    <n-alert v-if="checked" :type="checked.available ? 'info' : 'success'" role="status">
      目标版本：{{ checked.version }}；{{ checked.available ? '可更新' : '已与渠道一致' }}
      <p v-if="checked.message">{{ checked.message }}</p>
    </n-alert>
    <n-alert
      v-if="job.status !== 'idle'"
      :type="job.status === 'failed' ? 'error' : 'info'"
      role="status"
    >
      {{ job.message }}
      <p v-if="job.status === 'running'">
        更新程序会暂时关闭此窗口，完成后恢复管理器和原本运行的实例。
      </p>
    </n-alert>
    <div class="actions">
      <n-button :disabled="busy" @click="load">刷新状态</n-button>
      <n-button :loading="busy" :disabled="busy || running || disabled || !info" @click="check"
        >检查更新</n-button
      >
      <n-button
        type="primary"
        :disabled="busy || running || disabled || blocked || !checked?.available"
        @click="requestInstall"
        >下载并安装</n-button
      >
      <n-button v-if="running && job.cancellable" :disabled="busy" @click="cancel"
        >取消更新</n-button
      >
    </div>
    <n-modal
      :show="!!confirmation"
      preset="dialog"
      type="warning"
      title="确认安装并重启？"
      positive-text="确认安装"
      negative-text="取消"
      @positive-click="install"
      @negative-click="confirmation = null"
      @close="confirmation = null"
      @update:show="
        (show) => {
          if (!show) confirmation = null
        }
      "
    >
      将安装 {{ confirmation?.version }}，并重启管理器及同一安装目录下的
      {{ info?.instances.length || 0 }}
      个运行实例。原本运行中的实例保留已保存的心情、位置和任务队列继续运行；安装失败时尝试恢复原版本。
    </n-modal>
  </div>
</template>

<style scoped>
.software-update {
  min-width: 0;
  display: grid;
  gap: 12px;
}
.description {
  color: #666;
  line-height: 1.65;
  overflow-wrap: anywhere;
}
.actions {
  display: flex;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: 8px;
}
</style>
