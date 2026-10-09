<script setup>
import { computed, inject, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useMessage } from 'naive-ui'
import {
  AddOutline,
  ArrowDownOutline,
  ArrowUpOutline,
  CheckmarkOutline,
  CloseOutline,
  CopyOutline,
  DocumentTextOutline,
  GridOutline,
  MailOutline,
  SchoolOutline,
  SettingsOutline,
  SparklesOutline
} from '@vicons/ionicons5'
import markdownit from 'markdown-it'

const props = defineProps({ show: Boolean })
const emit = defineEmits(['update:show'])
const show = computed({ get: () => props.show, set: (value) => emit('update:show', value) })
const router = useRouter()
const notice = useMessage()
const showFeedback = inject('show_feedback', null)
const feedbackAvailable = showFeedback !== null
const md = markdownit({ html: false, breaks: true })
const visibleContent = (content) => content.replace(/<!--MOWER_MISS_STATE:[\s\S]*?-->/g, '')
const renderMessage = (content) => md.render(visibleContent(content))
const userInput = ref('')
const chatHistory = ref([])
const loading = ref(false)
const connecting = ref(false)
const historyRef = ref(null)
const inputRef = ref(null)
const atBottom = ref(true)
const canSend = computed(() => Boolean(userInput.value.trim()) && !loading.value)
const statusLabel = computed(() =>
  connecting.value ? '正在连接' : loading.value ? '正在回复' : '日志排查与使用建议'
)
const suggestions = [
  { title: '排查连接', description: '设备连接失败，应该先检查什么？', icon: DocumentTextOutline },
  { title: '理解排班', description: '干员到心情阈值还不下班，怎么排查？', icon: GridOutline },
  { title: '查看专精', description: '帮我查看当前专精计划的状态。', icon: SchoolOutline },
  { title: '整理反馈', description: '帮我整理一份问题反馈，先不要发送。', icon: MailOutline }
]
let ws = null
let activeReply = null
let connectTimer = null

function scrollToLatest() {
  atBottom.value = true
  if (historyRef.value) historyRef.value.scrollTop = historyRef.value.scrollHeight
}
function trackScroll() {
  const el = historyRef.value
  if (el) atBottom.value = el.scrollHeight - el.scrollTop - el.clientHeight < 80
}
function closeConnection() {
  clearTimeout(connectTimer)
  if (ws) {
    ws.onopen = ws.onmessage = ws.onerror = ws.onclose = null
    ws.close()
    ws = null
  }
  connecting.value = false
}
function failReply(text) {
  if (activeReply) {
    activeReply.content += `${activeReply.content ? '\n\n' : ''}${text}`
    activeReply.error = true
  }
  activeReply = null
  loading.value = false
  closeConnection()
}
function connectWS(text) {
  const token = new URLSearchParams(window.location.search).get('token')
  if (!token) {
    failReply('AI 助手需要 Web UI 访问密钥，请从 Mower 窗口或其浏览器入口打开。')
    return
  }
  closeConnection()
  connecting.value = true
  const backend = import.meta.env.DEV ? import.meta.env.VITE_HTTP_URL : location.origin
  try {
    ws = new WebSocket(backend.replace(/^http/, 'ws') + '/ws/chat')
  } catch {
    failReply('无法建立 AI 连接，请检查服务地址后重试。')
    return
  }
  connectTimer = setTimeout(() => {
    failReply('AI 连接超时，请检查服务是否运行后重试。')
  }, 20000)
  ws.onopen = () => {
    clearTimeout(connectTimer)
    connecting.value = false
    ws.send(JSON.stringify({ token }))
    ws.send(JSON.stringify({ message: text }))
  }
  ws.onmessage = (event) => {
    let data
    try {
      data = JSON.parse(event.data)
    } catch {
      failReply('无法读取 AI 回复，请重试。')
      return
    }
    if (!data || typeof data !== 'object' || Array.isArray(data)) {
      failReply('无法读取 AI 回复，请重试。')
      return
    }
    if (!activeReply) return
    if (typeof data.reply === 'string') activeReply.content += data.reply
    if (data.error) {
      failReply(`回复失败：${data.error}`)
      return
    }
    if (data.done === true) {
      if (!activeReply.content.trim()) {
        activeReply.content = '没有收到回复，请检查模型配置后重试。'
        activeReply.error = true
      }
      activeReply = null
      loading.value = false
    }
  }
  ws.onerror = () => failReply('AI 连接失败，请检查服务与访问密钥后重试。')
  ws.onclose = () => {
    clearTimeout(connectTimer)
    connecting.value = false
    ws = null
    if (loading.value) failReply('连接已中断。再次发送将建立新会话，请补充必要的问题背景。')
  }
}
function sendMessage() {
  if (!canSend.value) return
  const text = userInput.value.trim()
  if (text.length > 4000) return
  chatHistory.value.push({ role: 'user', content: text })
  chatHistory.value.push({ role: 'bot', content: '', followUpState: null, error: false })
  activeReply = chatHistory.value.at(-1)
  loading.value = true
  atBottom.value = true
  userInput.value = ''
  if (!ws || ws.readyState !== WebSocket.OPEN) connectWS(text)
  else ws.send(JSON.stringify({ message: text }))
  nextTick(scrollToLatest)
}
function onInputKeydown(event) {
  if (event.key !== 'Enter' || event.shiftKey || event.isComposing || event.keyCode === 229) return
  event.preventDefault()
  sendMessage()
}
function useSuggestion(suggestion) {
  userInput.value = suggestion.description
  inputRef.value?.focus()
}
function newConversation() {
  if (loading.value) return
  closeConnection()
  chatHistory.value = []
  userInput.value = ''
  activeReply = null
  atBottom.value = true
  inputRef.value?.focus()
}
async function copyMessage(msg) {
  try {
    await navigator.clipboard.writeText(visibleContent(msg.content))
    notice.success('已复制回复')
  } catch {
    notice.error('复制失败，请选中文字手动复制')
  }
}
function openFeedbackFlow(msg) {
  if (!showFeedback) return
  msg.followUpState = 'feedback'
  showFeedback.value = true
  show.value = false
}
function openSettings() {
  show.value = false
  router.push('/mowersettings')
}
watch(
  [chatHistory, loading],
  async () => {
    await nextTick()
    if (show.value && atBottom.value) scrollToLatest()
  },
  { deep: true }
)
watch(
  () => props.show,
  async (value) => {
    if (!value) return
    await nextTick()
    inputRef.value?.focus()
    if (atBottom.value) scrollToLatest()
  },
  { immediate: true }
)
onBeforeUnmount(closeConnection)
</script>

