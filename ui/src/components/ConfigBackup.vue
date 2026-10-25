<script setup>
import { inject, ref } from 'vue'
import { useConfigStore } from '@/stores/config'
import { usePlanStore, useRescuePlanStore } from '@/stores/plan'
import { createSaveCoordinator } from '@/utils/configPersistence'
import { consumeImportResult, reloadImportedConfiguration } from '@/utils/configBackup'
import { downloadConfiguration } from '@/composables/configProfiles'

const axios = inject('axios')
const configStore = useConfigStore()
const planStore = usePlanStore()
const saves = createSaveCoordinator(configStore, planStore, [useRescuePlanStore()])
const savesPaused = saves.paused
const base = `${import.meta.env.VITE_HTTP_URL || ''}/config-backup`
const input = ref(null)
const busy = ref(false)
const error = ref('')
const selected = ref(null)
const filename = ref('')
const showConfirm = ref(false)
const savedResult = consumeImportResult()
const result = ref(savedResult?.recovery_path ? savedResult : null)
const pendingReload = ref(false)
const reloadRequired = ref(false)

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
    await downloadConfiguration(axios, `${base}/export`)
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
  if (busy.value || reloadRequired.value || savesPaused.value) return
  busy.value = true
  error.value = ''
  let attempted = false
  try {
    await saves.pauseAndDrain()
    const form = new FormData()
    form.append('backup', selected.value)
    attempted = true
    const { data } = await axios.post(`${base}/import`, form, {
      headers: { 'X-Mower-Settings': '1' }
    })
    if (!data.ok) {
      attempted = false
      throw new Error(data.message)
    }
    result.value = data
    showConfirm.value = false
    pendingReload.value = true
    reloadRequired.value = true
    // Keep old stores paused until the page reloads with the imported values.
    reload()
  } catch (err) {
    error.value = pendingReload.value
      ? `配置已恢复，但自动刷新未完成，请重试刷新页面：${await message(err)}`
      : await message(err)
    showConfirm.value = false
    const detail = err.response?.data
    const changed = (detail?.code || detail?.error) === 'configuration_changed'
    const rejected = err.response?.status >= 400 && err.response.status < 500
    if (!pendingReload.value && !changed && (!attempted || rejected)) saves.resume()
    else reloadRequired.value = true
  } finally {
    busy.value = false
  }
}

function reload() {
  reloadImportedConfiguration(pendingReload.value ? result.value : null)
}
</script>

