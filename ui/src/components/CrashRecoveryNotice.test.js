import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { readFileSync } from 'node:fs'
import * as Vue from 'vue'
import { compile } from '@vue/compiler-dom'
import { compileScript, parse } from '@vue/compiler-sfc'
import CrashRecoveryNotice from './CrashRecoveryNotice.vue'
import StatusNotification from './StatusNotification.vue'

const state = vi.hoisted(() => ({ create: vi.fn() }))
vi.mock('vue', async (original) => ({
  ...(await original()),
  useSSRContext: () => ({ modules: new Set() })
}))
vi.mock('naive-ui', async (original) => ({
  ...(await original()),
  useNotification: () => ({ create: state.create })
}))

const { descriptor } = parse(
  readFileSync(new URL('./CrashRecoveryNotice.vue', import.meta.url), 'utf8')
)
const { bindings } = compileScript(descriptor, { id: 'crash-recovery-notice-test' })
const { code } = compile(descriptor.template.content, {
  mode: 'function',
  prefixIdentifiers: true,
  bindingMetadata: bindings
})
CrashRecoveryNotice.render = new Function('Vue', code)(Vue)
StatusNotification.render = () => null

function element(type, text = '') {
  return { type, text, children: [], parent: null }
}
const renderer = Vue.createRenderer({
  createElement: element,
  createText: (text) => element('text', text),
  createComment: (text) => element('comment', text),
  setText: (node, text) => (node.text = text),
  setElementText: (node, text) => (node.text = text),
  patchProp() {},
  parentNode: (node) => node.parent,
  nextSibling: (node) => node.parent?.children[node.parent.children.indexOf(node) + 1] || null,
  insert(node, parent, anchor = null) {
    if (node.parent) node.parent.children.splice(node.parent.children.indexOf(node), 1)
    node.parent = parent
    const index = anchor ? parent.children.indexOf(anchor) : -1
    if (index < 0) parent.children.push(node)
    else parent.children.splice(index, 0, node)
  },
  remove(node) {
    node.parent?.children.splice(node.parent.children.indexOf(node), 1)
    node.parent = null
  }
})

function children(value) {
  if (Array.isArray(value)) return value
  if (value?.children?.default) return value.children.default()
  return Array.isArray(value?.children) ? value.children : []
}
function contents(value) {
  if (typeof value === 'string') return value
  if (value?.text) return value.text
  if (typeof value?.children === 'string') return value.children
  return children(value).map(contents).join('')
}
function findButton(value) {
  if (value?.props?.onClick) return value
  return children(value).map(findButton).find(Boolean)
}
async function settle() {
  for (let turn = 0; turn < 5; turn++) {
    await Promise.resolve()
    await Vue.nextTick()
  }
}

let app
let client
let floating
let container
beforeEach(() => {
  vi.useFakeTimers()
  client = { get: vi.fn(), post: vi.fn() }
  floating = Vue.ref(true)
  state.create.mockReset().mockImplementation((options) => ({ ...options, destroy: vi.fn() }))
})
afterEach(() => {
  app?.unmount()
  app = undefined
  vi.useRealTimers()
})

async function mount() {
  app = renderer.createApp({
    setup() {
      Vue.provide('axios', client)
      return () => Vue.h(CrashRecoveryNotice, { floating: floating.value })
    }
  })
  for (const name of ['NAlert', 'NSpace', 'NText', 'NButton']) {
    app.component(name, {
      setup:
        (_, { slots }) =>
        () =>
          Vue.h('div', slots.default?.())
    })
  }
  container = element('root')
  app.mount(container)
  await settle()
}

