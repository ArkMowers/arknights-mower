<script setup>
import { inject, ref, watch } from 'vue'
import { useConfigStore } from '@/stores/config'
import { storeToRefs } from 'pinia'
import markdownit from 'markdown-it'

const store = useConfigStore()
const md = markdownit({ html: true, breaks: true })
const { ai_key, ai_type } = storeToRefs(store)
const showFeedback = inject('show_feedback', null)
const WELCOME_MESSAGE =
  '我是 Mower AI 助手，可以帮你查日志、分析漏单、定位报错、查询数据库记录，或协助整理问题描述。'
const userInput = ref('')
const chatHistory = ref([])
const loading = ref(false)
let ws = null
let pendingMsg = null

const props = defineProps({
  show: Boolean
})
const emit = defineEmits(['update:show'])

const show = ref(props.show)
watch(
  () => props.show,
  (val) => (show.value = val)
)
watch(show, (val) => emit('update:show', val))
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
        chatHistory.value.push({ role: 'bot', content: data.reply, followUpState: null })
      }
    }
    if (data.error) {
      chatHistory.value.push({
        role: 'bot',
        content: '错误: ' + data.error,
        followUpState: null
      })
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

function markResolved(msg) {
  msg.followUpState = 'resolved'
}

function openFeedbackFlow(msg) {
  msg.followUpState = 'feedback'
  if (showFeedback) {
    showFeedback.value = true
  }
}

function appendWelcomeMessage() {
  chatHistory.value.push({
    role: 'bot',
    content: WELCOME_MESSAGE,
    followUpState: null,
    showFollowUp: false
  })
}

watch(show, (val) => {
  if (val && chatHistory.value.length === 0) {
    appendWelcomeMessage()
  }
})
const isMobile = ref(window.innerWidth < 800)
window.addEventListener('resize', () => {
  isMobile.value = window.innerWidth < 800
})
</script>
<template>
  <div v-if="show" class="chatbot-container" :class="{ mobile: isMobile }">
    <n-card class="chatbot-card">
      <div class="chatbot-flexbox">
        <div class="chatbot-history" ref="historyRef">
          <div
            v-for="(msg, idx) in chatHistory"
            :key="idx"
            :style="{ textAlign: msg.role === 'user' ? 'right' : 'left' }"
            class="chat-row"
          >
            <b>{{ msg.role === 'user' ? '你' : 'Mower AI 助手' }}：</b>
            <span v-html="md.render(msg.content)"></span>
            <div v-if="msg.role === 'bot' && msg.showFollowUp !== false" class="follow-up-block">
              <div class="follow-up-title">是否解决了你的问题？</div>
              <div v-if="msg.followUpState === null" class="follow-up-actions">
                <n-button size="small" tertiary type="primary" @click="markResolved(msg)">
                  已解决
                </n-button>
                <n-button size="small" tertiary type="warning" @click="openFeedbackFlow(msg)">
                  反馈问题
                </n-button>
              </div>
              <div v-else-if="msg.followUpState === 'resolved'" class="follow-up-result">
                已标记为已解决。
              </div>
              <div v-else class="follow-up-result">已打开反馈窗口。</div>
            </div>
          </div>
        </div>
        <div class="chatbot-input-area">
          <n-input
            v-model:value="userInput"
            placeholder="输入你的问题..."
            @keyup.enter="sendMessage"
            :disabled="loading"
          />
          <div style="display: flex; gap: 8px; margin-top: 8px">
            <n-button type="primary" @click="sendMessage" :loading="loading">发送</n-button>
            <n-button type="error" @click="show = false" :loading="loading">关闭</n-button>
          </div>
        </div>
      </div>
    </n-card>
  </div>
</template>
<style scoped>
.chatbot-container {
  position: fixed;
  left: 32px;
  bottom: 16px;
  z-index: 9999;
  user-select: text;
  -webkit-user-select: text;
}
.chatbot-container.mobile {
  left: 0;
  bottom: 0;
  width: 100vw;
  height: 100vh;
  z-index: 9999;
  display: flex;
  justify-content: center;
  align-items: flex-end;
}
.chatbot-card {
  width: 600px;
  margin-top: 8px;
  display: flex;
  flex-direction: column;
  max-height: 80vh;
  height: auto;
  min-height: 320px;
}

.chatbot-container.mobile .chatbot-card {
  width: 100vw !important;
  height: 100vh !important;
  border-radius: 0 !important;
  margin: 0 !important;
  max-width: 100vw;
  max-height: 100vh;
  display: flex;
  flex-direction: column;
}
.chatbot-flexbox {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}
.chatbot-history {
  flex: 1 1 0%;
  min-height: 50vh;
  overflow-y: auto;
  margin-bottom: 12px;
  padding-right: 4px;
  max-height: calc(75vh - 135px);
  user-select: text;
  -webkit-user-select: text;
}

@media (max-width: 800px) {
  .chatbot-history {
    min-height: none;
    max-height: calc(100vh - 135px);
    height: 100%;
  }
}
.chatbot-input-area {
  flex-shrink: 0;
  padding-bottom: 8px;
  background: transparent;
}

.chatbot-history :deep(*) {
  user-select: text;
  -webkit-user-select: text;
}

.chat-row {
  margin-bottom: 12px;
}

.follow-up-block {
  margin-top: 8px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.follow-up-title {
  font-size: 12px;
  opacity: 0.8;
}

.follow-up-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.follow-up-result {
  font-size: 12px;
  opacity: 0.75;
}
</style>
