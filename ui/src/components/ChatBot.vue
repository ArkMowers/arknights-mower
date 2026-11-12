<script setup>
import { computed, inject, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useDialog, useMessage } from 'naive-ui'
import { useMowerStore } from '@/stores/mower'
import { CONFIG_GENERATION_HEADER } from '@/composables/configProfiles'
import AddOutline from '@vicons/ionicons5/es/AddOutline'
import ArrowDownOutline from '@vicons/ionicons5/es/ArrowDownOutline'
import ArrowUpOutline from '@vicons/ionicons5/es/ArrowUpOutline'
import CheckmarkOutline from '@vicons/ionicons5/es/CheckmarkOutline'
import CloseOutline from '@vicons/ionicons5/es/CloseOutline'
import CopyOutline from '@vicons/ionicons5/es/CopyOutline'
import DocumentTextOutline from '@vicons/ionicons5/es/DocumentTextOutline'
import GridOutline from '@vicons/ionicons5/es/GridOutline'
import TimeOutline from '@vicons/ionicons5/es/TimeOutline'
import MailOutline from '@vicons/ionicons5/es/MailOutline'
import SchoolOutline from '@vicons/ionicons5/es/SchoolOutline'
import SettingsOutline from '@vicons/ionicons5/es/SettingsOutline'
import markdownit from 'markdown-it'
import MowerAIIcon from './MowerAIIcon.vue'

const props = defineProps({ show: Boolean })
const emit = defineEmits(['update:show'])
const show = computed({ get: () => props.show, set: (value) => emit('update:show', value) })
const router = useRouter()
const notice = useMessage()
const dialog = useDialog()
const mower = useMowerStore()
const axios = inject('axios')
const showFeedback = inject('show_feedback', null)
const feedbackAvailable = showFeedback !== null
const md = markdownit({ html: false, breaks: true })
const visibleContent = (content) => content.replace(/<!--MOWER_MISS_STATE:[\s\S]*?-->/g, '')
const renderMessage = (content) => md.render(visibleContent(content))
const userInput = ref('')
const chatHistory = ref([])
const loading = ref(false)
const conversationId = ref(null)
const conversations = ref([])
const historyOpen = ref(false)
const historyBusy = ref(false)
const historyReady = ref(false)
const historyError = ref('')
const remoteBusy = ref(false)
const connectionLost = ref(false)
let reconnectTimer = null
let reconnectAttempts = 0
const contextInfo = ref(null)
const summarySource = ref(0)
const controlBusy = ref(false)
const stopping = ref(false)
let requestOptions = {}
const pretty = (value) => JSON.stringify(value, null, 2)
const toolStatus = {
  awaiting_approval: '待确认',
  running: '执行中',
  succeeded: '查询完成',
  verified: '已核对写入',
  accepted: '邮件服务已接受',
  failed: '失败或检查未通过',
  unknown: '结果待核实',
  not_executed: '未执行',
  not_repeated: '未重复执行'
}
function eventStatus(event, msg) {
  if (event.status === 'awaiting_approval' && !(loading.value && activeReply === msg))
    return '未执行（确认已失效）'
  if (event.status === 'running' && !(loading.value && activeReply === msg)) return '结果待核实'
  return toolStatus[event.status] || event.status
}
function replyProgress(msg) {
  if (connectionLost.value && activeReply === msg) return '连接中断，正在恢复进度'
  if (stopping.value && activeReply === msg) return '正在停止后续调用'
  const event = msg.events?.at(-1)
  if (event?.status === 'awaiting_approval') return '等待你核对并确认'
  if (event?.status === 'running') return event.label || '正在执行工具'
  return '正在生成回复'
}
async function sendControl(action, event = null) {
  if (!loading.value || !activeReply?.turn_id || controlBusy.value) return
  if (action !== 'stop' && (connectionLost.value || event?.decision)) return
  controlBusy.value = true
  const target = activeReply
  try {
    await axios.post(`${historyBase}/${conversationId.value}/turns/${target.turn_id}/control`, {
      action,
      ...(event ? { approval_id: event.approval_id, digest: event.digest } : {})
    })
    if (activeReply === target) {
      if (action === 'stop') stopping.value = true
      else if (event) event.decision = action
    }
  } catch (error) {
    notice.error(error.response?.data?.error || '操作未提交，请重试或刷新历史核实。')
  } finally {
    controlBusy.value = false
  }
}
function requestSummary() {
  if (!conversationId.value || loading.value || historyBusy.value || remoteBusy.value) return
  sendTurn('请整理当前会话摘要草稿，供我核对。', { mode: 'summary' })
}
async function adoptSummary(msg = null) {
  if (loading.value || historyBusy.value) return
  historyBusy.value = true
  try {
    await axios.post(`${historyBase}/${conversationId.value}/summary`, {
      turn_id: msg?.turn_id || null
    })
    summarySource.value = msg?.turn_id || 0
    notice.success(msg ? '已采用核对后的摘要，后续提问仍会重新查询当前状态。' : '已停用摘要')
  } catch (error) {
    notice.error(error.response?.data?.error || '摘要未保存，请重试。')
  } finally {
    historyBusy.value = false
  }
}
function resumeIncompleteTurn(msg, index) {
  if (
    loading.value ||
    historyBusy.value ||
    remoteBusy.value ||
    index !== chatHistory.value.length - 1 ||
    !msg.turn_id ||
    !msg.error
  )
    return
  sendTurn(chatHistory.value[index - 1].content, {
    [msg.mode === 'summary' ? 'retry_of' : 'continue_of']: msg.turn_id,
    mode: msg.mode || 'chat'
  })
}
const historyBase = `${import.meta.env.VITE_HTTP_URL || ''}/ai/conversations`
let historyRequest = 0
let disposed = false
const historyOptionsDisabled = computed(() => loading.value || historyBusy.value)

