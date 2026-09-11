<script setup>
import { inject, nextTick, ref } from 'vue'
import { useConfigStore } from '@/stores/config'
import { usePlanStore } from '@/stores/plan'
import {
  consumeImportResult,
  readBrowserSettings,
  reloadImportedConfiguration
} from '@/utils/configBackup'

const props = defineProps({
  saveNetwork: { type: Function, required: true },
  saveUpdates: { type: Function, required: true }
})
const axios = inject('axios')
const configStore = useConfigStore()
const planStore = usePlanStore()
const base = `${import.meta.env.VITE_HTTP_URL || ''}/config-backup`
const input = ref(null)
const busy = ref(false)
const error = ref('')
const selected = ref(null)
const filename = ref('')
const showConfirm = ref(false)
const result = ref(consumeImportResult())
const pendingReload = ref(false)

function message(err) {
  return err.response?.data?.message || err.message || '操作失败，请重试'
}

async function flushSettings() {
  configStore.autosave_paused = true
  planStore.autosave_paused = true
  await nextTick()
  await configStore.flush_pending_saves()
  await planStore.save_plan()
  if (!(await props.saveNetwork())) throw new Error('网络设置尚未保存，请先检查上方网络设置')
  await props.saveUpdates()
}

function resumeSaving() {
  configStore.autosave_paused = false
  planStore.autosave_paused = false
}

async function exportConfig() {
  busy.value = true
  error.value = ''
  try {
    await flushSettings()
    const { data } = await axios.get(`${base}/export`)
    data.browser_settings = readBrowserSettings()
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
    )
    const link = document.createElement('a')
    link.href = url
    link.download = `mower-config-${new Date().toISOString().replace(/[:.]/g, '-')}.json`
    document.body.appendChild(link)
    link.click()
    link.remove()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
  } catch (err) {
    error.value = message(err)
  } finally {
    resumeSaving()
    busy.value = false
  }
}

async function selectFile(event) {
  const file = event.target.files?.[0]
  event.target.value = ''
  if (!file) return
  error.value = ''
  busy.value = true
  selected.value = null
  try {
    if (file.size > 16 * 1024 * 1024) throw new Error('备份文件不能超过 16 MB')
    const backup = JSON.parse(await file.text())
    if (backup?.format !== 'arknights-mower-config' || backup.version !== 1 || !backup.data) {
      throw new Error('请选择 Mower 导出的完整配置 JSON 文件')
    }
    selected.value = backup
    filename.value = file.name
    showConfirm.value = true
  } catch (err) {
    error.value =
      err instanceof SyntaxError ? '无法解析 JSON 文件，请重新选择完整配置备份' : message(err)
  } finally {
    busy.value = false
  }
}

async function importConfig() {
  busy.value = true
  error.value = ''
  try {
    await flushSettings()
    const { data } = await axios.post(
      `${base}/import`,
      { ...selected.value, current_browser_settings: readBrowserSettings() },
      { headers: { 'X-Mower-Settings': '1' } }
    )
    if (!data.ok) throw new Error(data.message)
    result.value = data
    showConfirm.value = false
    pendingReload.value = true
    // Keep old stores paused until the page reloads with the imported values.
    reload()
  } catch (err) {
    error.value = pendingReload.value
      ? `配置已导入，但自动刷新未完成，请重试刷新页面：${message(err)}`
      : message(err)
    showConfirm.value = false
    if (!pendingReload.value) resumeSaving()
  } finally {
    busy.value = false
  }
}

function reload() {
  reloadImportedConfiguration(selected.value.browser_settings, result.value)
}
</script>

<template>
  <n-card title="配置导出与导入">
    <n-space vertical :size="16">
      <n-text>
        备份当前实例的全部 Mower 配置：Mower 与 MAA 设置、主排班及备用排班、所有周计划与库存规则、
        专精计划与训练员配置、加工站配置、保全派驻作业、窗口与页面偏好，以及共享网络设置、软件更新设置和森空岛设备信息。
      </n-text>
      <n-text depth="3">
        导入时保留当前管理页面端口、访问令牌和网络代理，以及需要重启生效的托盘和窗口尺寸。
        其余配置按备份恢复，并自动刷新页面加载，无需重启 Mower。
        备份包含账号、密码和密钥，请妥善保管。导入前会自动备份现有配置。
        不包含程序文件、其他实例、日志、统计记录和仓库识别数据。
      </n-text>
      <n-space>
        <n-button :loading="busy" :disabled="busy || pendingReload" @click="exportConfig">
          导出全部配置
        </n-button>
        <n-button :disabled="busy || pendingReload" @click="input.click()">导入配置</n-button>
        <input
          ref="input"
          type="file"
          accept=".json,application/json"
          aria-label="选择完整配置备份"
          hidden
          @change="selectFile"
        />
      </n-space>
      <n-alert v-if="error" type="error" aria-live="polite">{{ error }}</n-alert>
      <n-alert v-if="result" type="success" title="配置已导入" aria-live="polite">
        <n-space vertical>
          <n-text>{{ result.message }}</n-text>
          <n-text depth="3" class="recovery-path">导入前备份：{{ result.recovery_path }}</n-text>
          <n-button v-if="pendingReload" @click="reload">重试刷新页面</n-button>
        </n-space>
      </n-alert>
    </n-space>
    <n-modal
      v-model:show="showConfirm"
      preset="dialog"
      title="导入配置"
      positive-text="确认导入"
      negative-text="取消"
      :loading="busy"
      :closable="!busy"
      :mask-closable="!busy"
      :close-on-esc="!busy"
      :negative-button-props="{ disabled: busy }"
      :positive-button-props="{ disabled: busy }"
      @positive-click="importConfig"
    >
      将使用「{{ filename }}」恢复配置，保留当前管理页面端口、访问令牌和网络代理。 请先停止
      Mower；导入前会自动生成恢复备份。托盘和窗口尺寸保持不变，导入成功后自动刷新页面加载新配置，
      无需重启 Mower，且此次刷新不会自动开始任务。
    </n-modal>
  </n-card>
</template>

<style scoped>
.n-button {
  min-height: 40px;
}
.recovery-path {
  overflow-wrap: anywhere;
}
</style>
