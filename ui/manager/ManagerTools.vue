<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { managerCall } from './bridge'
import ManagerSoftwareUpdate from './ManagerSoftwareUpdate.vue'

const props = defineProps({ api: { type: Object, required: true } })
const tab = ref('network')
const busy = ref(false)
const error = ref('')
const notice = ref('')
const network = ref({ http_proxy: '', github_proxy: '' })
const originalNetwork = ref(null)
const groups = ref([])
const groupErrors = ref([])
const selectedTarget = ref(null)
const channel = ref('stable')
const component = ref('core')
const job = ref({ status: 'idle' })
const storage = ref([])
const cleanup = ref(null)
const days = ref(7)
const categories = ref(['log', 'screenshot'])
const group = computed(() => groups.value.find((item) => item.target === selectedTarget.value))
const canUpdate = computed(
  () =>
    job.value.status === 'completed' &&
    job.value.action === 'check' &&
    job.value.result?.available &&
    job.value.target === selectedTarget.value &&
    job.value.channel === channel.value &&
    job.value.component === component.value &&
    !group.value?.running
)
let timer
let disposed = false
let jobDeadline = 0

const bytes = (value) => `${(value / 1024 / 1024).toFixed(1)} MiB`
async function run(action) {
  if (busy.value) return
  busy.value = true
  error.value = ''
  notice.value = ''
  try {
    return await managerCall(action)
  } catch (failure) {
    error.value = failure?.message || '操作失败，请重试'
  } finally {
    busy.value = false
  }
}
async function loadNetwork() {
  await run(async () => {
    const values = await props.api.get_network_settings()
    if (disposed) return
    network.value = { ...values }
    originalNetwork.value = { ...values }
  })
}
async function saveNetwork() {
  await run(async () => {
    const values = await props.api.save_network_settings(
      { ...network.value },
      originalNetwork.value
    )
    if (disposed) return
    network.value = { ...values }
    originalNetwork.value = { ...values }
    notice.value = '网络配置已保存，后续网络请求使用新设置。'
  })
}
async function loadMaa() {
  await run(async () => {
    const result = await props.api.get_maa_installations()
    if (disposed) return
    groups.value = result.groups
    groupErrors.value = result.errors
    if (!groups.value.some((item) => item.target === selectedTarget.value))
      selectedTarget.value = groups.value[0]?.target || null
    job.value = await props.api.get_maintenance_status()
    if (job.value.status === 'running') {
      jobDeadline = performance.now() + 1800000
      scheduleJob()
    }
  })
}
function scheduleJob() {
  clearTimeout(timer)
  if (!disposed) timer = setTimeout(pollJob, 1000)
}
async function pollJob() {
  try {
    const snapshot = await managerCall(() => props.api.get_maintenance_status())
    if (disposed) return
    job.value = snapshot
    if (snapshot.status === 'running') {
      if (performance.now() >= jobDeadline) throw new Error('维护仍在进行，请重新加载状态')
      scheduleJob()
    }
  } catch (failure) {
    if (!disposed) error.value = failure?.message || '无法读取维护状态，请重新加载'
  }
}
async function maintenance(action) {
  await run(async () => {
    const result = await props.api.start_maa_maintenance(
      selectedTarget.value,
      channel.value,
      component.value,
      action
    )
    if (result?.ok === false) throw new Error(result.message)
    jobDeadline = performance.now() + 1800000
    await pollJob()
  })
}
async function loadStorage() {
  await run(async () => {
    const result = await props.api.get_storage_usage()
    if (!disposed) storage.value = result.rows
  })
}
async function clean() {
  const target = cleanup.value
  cleanup.value = null
  if (!target) return
  await run(async () => {
    const result = await props.api.clean_instance_storage(
      target.idx,
      { name: target.name, path: target.path },
      [...categories.value],
      days.value
    )
    if (result?.ok === false) throw new Error(result.message)
    notice.value = `已删除 ${result.deleted} 个文件，释放 ${bytes(result.freed)}。${result.errors.join('；')}`
    const current = await props.api.get_storage_usage()
    if (!disposed) storage.value = current.rows
  })
}
function changeTab(value) {
  if (busy.value) return
  tab.value = value
  error.value = notice.value = ''
  if (value === 'maa') loadMaa()
  else if (value === 'storage') loadStorage()
  else if (value === 'network') loadNetwork()
}
onMounted(loadNetwork)
onUnmounted(() => {
  disposed = true
  clearTimeout(timer)
})
</script>

