import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { effectScope, nextTick, reactive, ref } from 'vue'
import ChatBot from './ChatBot.vue'

const state = vi.hoisted(() => ({
  feedback: null,
  cleanup: null,
  notice: null,
  push: null,
  mower: null,
  axios: null,
  dialog: null
}))
vi.mock('vue', async (original) => ({
  ...(await original()),
  useSSRContext: () => ({ modules: new Set() }),
  inject: (key) => (key === 'axios' ? state.axios : state.feedback),
  onBeforeUnmount: (callback) => (state.cleanup = callback)
}))
vi.mock('naive-ui', () => ({ useMessage: () => state.notice, useDialog: () => state.dialog }))
vi.mock('@/stores/mower', () => ({ useMowerStore: () => state.mower }))
vi.mock('vue-router', () => ({ useRouter: () => ({ push: state.push }) }))

class FakeSocket {
  static OPEN = 1
  static instances = []
  readyState = 0
  send = vi.fn()
  close = vi.fn(() => {
    this.readyState = 3
  })
  constructor(url) {
    this.url = url
    FakeSocket.instances.push(this)
  }
  open() {
    this.readyState = 1
    this.onopen()
  }
  receive(data) {
    this.onmessage({ data: JSON.stringify(data) })
  }
}

let scope
let component
let emit
let props
async function flush() {
  await nextTick()
  await nextTick()
}

beforeEach(async () => {
  state.feedback = ref(false)
  state.notice = { success: vi.fn(), error: vi.fn(), warning: vi.fn() }
  state.dialog = { warning: vi.fn() }
  state.mower = reactive({ ai_assistant_enabled: true })
  state.axios = {
    defaults: { headers: { common: { 'X-Mower-Config-Generation': 'page-generation' } } },
    get: vi.fn().mockResolvedValue({ data: { conversations: [] } }),
    delete: vi.fn().mockResolvedValue({ data: { ok: true } }),
    post: vi.fn().mockResolvedValue({ data: { ok: true } })
  }
  state.push = vi.fn()
  FakeSocket.instances = []
  vi.useFakeTimers()
  vi.stubGlobal('window', { location: { search: '?token=test-session' }, innerWidth: 1280 })
  vi.stubGlobal('WebSocket', FakeSocket)
  vi.stubGlobal('navigator', { clipboard: { writeText: vi.fn().mockResolvedValue() } })
  scope = effectScope()
  emit = vi.fn()
  props = reactive({ show: true })
  component = scope.run(() => ChatBot.setup(props, { expose: vi.fn(), emit }))
  await flush()
})
afterEach(() => {
  state.cleanup?.()
  scope.stop()
  vi.useRealTimers()
  vi.unstubAllGlobals()
  vi.unstubAllEnvs()
})
function send(text = '检查日志') {
  component.userInput.value = text
  component.sendMessage()
  return FakeSocket.instances.at(-1)
}