function currentGeneration() {
  return axios.defaults.headers.common[CONFIG_GENERATION_HEADER]
}
function restoreConversation(data) {
  requestOptions = {}
  conversationId.value = data.id
  remoteBusy.value = data.busy
  summarySource.value = data.summary_source || 0
  contextInfo.value = null
  chatHistory.value = data.turns.flatMap((turn, index) => [
    { role: 'user', content: turn.continued_from ? '继续处理' : turn.user },
    {
      role: 'bot',
      turn_id: turn.id,
      mode: turn.mode || 'chat',
      events: turn.events || [],
      draft: '',
      content:
        turn.assistant +
        (turn.status !== 'complete' && !(data.busy && index === data.turns.length - 1)
          ? '\n\n本轮未完成，部分操作可能已执行，请核实后再继续。'
          : ''),
      error: turn.status !== 'complete' && !(data.busy && index === data.turns.length - 1),
      followUpState: null
    }
  ])
  if (data.busy && chatHistory.value.length) {
    activeReply = chatHistory.value.at(-1)
    loading.value = true
    connectionLost.value = true
    reconnectAttempts = 0
    connectWS(null, true)
  }
  atBottom.value = true
}
async function loadHistory({ restore = false, id = null } = {}) {
  if (loading.value || historyBusy.value || mower.ai_assistant_enabled !== true) return
  const requestId = ++historyRequest
  const generation = currentGeneration()
  const valid = () =>
    !disposed &&
    mower.ai_assistant_enabled === true &&
    requestId === historyRequest &&
    generation === currentGeneration()
  historyBusy.value = true
  historyError.value = ''
  try {
    const { data } = await axios.get(historyBase)
    if (!valid()) return
    conversations.value = data.conversations
    const selected = id || (restore ? data.conversations[0]?.id : null)
    if (selected) {
      const response = await axios.get(`${historyBase}/${selected}`)
      if (!valid()) return
      closeConnection()
      restoreConversation(response.data)
      userInput.value = ''
    }
    historyReady.value = true
  } catch (error) {
    if (valid()) historyError.value = error.response?.data?.error || '无法读取会话历史，请重试。'
  } finally {
    if (!disposed && requestId === historyRequest) historyBusy.value = false
  }
}
async function selectConversation(id) {
  await loadHistory({ id })
  if (!historyError.value) historyOpen.value = false
}
async function deleteConversation(id = null) {
  if (historyOptionsDisabled.value) return
  historyBusy.value = true
  historyError.value = ''
  try {
    await axios.delete(id ? `${historyBase}/${id}` : historyBase)
    if (disposed) return
    if (!id || id === conversationId.value) newConversation()
    conversations.value = id ? conversations.value.filter((item) => item.id !== id) : []
  } catch (error) {
    historyError.value = error.response?.data?.error || '删除失败，请重试。'
  } finally {
    historyBusy.value = false
  }
}
function toggleHistory() {
  historyOpen.value = !historyOpen.value
  if (historyOpen.value) loadHistory()
}
function historyTime(timestamp) {
  return new Date(timestamp * 1000).toLocaleString()
}
const connecting = ref(false)
const historyRef = ref(null)
const inputRef = ref(null)
const panelRef = ref(null)
const panelPosition = ref(null)
const dragging = ref(false)
const panelStyle = computed(() =>
  panelPosition.value
    ? { '--chat-left': `${panelPosition.value.x}px`, '--chat-top': `${panelPosition.value.y}px` }
    : {}
)
let dragOrigin = null
function startDrag(event) {
  if (
    dragOrigin ||
    event.button !== 0 ||
    window.innerWidth <= 640 ||
    event.target.closest('button, a, input, textarea, select, [role="button"], [contenteditable]')
  )
    return
  const rect = panelRef.value?.getBoundingClientRect()
  if (!rect) return
  dragOrigin = {
    id: event.pointerId,
    x: event.clientX,
    y: event.clientY,
    left: rect.left,
    top: rect.top
  }
  dragging.value = true
  event.currentTarget.setPointerCapture(event.pointerId)
  event.preventDefault()
}
function moveDrag(event) {
  if (!dragOrigin || event.pointerId !== dragOrigin.id) return
  panelPosition.value = {
    x: dragOrigin.left + event.clientX - dragOrigin.x,
    y: dragOrigin.top + event.clientY - dragOrigin.y
  }
}
function endDrag(event) {
  if (!dragOrigin || event.pointerId !== dragOrigin.id) return
  dragOrigin = null
  dragging.value = false
  if (event.currentTarget.hasPointerCapture(event.pointerId)) {
    event.currentTarget.releasePointerCapture(event.pointerId)
  }
}
const atBottom = ref(true)
const canSend = computed(
  () =>
    Boolean(userInput.value.trim()) &&
    !loading.value &&
    !historyBusy.value &&
    historyReady.value &&
    !remoteBusy.value
)
const statusLabel = computed(() =>
  stopping.value
    ? '正在停止后续调用'
    : connecting.value
      ? '正在连接'
      : loading.value
        ? '正在处理'
        : '日志排查与使用建议'
)
const suggestions = [
  { title: '排查连接', description: '设备连接失败，应该先检查什么？', icon: DocumentTextOutline },
  {
    title: '尝试排班',
    description: '结合我的森空岛干员练度和基建组合，尝试安排基建主班。',
    icon: GridOutline
  },
  { title: '查看专精', description: '帮我查看当前专精计划的状态。', icon: SchoolOutline },
  { title: '整理反馈', description: '帮我整理一份问题反馈，先不要发送。', icon: MailOutline }
]
let ws = null
let activeReply = null
let connectTimer = null

