<script setup>
import { computed, inject, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useDialog, useMessage } from 'naive-ui'
import { useMowerStore } from '@/stores/mower'
import { CONFIG_GENERATION_HEADER } from '@/composables/configProfiles'
import AddOutline from '@vicons/ionicons5/es/AddOutline'
import ArrowDownOutline from '@vicons/ionicons5/es/ArrowDownOutline'
import ArrowUpOutline from '@vicons/ionicons5/es/ArrowUpOutline'
import Stop from '@vicons/ionicons5/es/Stop'
import Play from '@vicons/ionicons5/es/Play'
import Attach from '@vicons/ionicons5/es/Attach'
import EllipsisHorizontal from '@vicons/ionicons5/es/EllipsisHorizontal'
import InformationCircleOutline from '@vicons/ionicons5/es/InformationCircleOutline'
import CloseOutline from '@vicons/ionicons5/es/CloseOutline'
import CopyOutline from '@vicons/ionicons5/es/CopyOutline'
import DocumentTextOutline from '@vicons/ionicons5/es/DocumentTextOutline'
import GridOutline from '@vicons/ionicons5/es/GridOutline'
import TimeOutline from '@vicons/ionicons5/es/TimeOutline'
import MailOutline from '@vicons/ionicons5/es/MailOutline'
import SchoolOutline from '@vicons/ionicons5/es/SchoolOutline'
import ExpandOutline from '@vicons/ionicons5/es/ExpandOutline'
import ContractOutline from '@vicons/ionicons5/es/ContractOutline'
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
const composeNewQuestion = ref(false)
const draftAttachments = ref([])
const attachmentsBusy = ref(false)
const fileInputRef = ref(null)
const fileDragDepth = ref(0)
let attachmentEpoch = 0
let pendingAttachments = null

const previewOpen = ref(false)
const previewFile = ref(null)
const previewBusy = ref(false)
const previewError = ref('')
let previewRequest = 0
async function inspectAttachment(file) {
  const request = ++previewRequest
  const generation = currentGeneration()
  previewFile.value = { id: file.id, name: file.name, kind: file.kind }
  previewOpen.value = true
  previewBusy.value = true
  previewError.value = ''
  try {
    const response = await axios.get(
      `${import.meta.env.VITE_HTTP_URL || ''}/ai/attachments/${file.id}`
    )
    if (disposed || request !== previewRequest || generation !== currentGeneration()) return
    previewFile.value = response.data
  } catch (error) {
    if (!disposed && request === previewRequest && generation === currentGeneration())
      previewError.value = error.response?.data?.error || '无法读取附件，请重试。'
  } finally {
    if (!disposed && request === previewRequest) previewBusy.value = false
  }
}
watch(previewOpen, (value) => {
  if (!value) {
    previewRequest++
    previewFile.value = null
    previewBusy.value = false
  }
})

function settleAttachments(accepted) {
  if (!pendingAttachments) return false
  const pending = pendingAttachments
  pendingAttachments = null
  if (!accepted && !disposed && pending.epoch === attachmentEpoch) {
    draftAttachments.value = [...pending.files, ...draftAttachments.value]
    composeNewQuestion.value = pending.asNewQuestion
    if (!userInput.value) userInput.value = pending.text
    return true
  } else {
    for (const file of pending.files) if (file.preview) URL.revokeObjectURL(file.preview)
  }
}