<template>
  <div class="manager-tools" :aria-busy="busy">
    <n-alert v-if="error" type="error" role="alert">{{ error }}</n-alert>
    <n-alert v-if="notice" type="success" role="status">{{ notice }}</n-alert>
    <n-tabs
      :value="tab"
      type="line"
      :theme-overrides="{ tabGapMediumLine: '18px' }"
      @update:value="changeTab"
    >
      <n-tab-pane name="network" tab="网络代理" :disabled="busy">
        <p class="description">同一数据目录下的实例共用这些设置。保存后用于后续请求。</p>
        <n-form label-placement="top">
          <n-form-item label="HTTP 代理">
            <n-input
              v-model:value="network.http_proxy"
              placeholder="例如 http://127.0.0.1:7890，留空使用系统环境"
              :disabled="busy"
            />
          </n-form-item>
          <n-form-item label="GitHub 下载代理">
            <n-input
              v-model:value="network.github_proxy"
              placeholder="代理地址，留空直连"
              :disabled="busy"
            />
          </n-form-item>
        </n-form>
        <div class="actions">
          <n-button :disabled="busy" @click="loadNetwork">重新加载</n-button>
          <n-button
            type="primary"
            :loading="busy"
            :disabled="busy || !originalNetwork"
            @click="saveNetwork"
            >保存网络配置</n-button
          >
        </div>
      </n-tab-pane>
      <n-tab-pane name="mower" tab="Mower 更新" :disabled="busy">
        <manager-software-update :api="api" :disabled="job.status === 'running'" />
      </n-tab-pane>
      <n-tab-pane name="maa" tab="MAA 更新" :disabled="busy">
        <p class="description">
          按实际安装目录合并显示。更新前需停止使用该目录的实例，并允许这些实例更新。维护期间关闭窗口会收起到托盘，完成后可退出管理器。
        </p>
        <n-alert v-for="message in groupErrors" :key="message" type="warning">{{
          message
        }}</n-alert>
        <n-empty v-if="!groups.length" description="尚无已配置目录的实例" />
        <template v-else>
          <n-form label-placement="top">
            <n-form-item label="MAA 安装目录">
              <n-select
                v-model:value="selectedTarget"
                :options="groups.map((item) => ({ label: item.target, value: item.target }))"
                :disabled="busy || job.status === 'running'"
                :consistent-menu-width="false"
              />
            </n-form-item>
            <p class="description">
              使用实例：{{ group?.instances.join('、') }}；实例配置的更新通道：{{
                group?.channels.join('、')
              }}
            </p>
            <div class="form-grid">
              <n-form-item label="更新内容">
                <n-select
                  v-model:value="component"
                  :options="[
                    { label: 'MAA 本体', value: 'core' },
                    { label: 'MAA 资源', value: 'resource' }
                  ]"
                  :disabled="busy || job.status === 'running'"
                />
              </n-form-item>
              <n-form-item v-if="component === 'core'" label="本次更新通道">
                <n-select
                  v-model:value="channel"
                  :options="[
                    { label: '正式版', value: 'stable' },
                    { label: '公测版', value: 'beta' }
                  ]"
                  :disabled="busy || job.status === 'running'"
                />
              </n-form-item>
            </div>
          </n-form>
          <p class="description">使用 GitHub 官方源；本次选择不改写实例的更新偏好。</p>
          <n-alert
            v-if="job.status !== 'idle'"
            :type="job.status === 'failed' ? 'error' : 'info'"
            role="status"
          >
            {{ job.message }}
            <p v-if="job.result?.latest">
              当前：{{ job.result.current || '未安装或版本未知' }} → 最新：{{
                job.result.latest
              }}；{{ job.result.available ? '可更新' : '未发现可更新版本' }}
            </p>
            <n-progress
              v-if="job.status === 'running' && job.progress != null"
              type="line"
              :percentage="Math.round(job.progress * 100)"
            />
          </n-alert>
          <div class="actions">
            <n-button :disabled="busy" @click="loadMaa">刷新状态</n-button>
            <n-button :disabled="busy || job.status === 'running'" @click="maintenance('check')"
              >检查更新</n-button
            >
            <n-button type="primary" :disabled="busy || !canUpdate" @click="maintenance('update')"
              >更新所选目录</n-button
            >
          </div>
          <p v-if="group?.running" class="description">有实例正在运行，停止后刷新状态即可更新。</p>
        </template>
      </n-tab-pane>
      <n-tab-pane name="storage" tab="存储清理" :disabled="busy">
        <p class="description">
          统计日志、日常截图和报错归档。清理仅处理已停止实例，不删除配置、排班和数据库。
        </p>
        <div class="form-grid">
          <n-form-item label="清理范围"
            ><n-checkbox-group v-model:value="categories"
              ><n-checkbox value="log">日志</n-checkbox
              ><n-checkbox value="screenshot">截图与报错归档</n-checkbox></n-checkbox-group
            ></n-form-item
          >
          <n-form-item label="删除多少天前的文件（0 表示全部）"
            ><n-input-number v-model:value="days" :min="0" :max="3650" :precision="0"
          /></n-form-item>
        </div>
        <div class="actions">
          <n-button :loading="busy" :disabled="busy" @click="loadStorage">刷新占用</n-button>
        </div>
        <n-empty v-if="!storage.length" description="暂无实例" />
        <div v-for="row in storage" :key="row.idx" class="storage-row">
          <div>
            <strong>{{ row.name }}</strong>
            <p>日志 {{ bytes(row.log) }} · 截图 {{ bytes(row.screenshot) }}</p>
            <p v-if="row.warning">{{ row.warning }}</p>
            <p v-if="row.clean_reason">{{ row.clean_reason }}</p>
          </div>
          <n-button
            :disabled="
              busy ||
              !row.path ||
              !row.can_clean ||
              !!row.warning ||
              !categories.length ||
              days == null
            "
            @click="cleanup = row"
            >清理…</n-button
          >
        </div>
      </n-tab-pane>
    </n-tabs>
    <n-modal
      :show="!!cleanup"
      preset="dialog"
      type="warning"
      title="清理实例文件"
      positive-text="确认清理"
      negative-text="取消"
      @positive-click="clean"
      @negative-click="cleanup = null"
      @close="cleanup = null"
      @update:show="
        (show) => {
          if (!show) cleanup = null
        }
      "
    >
      将删除“{{ cleanup?.name }}”的{{ categories.includes('log') ? '日志' : ''
      }}{{ categories.length > 1 ? '及' : ''
      }}{{ categories.includes('screenshot') ? '截图与报错归档' : '' }}中{{
        days ? `${days} 天前` : '全部'
      }}的文件，删除后无法撤销。
    </n-modal>
  </div>
</template>

<style scoped>
.manager-tools {
  min-width: 0;
  display: grid;
  gap: 12px;
}
.manager-tools > :deep(.n-tabs) {
  min-width: 0;
}
.description {
  color: #666;
  line-height: 1.65;
  overflow-wrap: anywhere;
  text-wrap: pretty;
}
.form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}
.actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  justify-content: flex-end;
  margin: 12px 0;
}
.storage-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 16px 0;
  border-bottom: 1px solid #eee;
  font-variant-numeric: tabular-nums;
}
.storage-row p {
  margin: 4px 0 0;
  color: #666;
}
@media (max-width: 640px) {
  .form-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
