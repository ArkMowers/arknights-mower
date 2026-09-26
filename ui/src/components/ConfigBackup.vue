<script setup>
import { inject, ref } from 'vue'
import { useConfigStore } from '@/stores/config'
import { usePlanStore } from '@/stores/plan'
import { createSaveCoordinator } from '@/utils/configPersistence'
import { consumeImportResult, reloadImportedConfiguration } from '@/utils/configBackup'

const axios = inject('axios')
const configStore = useConfigStore()
const planStore = usePlanStore()
const saves = createSaveCoordinator(configStore, planStore)
const base = `${import.meta.env.VITE_HTTP_URL || ''}/config-backup`
const input = ref(null)
const busy = ref(false)
const error = ref('')
const selected = ref(null)
const filename = ref('')
const showConfirm = ref(false)
const result = ref(consumeImportResult())
const pendingReload = ref(false)

async function message(err) {
  // Axios keeps JSON error responses as Blob when downloading a ZIP.
  if (err.response?.data instanceof Blob) {
    try {
      const body = JSON.parse(await err.response.data.text())
      if (body.message) return body.message
    } catch {
      /* Fall back to the transport error. */
    }
  }
  return err.response?.data?.message || err.message || '操作失败，请重试'
}

async function exportConfig() {
  busy.value = true
  error.value = ''
  try {
    await saves.drain()
    const { data } = await axios.get(`${base}/export`, { responseType: 'blob' })
    const url = URL.createObjectURL(data)
    const link = document.createElement('a')
    link.href = url
    link.download = `mower-config-${new Date().toISOString().replace(/[:.]/g, '-')}.zip`
    document.body.appendChild(link)
    link.click()
    link.remove()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
  } catch (err) {
    error.value = await message(err)
  } finally {
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
    if (!/\.zip$/i.test(file.name)) throw new Error('请选择包含 config 文件夹的 ZIP 备份')
    selected.value = file
    filename.value = file.name
    showConfirm.value = true
  } catch (err) {
    error.value = await message(err)
  } finally {
    busy.value = false
  }
}

async function importConfig() {
  busy.value = true
  error.value = ''
  try {
    await saves.pauseAndDrain()
    const form = new FormData()
    form.append('backup', selected.value)
    const { data } = await axios.post(`${base}/import`, form, {
      headers: { 'X-Mower-Settings': '1' }
    })
    if (!data.ok) throw new Error(data.message)
    result.value = data
    showConfirm.value = false
    pendingReload.value = true
    // Keep old stores paused until the page reloads with the imported values.
    reload()
  } catch (err) {
    error.value = pendingReload.value
      ? `配置已导入，但自动刷新未完成，请重试刷新页面：${await message(err)}`
      : await message(err)
    showConfirm.value = false
    if (!pendingReload.value) saves.resume()
  } finally {
    busy.value = false
  }
}

function reload() {
  reloadImportedConfiguration(result.value)
}
</script>

<template>
  <n-card title="配置导出与导入">
    <n-space vertical :size="16">
      <n-text>
        将当前实例的 config 文件夹打包为 ZIP，保留 conf.yml、plan.json、周计划等配置原文件， 不包含
        state.json。主排班和所有备用排班均包含在 plan.json 中。
      </n-text>
      <n-text depth="3">
        导入时保留当前管理页面端口、访问令牌和网络代理，以及需要重启生效的托盘和窗口尺寸。
        其余配置按备份恢复，并自动刷新页面加载，无需重启 Mower。
        备份包含账号、密码和密钥，请妥善保管。导入前会自动备份现有配置。 config
        文件夹以外的数据（包括数据库、其他实例及浏览器偏好）不在备份中。
      </n-text>
      <n-space>
        <n-button :loading="busy" :disabled="busy || pendingReload" @click="exportConfig">
          导出配置
        </n-button>
        <n-button :disabled="busy || pendingReload" @click="input.click()">导入配置</n-button>
        <input
          ref="input"
          type="file"
          accept=".zip,application/zip"
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