function messageFrame(text) {
  return JSON.stringify({
    message: text,
    conversation_id: conversationId.value,
    ...requestOptions,
    generation: axios.defaults.headers.common[CONFIG_GENERATION_HEADER]
  })
}

function scrollToLatest() {
  atBottom.value = true
  if (historyRef.value) historyRef.value.scrollTop = historyRef.value.scrollHeight
}
function trackScroll() {
  const el = historyRef.value
  if (el) atBottom.value = el.scrollHeight - el.scrollTop - el.clientHeight < 80
}
function closeConnection() {
  clearTimeout(reconnectTimer)
  reconnectTimer = null
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
    if (!activeReply.content) activeReply.content = activeReply.draft || ''
    activeReply.draft = ''
    activeReply.content += `${activeReply.content ? '\n\n' : ''}${text}`
    activeReply.error = true
  }
  activeReply = null
  loading.value = false
  stopping.value = false
  remoteBusy.value = false
  connectionLost.value = false
  closeConnection()
}
function reconnectRun() {
  if (disposed || !loading.value || !assistantAllowed()) return
  connectionLost.value = true
  connectWS(null, true)
}
function lostConnection() {
  closeConnection()
  if (!loading.value || disposed) return
  connectionLost.value = true
  if (reconnectAttempts < 3) {
    const delay = 1000 * 2 ** reconnectAttempts++
    reconnectTimer = setTimeout(reconnectRun, delay)
  }
}
function trimHistory() {
  let retained = chatHistory.value.reduce((size, item) => size + item.content.length, 0)
  while (chatHistory.value.length > 2 && (chatHistory.value.length > 200 || retained > 262144)) {
    retained -= chatHistory.value.splice(0, 2).reduce((size, item) => size + item.content.length, 0)
  }
}
function applySnapshot(snapshot) {
  if (!activeReply) return
  conversationId.value = snapshot.conversation_id
  activeReply.turn_id = snapshot.turn_id
  activeReply.mode = snapshot.mode || 'chat'
  activeReply.events = snapshot.events || []
  activeReply.content = snapshot.assistant || ''
  activeReply.draft = snapshot.draft || ''
  activeReply.error = false
  contextInfo.value = snapshot.context || contextInfo.value
  connectionLost.value = false
  reconnectAttempts = 0
  remoteBusy.value = false
  if (snapshot.status !== 'running') {
    if (snapshot.status !== 'complete') {
      activeReply.error = true
      activeReply.content += `\n\n${snapshot.error || '本轮未完成，部分操作可能已执行，请核实后再继续。'}`
    }
    activeReply = null
    loading.value = false
    stopping.value = false
    trimHistory()
  }
}
function connectWS(text, resume = false) {
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
    if (resume) lostConnection()
    else failReply('无法建立 AI 连接，请检查服务地址后重试。')
    return
  }
  connectTimer = setTimeout(() => {
    if (resume) lostConnection()
    else failReply('AI 连接超时，请检查服务是否运行后重试。')
  }, 20000)
  ws.onopen = () => {
    clearTimeout(connectTimer)
    connecting.value = false
    ws.send(JSON.stringify({ token }))
    ws.send(
      resume
        ? JSON.stringify({
            resume: true,
            conversation_id: conversationId.value,
            request_id: requestOptions.request_id,
            turn_id: activeReply?.turn_id,
            generation: currentGeneration()
          })
        : messageFrame(text)
    )
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
    if (data.snapshot) {
      applySnapshot(data.snapshot)
      return
    }
    if (data.conversation_id) conversationId.value = data.conversation_id
    if (!activeReply) return
    if (data.code === 'ai_assistant_disabled') {
      failReply(data.error || '管理员未开启')
      showAssistantUnavailable()
      return
    }
    if (data.turn_id) {
      activeReply.turn_id = data.turn_id
      activeReply.mode = data.mode || 'chat'
      contextInfo.value = data.context || null
    }
    if (data.event) {
      const event = data.event
      if (event.turn_id !== activeReply.turn_id) return
      if (event.type === 'answer_delta') activeReply.draft += event.text || ''
      else if (event.type === 'answer_reset' || event.type === 'model') activeReply.draft = ''
      else if (event.type === 'tool' || event.type === 'approval') {
        activeReply.events = [
          ...activeReply.events.filter((item) => item.id !== event.id),
          event
        ].slice(-32)
      }
      return
    }
    if (typeof data.reply === 'string') {
      activeReply.draft = ''
      activeReply.content += data.reply
    }
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
      stopping.value = false
      connectionLost.value = false
      remoteBusy.value = false
      reconnectAttempts = 0
      trimHistory()
    }
  }
  ws.onerror = lostConnection
  ws.onclose = lostConnection
}
function sendMessage() {
  if (!canSend.value) return
  const text = userInput.value.trim()
  if (text.length > 4000) return
  const last = chatHistory.value.at(-1)
  if (
    ['继续', '继续处理'].includes(text) &&
    last?.error &&
    last.turn_id &&
    last.mode !== 'summary'
  ) {
    resumeIncompleteTurn(last, chatHistory.value.length - 1)
    if (loading.value) userInput.value = ''
    return
  }
  sendTurn(text)
}
function sendTurn(text, options = {}) {
  if (
    loading.value ||
    historyBusy.value ||
    !historyReady.value ||
    remoteBusy.value ||
    !assistantAllowed()
  )
    return
  requestOptions = {
    request_id: Array.from(crypto.getRandomValues(new Uint8Array(16)), (value) =>
      value.toString(16).padStart(2, '0')
    ).join(''),
    ...options
  }
  chatHistory.value.push({ role: 'user', content: options.continue_of ? '继续处理' : text })
  chatHistory.value.push({
    role: 'bot',
    content: '',
    draft: '',
    events: [],
    followUpState: null,
    error: false,
    mode: options.mode || 'chat'
  })
  activeReply = chatHistory.value.at(-1)
  loading.value = true
  connectionLost.value = false
  reconnectAttempts = 0
  stopping.value = false
  atBottom.value = true
  historyOpen.value = false
  if (!options.mode && !options.retry_of && !options.continue_of) userInput.value = ''
  if (!ws || ws.readyState !== WebSocket.OPEN) connectWS(text)
  else ws.send(messageFrame(text))
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
  conversationId.value = null
  contextInfo.value = null
  summarySource.value = 0
  remoteBusy.value = false
  historyOpen.value = false
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
function assistantAllowed() {
  if (mower.ai_assistant_enabled === true) return true
  if (mower.ai_assistant_enabled === false) {
    failReply('管理员未开启')
    showAssistantUnavailable()
  } else {
    notice.warning('尚未取得助手授权状态，请稍后重试。')
  }
  return false
}
function showAssistantUnavailable() {
  dialog.warning({
    title: '管理员未开启',
    content: '当前实例暂未开启该功能，请联系管理员。',
    positiveText: '知道了'
  })
  show.value = false
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
  [() => props.show, () => mower.ai_assistant_enabled],
  async ([value, enabled]) => {
    if (enabled === false) {
      if (value) assistantAllowed()
      else failReply('管理员未开启')
      return
    }
    if (!value) return
    if (connectionLost.value && !ws && !reconnectTimer) reconnectRun()
    if (enabled === true && !historyReady.value) await loadHistory({ restore: true })
    await nextTick()
    inputRef.value?.focus()
    if (atBottom.value) scrollToLatest()
  },
  { immediate: true }
)
onBeforeUnmount(() => {
  disposed = true
  historyRequest++
  closeConnection()
})
</script>

<template>
  <section
    ref="panelRef"
    v-show="show"
    class="chatbot-container"
    :style="panelStyle"
    role="dialog"
    aria-label="Mower AI 助手"
  >
    <header
      class="chatbot-header"
      :class="{ dragging }"
      @pointerdown="startDrag"
      @pointermove="moveDrag"
      @pointerup="endDrag"
      @pointercancel="endDrag"
      @lostpointercapture="endDrag"
    >
      <div class="assistant-mark" aria-hidden="true"><n-icon :component="MowerAIIcon" /></div>
      <div class="assistant-heading">
        <h2>Mower AI <span>助手</span></h2>
        <div class="assistant-status" role="status">
          <span v-if="loading" class="status-dot" aria-hidden="true"></span>{{ statusLabel }}
        </div>
      </div>
      <div class="header-actions">
        <n-button
          quaternary
          circle
          class="icon-button"
          :disabled="historyOptionsDisabled"
          aria-label="历史会话"
          title="历史会话"
          @click="toggleHistory"
        >
          <template #icon><n-icon :component="TimeOutline" /></template>
        </n-button>
        <n-button
          quaternary
          circle
          class="icon-button"
          :disabled="historyOptionsDisabled || !historyReady"
          aria-label="新对话"
          title="新对话，保留历史"
          @click="newConversation"
        >
          <template #icon><n-icon :component="AddOutline" /></template>
        </n-button>
        <n-button
          quaternary
          circle
          class="icon-button"
          aria-label="Mower 设置"
          title="前往 Mower 设置"
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

    <div v-if="historyError" class="history-notice" role="alert">
      {{ historyError }}
      <n-button text @click="loadHistory({ restore: !historyReady })" :disabled="historyBusy"
        >重试</n-button
      >
    </div>
    <div v-if="connectionLost" class="history-notice" role="status">
      连接中断，服务仍可能在执行；恢复连接不会重复提交请求。
      <n-button text @click="reconnectRun" :disabled="connecting">重新连接</n-button>
    </div>
    <div v-if="historyOpen" class="conversation-browser">
      <div class="conversation-toolbar">
        <strong>历史会话</strong>
        <n-popconfirm
          :disabled="historyOptionsDisabled || !conversations.length"
          @positive-click="deleteConversation()"
        >
          <template #trigger
            ><n-button
              size="small"
              quaternary
              :disabled="historyOptionsDisabled || !conversations.length"
              >清空历史</n-button
            ></template
          >
          删除当前配置档案的全部会话？此操作无法撤销。
        </n-popconfirm>
      </div>
      <p class="history-help">保存在当前实例，按配置档案分别保存。最多保留 20 个会话。</p>
      <p v-if="!conversations.length" class="history-help">暂无历史会话</p>
      <div
        v-for="item in conversations"
        :key="item.id"
        class="conversation-item"
        :class="{ selected: item.id === conversationId }"
      >
        <button
          type="button"
          class="conversation-select"
          :disabled="historyOptionsDisabled"
          @click="selectConversation(item.id)"
        >
          <strong>{{ item.title }}</strong><time>{{ historyTime(item.updated) }}</time>
        </button>
        <n-popconfirm
          :disabled="historyOptionsDisabled"
          @positive-click="deleteConversation(item.id)"
        >
          <template #trigger
            ><n-button
              quaternary
              size="small"
              :disabled="historyOptionsDisabled"
              :aria-label="`删除会话：${item.title}`"
              >删除</n-button
            ></template
          >
          删除这个会话？已执行的操作不会撤销。
        </n-popconfirm>
      </div>
    </div>
    <div v-else class="history-container">
      <div ref="historyRef" class="chatbot-history" @scroll="trackScroll" :aria-busy="loading">
        <div v-if="!chatHistory.length" class="chatbot-welcome">
          <h3>从一个问题开始</h3>
          <p>查日志、理解排班、跟进专精、整理反馈。</p>
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
                >{{ replyProgress(msg) }}</span
              >
            </div>
            <div v-if="msg.role === 'bot' && msg.events?.length" class="tool-events">
              <details
                v-for="event in msg.events"
                :key="event.id"
                :open="event.status === 'awaiting_approval' && loading && msg === activeReply"
              >
                <summary>{{ event.label || event.name }} · {{ eventStatus(event, msg) }}</summary>
                <p class="evidence-label">
                  证据 {{ event.id }}
                  <span v-if="event.observed_at">· {{ event.observed_at }}</span>
                </p>
                <p v-if="event.source">{{ event.source }}</p>
                <pre v-if="event.preview">{{ pretty(event.preview) }}</pre>
                <pre v-else-if="event.arguments">{{ pretty(event.arguments) }}</pre>
                <pre v-if="event.result">{{ event.result }}</pre>
                <p v-if="event.truncated">仅展示部分结果，不能据此判断完整覆盖。</p>
                <template
                  v-if="
                    event.type === 'approval' &&
                    event.status === 'awaiting_approval' &&
                    loading &&
                    msg === activeReply
                  "
                >
                  <p>
                    请核对具体内容。确认有效期至
                    {{
                      event.expires_at
                        ? new Date(event.expires_at * 1000).toLocaleTimeString()
                        : '本轮截止时间'
                    }}；刷新不会延长，停止或服务重启后失效。
                  </p>
                  <n-button
                    size="small"
                    type="primary"
                    :disabled="controlBusy || stopping || connectionLost || Boolean(event.decision)"
                    @click="sendControl('approve', event)"
                    >{{ event.decision === 'approve' ? '已提交确认' : '确认执行' }}</n-button
                  >
                  <n-button
                    size="small"
                    :disabled="controlBusy || stopping || connectionLost || Boolean(event.decision)"
                    @click="sendControl('reject', event)"
                    >不执行</n-button
                  >
                </template>
              </details>
            </div>
            <div v-if="msg.role === 'user'" class="message-content user-content">
              {{ msg.content }}
            </div>
            <div v-else class="message-content assistant-content">
              <div
                v-if="msg.content || msg.draft"
                class="message-markdown"
                v-html="renderMessage(msg.content || msg.draft)"
              ></div>
              <div v-else class="thinking-indicator" role="status">
                <span aria-hidden="true">···</span
                >{{ connecting ? '正在建立连接' : replyProgress(msg) }}
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
              <n-button
                v-if="msg.error && msg.turn_id && idx === chatHistory.length - 1"
                quaternary
                class="reply-action"
                :disabled="loading || historyBusy || remoteBusy"
                @click="resumeIncompleteTurn(msg, idx)"
                >{{ msg.mode === 'summary' ? '重新生成摘要' : '继续处理' }}</n-button
              >
              <n-popconfirm
                v-if="!msg.error && msg.mode === 'summary'"
                :disabled="loading || historyBusy"
                @positive-click="adoptSummary(msg)"
              >
                <template #trigger
                  ><n-button quaternary class="reply-action" :disabled="loading || historyBusy"
                    >核对后采用摘要</n-button
                  ></template
                >
                将这份摘要作为后续对话的历史背景？请先核对其中的事实与未完成事项。
              </n-popconfirm>
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

    <footer v-if="!historyOpen" class="chatbot-input-area">
      <div class="context-toolbar">
        <span v-if="contextInfo?.continued_from"
          >已带入原目标和保存的进度，继续处理剩余工作。{{
            contextInfo.continuation_limited ? '部分记录已截断。' : ''
          }}</span
        >
        <span v-else-if="contextInfo?.limited"
          >本轮仅使用 {{ contextInfo.included_turns }} 轮近期记录，部分历史未传给模型。</span
        >
        <span v-else>近期上下文最多 10 轮、24,000 字符。</span>
        <n-button
          text
          size="tiny"
          :disabled="!conversationId || loading || historyBusy || remoteBusy"
          @click="requestSummary"
          >整理摘要</n-button
        >
        <n-button
          v-if="summarySource"
          text
          size="tiny"
          :disabled="loading || historyBusy"
          @click="adoptSummary()"
          >停用摘要</n-button
        >
      </div>
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
          <n-button
            v-if="loading"
            class="send-button"
            :disabled="!activeReply?.turn_id || controlBusy || stopping"
            @click="sendControl('stop')"
            >{{ stopping ? '停止中' : '停止' }}</n-button
          >
          <n-button
            v-else
            type="primary"
            class="send-button"
            :disabled="!canSend"
            @click="sendMessage"
            ><template #icon><n-icon :component="ArrowUpOutline" /></template
            >{{ loading ? '回复中' : '发送' }}</n-button
          >
        </div>
      </div>
      <p class="composer-note">会话自动保存在本机。AI 可能判断有误，请核对操作范围。</p>
    </footer>
  </section>
</template>

<style scoped>
.tool-events {
  margin: 0 0 12px;
  font-size: 12px;
  color: var(--mower-text-muted);
}
.tool-events details {
  border: 1px solid var(--mower-divider);
  border-radius: 8px;
  padding: 8px;
  margin-bottom: 6px;
}
.tool-events summary {
  cursor: pointer;
  color: var(--mower-text);
}
.tool-events pre {
  max-height: 200px;
  overflow: auto;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  font-size: 11px;
}
.tool-events p {
  margin: 6px 0;
}
.tool-events .n-button + .n-button {
  margin-left: 8px;
}
.context-toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 10px;
  align-items: center;
  margin-bottom: 8px;
  color: var(--mower-text-muted);
  font-size: 11px;
}
.context-toolbar > span {
  flex: 1;
}