it('shows active recovery once, updates its content and refreshes through the notification action', async () => {
  client.get.mockResolvedValueOnce({ data: { active: false } })
  await mount()
  expect(state.create).not.toHaveBeenCalled()

  client.get.mockResolvedValue({
    data: { active: true, automatic: true, phase: 'observing', message: '正在读取设备' }
  })
  await vi.advanceTimersByTimeAsync(15000)
  await settle()
  const entry = state.create.mock.results[0].value
  expect(entry.title).toBe('正在自动恢复')
  expect(contents(entry.content())).toContain('正在读取设备')

  client.get.mockResolvedValue({
    data: { active: true, automatic: true, phase: 'waiting', message: '等待重新读取驻员和心情' }
  })
  await vi.advanceTimersByTimeAsync(3000)
  await settle()
  expect(state.create).toHaveBeenCalledOnce()
  expect(contents(entry.content())).toContain('等待重新读取驻员和心情')
  expect(contents(entry.content())).not.toContain('正在读取设备')

  const calls = client.get.mock.calls.length
  await findButton(entry.action()).props.onClick()
  expect(client.get).toHaveBeenCalledTimes(calls + 1)
  expect(client.get.mock.calls.every(([url]) => url.endsWith('/crash-recovery/status'))).toBe(true)
  expect(client.post).not.toHaveBeenCalled()
})

it('retains recovery progress while disconnected and closes it after resolution', async () => {
  client.get.mockResolvedValueOnce({
    data: { active: true, automatic: true, phase: 'observing', message: '正在重新读取驻员' }
  })
  await mount()
  const entry = state.create.mock.results[0].value

  client.get.mockRejectedValueOnce(new Error('offline'))
  await vi.advanceTimersByTimeAsync(3000)
  await settle()
  expect(contents(entry.content())).toContain('正在重新读取驻员')
  expect(contents(entry.content())).toContain('服务暂时不可用，恢复状态稍后自动刷新')
  expect(entry.destroy).not.toHaveBeenCalled()
  expect(state.create).toHaveBeenCalledOnce()

  client.get.mockResolvedValue({ data: { active: false, phase: 'resolved' } })
  await vi.advanceTimersByTimeAsync(3000)
  await settle()
  expect(entry.destroy).toHaveBeenCalledOnce()
  await vi.advanceTimersByTimeAsync(15000)
  await settle()
  expect(state.create).toHaveBeenCalledOnce()
  expect(client.post).not.toHaveBeenCalled()
})

it('reports a stopped recovery without starting tasks and cleans up polling on unmount', async () => {
  client.get.mockResolvedValue({
    data: { active: true, automatic: false, phase: 'stopped', message: '已停止自动恢复' }
  })
  await mount()
  const entry = state.create.mock.results[0].value
  expect(entry).toMatchObject({ type: 'warning', title: '自动恢复已停止' })
  expect(contents(entry.content())).toContain('任务已停止。需要继续时，可使用原有的开始按钮。')
  await findButton(entry.action()).props.onClick()
  expect(client.get.mock.calls.every(([url]) => url.endsWith('/crash-recovery/status'))).toBe(true)
  expect(client.post).not.toHaveBeenCalled()

  app.unmount()
  app = undefined
  const calls = client.get.mock.calls.length
  expect(entry.destroy).toHaveBeenCalledOnce()
  await vi.advanceTimersByTimeAsync(15000)
  expect(client.get).toHaveBeenCalledTimes(calls)
  expect(vi.getTimerCount()).toBe(0)
})

it('keeps inline recovery on other pages and changes presentation without restarting polling', async () => {
  floating.value = false
  client.get.mockResolvedValue({
    data: { active: true, automatic: true, phase: 'observing', message: '正在读取设备' }
  })
  await mount()
  expect(state.create).not.toHaveBeenCalled()
  expect(contents(container)).toContain('正在读取设备')

  floating.value = true
  await settle()
  expect(state.create).toHaveBeenCalledOnce()
  expect(contents(container)).not.toContain('正在读取设备')
  expect(client.get).toHaveBeenCalledOnce()

  floating.value = false
  await settle()
  expect(state.create.mock.results[0].value.destroy).toHaveBeenCalledOnce()
  expect(contents(container)).toContain('正在读取设备')
  expect(client.get).toHaveBeenCalledOnce()
  expect(client.post).not.toHaveBeenCalled()
})