describe('AI chat interactions', () => {
  it.each([
    ['http://mower.example:18000', 'ws://mower.example:18000/ws/chat'],
    ['https://mower.example', 'wss://mower.example/ws/chat'],
    ['https://mower.example:8443', 'wss://mower.example:8443/ws/chat'],
    ['https://[2001:db8::1]:8443', 'wss://[2001:db8::1]:8443/ws/chat']
  ])('uses the public origin %s and sends credentials before the message', (origin, url) => {
    vi.stubEnv('DEV', false)
    vi.stubGlobal('location', { origin })
    window.location.search = '?token=test%2Bsecret%26value'
    const socket = send('hello')
    expect(socket.url).toBe(url)
    socket.open()
    expect(JSON.parse(socket.send.mock.calls[0][0])).toEqual({ token: 'test+secret&value' })
    expect(JSON.parse(socket.send.mock.calls[1][0])).toEqual({
      message: 'hello',
      conversation_id: null,
      request_id: expect.any(String),
      generation: 'page-generation'
    })
  })

  it.each(['/', '/mowersettings', '/mowersettings#mower-data'])(
    'closes the assistant before settings navigation from %s and keeps its conversation',
    async (path) => {
      const { createMemoryHistory, createRouter } = await vi.importActual('vue-router')
      const router = createRouter({
        history: createMemoryHistory(),
        routes: [
          { path: '/', component: {} },
          { path: '/mowersettings', component: {} }
        ]
      })
      await router.push(path)
      await router.isReady()
      const visibleDuringNavigation = []
      router.beforeEach(() => {
        visibleDuringNavigation.push(props.show)
      })
      state.push.mockImplementation((target) => router.push(target))
      emit.mockImplementation((event, visible) => {
        if (event === 'update:show') props.show = visible
      })
      const socket = send()
      socket.open()
      socket.receive({ reply: '保留正在回复的内容' })
      component.userInput.value = '保留未发送的草稿'

      component.openSettings()
      await state.push.mock.results.at(-1).value
      await flush()

      expect(props.show).toBe(false)
      expect(component.show.value).toBe(false)
      expect(visibleDuringNavigation.every((visible) => visible === false)).toBe(true)
      expect(router.currentRoute.value.path).toBe('/mowersettings')
      expect(component.userInput.value).toBe('保留未发送的草稿')
      expect(component.chatHistory.value.at(-1).content).toBe('保留正在回复的内容')
      expect(socket.close).not.toHaveBeenCalled()
      props.show = true
      await flush()
      expect(component.show.value).toBe(true)
    }
  )

  it('shows the refusal on lazy mount when authorization is already disabled', async () => {
    await flush()
    state.cleanup?.()
    scope.stop()
    state.mower.ai_assistant_enabled = false
    scope = effectScope()
    component = scope.run(() => ChatBot.setup({ show: true }, { expose: vi.fn(), emit }))
    expect(state.dialog.warning).toHaveBeenCalledOnce()
    expect(emit).toHaveBeenCalledWith('update:show', false)
    expect(FakeSocket.instances).toHaveLength(0)
  })

  it('keeps the entry usable but refuses disabled chat before opening a socket', async () => {
    state.mower.ai_assistant_enabled = false
    await flush()
    expect(state.dialog.warning).toHaveBeenCalledWith({
      title: '管理员未开启',
      content: '当前实例暂未开启该功能，请联系管理员。',
      positiveText: '知道了'
    })
    expect(emit).toHaveBeenCalledWith('update:show', false)
    component.userInput.value = '保留草稿'
    component.sendMessage()
    expect(FakeSocket.instances).toHaveLength(0)
    expect(component.chatHistory.value).toEqual([])
    expect(component.userInput.value).toBe('保留草稿')
  })

  it('does not establish chat while the server authorization snapshot is unknown', () => {
    state.mower.ai_assistant_enabled = null
    send()
    expect(FakeSocket.instances).toHaveLength(0)
    expect(component.chatHistory.value).toEqual([])
    expect(state.notice.warning).toHaveBeenCalledOnce()
    expect(state.dialog.warning).not.toHaveBeenCalled()
  })

  it('shows the administrator notice if a restarted backend refuses an existing authorization snapshot', () => {
    const socket = send()
    socket.open()
    socket.receive({
      code: 'ai_assistant_disabled',
      error: '当前实例暂未开启该功能，请联系管理员。'
    })
    expect(socket.close).toHaveBeenCalledOnce()
    expect(component.loading.value).toBe(false)
    expect(state.dialog.warning).toHaveBeenCalledOnce()
    expect(emit).toHaveBeenCalledWith('update:show', false)
  })

  it.each([
    ['connecting', true],
    ['streaming', true],
    ['connecting', false],
    ['streaming', false]
  ])(
    'ends a %s reply when authorization is disabled with panel visible=%s',
    async (phase, visible) => {
      const first = send()
      if (phase === 'streaming') {
        first.open()
        first.receive({ reply: '已收到的部分回复' })
      }
      const partial = component.chatHistory.value.at(-1)
      props.show = visible
      await flush()
      expect(component.loading.value).toBe(true)
      state.mower.ai_assistant_enabled = false
      await flush()
      expect(component.loading.value).toBe(false)
      expect(component.connecting.value).toBe(false)
      expect(vi.getTimerCount()).toBe(0)
      expect(first.close).toHaveBeenCalledOnce()
      expect(first.onclose).toBeNull()
      expect(first.onmessage).toBeNull()
      expect(partial.error).toBe(true)
      expect(partial.content).toContain('管理员未开启')
      if (phase === 'streaming') expect(partial.content).toContain('已收到的部分回复')
      expect(state.dialog.warning).toHaveBeenCalledTimes(visible ? 1 : 0)
      const retained = partial.content
      state.mower.ai_assistant_enabled = true
      props.show = true
      await flush()
      const second = send('恢复后重新查询')
      expect(second).not.toBe(first)
      expect(FakeSocket.instances).toHaveLength(2)
      second.open()
      second.receive({ reply: '新的回复' })
      second.receive({ done: true })
      expect(component.chatHistory.value.at(-1).content).toBe('新的回复')
      expect(partial.content).toBe(retained)
      component.newConversation()
      expect(component.chatHistory.value).toEqual([])
    }
  )

  it('drags by the header with pointer capture and stops after cancellation', () => {
    component.panelRef.value = { getBoundingClientRect: () => ({ left: 800, top: 300 }) }
    const handle = {
      setPointerCapture: vi.fn(),
      hasPointerCapture: vi.fn(() => true),
      releasePointerCapture: vi.fn()
    }
    const event = {
      button: 0,
      pointerId: 4,
      clientX: 830,
      clientY: 320,
      target: { closest: () => null },
      currentTarget: handle,
      preventDefault: vi.fn()
    }
    component.startDrag(event)
    expect(handle.setPointerCapture).toHaveBeenCalledWith(4)
    component.startDrag({ ...event, pointerId: 5 })
    expect(handle.setPointerCapture).toHaveBeenCalledTimes(1)
    component.moveDrag({ pointerId: 5, clientX: 300, clientY: 200 })
    expect(component.panelPosition.value).toBeNull()
    component.moveDrag({ pointerId: 4, clientX: 330, clientY: 220 })
    expect(component.panelStyle.value).toEqual({ '--chat-left': '300px', '--chat-top': '200px' })
    component.endDrag(event)
    expect(handle.releasePointerCapture).toHaveBeenCalledWith(4)
    expect(component.dragging.value).toBe(false)
    component.moveDrag({ pointerId: 4, clientX: 430, clientY: 320 })
    expect(component.panelPosition.value).toEqual({ x: 300, y: 200 })
    expect(component.chatHistory.value).toEqual([])
    expect(FakeSocket.instances).toHaveLength(0)
  })

  it('leaves header controls and the mobile panel free of dragging', () => {
    component.panelRef.value = { getBoundingClientRect: () => ({ left: 800, top: 300 }) }
    const event = {
      button: 0,
      pointerId: 1,
      target: { closest: () => ({}) },
      currentTarget: { setPointerCapture: vi.fn() },
      preventDefault: vi.fn()
    }
    component.startDrag(event)
    event.target.closest = () => null
    component.startDrag({ ...event, button: 2 })
    window.innerWidth = 390
    component.startDrag(event)
    expect(event.currentTarget.setPointerCapture).not.toHaveBeenCalled()
    expect(event.preventDefault).not.toHaveBeenCalled()
    expect(component.dragging.value).toBe(false)
  })

  it('fills suggestions without sending and waits for the whole streamed reply', () => {
    expect(component.chatHistory.value).toEqual([])
    component.useSuggestion(component.suggestions[0])
    expect(FakeSocket.instances).toHaveLength(0)
    expect(component.userInput.value).toBe(component.suggestions[0].description)
    const socket = send('  检查日志  ')
    socket.open()
    expect(socket.send.mock.calls.map(([data]) => JSON.parse(data))).toEqual([
      { token: 'test-session' },
      {
        message: '检查日志',
        conversation_id: null,
        request_id: expect.any(String),
        generation: 'page-generation'
      }
    ])
    socket.receive({ reply: '正在查询\n' })
    expect(component.loading.value).toBe(true)
    component.userInput.value = '下一条草稿'
    component.sendMessage()
    expect(socket.send).toHaveBeenCalledTimes(2)
    expect(component.userInput.value).toBe('下一条草稿')
    socket.receive({ reply: '查询完成' })
    socket.receive({ done: true })
    expect(component.loading.value).toBe(false)
    expect(component.chatHistory.value.at(-1).content).toBe('正在查询\n查询完成')
    component.sendMessage()
    expect(component.chatHistory.value).toHaveLength(4)
    expect(JSON.parse(socket.send.mock.calls.at(-1)[0])).toEqual({
      message: '下一条草稿',
      conversation_id: null,
      request_id: expect.any(String),
      generation: 'page-generation'
    })
  })

  it('does not send Chinese composition or Shift+Enter as a message', () => {
    component.userInput.value = '正在输入'
    const preventDefault = vi.fn()
    for (const event of [{ isComposing: true }, { keyCode: 229 }, { shiftKey: true }]) {
      component.onInputKeydown({ key: 'Enter', preventDefault, ...event })
    }
    expect(preventDefault).not.toHaveBeenCalled()
    expect(component.chatHistory.value).toEqual([])
    component.onInputKeydown({ key: 'Enter', preventDefault })
    expect(preventDefault).toHaveBeenCalledOnce()
    expect(component.chatHistory.value).toHaveLength(2)
  })

  it('reports missing credentials and connection timeouts without leaving a busy turn', () => {
    window.location.search = ''
    send()
    expect(FakeSocket.instances).toHaveLength(0)
    expect(component.loading.value).toBe(false)
    expect(component.chatHistory.value.at(-1).error).toBe(true)
    window.location.search = '?token=test-session'
    const socket = send()
    vi.advanceTimersByTime(20000)
    expect(socket.close).toHaveBeenCalledOnce()
    expect(component.chatHistory.value.at(-1).content).toContain('超时')
    expect(component.loading.value).toBe(false)
  })

  it('reconnects to the same request and replaces the partial snapshot without resending', () => {
    const first = send()
    first.open()
    const request = JSON.parse(first.send.mock.calls[1][0])
    first.receive({ conversation_id: 'saved', turn_id: 7 })
    first.receive({ reply: '已查询的内容' })
    first.onclose()
    const partial = component.chatHistory.value.at(-1)
    expect(partial.content).toBe('已查询的内容')
    expect(partial.error).toBe(false)
    expect(component.loading.value).toBe(true)
    expect(component.connectionLost.value).toBe(true)
    vi.advanceTimersByTime(1000)
    const second = FakeSocket.instances.at(-1)
    second.open()
    expect(JSON.parse(second.send.mock.calls[1][0])).toEqual({
      resume: true,
      conversation_id: 'saved',
      request_id: request.request_id,
      turn_id: 7,
      generation: 'page-generation'
    })
    second.receive({
      snapshot: {
        conversation_id: 'saved',
        turn_id: 7,
        assistant: '已查询的内容和后续结果',
        status: 'complete',
        events: []
      }
    })
    expect(component.chatHistory.value).toHaveLength(2)
    expect(partial.content).toBe('已查询的内容和后续结果')
    expect(component.loading.value).toBe(false)
    expect(component.connectionLost.value).toBe(false)
  })

  it('uses the request identity when the initial acknowledgement is lost', () => {
    const first = send()
    first.open()
    const request = JSON.parse(first.send.mock.calls[1][0])
    first.onclose()
    vi.advanceTimersByTime(1000)
    const second = FakeSocket.instances.at(-1)
    second.open()
    expect(JSON.parse(second.send.mock.calls[1][0])).toEqual({
      resume: true,
      conversation_id: null,
      request_id: request.request_id,
      generation: 'page-generation'
    })
    second.receive({
      snapshot: {
        conversation_id: 'accepted',
        turn_id: 8,
        assistant: '已保存的回答',
        status: 'complete'
      }
    })
    expect(component.conversationId.value).toBe('accepted')
    expect(component.chatHistory.value).toHaveLength(2)
  })

  it('retains interrupted results and trims history after a terminal snapshot', () => {
    const socket = send()
    socket.open()
    component.chatHistory.value.unshift(
      ...Array.from({ length: 200 }, (_, i) => ({
        role: i % 2 ? 'bot' : 'user',
        content: '历史'
      }))
    )
    socket.receive({
      snapshot: {
        conversation_id: 'saved',
        turn_id: 7,
        assistant: '已开始的操作结果',
        status: 'cancelled',
        error: '已停止后续调用'
      }
    })
    expect(component.chatHistory.value).toHaveLength(200)
    expect(component.chatHistory.value.at(-1).content).toContain('已开始的操作结果')
    expect(component.chatHistory.value.at(-1).error).toBe(true)
    expect(component.loading.value).toBe(false)
  })

  it('bounds automatic reconnection and cancels its timers on disposal', () => {
    const first = send()
    first.open()
    first.onerror()
    for (const delay of [1000, 2000, 4000]) {
      vi.advanceTimersByTime(delay)
      FakeSocket.instances.at(-1).onerror()
    }
    vi.advanceTimersByTime(60000)
    expect(FakeSocket.instances).toHaveLength(4)
    expect(component.loading.value).toBe(true)
    component.reconnectRun()
    expect(FakeSocket.instances).toHaveLength(5)
    state.cleanup()
    vi.advanceTimersByTime(60000)
    expect(FakeSocket.instances).toHaveLength(5)
  })

  it.each([{ error: '模型不可用' }, null, [], { done: true }])(
    'ends failed/empty replies for %j',
    (frame) => {
      const socket = send()
      socket.open()
      socket.receive(frame)
      expect(component.loading.value).toBe(false)
      expect(component.chatHistory.value.at(-1).error).toBe(true)
    }
  )

  it('keeps the draft and active request when hidden, and clears the session only when idle', () => {
    const socket = send()
    socket.open()
    component.userInput.value = '草稿'
    component.show.value = false
    expect(emit).toHaveBeenCalledWith('update:show', false)
    expect(socket.close).not.toHaveBeenCalled()
    component.newConversation()
    expect(component.chatHistory.value).toHaveLength(2)
    socket.receive({ reply: '已完成' })
    socket.receive({ done: true })
    component.newConversation()
    expect(socket.close).toHaveBeenCalledOnce()
    expect(socket.onmessage).toBeNull()
    expect(component.chatHistory.value).toEqual([])
    expect(component.userInput.value).toBe('')
  })

  it('does not pull the reader down while they inspect earlier messages', async () => {
    const socket = send()
    socket.open()
    const history = { scrollTop: 1000, scrollHeight: 1500, clientHeight: 500 }
    component.historyRef.value = history
    await flush()
    history.scrollTop = 0
    component.trackScroll()
    expect(component.atBottom.value).toBe(false)
    socket.receive({ reply: '新回复' })
    await flush()
    expect(history.scrollTop).toBe(0)
    component.scrollToLatest()
    expect(history.scrollTop).toBe(1500)
  })

  it('copies visible Markdown without conversation metadata and leaves HTML escaped', async () => {
    const content =
      '<script>alert(1)</script>\n**结果**<!--MOWER_MISS_STATE:{"flow":"missed_order"}-->'
    expect(component.renderMessage(content)).not.toContain('<script>')
    expect(component.renderMessage(content)).not.toContain('MOWER_MISS_STATE')
    await component.copyMessage({ content })
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith(
      '<script>alert(1)</script>\n**结果**'
    )
    navigator.clipboard.writeText.mockRejectedValueOnce(new Error('denied'))
    await component.copyMessage({ content: '回复' })
    expect(state.notice.error).toHaveBeenCalledOnce()
  })

  it('opens feedback even while its provided visibility starts false', () => {
    expect(component.feedbackAvailable).toBe(true)
    const message = { followUpState: null }
    component.openFeedbackFlow(message)
    expect(state.feedback.value).toBe(true)
    expect(message.followUpState).toBe('feedback')
    expect(emit).toHaveBeenCalledWith('update:show', false)
  })

  it('closes the socket and connection timer on component disposal', () => {
    const socket = send()
    state.cleanup()
    expect(socket.onclose).toBeNull()
    expect(socket.close).toHaveBeenCalledOnce()
    expect(vi.getTimerCount()).toBe(0)
  })
})

