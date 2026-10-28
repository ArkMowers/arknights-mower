<script setup>
import { i18n } from '@/i18n'
import axios from 'axios'
import { NCard, useDialog } from 'naive-ui'
import { computed, onMounted, ref } from 'vue'
import { resourceUpdateMessage } from '@/utils/resourceUpdatePresentation'
import { storeToRefs } from 'pinia'
import { useConfigStore } from '@/stores/config'
import { usePlanStore } from '@/stores/plan'
import { useResourceVersionStore } from '@/stores/resourceVersion'
import { useUpdateProgress } from '@/composables/useUpdateProgress'
import { getDroppedFile, postManualUpdate } from '@/utils/manualUpdate'
import '@/styles/updates.css'
import UpdatePreview from './UpdatePreview.vue'
import { showResourceUpdateDialog } from '@/utils/updateDialog'

const props = defineProps({ skipInitialCheck: Boolean, compact: Boolean, preview: Object })
defineExpose({ installCheckedUpdate: install_resource })

const dialogs = useDialog()

const manual_url = `${import.meta.env.VITE_HTTP_URL}/resource-update/manual`

const config_store = useConfigStore()
const { resource_update_enable, resource_update_auto_update } = storeToRefs(config_store)
const { load_item, load_shop } = config_store

const plan_store = usePlanStore()
const { load_operators } = plan_store

const resource_store = useResourceVersionStore()
const { canInstall, info, loading, installing, install_message, job, progress_error } =
  storeToRefs(resource_store)
const { loadResourceVersion, loadResourceVersionLocal, installResource, loadResourceJob } =
  resource_store
const showProgress = useUpdateProgress(job)

const manual_result = ref('')
const manualResultKey = ref('')
const manualResultText = computed(() =>
  manualResultKey.value
    ? i18n.global.t(manualResultKey.value)
    : resourceUpdateMessage(manual_result.value)
)
const manual_installing = ref(false)

async function refresh_resource_options() {
  try {
    await Promise.all([load_item(), load_shop(), load_operators()])
  } catch (error) {
    console.error('failed to refresh resource-backed options', error)
  }
}

onMounted(() => {
  loadResourceJob()
  if (props.skipInitialCheck) return
  // 当前版本常驻显示；开启「启动时检查更新」时才顺带拉远端最新版本。
  if (resource_update_enable.value) {
    loadResourceVersion()
  } else {
    loadResourceVersionLocal()
  }
})

async function show_manual_result(data) {
  manualResultKey.value =
    data && typeof data.message === 'string'
      ? ''
      : 'settings.resource.failedToApplyTheUpdatePackage'
  manual_result.value =
    data && typeof data.message === 'string'
      ? data.message
      : i18n.global.t('settings.resource.failedToApplyTheUpdatePackage')
  if (data?.ok && data.kind === 'resource') {
    await refresh_resource_options()
    if (resource_update_enable.value) {
      await loadResourceVersion(true)
    } else {
      await loadResourceVersionLocal()
    }
  }
}

function request_install() {
  if (!canInstall.value || manual_installing.value) return
  showResourceUpdateDialog(dialogs, resource_store, info.value)
}

async function install_resource() {
  if (await installResource()) {
    await refresh_resource_options()
  }
}

async function upload_manual_file(file, onProgress) {
  if (!file || manual_installing.value || installing.value) return false
  manual_installing.value = true
  manualResultKey.value = 'settings.resource.applyingUpdatePackage'
  manual_result.value = i18n.global.t('settings.resource.applyingUpdatePackage')
  try {
    const data = await postManualUpdate(axios, manual_url, file, onProgress)
    await show_manual_result(data)
    return data?.ok === true
  } catch (error) {
    await show_manual_result(error.response?.data)
    return false
  } finally {
    manual_installing.value = false
  }
}

async function request_manual_update({ file, onProgress, onFinish, onError }) {
  const ok = await upload_manual_file(file.file, onProgress)
  if (ok) {
    onFinish()
  } else {
    onError()
  }
}

function drop_manual_update(event) {
  // 直接读取标准 FileList，兼容未实现 webkitGetAsEntry 的浏览器与桌面 WebView。
  const file = getDroppedFile(event)
  if (file) {
    void upload_manual_file(file)
  }
}

function set_auto_check(checked) {
  resource_update_enable.value = checked
  if (!checked) {
    resource_update_auto_update.value = false
  }
}

function set_auto_update(checked) {
  resource_update_auto_update.value = checked
  if (checked) {
    resource_update_enable.value = true
  }
}
</script>