function releaseAttachments() {
  attachmentEpoch++
  settleAttachments(true)
  for (const file of draftAttachments.value) if (file.preview) URL.revokeObjectURL(file.preview)
  draftAttachments.value = []
}
async function addFiles(files) {
  if (!assistantAllowed() || attachmentsBusy.value || loading.value) return
  const selected = Array.from(files || [])
  if (!selected.length) return
  if (draftAttachments.value.length + selected.length > 4) {
    notice.warning('最多添加 4 个文件')
    return
  }
  const epoch = attachmentEpoch
  const generation = currentGeneration()
  attachmentsBusy.value = true
  try {
    for (const file of selected) {
      if (!file.size || file.size > 2 * 1024 * 1024) {
        notice.error(`${file.name}：文件为空或超过 2 MB`)
        continue
      }
      const body = new FormData()
      body.append('file', file)
      try {
        const response = await axios.post(
          `${import.meta.env.VITE_HTTP_URL || ''}/ai/attachments`,
          body
        )
        if (disposed || epoch !== attachmentEpoch || generation !== currentGeneration()) return
        const attachment = response.data
        draftAttachments.value.push({
          ...attachment,
          preview: attachment.kind === 'image' ? URL.createObjectURL(file) : null
        })
        if (attachment.truncated) notice.warning(`${attachment.name}：仅发送文字摘录，内容有省略`)
      } catch (error) {
        if (!disposed && epoch === attachmentEpoch)
          notice.error(error.response?.data?.error || '文件未添加，请重试。')
      }
    }
  } finally {
    attachmentsBusy.value = false
  }
}
function removeAttachment(file) {
  draftAttachments.value = draftAttachments.value.filter((item) => item.id !== file.id)
  if (file.preview) URL.revokeObjectURL(file.preview)
  axios.delete(`${import.meta.env.VITE_HTTP_URL || ''}/ai/attachments/${file.id}`).catch(() => {})
}
function pickFiles(event) {
  const files = Array.from(event.target.files || [])
  event.target.value = ''
  return addFiles(files)
}
function dragFiles(event) {
  if (!Array.from(event.dataTransfer?.types || []).includes('Files')) return
  event.preventDefault()
  event.stopPropagation()
  if (event.type === 'dragenter') fileDragDepth.value++
  if (event.dataTransfer) event.dataTransfer.dropEffect = 'copy'
}
function leaveFiles(event) {
  if (!fileDragDepth.value) return
  event.preventDefault()
  fileDragDepth.value = Math.max(0, fileDragDepth.value - 1)
}
function dropFiles(event) {
  if (!Array.from(event.dataTransfer?.types || []).includes('Files')) return
  event.preventDefault()
  event.stopPropagation()
  fileDragDepth.value = 0
  return addFiles(event.dataTransfer.files)
}
function pasteFiles(event) {
  const files = Array.from(event.clipboardData?.files || [])
  if (!files.length) return
  event.preventDefault()
  return addFiles(files)
}
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
function isIncomplete(msg) {
  return Boolean(msg?.error || msg?.status === 'cancelled')
}
function terminalNotice(status, failure = {}, mode = 'chat') {
  if (status === 'cancelled') {
    return `已停止，可${mode === 'summary' ? '重新生成摘要' : '继续处理'}。已开始的操作可能已执行，请核对执行记录。`
  }
  const labels = {
    model_timeout: '模型响应超时',
    model_connection: '模型服务连接失败',
    model_error: '模型调用失败',
    execution_error: '本轮处理失败',
    request_error: '请求未完成'
  }
  const label = labels[failure.code] || '本轮未完成'
  return `${label}${failure.message ? `：${failure.message}` : '，原因未记录。'} 请核对执行记录后再继续。`
}
function resumeIncompleteTurn(msg, index, instruction = '') {
  if (
    loading.value ||
    historyBusy.value ||
    remoteBusy.value ||
    index !== chatHistory.value.length - 1 ||
    !msg.turn_id ||
    !isIncomplete(msg) ||
    instruction.length > 4000
  )
    return
  sendTurn(chatHistory.value[index - 1].content, {
    [msg.mode === 'summary' ? 'retry_of' : 'continue_of']: msg.turn_id,
    mode: msg.mode || 'chat',
    ...(instruction ? { continue_instruction: instruction } : {})
  })
  if (instruction && loading.value) userInput.value = ''
}
const historyBase = `${import.meta.env.VITE_HTTP_URL || ''}/ai/conversations`
let historyRequest = 0
let disposed = false
const historyOptionsDisabled = computed(() => loading.value || historyBusy.value)