describe('persistent conversations', () => {
  const saved = {
    id: 'saved-conversation',
    busy: false,
    turns: [
      { user: '之前的问题', assistant: '完整回复<!--MOWER_MISS_STATE:{}-->', status: 'complete' }
    ]
  }
  function historyResponses() {
    state.axios.get.mockImplementation(async (url) => ({
      data: url.endsWith('/saved-conversation')
        ? saved
        : { conversations: [{ id: saved.id, title: '之前的问题', updated: 1 }] }
    }))
  }
  it('restores the latest conversation on remount without creating a socket', async () => {
    state.cleanup()
    scope.stop()
    historyResponses()
    scope = effectScope()
    component = scope.run(() => ChatBot.setup(props, { expose: vi.fn(), emit }))
    await flush()
    expect(component.conversationId.value).toBe(saved.id)
    expect(component.chatHistory.value[1].content).toBe(saved.turns[0].assistant)
    expect(component.renderMessage(component.chatHistory.value[1].content)).not.toContain(
      'MOWER_MISS_STATE'
    )
    expect(FakeSocket.instances).toHaveLength(0)
    const socket = send('继续')
    socket.open()
    expect(JSON.parse(socket.send.mock.calls[1][0]).conversation_id).toBe(saved.id)
  })
  it('uses the acknowledged conversation after reconnect and preserves it when starting a new one', () => {
    const socket = send()
    socket.open()
    socket.receive({ conversation_id: 'persisted' })
    socket.receive({ reply: 'answer', done: true })
    socket.onclose()
    const next = send('继续')
    next.open()
    expect(JSON.parse(next.send.mock.calls[1][0]).conversation_id).toBe('persisted')
    next.receive({ reply: 'next', done: true })
    component.newConversation()
    expect(component.conversationId.value).toBeNull()
    expect(component.chatHistory.value).toEqual([])
    expect(state.axios.delete).not.toHaveBeenCalled()
  })
  it('deletes selected history and clears only through the history endpoint', async () => {
    historyResponses()
    await component.selectConversation(saved.id)
    await component.deleteConversation(saved.id)
    expect(state.axios.delete).toHaveBeenCalledWith(
      expect.stringContaining('/ai/conversations/saved-conversation')
    )
    expect(component.conversationId.value).toBeNull()
    await component.deleteConversation()
    expect(state.axios.delete).toHaveBeenLastCalledWith(
      expect.stringMatching(/\/ai\/conversations$/)
    )
    expect(component.conversations.value).toEqual([])
  })
  it('retains history on deletion failure and refuses to mutate during a reply', async () => {
    historyResponses()
    await component.selectConversation(saved.id)
    state.axios.delete.mockRejectedValue({ response: { data: { error: '会话正在回复' } } })
    await component.deleteConversation(saved.id)
    expect(component.historyError.value).toBe('会话正在回复')
    expect(component.conversationId.value).toBe(saved.id)
    state.axios.delete.mockClear()
    send()
    await component.deleteConversation(saved.id)
    expect(state.axios.delete).not.toHaveBeenCalled()
    expect(component.conversationId.value).toBe(saved.id)
  })
  it('blocks sending after an initial read failure until retry succeeds', async () => {
    component.historyReady.value = false
    state.axios.get.mockRejectedValue(new Error('offline'))
    await component.loadHistory({ restore: true })
    component.userInput.value = 'hello'
    expect(component.canSend.value).toBe(false)
    expect(component.historyError.value).toBeTruthy()
    state.axios.get.mockResolvedValue({ data: { conversations: [] } })
    await component.loadHistory({ restore: true })
    expect(component.canSend.value).toBe(true)
  })
  it('ignores an old generation or disposed history response', async () => {
    let resolve
    state.axios.get.mockReturnValue(
      new Promise((done) => {
        resolve = done
      })
    )
    const pending = component.loadHistory({ restore: true })
    state.axios.defaults.headers.common['X-Mower-Config-Generation'] = 'new-generation'
    resolve({ data: { conversations: [{ id: 'old', title: 'old' }] } })
    await pending
    expect(component.conversations.value).toEqual([])
    expect(component.chatHistory.value).toEqual([])
    state.axios.get.mockReturnValue(
      new Promise((done) => {
        resolve = done
      })
    )
    const disposed = component.loadHistory({ restore: true })
    state.cleanup()
    resolve({ data: { conversations: [{ id: 'old', title: 'old' }] } })
    await disposed
    expect(component.conversations.value).toEqual([])
  })
  it('attaches to an active history turn and restores confirmation after a reload', async () => {
    state.axios.get.mockResolvedValueOnce({ data: { conversations: [] } }).mockResolvedValueOnce({
      data: {
        ...saved,
        busy: true,
        turns: [{ id: 7, user: '执行', assistant: '部分', status: 'interrupted' }]
      }
    })
    await component.selectConversation(saved.id)
    const reply = component.chatHistory.value[1]
    expect(reply.error).toBe(false)
    expect(reply.content).toBe('部分')
    expect(component.loading.value).toBe(true)
    const socket = FakeSocket.instances.at(-1)
    socket.open()
    expect(JSON.parse(socket.send.mock.calls[1][0])).toEqual({
      resume: true,
      conversation_id: saved.id,
      turn_id: 7,
      generation: 'page-generation'
    })
    const event = {
      id: 'T7-1',
      type: 'approval',
      status: 'awaiting_approval',
      approval_id: 'original-nonce',
      digest: 'original-digest',
      expires_at: 1800000000
    }
    await component.sendControl('approve', event)
    expect(state.axios.post).not.toHaveBeenCalled()
    socket.receive({
      snapshot: {
        conversation_id: saved.id,
        turn_id: 7,
        assistant: '',
        draft: '',
        events: [event],
        status: 'running'
      }
    })
    expect(component.eventStatus(reply.events[0], reply)).toBe('待确认')
    expect(reply.events[0].expires_at).toBe(1800000000)
    await component.sendControl('approve', reply.events[0])
    await component.sendControl('approve', reply.events[0])
    expect(state.axios.post).toHaveBeenCalledExactlyOnceWith(
      `/ai/conversations/${saved.id}/turns/7/control`,
      { action: 'approve', approval_id: 'original-nonce', digest: 'original-digest' }
    )
    socket.receive({
      snapshot: {
        conversation_id: saved.id,
        turn_id: 7,
        assistant: '已完成',
        events: [],
        status: 'complete'
      }
    })
    expect(component.loading.value).toBe(false)
    expect(component.remoteBusy.value).toBe(false)
  })
})

