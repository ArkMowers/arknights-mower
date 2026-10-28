<script setup>
import { i18n } from '@/i18n'
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
  return (
    err.response?.data?.message ||
    err.message ||
    i18n.global.t('settings.backup.operationFailedPleaseTryAgain')
  )
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
    if (file.size > 16 * 1024 * 1024)
      throw new Error(i18n.global.t('settings.backup.theBackupFileMustNotExceed16'))
    if (!/\.zip$/i.test(file.name))
      throw new Error(i18n.global.t('settings.backup.chooseAZipBackupContainingAConfig'))
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
      ? i18n.global.t('settings.backup.configurationRestoredButAutomaticReloadFailedRetry', {
          value0: await message(err)
        })
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
  <n-card :title="i18n.global.t('settings.backup.fullBackupRestore')" class="config-backup">
    <n-space vertical :size="16">
      <p class="config-backup-notice">
        {{ i18n.global.t('settings.backup.backupsIncludeAccountsPasswordsAndKeysKeep') }}
      </p>
      <div class="config-backup-actions">
        <div
          class="config-backup-row"
          :data-settings-label="i18n.global.t('settings.backup.exportFullBackup')"
        >
          <div class="config-backup-copy">
            <span class="config-backup-label">{{
              i18n.global.t('settings.backup.exportFullBackup')
            }}</span>
            <p>
              {{ i18n.global.t('settings.backup.packageThisInstanceSSettingsSchedulingPlans') }}
            </p>
          </div>
          <n-button :loading="busy" :disabled="busy || savesPaused" @click="exportConfig">
            {{ i18n.global.t('settings.backup.exportFullBackup') }}
          </n-button>
        </div>
        <div
          class="config-backup-row"
          :data-settings-label="i18n.global.t('settings.backup.restoreCurrentConfiguration')"
        >
          <div class="config-backup-copy">
            <span class="config-backup-label">{{
              i18n.global.t('settings.backup.restoreCurrentConfiguration')
            }}</span>
            <p>
              {{ i18n.global.t('settings.backup.overwriteTheCurrentProfileSConfigurationAnd') }}
            </p>
          </div>
          <n-button :disabled="busy || savesPaused" @click="input.click()">{{
            i18n.global.t('settings.backup.restoreCurrentConfiguration')
          }}</n-button>
          <input
            ref="input"
            type="file"
            accept=".zip,application/zip"
            :aria-label="i18n.global.t('settings.backup.selectAFullConfigurationBackup')"
            hidden
            @change="selectFile"
          />
        </div>
      </div>
      <n-collapse class="config-backup-help">
        <n-collapse-item
          :title="i18n.global.t('settings.backup.backupContentsRestoreDetails')"
          name="backup-help"
          :data-settings-label="i18n.global.t('settings.backup.backupContentsRestoreDetails')"
        >
          <dl class="config-backup-details">
            <div>
              <dt>{{ i18n.global.t('settings.backup.backupContents') }}</dt>
              <dd>
                {{ i18n.global.t('settings.backup.containsThisInstanceSConfigFilesAnd') }}
              </dd>
            </div>
            <div>
              <dt>{{ i18n.global.t('settings.backup.preservedDuringRestore') }}</dt>
              <dd>
                {{ i18n.global.t('settings.backup.keepTheCurrentManagementPagePortAccess') }}
              </dd>
            </div>
            <div>
              <dt>{{ i18n.global.t('settings.backup.afterRestoration') }}</dt>
              <dd>
                {{ i18n.global.t('settings.backup.backUpTheCurrentSettingsAndTmp') }}
              </dd>
            </div>
          </dl>
        </n-collapse-item>
      </n-collapse>
      <n-alert v-if="error" type="error" aria-live="polite">{{ error }}</n-alert>
      <n-alert v-if="reloadRequired && !pendingReload" type="info" aria-live="polite">
        {{ i18n.global.t('settings.backup.theRestoreResultIsNotConfirmedConfiguration') }}
        <n-button @click="reload">{{ i18n.global.t('settings.backup.reloadPage') }}</n-button>
      </n-alert>
      <n-alert
        v-if="result"
        type="success"
        :title="i18n.global.t('settings.backup.currentConfigurationRestored')"
        aria-live="polite"
      >
        <n-space vertical>
          <n-text>{{ result.message }}</n-text>
          <n-text depth="3" class="recovery-path"
            >{{ i18n.global.t('settings.backup.backupFromBeforeRestoration')
            }}{{ result.recovery_path }}</n-text
          >
          <n-button v-if="pendingReload" @click="reload">{{
            i18n.global.t('settings.backup.retryPageReload')
          }}</n-button>
        </n-space>
      </n-alert>
    </n-space>
    <n-modal
      v-model:show="showConfirm"
      preset="dialog"
      :title="i18n.global.t('settings.backup.restoreCurrentConfiguration')"
      :positive-text="i18n.global.t('settings.backup.confirmRestore')"
      :negative-text="i18n.global.t('settings.backup.cancel')"
      :loading="busy"
      :closable="!busy"
      :mask-closable="!busy"
      :close-on-esc="!busy"
      :negative-button-props="{ disabled: busy }"
      :positive-button-props="{ disabled: busy }"
      @positive-click="importConfig"
    >
      {{ i18n.global.t('settings.backup.use') }}{{ filename
      }}{{ i18n.global.t('settings.backup.toRestoreSettingsAndTheBackedUp') }}
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
