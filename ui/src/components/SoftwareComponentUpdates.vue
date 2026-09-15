<script setup>
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
function confirm(action) {
  dialogs.warning({
    title: action === 'reset' ? '确认恢复内置版本？' : '确认更新兼容接口？',
    content: props.component.hint,
    positiveText: '确认',
    negativeText: '取消',
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
    <span>当前版本：{{ data?.installed?.version || '—' }}</span>
    <n-alert
      v-if="data?.latest?.available && data.latest.sha256 !== data.installed.sha256"
      type="info"
    >
      可更新至 {{ data.latest.version }}
    </n-alert>
    <span v-else-if="data?.latest?.version">{{
      data.latest.compatible === false ? '新接口需要更新 APK' : '兼容接口内容没有变化，无需更新'
    }}</span>
    <n-checkbox
      v-if="component.check"
      :checked="data?.auto_check ?? true"
      :disabled="busy || disabled || !data"
      @update:checked="(value) => run({ auto_check: value })"
    >
      自动检查兼容接口（服务运行时每 6 小时）
    </n-checkbox>
    <n-space>
      <n-button
        v-if="component.check"
        size="small"
        :disabled="busy || disabled"
        @click="run({ action: 'check' })"
        >检查接口更新</n-button
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
        >热更新接口</n-button
      >
      <n-button size="small" :disabled="busy || disabled" @click="confirm('reset')"
        >恢复内置版本</n-button
      >
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