<template>
  <section v-show="show" class="chatbot-container" role="dialog" aria-label="Mower AI 助手">
    <header class="chatbot-header">
      <div class="assistant-mark" aria-hidden="true"><n-icon :component="SparklesOutline" /></div>
      <div class="assistant-heading">
        <h2>Mower AI <span>助手</span></h2>
        <div class="assistant-status" role="status">
          <span v-if="loading" class="status-dot" aria-hidden="true"></span>{{ statusLabel }}
        </div>
      </div>
      <div class="header-actions">
        <n-popconfirm :disabled="loading || !chatHistory.length" @positive-click="newConversation">
          <template #trigger>
            <n-button
              quaternary
              circle
              class="icon-button"
              :disabled="loading || !chatHistory.length"
              aria-label="新对话"
              title="新对话"
              ><template #icon><n-icon :component="AddOutline" /></template
            ></n-button>
          </template>
          清空当前对话，开始新的会话？
        </n-popconfirm>
        <n-button
          quaternary
          circle
          class="icon-button"
          aria-label="模型设置"
          title="模型设置"
          @click="openSettings"
        >
          <template #icon><n-icon :component="SettingsOutline" /></template>
        </n-button>
        <n-button
          quaternary
          circle
          class="icon-button"
          aria-label="收起助手"
          title="收起助手，保留当前对话"
          @click="show = false"
        >
          <template #icon><n-icon :component="CloseOutline" /></template>
        </n-button>
      </div>
    </header>

    <div class="history-container">
      <div ref="historyRef" class="chatbot-history" @scroll="trackScroll" :aria-busy="loading">
        <div v-if="!chatHistory.length" class="chatbot-welcome">
          <div class="welcome-mark" aria-hidden="true"><n-icon :component="SparklesOutline" /></div>
          <h3>从一个问题开始</h3>
          <p>查日志、理解排班、跟进专精，<br />也可以一起整理遇到的问题。</p>
          <div class="suggestion-grid">
            <button
              v-for="suggestion in suggestions"
              :key="suggestion.title"
              type="button"
              class="suggestion"
              @click="useSuggestion(suggestion)"
            >
              <n-icon :component="suggestion.icon" aria-hidden="true" />
              <strong>{{ suggestion.title }}</strong>
              <span>{{ suggestion.description }}</span>
            </button>
          </div>
          <span class="welcome-hint">选择一个话题，补充细节后发送</span>
        </div>
        <div v-else class="message-list">
          <article
            v-for="(msg, idx) in chatHistory"
            :key="idx"
            class="chat-row"
            :class="[msg.role, { 'message-error': msg.error }]"
          >
            <div class="message-meta">
              <span>{{ msg.role === 'user' ? '你' : 'Mower AI' }}</span>
              <span
                v-if="msg.role === 'bot' && loading && idx === chatHistory.length - 1"
                class="message-state"
                >正在回复</span
              >
            </div>
            <div v-if="msg.role === 'user'" class="message-content user-content">
              {{ msg.content }}
            </div>
            <div v-else class="message-content assistant-content">
              <div
                v-if="msg.content"
                class="message-markdown"
                v-html="renderMessage(msg.content)"
              ></div>
              <div v-else class="thinking-indicator" role="status">
                <span aria-hidden="true">···</span
                >{{ connecting ? '正在建立连接' : '正在思考你的问题' }}
              </div>
            </div>
            <div
              v-if="
                msg.role === 'bot' && msg.content && !(loading && idx === chatHistory.length - 1)
              "
              class="message-actions"
            >
              <n-button quaternary class="reply-action" @click="copyMessage(msg)"
                ><template #icon><n-icon :component="CopyOutline" /></template>复制</n-button
              >
              <template v-if="!msg.error">
                <n-button
                  v-if="!msg.followUpState"
                  quaternary
                  class="reply-action"
                  @click="msg.followUpState = 'resolved'"
                  ><template #icon><n-icon :component="CheckmarkOutline" /></template
                  >已解决</n-button
                >
                <n-button
                  v-if="!msg.followUpState && feedbackAvailable"
                  quaternary
                  class="reply-action"
                  @click="openFeedbackFlow(msg)"
                  >反馈问题</n-button
                >
                <span v-if="msg.followUpState === 'resolved'" class="follow-up-result"
                  ><n-icon :component="CheckmarkOutline" />已标记解决</span
                >
                <span v-else-if="msg.followUpState === 'feedback'" class="follow-up-result"
                  >已打开反馈窗口</span
                >
              </template>
            </div>
          </article>
        </div>
      </div>
      <n-button
        v-if="!atBottom && chatHistory.length"
        round
        class="jump-latest"
        @click="scrollToLatest"
        ><template #icon><n-icon :component="ArrowDownOutline" /></template>回到最新</n-button
      >
    </div>

    <footer class="chatbot-input-area">
      <div class="composer">
        <n-input
          ref="inputRef"
          v-model:value="userInput"
          type="textarea"
          :bordered="false"
          :autosize="{ minRows: 2, maxRows: 6 }"
          :maxlength="4000"
          placeholder="描述问题，或粘贴相关日志…"
          aria-label="发送给 Mower AI 的问题"
          @keydown="onInputKeydown"
        />
        <div class="composer-toolbar">
          <span class="keyboard-hint">Enter 发送 <span>·</span> Shift + Enter 换行</span>
          <span v-if="userInput.length > 3500" class="input-count"
            >{{ userInput.length }} / 4000</span
          >
          <n-button type="primary" class="send-button" :disabled="!canSend" @click="sendMessage"
            ><template #icon><n-icon :component="ArrowUpOutline" /></template
            >{{ loading ? '回复中' : '发送' }}</n-button
          >
        </div>
      </div>
      <p class="composer-note">AI 可能判断有误，请核对日志与操作范围。</p>
    </footer>
  </section>
