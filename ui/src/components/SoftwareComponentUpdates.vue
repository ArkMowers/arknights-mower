<script setup>
import { i18n } from '@/i18n'
import { inject, onMounted, onUnmounted, ref } from 'vue'
import { useDialog, useMessage } from 'naive-ui'
const props = defineProps({ component: { type: Object, required: true }, disabled: Boolean })
const axios = inject('axios')
const dialogs = useDialog()
const messages = useMessage()
const data = ref(null)
const busy = ref(false)
const error = ref('')
const url = `${import.meta.env.VITE_HTTP_URL || ''}${props.component.endpoint}`
let timer
let disposed = false
async function load() {
  const response = await axios.get(url)
  if (!response.data.ok) throw new Error(response.data.message)
  if (!disposed) data.value = response.data
}
async function run(payload) {
  if (busy.value || props.disabled) return
  busy.value = true
  error.value = ''
  try {
    const response = await axios.post(url, payload, { headers: { 'X-Mower-Update': '1' } })
    if (!response.data.ok) throw new Error(response.data.message)
    await load()
    if (response.data.message) messages.success(response.data.message)
  } catch (err) {
    error.value = err.response?.data?.message || err.message
  } finally {
    busy.value = false
  }
}
function check() {
  if (props.component.check) return run({ action: 'check' })
}
defineExpose({ check })

function confirm(action) {
  dialogs.warning({
    title:
      action === 'reset'
        ? i18n.global.t('settings.components.restoreTheBundledVersion')
        : i18n.global.t('settings.components.updateTheCompatibilityApi'),
    content: props.component.hint,
    positiveText: i18n.global.t('settings.components.confirm'),
    negativeText: i18n.global.t('settings.components.cancel'),
    onPositiveClick: () => run({ action })
  })
}
async function poll() {
  try {
    if (!busy.value) await load()
  } catch (err) {
    error.value = err.message
  }
  if (!disposed) timer = setTimeout(poll, 60000)
}
onMounted(poll)
onUnmounted(() => {
  disposed = true
  clearTimeout(timer)
})
</script>

<template>
  <n-space vertical :size="12" class="component-update">
    <strong>{{ component.label }}</strong>
    <span
      >{{ i18n.global.t('settings.components.currentVersion')
      }}{{ data?.installed?.version || '—' }}</span
    >
    <n-alert
      v-if="data?.latest?.available && data.latest.sha256 !== data.installed.sha256"
      type="info"
    >
      {{ i18n.global.t('settings.components.updateAvailable') }} {{ data.latest.version }}
    </n-alert>
    <span v-else-if="data?.latest?.version">{{
      data.latest.compatible === false
        ? i18n.global.t('settings.components.theNewApiRequiresAnApkUpdate')
        : i18n.global.t('settings.components.theCompatibilityApiHasNotChangedNo')
    }}</span>
    <n-checkbox
      v-if="component.check"
      :checked="data?.auto_check ?? true"
      :disabled="busy || disabled || !data"
      @update:checked="(value) => run({ auto_check: value })"
    >
      {{ i18n.global.t('settings.components.automaticallyCheckTheCompatibilityApiEvery6') }}
    </n-checkbox>
    <n-space>
      <n-button
        v-if="component.check && !component.combined_check"
        size="small"
        :disabled="busy || disabled"
        @click="run({ action: 'check' })"
        >{{ i18n.global.t('settings.components.checkForApiUpdates') }}</n-button
      >
      <n-button
        v-if="component.check"
        size="small"
        type="primary"
        :disabled="
          busy ||
          disabled ||
          !data?.latest?.available ||
          data.latest.sha256 === data.installed.sha256
        "
        @click="confirm('install')"
        >{{ i18n.global.t('settings.components.hotUpdateApi') }}</n-button
      >
      <n-button size="small" :disabled="busy || disabled" @click="confirm('reset')">{{
        i18n.global.t('settings.components.restoreBundledVersion')
      }}</n-button>
    </n-space>
    <span class="hint">{{ component.hint }}</span>
    <n-alert v-if="error" type="error">{{ error }}</n-alert>
  </n-space>
</template>

<style scoped>
.component-update {
  margin: 16px 0;
}
.hint {
  color: var(--n-text-color-3);
  font-size: 12px;
}
</style>