it('bounds live messages independently of stored history', () => {
  component.chatHistory.value = Array.from({ length: 200 }, (_, index) => ({
    role: index % 2 ? 'bot' : 'user',
    content: 'older'
  }))
  const socket = send('newest question')
  socket.open()
  socket.receive({ reply: 'newest reply', done: true })
  expect(component.chatHistory.value).toHaveLength(200)
  expect(component.chatHistory.value.at(-1).content).toBe('newest reply')
})

describe('retained execution controls', () => {
  function begin(mode = 'chat') {
    const socket = send()
    socket.open()
    socket.receive({
      conversation_id: 'conversation',
      turn_id: 7,
      mode,
      context: { limited: true, included_turns: 2 }
    })
    return socket
  }
  function approval(socket) {
    const event = {
      type: 'approval',
      id: 'T7-1',
      turn_id: 7,
      name: 'set_route',
      status: 'awaiting_approval',
      approval_id: 'nonce',
      digest: 'digest',
      preview: { before: [], after: [{ name: 'test' }] }
    }
    socket.receive({ event })
    return event
  }
  it('keeps tool evidence separate from speculative drafts and final answers', () => {
    const socket = begin()
    socket.receive({ event: { type: 'answer_delta', turn_id: 7, text: '正在检查' } })
    const reply = component.chatHistory.value.at(-1)
    expect(reply.content).toBe('')
    expect(reply.draft).toBe('正在检查')
    socket.receive({ event: { type: 'answer_reset', turn_id: 7 } })
    const event = approval(socket)
    socket.receive({ event: { ...event, type: 'tool', status: 'verified', result: '保存成功' } })
    socket.receive({ reply: '路线已保存 [证据 T7-1]', done: true })
    expect(reply.draft).toBe('')
    expect(reply.content).toBe('路线已保存 [证据 T7-1]')
    expect(reply.events).toHaveLength(1)
    expect(reply.events[0].status).toBe('verified')
    expect(component.contextInfo.value).toEqual({ limited: true, included_turns: 2 })
  })
  it.each(['approve', 'reject'])(
    'sends only server-held confirmation identity for %s',
    async (action) => {
      const socket = begin()
      const event = approval(socket)
      await component.sendControl(action, event)
      expect(state.axios.post).toHaveBeenCalledWith(
        '/ai/conversations/conversation/turns/7/control',
        { action, approval_id: 'nonce', digest: 'digest' }
      )
      expect(component.loading.value).toBe(true)
      expect(socket.close).not.toHaveBeenCalled()
    }
  )
  it('waits for backend completion after stop and does not claim to undo a started write', async () => {
    const socket = begin()
    await component.sendControl('stop')
    expect(component.stopping.value).toBe(true)
    expect(component.loading.value).toBe(true)
    expect(state.axios.post).toHaveBeenCalledWith(
      '/ai/conversations/conversation/turns/7/control',
      { action: 'stop' }
    )
    socket.receive({ event: { type: 'tool', turn_id: 7, id: 'T7-1', status: 'accepted' } })
    socket.receive({ error: '已停止后续调用' })
    expect(component.loading.value).toBe(false)
    expect(component.chatHistory.value.at(-1).events[0].status).toBe('accepted')
  })
  it('keeps controls available when their HTTP request fails', async () => {
    const socket = begin()
    state.axios.post.mockRejectedValueOnce(new Error('offline'))
    await component.sendControl('stop')
    expect(component.stopping.value).toBe(false)
    expect(component.controlBusy.value).toBe(false)
    expect(component.loading.value).toBe(true)
    expect(state.notice.error).toHaveBeenCalledOnce()
    expect(socket.close).not.toHaveBeenCalled()
  })
  it('marks restored approvals expired and refuses to send a control outside a live turn', async () => {
    component.restoreConversation({
      id: 'conversation',
      turns: [
        {
          id: 7,
          user: '请求',
          assistant: '',
          status: 'interrupted',
          events: [{ status: 'awaiting_approval' }, { status: 'running' }]
        }
      ]
    })
    const reply = component.chatHistory.value.at(-1)
    expect(component.eventStatus(reply.events[0], reply)).toBe('未执行（确认已失效）')
    expect(component.eventStatus(reply.events[1], reply)).toBe('结果待核实')
    await component.sendControl('approve', reply.events[0])
    expect(state.axios.post).not.toHaveBeenCalled()
  })
  it('continues the last interrupted turn with a fresh request ID and retained turn identity', () => {
    const socket = begin()
    const first = JSON.parse(socket.send.mock.calls[1][0])
    socket.receive({ error: '断线' })
    component.resumeIncompleteTurn(component.chatHistory.value.at(-1), 1)
    const next = FakeSocket.instances.at(-1)
    next.open()
    const retry = JSON.parse(next.send.mock.calls[1][0])
    expect(retry.continue_of).toBe(7)
    expect(retry.request_id).not.toBe(first.request_id)
    expect(retry.conversation_id).toBe('conversation')
    expect(retry.message).toBe(first.message)
  })
  it('preserves the unsent draft and blocks double continuation clicks', () => {
    const socket = begin()
    socket.receive({ error: '已停止' })
    component.userInput.value = '另一个问题草稿'
    const stopped = component.chatHistory.value.at(-1)
    component.resumeIncompleteTurn(stopped, 1)
    component.resumeIncompleteTurn(stopped, 1)
    expect(component.userInput.value).toBe('另一个问题草稿')
    expect(component.chatHistory.value).toHaveLength(4)
    expect(component.chatHistory.value[2].content).toBe('继续处理')
  })
  it.each(['继续', '继续处理'])(
    'maps typed %s to continuation after restoring a stopped turn',
    (text) => {
      component.restoreConversation({
        id: 'conversation',
        turns: [
          { id: 9, user: '原始目标', assistant: '已有进度', status: 'cancelled', continued_from: 7 }
        ]
      })
      expect(component.chatHistory.value[0].content).toBe('继续处理')
      const socket = send(text)
      socket.open()
      const request = JSON.parse(socket.send.mock.calls[1][0])
      expect(request.continue_of).toBe(9)
      expect(component.userInput.value).toBe('')
    }
  )
  it('regenerates an interrupted summary without task continuation', () => {
    const socket = begin('summary')
    socket.receive({ error: '摘要生成中断' })
    component.resumeIncompleteTurn(component.chatHistory.value.at(-1), 1)
    const next = FakeSocket.instances.at(-1)
    next.open()
    const request = JSON.parse(next.send.mock.calls[1][0])
    expect(request.retry_of).toBe(7)
    expect(request.continue_of).toBeUndefined()
    expect(request.mode).toBe('summary')
  })
  it('does not adopt generated summaries until explicitly selected and supports clearing them', async () => {
    const socket = begin('summary')
    socket.receive({ reply: '摘要草稿', done: true })
    expect(state.axios.post).not.toHaveBeenCalled()
    expect(component.summarySource.value).toBe(0)
    await component.adoptSummary(component.chatHistory.value.at(-1))
    expect(state.axios.post).toHaveBeenLastCalledWith('/ai/conversations/conversation/summary', {
      turn_id: 7
    })
    expect(component.summarySource.value).toBe(7)
    await component.adoptSummary()
    expect(state.axios.post).toHaveBeenLastCalledWith('/ai/conversations/conversation/summary', {
      turn_id: null
    })
    expect(component.summarySource.value).toBe(0)
  })
  it('requests summary generation without sending the unsent draft', () => {
    const socket = begin()
    socket.receive({ reply: '回答', done: true })
    component.userInput.value = '保留草稿'
    component.requestSummary()
    const frame = JSON.parse(socket.send.mock.calls.at(-1)[0])
    expect(frame.mode).toBe('summary')
    expect(frame.message).not.toBe('保留草稿')
    expect(component.userInput.value).toBe('保留草稿')
  })
})
