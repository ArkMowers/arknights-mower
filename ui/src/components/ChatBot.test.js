import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { effectScope, nextTick, ref } from 'vue'
import ChatBot from './ChatBot.vue'

const state = vi.hoisted(() => ({ feedback: null, cleanup: null, notice: null, push: null }))
vi.mock('vue', async (original) => ({
  ...(await original()),
  useSSRContext: () => ({ modules: new Set() }),
  inject: () => state.feedback,
  onBeforeUnmount: (callback) => (state.cleanup = callback)
}))
vi.mock('naive-ui', () => ({ useMessage: () => state.notice }))
vi.mock('vue-router', () => ({ useRouter: () => ({ push: state.push }) }))

class FakeSocket {
  static OPEN = 1
  static instances = []
  readyState = 0
  send = vi.fn()
  close = vi.fn(() => {
    this.readyState = 3
  })
  constructor() {
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
async function flush() {
  await nextTick()
  await nextTick()
}

beforeEach(() => {
  state.feedback = ref(false)
  state.notice = { success: vi.fn(), error: vi.fn() }
  state.push = vi.fn()
  FakeSocket.instances = []
  vi.useFakeTimers()
  vi.stubGlobal('window', { location: { search: '?token=test-session' }, innerWidth: 1280 })
  vi.stubGlobal('WebSocket', FakeSocket)
  vi.stubGlobal('navigator', { clipboard: { writeText: vi.fn().mockResolvedValue() } })
  scope = effectScope()
  emit = vi.fn()
  component = scope.run(() => ChatBot.setup({ show: true }, { expose: vi.fn(), emit }))
})
afterEach(() => {
  state.cleanup?.()
  scope.stop()
  vi.useRealTimers()
  vi.unstubAllGlobals()
})
function send(text = '检查日志') {
  component.userInput.value = text
  component.sendMessage()
  return FakeSocket.instances.at(-1)
}

describe('AI chat interactions', () => {
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
      { message: '检查日志' }
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
    expect(JSON.parse(socket.send.mock.calls.at(-1)[0])).toEqual({ message: '下一条草稿' })
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

  it('preserves a partial reply on disconnect and reconnects without overwriting it', () => {
    const first = send()
    first.open()
    first.receive({ reply: '已查询的内容' })
    first.onclose()
    const partial = component.chatHistory.value.at(-1)
    expect(partial.content).toContain('已查询的内容')
    expect(partial.content).toContain('连接已中断')
    expect(partial.error).toBe(true)
    const second = send('补充背景重新查询')
    expect(second).not.toBe(first)
    second.open()
    second.receive({ reply: '新的回复' })
    second.receive({ done: true })
    expect(partial.content).not.toContain('新的回复')
    expect(component.chatHistory.value.at(-1).content).toBe('新的回复')
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
