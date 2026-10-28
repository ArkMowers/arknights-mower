<script setup>
import { i18n } from '@/i18n'
const { t } = i18n.global

import { computed, inject, onMounted, onUnmounted, ref, watch } from 'vue'
const axios = inject('axios')

defineProps({
  showTitle: { type: Boolean, default: true }
})

import { useConfigStore } from '@/stores/config'
const store = useConfigStore()

import { storeToRefs } from 'pinia'
const managerOwned = computed(() => manager_owned_device.value === true)
const {
  manager_owned_device,
  runtime_platform,
  maa_path,
  maa_restore_theme_enable,
  maa_restore_theme,
  maa_conn_preset,
  maa_touch_option
} = storeToRefs(store)

import { folder_dialog } from '@/utils/dialog'
import { getMaaThemeOptions } from '@/utils/maa_theme_options'

const maa_theme_options = computed(() => getMaaThemeOptions(maa_restore_theme.value))

async function select_maa_dir() {
  if (managerOwned.value) return
  const folder_path = await folder_dialog()
  if (folder_path && !managerOwned.value) {
    maa_path.value = folder_path
  }
}

const maa_msg = ref('')
const maa_testing = ref(false)

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

async function test_maa() {
  if (managerOwned.value || maa_testing.value) return
  maa_testing.value = true
  maa_msg.value = t('tasks.testing')
  try {
    let response = await axios.get(`${import.meta.env.VITE_HTTP_URL}/check-maa`)
    let data = response.data
    if (typeof data === 'string') {
      maa_msg.value = data
      return
    }
    while (!managerOwned.value && data.status === 'running') {
      maa_msg.value = data.message || t('tasks.testing')
      await sleep(1000)
      if (managerOwned.value) return
      response = await axios.get(`${import.meta.env.VITE_HTTP_URL}/check-maa/status`)
      data = response.data
      if (typeof data === 'string') {
        maa_msg.value = data
        return
      }
    }
    maa_msg.value = data.message || t('tasks.maaTestFailed')
  } catch (error) {
    maa_msg.value = t('tasks.testFailedMessage', { message: error.message })
  } finally {
    maa_testing.value = false
  }
}

const maa_conn_presets = ref([])

async function get_maa_conn_presets() {
  if (managerOwned.value || disposed) return
  try {
    const response = await axios.get(`${import.meta.env.VITE_HTTP_URL}/maa-conn-preset`)
    if (managerOwned.value || disposed) return
    if (Array.isArray(response.data)) {
      maa_conn_presets.value = response.data.map((x) => ({ label: x, value: x }))
    } else {
      maa_conn_presets.value = []
      maa_msg.value = response.data.message || t('tasks.maaConnectionConfigFailed')
    }
  } catch (error) {
    maa_msg.value = t('tasks.connectionConfigReadFailed', { message: error.message })
  }
}

const maa_touch_options = ['maatouch', 'minitouch', 'adb'].map((x) => {
  return { label: x, value: x }
})

let disposed = false
let maa_path_refresh_timer = null

watch(maa_path, (value, previous_value) => {
  if (managerOwned.value || value === previous_value) return
  if (maa_path_refresh_timer) window.clearTimeout(maa_path_refresh_timer)
  maa_path_refresh_timer = window.setTimeout(get_maa_conn_presets, 400)
})

onMounted(get_maa_conn_presets)

onUnmounted(() => {
  disposed = true
  if (maa_path_refresh_timer) window.clearTimeout(maa_path_refresh_timer)
})
</script>

