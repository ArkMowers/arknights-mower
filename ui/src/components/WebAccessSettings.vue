<script setup>
import { computed, ref, watch } from 'vue'
import { useConfigStore } from '@/stores/config'

const config = useConfigStore()
const port = ref(config.webview.port ?? 58000)
const token = ref(config.webview.token ?? '')
const saving = ref(false)
const error = ref('')
const saved = ref(false)
const dirty = computed(
  () =>
    port.value !== (config.webview.port ?? 58000) || token.value !== (config.webview.token ?? '')
)
const valid = computed(() => Number.isInteger(port.value) && port.value >= 0 && port.value <= 65535)

watch(
  () => [config.webview.port, config.webview.token],
  ([nextPort, nextToken], [previousPort, previousToken]) => {
    if (port.value === (previousPort ?? 58000)) port.value = nextPort ?? 58000
    if (token.value === (previousToken ?? '')) token.value = nextToken ?? ''
  }
)

async function save() {
  if (saving.value || !valid.value || !dirty.value) return
  saving.value = true
  error.value = ''
  saved.value = false
  try {
    await config.save_web_access({ port: port.value, token: token.value })
    saved.value = true
  } catch (err) {
    error.value = err.response?.data?.message || err.message || '保存失败，请重试'
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <n-card id="web-access-settings" title="访问端口与 Token">
    <n-space vertical :size="16">
      <n-text depth="3"
        >保存后，请彻底退出并重新启动 Mower。当前连接继续使用原端口和 Token。
      </n-text>
      <n-form label-placement="top" :show-feedback="false">
        <n-form-item label="端口">
          <n-input-number
            v-model:value="port"
            :min="0"
            :max="65535"
            :precision="0"
            :disabled="saving"
            :input-props="{ 'aria-label': '访问端口' }"
          />
        </n-form-item>
        <n-form-item label="Token" class="token-field">
          <n-input
            v-model:value="token"
            type="password"
            show-password-on="click"
            :disabled="saving"
            placeholder="留空时仅允许本机访问"
            :input-props="{ 'aria-label': '访问 Token', autocomplete: 'off' }"
          />
        </n-form-item>
      </n-form>
      <n-text depth="3">
        固定访问地址需要填写非空 Token 和 1–65535 的端口。设置 Token 后允许远程连接，访问时需提供此
        Token；留空时仅允许本机访问，每次启动自动分配端口和临时 Token。端口设为 0 时自动分配。
      </n-text>
      <n-alert v-if="error" type="error" :show-icon="false">{{ error }}</n-alert>
      <n-alert v-if="saved && !dirty" type="success" :show-icon="false">
        已保存，彻底退出并重新启动 Mower 后生效。
      </n-alert>
      <n-button type="primary" :loading="saving" :disabled="!dirty || !valid" @click="save">
        保存端口与 Token
      </n-button>
    </n-space>
  </n-card>
</template>

<style scoped>
.token-field {
  margin-top: 16px;
}
</style>
