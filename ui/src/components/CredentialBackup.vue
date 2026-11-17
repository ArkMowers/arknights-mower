<script setup>
import { inject, onBeforeUnmount, ref, watch } from 'vue'
import { useConfigStore } from '@/stores/config'
import { usePlanStore, useRescuePlanStore } from '@/stores/plan'
import { createSaveCoordinator } from '@/utils/configPersistence'
import { reloadImportedConfiguration } from '@/utils/configBackup'

const axios = inject('axios')
const saves = createSaveCoordinator(useConfigStore(), usePlanStore(), [useRescuePlanStore()])
const savesPaused = saves.paused
const base = `${import.meta.env.VITE_HTTP_URL || ''}/credential-backup`
const headers = { 'X-Mower-Settings': '1' }
const mode = ref('')
const busy = ref(false)
const password = ref('')
const repeated = ref('')
const selected = ref(null)
const preview = ref(null)
const error = ref('')
const receipt = ref('')
const reloadRequired = ref(false)
const input = ref(null)

function clearSecrets() {
  password.value = ''
  repeated.value = ''
  selected.value = null
  preview.value = null
}

onBeforeUnmount(clearSecrets)
watch(password, () => (preview.value = null))

function open(next) {
  if (busy.value || savesPaused.value || reloadRequired.value) return
  clearSecrets()
  error.value = ''
  receipt.value = ''
  mode.value = next
}

function close() {
  if (busy.value) return
  clearSecrets()
  mode.value = ''
}

async function errorText(failure) {
  let detail = failure.response?.data
  if (detail instanceof Blob) {
    try {
      detail = JSON.parse(await detail.text())
    } catch {
      detail = null
    }
  }
  return detail?.message || failure.message || '凭据备份操作失败，请重试'
}

function form() {
  if (!selected.value) throw new Error('请选择凭据备份文件')
  const result = new FormData()
  result.append('backup', selected.value)
  result.append('password', password.value)
  return result
}

function chooseFile(event) {
  selected.value = null
  preview.value = null
  error.value = ''
  const file = event.target.files?.[0]
  event.target.value = ''
  if (!file) return
  if (file.size > 4 * 1024 * 1024) {
    error.value = '凭据备份文件不能超过 4 MiB'
    return
  }
  selected.value = file
}

async function exportBackup() {
  if (busy.value || savesPaused.value) return
  error.value = ''
  if ([...password.value].length < 12) {
    error.value = '备份口令至少需要 12 个字符，请使用较长且不重复使用的口令'
    return
  }
  if (password.value !== repeated.value) {
    error.value = '两次输入的备份口令不一致'
    return
  }
  busy.value = true
  try {
    await saves.drain()
    const { data } = await axios.post(
      `${base}/export`,
      { password: password.value },
      {
        headers,
        responseType: 'blob'
      }
    )
    const url = URL.createObjectURL(data)
    try {
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = `mower-credentials-${new Date().toISOString().replace(/[:.]/g, '-')}.mower-credentials`
      document.body.appendChild(anchor)
      anchor.click()
      anchor.remove()
    } finally {
      setTimeout(() => URL.revokeObjectURL(url), 1000)
    }
    receipt.value = '凭据备份已生成。请将备份文件和口令分开保管；忘记口令无法解密。'
    mode.value = ''
  } catch (failure) {
    error.value = await errorText(failure)
  } finally {
    clearSecrets()
    busy.value = false
  }
}

async function previewBackup() {
  if (busy.value || savesPaused.value) return
  busy.value = true
  error.value = ''
  preview.value = null
  try {
    const { data } = await axios.post(`${base}/preview`, form(), { headers })
    if (!data.ok) throw new Error(data.message)
    preview.value = data
  } catch (failure) {
    error.value = await errorText(failure)
    password.value = ''
  } finally {
    busy.value = false
  }
}

function reload() {
  reloadImportedConfiguration(null)
}

async function importBackup() {
  if (!preview.value || busy.value || savesPaused.value || reloadRequired.value) return
  busy.value = true
  error.value = ''
  let attempted = false
  try {
    await saves.pauseAndDrain()
    const body = form()
    body.append('confirmed', '1')
    attempted = true
    const { data } = await axios.post(`${base}/import`, body, { headers })
    if (!data.ok) throw new Error(data.message)
    receipt.value = data.message
    reloadRequired.value = true
    mode.value = ''
    reload()
  } catch (failure) {
    error.value = await errorText(failure)
    const changed = failure.response?.data?.code === 'configuration_changed'
    const rejected = failure.response?.status >= 400 && failure.response.status < 500
    if (!reloadRequired.value && !changed && (!attempted || rejected)) saves.resume()
    else reloadRequired.value = true
  } finally {
    clearSecrets()
    busy.value = false
  }
}
</script>