function currentGeneration() {
  return axios.defaults.headers.common[CONFIG_GENERATION_HEADER]
}
function restoreConversation(data) {
  composeNewQuestion.value = false
  requestOptions = {}
  conversationId.value = data.id
  remoteBusy.value = data.busy
  summarySource.value = data.summary_source || 0
  contextInfo.value = null
  chatHistory.value = data.turns.flatMap((turn, index) => [
    {
      role: 'user',
      content: turn.continued_from ? turn.continue_instruction || '继续处理' : turn.user,
      silent: Boolean(turn.continued_from && !turn.continue_instruction),
      attachments: turn.attachments || []
    },
    {
      role: 'bot',
      turn_id: turn.id,
      mode: turn.mode || 'chat',
      status: turn.status,
      events: turn.events || [],
      draft: '',
      content:
        turn.assistant +
        (turn.status !== 'complete' && !(data.busy && index === data.turns.length - 1)
          ? `\n\n${terminalNotice(turn.status, turn.failure, turn.mode)}`
          : ''),
      error:
        !['complete', 'cancelled'].includes(turn.status) &&
        !(data.busy && index === data.turns.length - 1)
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
  if (layoutMode.value === 'expanded' && viewportWidth.value >= 900) {
    historySidebarOpen.value = !historySidebarOpen.value
    if (historySidebarOpen.value) loadHistory()
    return
  }
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
const layoutMode = ref('docked')
const historySidebarOpen = ref(true)
const viewportWidth = ref(window.innerWidth)
const panelWidth = ref(560)
const maxPanelWidth = computed(() => Math.min(900, viewportWidth.value - 640))
const effectivePanelWidth = computed(() =>
  Math.max(400, Math.min(panelWidth.value, maxPanelWidth.value))
)
const sideHistory = computed(
  () => layoutMode.value === 'expanded' && viewportWidth.value >= 900 && historySidebarOpen.value
)
const panelStyle = computed(() => ({
  '--panel-width': `${effectivePanelWidth.value}px`,
  ...(panelPosition.value
    ? { '--chat-left': `${panelPosition.value.x}px`, '--chat-top': `${panelPosition.value.y}px` }
    : {})
}))
const layoutActions = computed(() => [
  { label: '右侧面板', key: 'docked' },
  { label: '展开工作区', key: 'expanded' },
  { label: '悬浮窗口', key: 'floating' },
  { type: 'divider', key: 'divider' },
  { label: 'Mower 设置', key: 'settings' }
])
function selectLayout(key) {
  if (key === 'settings') return openSettings()
  if (!['docked', 'expanded', 'floating'].includes(key)) return
  layoutMode.value = key
  historyOpen.value = false
  if (key === 'expanded') {
    historySidebarOpen.value = true
    loadHistory()
  }
}
function resizeViewport() {
  viewportWidth.value = window.innerWidth
}
window.addEventListener('resize', resizeViewport)
let resizeOrigin = null
function startResize(event) {
  if (event.button !== 0 || resizeOrigin) return
  resizeOrigin = { id: event.pointerId, x: event.clientX, width: effectivePanelWidth.value }
  event.currentTarget.setPointerCapture(event.pointerId)
  event.preventDefault()
}
function moveResize(event) {
  if (!resizeOrigin || event.pointerId !== resizeOrigin.id) return
  panelWidth.value = Math.max(
    400,
    Math.min(maxPanelWidth.value, resizeOrigin.width + resizeOrigin.x - event.clientX)
  )
}
function endResize(event) {
  if (!resizeOrigin || event.pointerId !== resizeOrigin.id) return
  resizeOrigin = null
  if (event.currentTarget.hasPointerCapture(event.pointerId))
    event.currentTarget.releasePointerCapture(event.pointerId)
}
function resizeKey(event) {
  const delta = { ArrowLeft: 32, ArrowRight: -32, Home: -Infinity, End: Infinity }[event.key]
  if (delta === undefined) return
  event.preventDefault()
  panelWidth.value = Math.max(400, Math.min(maxPanelWidth.value, effectivePanelWidth.value + delta))
}
const unreadResult = ref(false)
const backgroundStatus = computed(() => {
  if (connectionLost.value) return '连接中断'
  if (loading.value) {
    const last = chatHistory.value.at(-1)
    return last?.events?.at(-1)?.status === 'awaiting_approval' ? '等待确认' : '执行中'
  }
  const last = chatHistory.value.at(-1)
  if (last?.status === 'cancelled') return '已停止'
  return last?.error || (last && isIncomplete(last)) ? '未完成' : '已完成'
})
watch(loading, (value, previous) => {
  if (previous && !value && !show.value) unreadResult.value = true
})
watch(
  () => props.show,
  (value) => {
    if (value) unreadResult.value = false
  }
)
let dragOrigin = null
function startDrag(event) {
  if (
    layoutMode.value !== 'floating' ||
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
const continuationTarget = computed(() => {
  const last = chatHistory.value.at(-1)
  return last?.turn_id && last.mode !== 'summary' && isIncomplete(last) ? last : null
})
const continueMode = computed(() => Boolean(continuationTarget.value) && !composeNewQuestion.value)
const composerActions = computed(() => [
  ...(continuationTarget.value
    ? [
        {
          label: continueMode.value ? '作为新提问' : '继续原任务',
          key: 'toggle-question',
          disabled: loading.value || historyBusy.value || remoteBusy.value
        }
      ]
    : []),
  {
    label: '整理摘要',
    key: 'summary',
    disabled: !conversationId.value || loading.value || historyBusy.value || remoteBusy.value
  },
  ...(summarySource.value
    ? [
        {
          label: '停用摘要',
          key: 'clear-summary',
          disabled: loading.value || historyBusy.value || remoteBusy.value
        }
      ]
    : [])
])
function selectComposerAction(key) {
  if (loading.value || historyBusy.value || remoteBusy.value) return
  if (key === 'toggle-question') composeNewQuestion.value = !composeNewQuestion.value
  else if (key === 'summary') requestSummary()
  else if (key === 'clear-summary') adoptSummary()
}
const contextHint = computed(() =>
  contextInfo.value?.continued_from
    ? `已带入原目标和保存的进度。${contextInfo.value.continuation_limited ? '部分记录已截断。' : ''}`
    : contextInfo.value?.limited
      ? `本轮使用 ${contextInfo.value.included_turns} 轮近期记录，部分历史未传给模型。`
      : '近期上下文最多 10 轮、24,000 字符。'
)
const canSend = computed(
  () =>
    (Boolean(userInput.value.trim()) || continueMode.value || draftAttachments.value.length > 0) &&
    !attachmentsBusy.value &&
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
function failReply(text, status = 'interrupted') {
  const restored = settleAttachments(false)
  if (restored && activeReply && !activeReply.turn_id) {
    chatHistory.value.splice(-2)
    activeReply = null
    notice.error(text)
  }
  if (activeReply) {
    if (!activeReply.content) activeReply.content = activeReply.draft || ''
    activeReply.draft = ''
    activeReply.content += `${activeReply.content ? '\n\n' : ''}${text}`
    activeReply.status = status
    activeReply.error = status !== 'cancelled'
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
  if (snapshot.turn_id) settleAttachments(true)
  activeReply.turn_id = snapshot.turn_id
  activeReply.status = snapshot.status
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
      activeReply.error = snapshot.status !== 'cancelled'
      activeReply.content += `\n\n${terminalNotice(snapshot.status, snapshot.failure || { message: snapshot.error }, snapshot.mode)}`
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
      settleAttachments(true)
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
      failReply(
        terminalNotice(data.status, { code: data.code, message: data.error }, activeReply.mode),
        data.status
      )
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
  if (continueMode.value) {
    resumeIncompleteTurn(
      continuationTarget.value,
      chatHistory.value.length - 1,
      ['', '继续', '继续处理'].includes(text) ? '' : text
    )
    if (loading.value) userInput.value = ''
    return
  }
  sendTurn(text || '请查看附件。')
}
function sendTurn(text, options = {}) {
  if (
    loading.value ||
    historyBusy.value ||
    !historyReady.value ||
    remoteBusy.value ||
    !assistantAllowed() ||
    attachmentsBusy.value
  )
    return
  const files = options.mode === 'summary' ? [] : [...draftAttachments.value]
  const asNewQuestion = composeNewQuestion.value
  composeNewQuestion.value = false
  requestOptions = {
    request_id: Array.from(crypto.getRandomValues(new Uint8Array(16)), (value) =>
      value.toString(16).padStart(2, '0')
    ).join(''),
    ...options,
    ...(files.length ? { attachment_ids: files.map((file) => file.id) } : {})
  }
  chatHistory.value.push({
    role: 'user',
    content: options.continue_of ? options.continue_instruction || '继续处理' : text,
    silent: Boolean(options.continue_of && !options.continue_instruction),
    attachments: files.map((file) => ({
      id: file.id,
      name: file.name,
      kind: file.kind,
      truncated: file.truncated
    }))
  })
  chatHistory.value.push({
    role: 'bot',
    content: '',
    draft: '',
    events: [],
    error: false,
    mode: options.mode || 'chat'
  })
  if (files.length) {
    pendingAttachments = { files, text: userInput.value, epoch: attachmentEpoch, asNewQuestion }
    draftAttachments.value = []
  }
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
  releaseAttachments()
  composeNewQuestion.value = false
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
function openFeedback() {
  if (!showFeedback) return
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
  window.removeEventListener('resize', resizeViewport)
  historyRequest++
  releaseAttachments()
  closeConnection()
})
</script>

<template>
  <section
    ref="panelRef"
    v-show="show"
    class="chatbot-container"
    :class="[`chatbot--${layoutMode}`, { 'side-history': sideHistory }]"
    :style="panelStyle"
    role="dialog"
    aria-label="Mower AI 助手"
    @dragenter="dragFiles"
    @dragover="dragFiles"
    @dragleave="leaveFiles"
    @drop="dropFiles"
  >
    <div
      v-if="layoutMode === 'docked' && viewportWidth >= 1200"
      class="panel-resizer"
      role="separator"
      aria-label="调整助手宽度"
      aria-orientation="vertical"
      :aria-valuenow="effectivePanelWidth"
      :aria-valuemin="400"
      :aria-valuemax="maxPanelWidth"
      tabindex="0"
      @pointerdown="startResize"
      @pointermove="moveResize"
      @pointerup="endResize"
      @pointercancel="endResize"
      @lostpointercapture="endResize"
      @keydown="resizeKey"
    />
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
          class="icon-button expand-button"
          :aria-label="layoutMode === 'expanded' ? '返回侧栏' : '展开工作区'"
          :title="layoutMode === 'expanded' ? '返回侧栏' : '展开工作区'"
          @click="selectLayout(layoutMode === 'expanded' ? 'docked' : 'expanded')"
        >
          <template #icon
            ><n-icon :component="layoutMode === 'expanded' ? ContractOutline : ExpandOutline"
          /></template>
        </n-button>
        <n-dropdown :options="layoutActions" trigger="click" @select="selectLayout">
          <n-button
            quaternary
            circle
            class="icon-button"
            aria-label="显示方式与设置"
            title="显示方式与设置"
          >
            <template #icon><n-icon :component="EllipsisHorizontal" /></template>
          </n-button>
        </n-dropdown>
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
    <div class="chatbot-body">
      <div v-show="historyOpen || sideHistory" class="conversation-browser">
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
      <div v-show="!historyOpen || sideHistory" class="chatbot-main">
        <div class="history-container">
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
                v-show="!msg.silent || msg.attachments?.length"
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
                <div v-if="msg.role === 'user' && msg.attachments?.length" class="sent-attachments">
                  <button
                    type="button"
                    @click="inspectAttachment(file)"
                    v-for="file in msg.attachments"
                    :key="file.id"
                    :title="file.truncated ? '仅包含末尾 6000 字符' : file.name"
                  >
                    <n-icon :component="Attach" />{{ file.name }}
                  </button>
                </div>
                <div v-if="msg.role === 'bot' && msg.events?.length" class="tool-events">
                  <details
                    v-for="event in msg.events"
                    :key="event.id"
                    :open="event.status === 'awaiting_approval' && loading && msg === activeReply"
                  >
                    <summary>
                      {{ event.label || event.name }} · {{ eventStatus(event, msg) }}
                    </summary>
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
                        :disabled="
                          controlBusy || stopping || connectionLost || Boolean(event.decision)
                        "
                        @click="sendControl('approve', event)"
                        >{{ event.decision === 'approve' ? '已提交确认' : '确认执行' }}</n-button
                      >
                      <n-button
                        size="small"
                        :disabled="
                          controlBusy || stopping || connectionLost || Boolean(event.decision)
                        "
                        @click="sendControl('reject', event)"
                        >不执行</n-button
                      >
                    </template>
                  </details>
                </div>
                <div v-if="msg.role === 'user' && !msg.silent" class="message-content user-content">
                  {{ msg.content }}
                </div>
                <div v-else-if="msg.role === 'bot'" class="message-content assistant-content">
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
                    msg.role === 'bot' &&
                    msg.content &&
                    !(loading && idx === chatHistory.length - 1)
                  "
                  class="message-actions"
                >
                  <n-button quaternary class="reply-action" @click="copyMessage(msg)"
                    ><template #icon><n-icon :component="CopyOutline" /></template>复制</n-button
                  >
                  <n-button
                    v-if="
                      isIncomplete(msg) &&
                      msg.mode === 'summary' &&
                      msg.turn_id &&
                      idx === chatHistory.length - 1
                    "
                    quaternary
                    class="reply-action"
                    :disabled="loading || historyBusy || remoteBusy"
                    @click="resumeIncompleteTurn(msg, idx)"
                    >重新生成摘要</n-button
                  >
                  <n-popconfirm
                    v-if="!isIncomplete(msg) && msg.mode === 'summary'"
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
                  <n-button
                    v-if="!isIncomplete(msg) && feedbackAvailable"
                    quaternary
                    class="reply-action"
                    @click="openFeedback"
                    >打开反馈</n-button
                  >
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
          <input ref="fileInputRef" class="file-picker" type="file" multiple @change="pickFiles" />
          <div class="composer" :class="{ 'file-dragging': fileDragDepth > 0 }">
            <div v-if="draftAttachments.length" class="attachment-list">
              <div
                v-for="file in draftAttachments"
                :key="file.id"
                class="attachment-chip"
                :title="file.truncated ? `${file.name}：仅发送文字摘录，内容有省略` : file.name"
              >
                <button
                  type="button"
                  class="attachment-preview-trigger"
                  @click="inspectAttachment(file)"
                >
                  <img v-if="file.preview" :src="file.preview" :alt="file.name" />
                  <n-icon v-else :component="DocumentTextOutline" />
                  <span>{{ file.name }}</span>
                </button>
                <n-button
                  quaternary
                  circle
                  size="tiny"
                  :aria-label="`移除 ${file.name}`"
                  :title="`移除 ${file.name}`"
                  @click="removeAttachment(file)"
                  ><template #icon><n-icon :component="CloseOutline" /></template
                ></n-button>
              </div>
            </div>
            <n-input
              ref="inputRef"
              v-model:value="userInput"
              type="textarea"
              :bordered="false"
              :autosize="{ minRows: 2, maxRows: 6 }"
              :maxlength="4000"
              :placeholder="continueMode ? '补充要求…' : '发消息…'"
              :input-props="{ 'aria-label': '发送给 Mower AI 的问题' }"
              @keydown="onInputKeydown"
              @paste="pasteFiles"
            />
            <div class="composer-toolbar">
              <n-button
                quaternary
                circle
                aria-label="添加文件"
                title="添加文件"
                :loading="attachmentsBusy"
                :disabled="attachmentsBusy || loading"
                @click="fileInputRef?.click()"
                ><template #icon><n-icon :component="Attach" /></template
              ></n-button>
              <n-dropdown :options="composerActions" trigger="click" @select="selectComposerAction">
                <n-button quaternary circle aria-label="更多操作" title="更多操作">
                  <template #icon><n-icon :component="EllipsisHorizontal" /></template>
                </n-button>
              </n-dropdown>
              <n-icon
                v-if="contextInfo?.limited"
                :component="InformationCircleOutline"
                :title="contextHint"
                :aria-label="contextHint"
                class="context-info"
              />
              <span class="composer-spacer" />
              <span v-if="userInput.length > 3500" class="input-count"
                >{{ userInput.length }} / 4000</span
              >
              <n-button
                v-if="loading"
                circle
                class="send-button"
                :title="stopping ? '停止中' : '停止'"
                :aria-label="stopping ? '停止中' : '停止'"
                :loading="stopping"
                :disabled="!activeReply?.turn_id || controlBusy || stopping"
                @click="sendControl('stop')"
                ><template #icon><n-icon :component="Stop" /></template
              ></n-button>
              <n-button
                v-else
                type="primary"
                circle
                class="send-button"
                :title="continueMode ? '继续处理' : '发送'"
                :aria-label="continueMode ? '继续处理' : '发送'"
                :disabled="!canSend"
                @click="sendMessage"
                ><template #icon
                  ><n-icon :component="continueMode ? Play : ArrowUpOutline" /></template
              ></n-button>
            </div>
          </div>
        </footer>
      </div>
    </div>
  </section>
  <button
    v-if="!show && mower.ai_assistant_enabled === true && (loading || unreadResult)"
    class="background-task"
    type="button"
    @click="show = true"
  >
    <n-icon :component="MowerAIIcon" />
    <span>Mower AI · {{ backgroundStatus }}</span>
  </button>
  <n-modal
    v-model:show="previewOpen"
    preset="card"
    :title="previewFile?.name || '附件'"
    class="attachment-preview"
    style="width: min(760px, calc(100vw - 32px))"
  >
    <p v-if="previewBusy" role="status">正在读取附件…</p>
    <div v-else-if="previewError" role="alert">
      {{ previewError }} <n-button @click="inspectAttachment(previewFile)">重试</n-button>
    </div>
    <template v-else-if="previewFile">
      <p v-if="previewFile.truncated">以下是实际发送的文字摘录，内容有省略。</p>
      <pre v-if="previewFile.kind === 'text'" class="attachment-text">{{
        previewFile.content
      }}</pre>
      <img
        v-else-if="previewFile.kind === 'image'"
        :src="previewFile.content"
        :alt="previewFile.name"
        class="attachment-image"
      />
      <p v-else>PDF 作为原文件交给模型读取；当前服务需要支持 PDF 输入。本地未提取文字。</p>
    </template>
  </n-modal>
</template>

<style scoped>
.attachment-preview-trigger,
.sent-attachments button {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
  min-height: 40px;
  border: 0;
  font: inherit;
  color: inherit;
  background: transparent;
  cursor: pointer;
}
.attachment-text {
  max-height: 65dvh;
  overflow: auto;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
.attachment-image {
  display: block;
  max-width: 100%;
  max-height: 65dvh;
  margin: auto;
  object-fit: contain;
}
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
.chatbot--docked {
  position: relative;
  inset: auto;
  flex: 0 0 var(--panel-width);
  width: var(--panel-width);
  height: 100%;
  border-radius: 0;
  border-width: 0 0 0 1px;
  box-shadow: none;
  overflow: visible;
}
.chatbot--expanded {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  border: 0;
  border-radius: 0;
}
.chatbot--floating {
  --chat-width: min(560px, calc(100vw - 32px));
  --chat-height: min(760px, calc(100dvh - 72px));
}
.chatbot--floating .chatbot-header {
  cursor: grab;
  touch-action: none;
}
.chatbot-body,
.chatbot-main {
  display: flex;
  flex: 1;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
}
.chatbot-main {
  flex-direction: column;
}
.side-history .conversation-browser {
  flex: 0 0 244px;
  box-sizing: border-box;
  border-right: 1px solid var(--mower-divider);
  background: var(--mower-body-bg, var(--mower-surface));
}
.chatbot--expanded .message-list,
.chatbot--expanded .chatbot-welcome,
.chatbot--expanded .chatbot-input-area {
  width: 100%;
  max-width: 900px;
  box-sizing: border-box;
  margin-inline: auto;
}
.panel-resizer {
  position: absolute;
  left: -5px;
  top: 0;
  bottom: 0;
  width: 10px;
  cursor: col-resize;
  touch-action: none;
  z-index: 1;
}
.panel-resizer:hover,
.panel-resizer:focus-visible {
  background: var(--mower-primary-block);
}
.background-task {
  position: fixed;
  right: 20px;
  bottom: max(72px, env(safe-area-inset-bottom));
  z-index: 2000;
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 44px;
  padding: 8px 16px;
  border: 1px solid var(--mower-border);
  border-radius: 24px;
  background: var(--mower-surface);
  color: var(--mower-text);
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.12);
  cursor: pointer;
}
@media (max-width: 1199px) {
  .chatbot--docked {
    position: absolute;
    inset: 0 0 0 auto;
    width: min(560px, 100%);
  }
}
.chatbot-header {
  display: flex;
  align-items: center;
  flex-shrink: 0;
  gap: 12px;
  padding: 10px 14px;
  border-bottom: 1px solid var(--mower-divider);
  cursor: default;
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
.file-picker {
  display: none;
}
.attachment-list {
  display: flex;
  gap: 6px;
  overflow-x: auto;
  padding: 5px;
}
.attachment-chip {
  display: flex;
  align-items: center;
  gap: 6px;
  flex: 0 0 auto;
  max-width: 200px;
  padding: 4px 6px;
  border: 1px solid var(--mower-border);
  border-radius: 9px;
  color: var(--mower-text);
  font-size: 12px;
}
.attachment-preview-trigger > span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.attachment-chip img {
  width: 32px;
  height: 32px;
  object-fit: cover;
  border-radius: 5px;
}
.sent-attachments {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  max-width: 100%;
}
.sent-attachments > button {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  max-width: 100%;
  overflow-wrap: anywhere;
  font-size: 12px;
  color: var(--mower-text-muted);
}
.composer.file-dragging {
  border-style: dashed;
  border-color: var(--mower-primary);
  background: var(--mower-primary-block);
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
.composer-spacer {
  flex: 1;
}
.context-info {
  color: var(--mower-text-muted);
}
.input-count {
  font-size: 11px;
  font-variant-numeric: tabular-nums;
  color: var(--mower-text-muted);
}
.send-button {
  transition: transform 0.15s;
}
@media (max-width: 640px) {
  .chatbot-container {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    border: 0;
    border-radius: 0;
  }
  .expand-button {
    display: none;
  }
  .chatbot-header {
    gap: 8px;
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
  .composer-toolbar {
    padding-left: 4px;
  }
}
@media (max-width: 360px) {
  .assistant-mark {
    display: none;
  }
  .icon-button {
    width: 40px;
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