<template>
  <component
    :is="compact ? 'div' : NCard"
    :title="compact ? undefined : i18n.global.t('settings.resource.resourceUpdates')"
    class="update-card"
  >
    <UpdatePreview v-if="compact" v-bind="preview" />
    <div v-if="!compact" class="update-overview">
      <div class="update-installed">
        <span
          class="update-caption"
          :data-settings-label="i18n.global.t('settings.resource.currentVersion')"
          >{{ i18n.global.t('settings.resource.currentVersion') }}</span
        >
        <strong class="update-version">{{
          info.current_display || i18n.global.t('settings.resource.notInstalled')
        }}</strong>
        <span v-if="info.current_version" class="update-caption update-version-value">{{
          info.current_version
        }}</span>
      </div>
      <div class="update-actions">
        <n-button
          :loading="loading"
          :disabled="installing || manual_installing"
          @click="loadResourceVersion(true)"
          >{{ i18n.global.t('settings.resource.checkForUpdates') }}</n-button
        >
        <n-button
          v-if="info.update_available === true"
          type="primary"
          :loading="installing"
          :disabled="!canInstall || manual_installing"
          @click="request_install"
          >{{ i18n.global.t('settings.resource.downloadInstall') }}</n-button
        >
      </div>
    </div>
    <div
      v-if="!compact"
      class="update-status"
      role="status"
      :data-settings-label="i18n.global.t('settings.resource.latestVersion')"
    >
      <template v-if="loading">{{
        i18n.global.t('settings.resource.checkingTheLatestResourceVersion')
      }}</template>
      <template v-else-if="info.update_available != null">
        <n-tag v-if="info.update_available" size="small" :bordered="false" type="warning">{{
          i18n.global.t('settings.resource.updateAvailable')
        }}</n-tag>
        <n-tag v-else size="small" :bordered="false" type="success">{{
          i18n.global.t('settings.resource.upToDate')
        }}</n-tag>
        <span v-if="info.remote_display"
          >{{ i18n.global.t('settings.resource.latestVersion') }} {{ info.remote_display }}</span
        >
        <span v-if="info.remote_version" class="update-caption update-version-value">{{
          info.remote_version
        }}</span>
      </template>
      <span v-else class="update-caption">{{
        i18n.global.t('settings.resource.checkForUpdatesToFindTheLatest')
      }}</span>
    </div>
    <n-alert
      v-if="info.error"
      type="error"
      :title="i18n.global.t('settings.resource.resourceCheckIncomplete')"
      role="alert"
      >{{ info.error }}</n-alert
    >

    <div v-if="showProgress" class="update-progress" aria-live="polite">
      <n-progress
        type="line"
        :percentage="job.progress ?? 100"
        :show-indicator="job.progress != null"
        :processing="installing"
        :status="
          job.status === 'error' ? 'error' : job.status === 'success' ? 'success' : 'default'
        "
      />
      <p>{{ resourceUpdateMessage(job.message || install_message) }}</p>
      <p v-if="job.current" class="update-caption">
        {{ i18n.global.t('settings.resource.downloaded') }}
        {{ (job.current / 1048576).toFixed(1) }} MiB<span v-if="job.total">
          / {{ (job.total / 1048576).toFixed(1) }} MiB</span
        >
      </p>
      <p v-if="progress_error">{{ progress_error }}</p>
    </div>

    <n-form
      v-if="!compact"
      class="update-preferences"
      :show-feedback="false"
      label-placement="left"
    >
      <n-form-item>
        <template #label>
          <span class="settings-row-copy">
            <span>{{ i18n.global.t('settings.resource.automaticallyCheckForUpdates') }}</span>
            <span class="settings-row-description">{{
              i18n.global.t('settings.resource.checkForResourcePackagesWhenMowerOpens')
            }}</span>
          </span>
        </template>
        <n-switch
          :value="resource_update_enable"
          :aria-label="i18n.global.t('settings.resource.automaticallyCheckForUpdates')"
          @update:value="set_auto_check"
        />
      </n-form-item>
      <n-form-item>
        <template #label>
          <span class="settings-row-copy">
            <span>{{ i18n.global.t('settings.resource.automaticallyUpdate') }}</span>
            <span class="settings-row-description">{{
              i18n.global.t('settings.resource.installNewResourcePackagesAutomatically')
            }}</span>
          </span>
        </template>
        <n-switch
          :value="resource_update_auto_update"
          :aria-label="i18n.global.t('settings.resource.automaticallyUpdate')"
          @update:value="set_auto_update"
        />
      </n-form-item>
    </n-form>
    <p v-if="!compact" class="update-footnote">
      {{ i18n.global.t('settings.resource.preferAnOtaPatchAndFallBack') }}
    </p>
    <n-collapse v-if="!compact" class="update-details">
      <n-collapse-item
        :title="i18n.global.t('settings.resource.updateFromALocalResourcePackage')"
        name="manual"
        :data-settings-label="i18n.global.t('settings.resource.updateFromALocalResourcePackage')"
      >
        <div class="update-manual">
          <n-upload
            accept=".zip"
            :custom-request="request_manual_update"
            :disabled="manual_installing || installing"
            :show-file-list="false"
          >
            <n-upload-dragger @dragover.prevent @drop.capture.stop.prevent="drop_manual_update">
              <div>{{ i18n.global.t('settings.resource.clickOrDropAResourceUpdatePackage') }}</div>
              <p class="update-caption">
                {{ i18n.global.t('settings.resource.acceptsFullResourcePackagesAndOtaPatches') }}
              </p>
            </n-upload-dragger>
          </n-upload>
        </div>
      </n-collapse-item>
    </n-collapse>
    <p v-if="manual_result" class="update-result" role="status">{{ manualResultText }}</p>
  </component>
</template>