<template>
  <section
    class="credential-backup"
    data-settings-label="凭据备份与迁移"
    aria-label="凭据备份与迁移"
  >
    <div class="config-backup-copy">
      <span class="config-backup-label">凭据备份与迁移（可选）</span>
      <p>默认换机后重新填写凭据。需要一起迁移时，可单独导出由口令保护的凭据备份。</p>
      <p>
        包含当前档案的邮箱、森空岛、AI、MAA 和一图流凭据，以及共享的 GitHub Token、备用 AI Key。
        不包含其他档案和私钥；访问 Token 沿用目标机设置。排班和其他配置请使用完整备份迁移。
      </p>
      <p>
        私钥丢失时，请重新启动 Mower 进入凭据恢复页面；重置后可重新填写凭据或导入此前的凭据备份。
      </p>
    </div>
    <n-space>
      <n-button :disabled="busy || savesPaused || reloadRequired" @click="open('export')"
        >导出凭据备份</n-button
      >
      <n-button :disabled="busy || savesPaused || reloadRequired" @click="open('import')"
        >导入凭据备份</n-button
      >
    </n-space>
    <n-alert v-if="receipt" type="success" aria-live="polite">{{ receipt }}</n-alert>
    <n-alert v-if="reloadRequired" type="info" aria-live="polite">
      请重新加载页面后继续编辑，配置自动保存保持暂停，此次刷新不会自动开始任务。
      <n-button @click="reload">重新加载页面</n-button>
    </n-alert>
    <n-modal
      :show="Boolean(mode)"
      preset="card"
      :title="mode === 'export' ? '导出凭据备份' : '导入凭据备份'"
      style="width: min(540px, 94vw)"
      :closable="!busy"
      :mask-closable="!busy"
      :close-on-esc="!busy"
      @update:show="(show) => !show && close()"
    >
      <n-space vertical :size="16">
        <p class="config-backup-notice">
          口令只用于本次操作，不会保存。请使用较长且不重复使用的口令；忘记口令无法解密备份。
        </p>
        <template v-if="mode === 'import'">
          <n-button :disabled="busy" @click="input.click()">选择凭据备份文件</n-button>
          <input
            ref="input"
            type="file"
            accept=".mower-credentials"
            aria-label="选择凭据备份文件"
            hidden
            @change="chooseFile"
          />
          <n-text v-if="selected">{{ selected.name }}</n-text>
        </template>
        <n-input
          v-model:value="password"
          type="password"
          :disabled="busy"
          autocomplete="new-password"
          placeholder="备份口令（至少 12 个字符）"
          aria-label="备份口令"
        />
        <n-input
          v-if="mode === 'export'"
          v-model:value="repeated"
          type="password"
          :disabled="busy"
          autocomplete="new-password"
          placeholder="再次输入备份口令"
          aria-label="再次输入备份口令"
        />
        <n-alert v-if="preview" type="warning">
          <p>将覆盖以下类别中备份包含的凭据，未包含的凭据保留。共享凭据会影响本机其他实例。</p>
          <ul>
            <li v-for="group in preview.groups" :key="group.id">
              {{ group.label }}：{{ group.count }} 项
            </li>
          </ul>
          <p v-if="preview.clear_count">
            其中 {{ preview.clear_count }} 项为空值，导入后会清空对应凭据。
          </p>
          <p>请先停止 Mower。排班、其他配置和本机访问 Token 保持不变。导入成功后页面刷新。</p>
        </n-alert>
        <n-alert v-if="error" type="error" aria-live="polite">{{ error }}</n-alert>
        <n-space justify="end">
          <n-button :disabled="busy" @click="close">取消</n-button>
          <n-button
            v-if="mode === 'export'"
            type="primary"
            :loading="busy"
            :disabled="busy"
            @click="exportBackup"
            >加密并下载</n-button
          >
          <n-button
            v-else-if="!preview"
            type="primary"
            :loading="busy"
            :disabled="busy || !selected"
            @click="previewBackup"
            >解密并查看内容</n-button
          >
          <n-button v-else type="warning" :loading="busy" :disabled="busy" @click="importBackup"
            >确认覆盖凭据</n-button
          >
        </n-space>
      </n-space>
    </n-modal>
    <n-alert v-if="error && !mode" type="error" aria-live="polite">{{ error }}</n-alert>
  </section>
</template>

<style scoped>
.credential-backup {
  display: grid;
  gap: 16px;
  padding-top: 16px;
  border-top: 1px solid var(--settings-card-border);
}
</style>
