<script setup>
import { computed, inject, onMounted, onUnmounted, ref } from 'vue'

const axios = inject('axios')
const base = `${import.meta.env.VITE_HTTP_URL || ''}/relay/settings`
const enabled = ref(false)
const subdomain = ref('')
const username = ref('')
const credential = ref('')
const password = ref('')
const credentialSaved = ref(false)
const passwordSaved = ref(false)
const status = ref('尚未连接')
const busy = ref(false)
const ready = ref(false)
const error = ref('')
const url = computed(() =>
  /^[a-z0-9](?:[a-z0-9-]{0,30}[a-z0-9])?$/.test(subdomain.value)
    ? `https://${subdomain.value}.free.mower.work:58000`
    : ''
)
let timer
let active = false
let disposed = false

function apply(data) {
  active = data.enabled
  enabled.value = data.enabled
  subdomain.value = data.subdomain
  username.value = data.username
  credentialSaved.value = data.credential_saved
  passwordSaved.value = data.password_saved
  status.value = data.message
}

async function load() {
  try {
    const { data } = await axios.get(base)
    if (!disposed) {
      apply(data)
      ready.value = true
    }
  } catch (err) {
    if (!disposed) error.value = err.response?.data?.message || '请在本机 Mower 中配置免费中转'
  }
}

async function refreshStatus() {
  try {
    const { data } = await axios.get(base)
    if (!disposed && !busy.value) status.value = data.message
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
            subdomain: subdomain.value,
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
      <n-switch :value="enabled" :disabled="!ready || busy" @update:value="toggle" />
    </n-form-item>
    <n-alert v-if="error" type="error">{{ error }}</n-alert>
    <template v-if="enabled">
      <n-text depth="3">
        向管理员领取子域名和中转凭据，在此设置自己的登录用户名和密码。远程访问时，先在浏览器认证弹窗登录，再填写实例
        Token。
      </n-text>
      <n-form :disabled="!ready || busy" label-width="120" label-placement="left">
        <n-form-item label="子域名">
          <n-input v-model:value="subdomain" placeholder="管理员批准的名称" :maxlength="32">
            <template #suffix>.free.mower.work</template>
          </n-input>
        </n-form-item>
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
          :disabled="!ready || (!credentialSaved && !credential)"
          @click="save"
          >保存并应用</n-button
        >
        <n-text>{{ status }}</n-text>
      </n-space>
      <n-a v-if="url" :href="url" target="_blank" rel="noopener noreferrer">{{ url }}</n-a>
      <n-text depth="3"
        >中转连接随 Mower 启动，退出 Mower 后关闭。请在本机导入大文件、安装更新或管理进程。</n-text
      >
    </template>
  </n-space>
</template>