</template>

<style scoped>
.chatbot-container {
  position: fixed;
  right: 24px;
  bottom: 24px;
  z-index: 2000;
  display: flex;
  flex-direction: column;
  width: min(560px, calc(100vw - 48px));
  height: min(720px, calc(100dvh - 48px));
  overflow: hidden;
  border: 1px solid var(--mower-border);
  border-radius: 20px;
  background: var(--mower-surface);
  color: var(--mower-text);
  box-shadow:
    0 16px 56px rgba(0, 0, 0, 0.14),
    0 2px 8px rgba(0, 0, 0, 0.06);
  user-select: text;
  -webkit-user-select: text;
  -webkit-font-smoothing: antialiased;
}
.chatbot-header {
  display: flex;
  align-items: center;
  flex-shrink: 0;
  gap: 12px;
  padding: 16px 18px;
  border-bottom: 1px solid var(--mower-divider);
}
.assistant-mark,
.welcome-mark {
  display: grid;
  place-items: center;
  flex-shrink: 0;
  background: var(--mower-primary-block);
  color: var(--mower-primary-text);
}
.assistant-mark {
  width: 40px;
  height: 40px;
  border-radius: 12px;
  font-size: 21px;
}
.assistant-heading {
  min-width: 0;
  flex: 1;
}
.assistant-heading h2 {
  margin: 0 0 3px;
  font-size: 16px;
  font-weight: 650;
  line-height: 1.4;
}
.assistant-heading h2 span {
  margin-left: 3px;
  font-weight: 400;
  font-size: 13px;
  color: var(--mower-text-muted);
}
.assistant-status {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--mower-text-muted);
}
.status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--mower-primary);
}
.header-actions {
  display: flex;
  gap: 2px;
}
.icon-button {
  width: 40px;
  height: 40px;
}
.history-container {
  position: relative;
  flex: 1;
  min-height: 0;
}
.chatbot-history {
  height: 100%;
  overflow-y: auto;
  overscroll-behavior: contain;
  scrollbar-gutter: stable;
}
.chatbot-welcome {
  padding: 36px 24px 28px;
  text-align: center;
}
.welcome-mark {
  width: 56px;
  height: 56px;
  margin: 0 auto 18px;
  border-radius: 18px;
  font-size: 28px;
}
.chatbot-welcome h3 {
  margin: 0 0 10px;
  font-size: 24px;
  font-weight: 600;
  text-wrap: balance;
}
.chatbot-welcome p {
  margin: 0;
  line-height: 1.8;
  color: var(--mower-text-muted);
  text-wrap: pretty;
}
.suggestion-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
  margin: 28px 0 16px;
  text-align: left;
}
.suggestion {
  display: grid;
  grid-template-columns: 20px 1fr;
  align-content: start;
  gap: 7px 8px;
  padding: 14px;
  border: 1px solid var(--mower-divider);
  border-radius: 12px;
  background: var(--mower-control-surface);
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
  transition:
    background-color 0.15s,
    border-color 0.15s,
    transform 0.15s;
}
.suggestion > .n-icon {
  font-size: 18px;
  color: var(--mower-primary-text);
}
.suggestion strong {
  font-size: 13px;
  font-weight: 550;
}
.suggestion > span {
  grid-column: 1 / -1;
  font-size: 12px;
  line-height: 1.7;
  color: var(--mower-text-muted);
  text-wrap: pretty;
}
.suggestion:hover {
  background: var(--mower-control-hover);
  border-color: var(--mower-primary);
}
.suggestion:active,
.icon-button:active,
.send-button:active {
  transform: scale(0.96);
}
.suggestion:focus-visible {
  outline: 2px solid var(--mower-primary);
  outline-offset: 3px;
}
.welcome-hint {
  font-size: 12px;
  color: var(--mower-text-muted);
}
.message-list {
  padding: 24px 20px 12px;
}
.chat-row {
  margin-bottom: 24px;
  min-width: 0;
}
.message-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 7px;
  font-size: 12px;
  font-weight: 550;
  color: var(--mower-text-muted);
}
.message-state {
  font-weight: 400;
  color: var(--mower-primary-text);
}
.message-content {
  font-size: 14px;
  line-height: 1.8;
  overflow-wrap: anywhere;
}
.user .message-meta {
  justify-content: flex-end;
}
.user-content {
  width: fit-content;
  max-width: 88%;
  margin-left: auto;
  padding: 10px 14px;
  border-radius: 14px 14px 4px 14px;
  background: var(--mower-primary-block);
  white-space: pre-wrap;
}
.assistant-content {
  padding: 2px 0;
}
.message-error .assistant-content {
  padding: 12px 14px;
  border-radius: 12px;
  color: var(--mower-error-text);
  background: var(--mower-error-block);
}
.message-markdown :deep(> :first-child) {
  margin-top: 0;
}
.message-markdown :deep(> :last-child) {
  margin-bottom: 0;
}
.message-markdown :deep(p) {
  margin: 0 0 12px;
}
.message-markdown :deep(ul),
.message-markdown :deep(ol) {
  padding-left: 22px;
  margin: 10px 0;
}
.message-markdown :deep(li + li) {
  margin-top: 5px;
}
.message-markdown :deep(h1),
.message-markdown :deep(h2),
.message-markdown :deep(h3) {
  margin: 18px 0 8px;
  font-size: 16px;
  line-height: 1.5;
}
.message-markdown :deep(a) {
  color: var(--mower-primary-text);
  text-decoration: underline;
  text-underline-offset: 3px;
}
.message-markdown :deep(pre) {
  max-width: 100%;
  overflow-x: auto;
  padding: 12px 14px;
  border: 1px solid var(--mower-divider);
  border-radius: 10px;
  background: var(--mower-control-surface);
  line-height: 1.6;
}
.message-markdown :deep(code) {
  padding: 2px 5px;
  border-radius: 4px;
  background: var(--mower-control-surface);
  font-size: 12px;
}
.message-markdown :deep(pre code) {
  padding: 0;
  background: transparent;
  white-space: pre;
  overflow-wrap: normal;
}
.message-markdown :deep(blockquote) {
  margin: 12px 0;
  padding-left: 12px;
  border-left: 3px solid var(--mower-border);
  color: var(--mower-text-muted);
}
.message-markdown :deep(table) {
  display: block;
  max-width: 100%;
  width: max-content;
  overflow-x: auto;
  border-collapse: collapse;
  font-size: 12px;
}
.message-markdown :deep(th),
.message-markdown :deep(td) {
  padding: 8px 10px;
  border: 1px solid var(--mower-border);
  text-align: left;
}
.message-markdown :deep(th) {
  background: var(--mower-control-surface);
}
.message-markdown :deep(img) {
  max-width: 100%;
  height: auto;
  border-radius: 8px;
}
.thinking-indicator {
  display: flex;
  align-items: center;
  gap: 10px;
  color: var(--mower-text-muted);
  font-size: 13px;
}
.thinking-indicator > span {
  font-size: 26px;
  line-height: 1;
  letter-spacing: 3px;
  color: var(--mower-primary);
}
.message-actions {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 2px;
  margin: 8px 0 0 -8px;
}
.reply-action {
  height: 40px;
  font-size: 12px;
  color: var(--mower-text-muted);
}
.follow-up-result {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 0 10px;
  font-size: 12px;
  color: var(--mower-success-text);
}
.jump-latest {
  position: absolute;
  bottom: 12px;
  left: 50%;
  transform: translateX(-50%);
  height: 40px;
  box-shadow: 0 3px 12px rgba(0, 0, 0, 0.12);
}
.chatbot-input-area {
  flex-shrink: 0;
  padding: 12px 18px 10px;
  border-top: 1px solid var(--mower-divider);
}
.composer {
  padding: 6px;
  border: 1px solid var(--mower-border);
  border-radius: 14px;
  background: var(--mower-control-surface);
  transition:
    border-color 0.15s,
    box-shadow 0.15s;
}
.composer:focus-within {
  border-color: var(--mower-primary);
  box-shadow: 0 0 0 2px var(--mower-primary-block);
}
.composer :deep(.n-input) {
  --n-color: transparent !important;
  --n-color-focus: transparent !important;
  --n-box-shadow-focus: none !important;
}
.composer-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 4px 2px 8px;
}
.keyboard-hint {
  flex: 1;
  font-size: 11px;
  color: var(--mower-text-muted);
}
.keyboard-hint > span {
  margin: 0 3px;
}
.input-count {
  font-size: 11px;
  font-variant-numeric: tabular-nums;
  color: var(--mower-text-muted);
}
.send-button {
  height: 40px;
  border-radius: 10px;
  transition: transform 0.15s;
}
.composer-note {
  margin: 8px 0 0;
  font-size: 11px;
  text-align: center;
  color: var(--mower-text-muted);
}
@media (max-width: 640px) {
  .chatbot-container {
    inset: 0;
    width: 100%;
    height: 100dvh;
    border: 0;
    border-radius: 0;
  }
  .chatbot-header {
    padding: max(12px, env(safe-area-inset-top)) 14px 12px;
  }
  .chatbot-welcome {
    padding: 28px 18px 20px;
  }
  .message-list {
    padding: 20px 16px 12px;
  }
  .chatbot-input-area {
    padding: 10px 12px max(10px, env(safe-area-inset-bottom));
  }
  .keyboard-hint {
    font-size: 10px;
  }
  .composer-toolbar {
    padding-left: 4px;
  }
}
@media (prefers-reduced-motion: reduce) {
  .suggestion,
  .composer,
  .send-button {
    transition: none;
  }
  .suggestion:active,
  .icon-button:active,
  .send-button:active {
    transform: none;
  }
}
</style>
