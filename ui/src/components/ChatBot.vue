<script setup>
import { ref, watch } from 'vue'
import { useConfigStore } from '@/stores/config'
import { storeToRefs } from 'pinia'

const store = useConfigStore()
const { ai_key, ai_type } = storeToRefs(store)
const show = ref(false)
const userInput = ref('')
const chatHistory = ref([])
const loading = ref(false)
let ws = null
let pendingMsg = null

function connectWS(callback) {
  if (ws) ws.close()
  let backend_url
  if (import.meta.env.DEV) {
    backend_url = import.meta.env.VITE_HTTP_URL
  } else {
    backend_url = location.origin
  }
  const ws_url = backend_url.replace(/^http/, 'ws') + '/ws/chat'
  ws = new WebSocket(ws_url)
  ws.onopen = () => {
    ws.send(JSON.stringify({ ai_type: ai_type.value, api_key: ai_key.value }))
    if (pendingMsg) {
      ws.send(JSON.stringify({ message: pendingMsg }))
      pendingMsg = null
    }
    if (callback) callback()
  }
  ws.onmessage = (event) => {
    const data = JSON.parse(event.data)
    if (data.reply) {
      // 如果上一条是 bot，拼接内容
      if (
        chatHistory.value.length > 0 &&
        chatHistory.value[chatHistory.value.length - 1].role == 'bot'
      ) {
        chatHistory.value[chatHistory.value.length - 1].content += data.reply
      } else {
        chatHistory.value.push({ role: 'bot', content: data.reply })
      }
    }
    if (data.error) {
      chatHistory.value.push({ role: 'bot', content: '错误: ' + data.error })
    }
    loading.value = false
  }
}

function sendMessage() {
  if (!userInput.value.trim()) return
  chatHistory.value.push({ role: 'user', content: userInput.value })
  loading.value = true
  if (!ws || ws.readyState === 3) {
    // ws未连接或已关闭，先连接再发
    pendingMsg = userInput.value
    connectWS()
  } else if (ws.readyState === 0) {
    // 正在连接，等 onopen 时自动发送
    pendingMsg = userInput.value
  } else if (ws.readyState === 1) {
    ws.send(JSON.stringify({ message: userInput.value }))
  }
  userInput.value = ''
}

watch(show, (val) => {
  if (
    val &&
    (chatHistory.value.length === 0 ||
      (chatHistory.value.length > 0 &&
        chatHistory.value[chatHistory.value.length - 1].content ===
          '未检测到 API Key，请先在设置中配置你的 AI Key。'))
  ) {
    loading.value = true
    const intro = '请用简洁的语言介绍一下你能为用户做什么。'
    if (!ws || ws.readyState === 3) {
      pendingMsg = intro
      connectWS()
    } else if (ws.readyState === 0) {
      pendingMsg = intro
    } else if (ws.readyState === 1) {
      ws.send(JSON.stringify({ message: intro }))
    }
  }
})
</script>
<template>
  <div style="position: fixed; left: 32px; bottom: 16px; z-index: 9999">
    <n-button v-if="!show" type="primary" @click="show = !show">Mower 助手</n-button>
    <n-card v-if="show" style="width: 600px; margin-top: 8px">
      <div style="height: 600px; overflow-y: auto; margin-bottom: 12px">
        <div
          v-for="(msg, idx) in chatHistory"
          :key="idx"
          :style="{ textAlign: msg.role === 'user' ? 'right' : 'left' }"
        >
          <b>{{ msg.role === 'user' ? '你' : 'Mower AI 助手' }}：</b>
          <span v-html="msg.content"></span>
        </div>
      </div>
      <n-input
        v-model:value="userInput"
        placeholder="输入你的问题..."
        @keyup.enter="sendMessage"
        :disabled="loading"
      />
      <n-button type="primary" @click="sendMessage" :loading="loading" style="margin-top: 8px"
        >发送</n-button
      >
      <n-button type="error" @click="show = !show" :loading="loading" style="margin-top: 8px"
        >关闭</n-button
      >
    </n-card>
  </div>
</template>