.history-notice {
  padding: 8px 14px;
  font-size: 12px;
  color: var(--mower-error-text);
}
.conversation-browser {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 16px;
}
.conversation-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.history-help {
  font-size: 12px;
  color: var(--mower-text-muted);
  line-height: 1.8;
}
.conversation-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  border-bottom: 1px solid var(--mower-divider);
  border-radius: 8px;
}
.conversation-item.selected {
  background: var(--mower-primary-block);
}
.conversation-select {
  flex: 1;
  min-width: 0;
  border: 0;
  padding: 8px 0;
  text-align: left;
  background: transparent;
  color: inherit;
  font: inherit;
  cursor: pointer;
}
.conversation-select strong {
  display: block;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
  font-size: 13px;
}
.conversation-select time {
  display: block;
  font-size: 11px;
  color: var(--mower-text-muted);
  margin-top: 6px;
}

.chatbot-container {
  --chat-width: min(440px, calc(100vw - 32px));
  --chat-height: min(560px, calc(100dvh - 32px));
  position: fixed;
  left: clamp(16px, var(--chat-left, 100vw), calc(100vw - var(--chat-width) - 16px));
  top: clamp(16px, var(--chat-top, 100dvh), calc(100dvh - var(--chat-height) - 16px));
  z-index: 2000;
  display: flex;
  flex-direction: column;
  width: var(--chat-width);
  height: var(--chat-height);
  box-sizing: border-box;
  overflow: hidden;
  border: 1px solid var(--mower-border);
  border-radius: 16px;
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
  padding: 10px 14px;
  border-bottom: 1px solid var(--mower-divider);
  cursor: grab;
  touch-action: none;
  user-select: none;
  -webkit-user-select: none;
}
.chatbot-header.dragging {
  cursor: grabbing;
}
.assistant-mark {
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
  font-size: 26px;
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
  padding: 20px 16px 16px;
  text-align: center;
}
.chatbot-welcome h3 {
  margin: 0 0 8px;
  font-size: 20px;
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
  gap: 8px;
  margin: 16px 0 12px;
  text-align: left;
}
.suggestion {
  display: grid;
  grid-template-columns: 20px 1fr;
  align-content: start;
  gap: 7px 8px;
  padding: 10px;
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
    cursor: default;
    touch-action: auto;
  }
  .chatbot-welcome {
    padding: 20px 18px;
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
@media (max-width: 360px) {
  .assistant-mark {
    display: none;
  }
  .icon-button {
    width: 36px;
  }
  .assistant-heading h2 {
    white-space: nowrap;
  }
  .assistant-status {
    display: block;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
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