<template>
  <n-card class="maa-basic" content-class="maa-basic-content">
    <template v-if="showTitle" #header
      >{{ t('tasks.maaCore')
      }}<help-text>{{
        managerOwned ? t('tasks.gameThemeRestoration') : t('tasks.connectionTouchTheme')
      }}</help-text></template
    >
    <n-form
      class="maa-basic-form"
      label-placement="left"
      :show-feedback="false"
      label-width="128"
      label-align="left"
    >
      <n-alert v-if="!managerOwned && runtime_platform === 'android'" :show-icon="false">{{
        t('tasks.androidMaaManaged')
      }}</n-alert>
      <div v-if="!managerOwned && runtime_platform === 'android'" style="margin-bottom: 16px">
        <SessionLink to="/mowersettings#software-update">{{
          t('tasks.importAndroidMaa')
        }}</SessionLink>
      </div>
      <template v-else-if="!managerOwned">
        <n-form-item :label="t('tasks.maaDirectory')">
          <template #label
            >{{ t('tasks.maaDirectory') }}<help-text>{{ t('tasks.maaDirectoryHelp') }}</help-text>
          </template>
          <div class="maa-field-with-action">
            <n-input
              v-model:value="maa_path"
              :input-props="{ 'aria-label': t('tasks.maaDirectory') }"
            />
            <n-button @click="select_maa_dir">{{ t('tasks.browse') }}</n-button>
          </div>
        </n-form-item>
        <n-form-item :label="t('tasks.connectionConfig')">
          <div class="maa-field-with-action">
            <n-select :options="maa_conn_presets" v-model:value="maa_conn_preset" />
            <n-button @click="get_maa_conn_presets">{{ t('tasks.refresh') }}</n-button>
          </div>
        </n-form-item>
        <n-form-item :label="t('tasks.touchMode')">
          <n-select v-model:value="maa_touch_option" :options="maa_touch_options" />
        </n-form-item>
      </template>
      <n-form-item :label="t('tasks.restoreTheme')">
        <template #label
          >{{ t('tasks.restoreTheme')
          }}<help-text :label="t('tasks.restoreThemeHelpTitle')" :max-width="480">{{
            t('tasks.restoreThemeHelp')
          }}</help-text>
        </template>
        <n-checkbox v-model:checked="maa_restore_theme_enable">{{
          t('tasks.restoreThemeAfterTasks')
        }}</n-checkbox>
      </n-form-item>
      <n-form-item v-if="maa_restore_theme_enable" :label="t('tasks.targetTheme')">
        <n-select
          :value="maa_restore_theme || null"
          :options="maa_theme_options"
          filterable
          clearable
          :placeholder="t('tasks.selectTargetTheme')"
          @update:value="maa_restore_theme = $event ?? ''"
        />
      </n-form-item>
    </n-form>
    <n-divider v-if="!managerOwned" />
    <div v-if="!managerOwned" class="maa-connection-test">
      <n-button :loading="maa_testing" :disabled="maa_testing" @click="test_maa">{{
        t('tasks.testConnection')
      }}</n-button>
      <p v-if="maa_msg" class="maa-connection-result" role="status">{{ maa_msg }}</p>
    </div>
  </n-card>
</template>

<style scoped>
.maa-basic {
  min-width: 0;
  container: maa-basic / inline-size;
}

.maa-basic :deep(> .maa-basic-content) {
  min-width: 0;
  max-width: 760px;
}

.maa-basic .maa-basic-form :deep(> .n-form-item) {
  margin: 0;
  padding: 12px 0;
  grid-template-columns: 128px minmax(0, 480px);
  grid-template-areas: 'label blank' 'label feedback';
  grid-template-rows: auto auto;
  gap: 0 16px;
  align-items: center;
}

.maa-basic .maa-basic-form :deep(> .n-form-item:first-child) {
  padding-top: 0;
}

.maa-basic .maa-basic-form :deep(> .n-form-item:last-child) {
  padding-bottom: 0;
}

.maa-basic .maa-basic-form :deep(> .n-form-item > .n-form-item-label) {
  min-width: 0;
  min-height: 0;
  width: auto;
  padding: 0;
  justify-content: flex-start;
}

.maa-basic .maa-basic-form :deep(> .n-form-item > .n-form-item-blank) {
  width: 100%;
  max-width: none;
  min-width: 0;
  justify-content: flex-start;
}

.maa-basic .maa-basic-form :deep(.n-form-item-blank > .n-select) {
  max-width: none;
}

.maa-field-with-action {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  min-width: 0;
}

.maa-field-with-action :deep(> .n-input),
.maa-field-with-action :deep(> .n-select) {
  flex: 1;
  min-width: 0;
}

.maa-field-with-action :deep(> .n-button) {
  flex: none;
}

.maa-connection-test {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
}

.maa-connection-result {
  flex-basis: 100%;
  margin: 0;
  line-height: 1.6;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

@container maa-basic (max-width: 480px) {
  .maa-basic .maa-basic-form :deep(> .n-form-item) {
    grid-template-columns: minmax(0, 1fr);
    grid-template-areas: 'label' 'blank' 'feedback';
    gap: 8px 0;
  }
}
</style>
