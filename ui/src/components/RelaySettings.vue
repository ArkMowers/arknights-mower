<script setup>
import { computed, inject, onMounted, onUnmounted, ref } from 'vue'

import { useConfigStore } from '@/stores/config'
import { instanceToken } from '@/utils/instanceToken'

const config = useConfigStore()
const axios = inject('axios')
const base = `${import.meta.env.VITE_HTTP_URL || ''}/relay/settings`
const enabled = ref(false)
const origin = ref('')
const tokenReady = ref(false)
const username = ref('')
const credential = ref('')
const password = ref('')
const credentialSaved = ref(false)
const passwordSaved = ref(false)
const status = ref('尚未连接')
const busy = ref(false)
const ready = ref(false)
const error = ref('')
const canEnable = computed(
  () => tokenReady.value && !!config.webview.token && config.webview.token === instanceToken()
)
const url = computed(() => {
  if (!origin.value || !canEnable.value) return ''
  const link = new URL(origin.value)
  link.hash = new URLSearchParams({ token: config.webview.token }).toString()
  return link.href
})
let timer
let active = false
let disposed = false

function updateStatus(data) {
  status.value = data.message
  origin.value = data.url
  tokenReady.value = data.token_ready
}

function apply(data) {
  active = data.enabled
  enabled.value = data.enabled
  username.value = data.username
  credentialSaved.value = data.credential_saved
  passwordSaved.value = data.password_saved
  updateStatus(data)
}

async function load() {
  try {
    const { data } = await axios.get(base)
    if (!disposed) {
      apply(data)
      ready.value = true
    }
  } catch (err) {
    if (!disposed) error.value = err.response?.data?.message || '请在本机 Mower 中配置远程访问'
  }
}

async function refreshStatus() {
  try {
    const { data } = await axios.get(base)
    if (!disposed && !busy.value) updateStatus(data)
  } catch {
    // Configuration errors stay visible until the next explicit save.
  } finally {
    if (!disposed && active) timer = setTimeout(refreshStatus, 10000)
  }
}

async function toggle(value) {
  enabled.value = value
  if (!value) {
    credential.value = ''
    password.value = ''
    error.value = ''
    if (active) await save()
  }
}

async function save() {
  busy.value = true
  error.value = ''
  try {
    const { data } = await axios.post(
      base,
      enabled.value
        ? {
            enabled: true,
            username: username.value,
            credential: credential.value,
            password: password.value
          }
        : { enabled: false },
      { headers: { 'X-Mower-Settings': '1' } }
    )
    if (!disposed) {
      apply(data)
      credential.value = ''
      password.value = ''
      clearTimeout(timer)
      if (active) timer = setTimeout(refreshStatus, 1000)
    }
  } catch (err) {
    if (!disposed) {
      if (!enabled.value) enabled.value = active
      error.value = err.response?.data?.message || '中转设置保存失败'
    }
  } finally {
    busy.value = false
  }
}

onMounted(async () => {
  await load()
  if (!disposed && ready.value && active) timer = setTimeout(refreshStatus, 10000)
})
onUnmounted(() => {
  disposed = true
  clearTimeout(timer)
})
</script>

<template>
  <n-space id="mower-relay-settings" vertical :size="16">
    <n-form-item label="启用中转" label-placement="left" label-width="120" :show-feedback="false">
      <n-switch
        :value="enabled"
        :disabled="!ready || busy || (!enabled && !canEnable)"
        @update:value="toggle"
      />
    </n-form-item>
    <n-text v-if="ready && !canEnable" depth="3"
      >请先设置访问 Token，保存并重启实例后即可启用中转。</n-text
    >
    <n-alert v-if="error" type="error">{{ error }}</n-alert>
    <template v-if="enabled">
      <n-text depth="3">
        填写管理员发放的中转凭据，并设置登录用户名和密码。连接成功后，打开远程访问链接即可登录。
      </n-text>
      <n-form :disabled="!ready || busy" label-width="120" label-placement="left">
        <n-form-item label="中转凭据">
          <n-input
            v-model:value="credential"
            type="password"
            show-password-on="click"
            :placeholder="credentialSaved ? '留空继续使用已保存凭据' : '管理员发放的独立凭据'"
            :maxlength="256"
            :input-props="{ autocomplete: 'off' }"
          />
        </n-form-item>
        <n-form-item label="登录用户名">
          <n-input v-model:value="username" :maxlength="64" />
        </n-form-item>
        <n-form-item label="登录密码">
          <n-input
            v-model:value="password"
            type="password"
            show-password-on="click"
            :placeholder="passwordSaved ? '留空继续使用已保存密码' : '设置登录密码'"
            :input-props="{ autocomplete: 'new-password' }"
          />
        </n-form-item>
      </n-form>
      <n-space align="center">
        <n-button
          type="primary"
          :loading="busy"
          :disabled="!ready || !canEnable || (!credentialSaved && !credential)"
          @click="save"
          >保存并应用</n-button
        >
        <n-text>{{ status }}</n-text>
      </n-space>
      <n-a v-if="url" :href="url" target="_blank" rel="noopener noreferrer"
        >打开远程访问（含实例 Token）</n-a
      >
      <n-text depth="3"
        >中转连接随 Mower 启动，退出 Mower 后关闭。请在本机导入大文件、安装更新或管理进程。</n-text
      >
    </template>
  </n-space>
</template>
