<script setup>
import { onMounted, ref } from 'vue'
import axios from 'axios'
import { instanceToken, rememberRelayToken } from '@/utils/instanceToken'

const emit = defineEmits(['ready'])
const value = ref(instanceToken() || '')
const error = ref('')
const busy = ref(false)
async function verify() {
  if (busy.value || !value.value) return
  busy.value = true
  error.value = ''
  try {
    await axios.get('/getwatermark', { headers: { token: value.value }, timeout: 10000 })
    rememberRelayToken(value.value)
    emit('ready')
  } catch (failure) {
    error.value = failure.response?.status === 403 ? '实例 Token 不正确' : '无法连接实例，请重试'
  } finally {
    busy.value = false
  }
}
onMounted(() => {
  if (value.value) void verify()
})
</script>
<template>
  <main class="relay-token">
    <form @submit.prevent="verify">
      <h1>连接 Mower 实例</h1>
      <label for="instance-token">实例 Token</label>
      <input id="instance-token" v-model="value" type="password" autocomplete="off" required />
      <p v-if="error" role="alert">{{ error }}</p>
      <button :disabled="busy || !value">{{ busy ? '正在连接…' : '连接实例' }}</button>
    </form>
  </main>
</template>
<style scoped>
.relay-token {
  min-height: 90vh;
  display: grid;
  place-items: center;
  font:
    1rem system-ui,
    sans-serif;
}
form {
  display: grid;
  gap: 0.8rem;
  width: min(24rem, 85vw);
}
h1 {
  font-size: 1.5rem;
}
input,
button {
  font: inherit;
  padding: 0.6rem;
}
p {
  color: #a22;
}
</style>