<template>
  <n-card title="完整备份与恢复" class="config-backup">
    <n-space vertical :size="16">
      <p class="config-backup-notice">备份包含账号、密码和密钥，请妥善保管。</p>
      <div class="config-backup-actions">
        <div class="config-backup-row" data-settings-label="导出完整备份">
          <div class="config-backup-copy">
            <span class="config-backup-label">导出完整备份</span>
            <p>将当前实例的设置、排班与本地数据打包为 ZIP。</p>
          </div>
          <n-button :loading="busy" :disabled="busy || savesPaused" @click="exportConfig">
            导出完整备份
          </n-button>
        </div>
        <div class="config-backup-row" data-settings-label="恢复当前配置">
          <div class="config-backup-copy">
            <span class="config-backup-label">恢复当前配置</span>
            <p>使用 ZIP 备份覆盖当前档案的配置与对应数据，不新建档案。恢复前自动备份现有数据。</p>
          </div>
          <n-button :disabled="busy || savesPaused" @click="input.click()">恢复当前配置</n-button>
          <input
            ref="input"
            type="file"
            accept=".zip,application/zip"
            aria-label="选择完整配置备份"
            hidden
            @change="selectFile"
          />
        </div>
      </div>
      <n-collapse class="config-backup-help">
        <n-collapse-item
          title="备份内容与恢复说明"
          name="backup-help"
          data-settings-label="备份内容与恢复说明"
        >
          <dl class="config-backup-details">
            <div>
              <dt>备份内容</dt>
              <dd>
                包含当前实例的 config 配置文件与 tmp 数据表、库存和记录，不包含 state.json。
                主排班和所有备用排班均包含在 plan.json 中，数据库包含专精计划和历史数据。
                资源包、更新文件、其他实例及浏览器偏好不在备份中。
              </dd>
            </div>
            <div>
              <dt>恢复时保留</dt>
              <dd>
                保留当前管理页面端口、访问令牌和网络代理，以及需要重启生效的托盘和窗口尺寸。
                其余设置与数据按备份恢复，未包含的数据文件保持不变。
              </dd>
            </div>
            <div>
              <dt>恢复后加载</dt>
              <dd>
                恢复前自动备份现有设置及 tmp 数据，恢复后清空调度状态缓存。
                成功后自动刷新页面加载，无需重启 Mower，且此次刷新不会自动开始任务。
              </dd>
            </div>
          </dl>
        </n-collapse-item>
      </n-collapse>
      <n-alert v-if="error" type="error" aria-live="polite">{{ error }}</n-alert>
      <n-alert v-if="reloadRequired && !pendingReload" type="info" aria-live="polite">
        恢复结果尚未确认，配置自动保存保持暂停。请重新加载页面后继续编辑。
        <n-button @click="reload">重新加载页面</n-button>
      </n-alert>
      <n-alert v-if="result" type="success" title="当前配置已恢复" aria-live="polite">
        <n-space vertical>
          <n-text>{{ result.message }}</n-text>
          <n-text depth="3" class="recovery-path">恢复前备份：{{ result.recovery_path }}</n-text>
          <n-button v-if="pendingReload" @click="reload">重试刷新页面</n-button>
        </n-space>
      </n-alert>
    </n-space>
    <n-modal
      v-model:show="showConfirm"
      preset="dialog"
      title="恢复当前配置"
      positive-text="确认恢复"
      negative-text="取消"
      :loading="busy"
      :closable="!busy"
      :mask-closable="!busy"
      :close-on-esc="!busy"
      :negative-button-props="{ disabled: busy }"
      :positive-button-props="{ disabled: busy }"
      @positive-click="importConfig"
    >
      将使用「{{ filename }}」恢复设置及备份内的 tmp 数据表、库存和记录，覆盖对应本机数据，
      未包含的数据文件保持不变。保留当前管理页面端口、访问令牌和网络代理。请先停止
      Mower；恢复前会自动生成备份。托盘和窗口尺寸保持不变，恢复成功后自动刷新页面加载当前档案，
      无需重启 Mower，且此次刷新不会自动开始任务。
    </n-modal>
  </n-card>
</template>

<style>
.config-backup {
  container: config-backup / inline-size;
}

.config-backup-notice {
  margin: 0;
  color: var(--mower-text-muted);
  font-size: 12px;
  line-height: 1.65;
}

.config-backup-actions {
  display: grid;
}

.config-backup-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 16px 0;
}

.config-backup-row:first-child {
  padding-top: 0;
}

.config-backup-row:last-child {
  padding-bottom: 0;
}

.config-backup-row + .config-backup-row {
  border-top: 1px solid var(--settings-card-border);
}

.config-backup-copy {
  min-width: 0;
}

.config-backup-label {
  font-size: 14px;
}

.config-backup-copy p,
.config-backup-details dd {
  margin: 4px 0 0;
  color: var(--mower-text-muted);
  font-size: 12px;
  line-height: 1.65;
  text-wrap: pretty;
  overflow-wrap: anywhere;
}

.config-backup-row > .n-button {
  flex: none;
}

.config-backup .config-backup-help > .n-collapse-item {
  padding: 0;
  background: transparent;
}

.config-backup-details {
  display: grid;
  gap: 14px;
  margin: 0;
}

.config-backup-details dt {
  font-size: 13px;
}

.config-backup .recovery-path {
  overflow-wrap: anywhere;
}

@container config-backup (max-width: 360px) {
  .config-backup-row {
    align-items: flex-start;
    flex-direction: column;
    gap: 10px;
  }
}
</style>
