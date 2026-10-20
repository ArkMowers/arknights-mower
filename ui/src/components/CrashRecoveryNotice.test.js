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

const { descriptor: appDescriptor } = parse(
  readFileSync(new URL('../App.vue', import.meta.url), 'utf8')
)
const { bindings: appBindings } = compileScript(appDescriptor, { id: 'recovery-app-test' })
const noticesStart = appDescriptor.template.content.indexOf('<ConfigSaveNotice')
const noticesEnd = appDescriptor.template.content.indexOf('<router-view', noticesStart)
const { code: noticesCode } = compile(
  appDescriptor.template.content.slice(noticesStart, noticesEnd),
  { mode: 'function', prefixIdentifiers: true, bindingMetadata: appBindings }
)
const renderNotices = new Function('Vue', noticesCode)(Vue)
const configNotice = { render: () => null }
const firstOccurrence = '2026-10-20T01:00:00+00:00'
const secondOccurrence = '2026-10-20T01:10:00+00:00'

function recoveryStatus(values = {}) {
  return {
    active: true,
    automatic: true,
    phase: 'observing',
    occurred_at: firstOccurrence,
    message: '正在读取设备',
    ...values
  }
}

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
let route
let container
beforeEach(() => {
  vi.useFakeTimers()
  client = { get: vi.fn(), post: vi.fn() }
  route = Vue.ref('log')
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
      return () =>
        renderNotices(
          { $route: { name: route.value } },
          [],
          {},
          {
            ConfigSaveNotice: configNotice,
            CrashRecoveryNotice,
            loaded: true,
            config_save_error: '',
            config_saving: false,
            config_store: { save_config: vi.fn() }
          }
        )
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
    data: recoveryStatus()
  })
  await vi.advanceTimersByTimeAsync(15000)
  await settle()
  const entry = state.create.mock.results[0].value
  expect(entry.title).toBe('正在自动恢复')
  expect(contents(entry.content())).toContain('正在读取设备')

  client.get.mockResolvedValue({
    data: recoveryStatus({ phase: 'waiting', message: '等待重新读取驻员和心情' })
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
    data: recoveryStatus({ message: '正在重新读取驻员' })
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

it('does not announce a stopped historical recovery when loading or remounting the page', async () => {
  client.get.mockResolvedValue({
    data: recoveryStatus({ automatic: false, phase: 'stopped', message: '已停止自动恢复' })
  })
  await mount()
  expect(state.create).not.toHaveBeenCalled()
  await vi.advanceTimersByTimeAsync(15000)
  await settle()
  expect(state.create).not.toHaveBeenCalled()

  app.unmount()
  app = undefined
  expect(vi.getTimerCount()).toBe(0)
  await mount()
  expect(state.create).not.toHaveBeenCalled()
  expect(client.post).not.toHaveBeenCalled()
})

it('announces a stop during observed recovery and keeps the closed stop dismissed', async () => {
  client.get.mockResolvedValue({ data: recoveryStatus() })
  await mount()
  const entry = state.create.mock.results[0].value

  client.get.mockResolvedValue({
    data: recoveryStatus({ automatic: false, phase: 'stopped', message: '已停止自动恢复' })
  })
  await vi.advanceTimersByTimeAsync(3000)
  await settle()
  expect(state.create).toHaveBeenCalledOnce()
  expect(entry).toMatchObject({ type: 'warning', title: '自动恢复已停止' })
  expect(contents(entry.content())).toContain('任务已停止。需要继续时，可使用原有的开始按钮。')
  entry.onClose()
  entry.onAfterLeave()

  await vi.advanceTimersByTimeAsync(15000)
  await settle()
  expect(state.create).toHaveBeenCalledOnce()
  expect(client.post).not.toHaveBeenCalled()
})

it('cleans up its notification and polling on unmount', async () => {
  client.get.mockResolvedValue({ data: recoveryStatus() })
  await mount()
  const entry = state.create.mock.results[0].value

  app.unmount()
  app = undefined
  const calls = client.get.mock.calls.length
  expect(entry.destroy).toHaveBeenCalledOnce()
  await vi.advanceTimersByTimeAsync(15000)
  expect(client.get).toHaveBeenCalledTimes(calls)
  expect(vi.getTimerCount()).toBe(0)
})

it('keeps a closed recovery dismissed across real App route changes without restarting polling', async () => {
  client.get.mockResolvedValue({ data: recoveryStatus() })
  await mount()
  const entry = state.create.mock.results[0].value
  entry.onClose()
  entry.onAfterLeave()

  for (const name of ['plan', 'mowersettings', 'record_line', 'log']) {
    route.value = name
    await settle()
    expect(contents(container)).not.toContain('正在读取设备')
    expect(client.get).toHaveBeenCalledOnce()
    expect(state.create).toHaveBeenCalledOnce()
  }

  await vi.advanceTimersByTimeAsync(3000)
  await settle()
  expect(state.create).toHaveBeenCalledOnce()
  expect(client.post).not.toHaveBeenCalled()
})

it('keeps the visible notification outside page content across settings navigation', async () => {
  client.get.mockResolvedValue({ data: recoveryStatus() })
  await mount()
  const entry = state.create.mock.results[0].value

  for (const name of ['mowersettings', 'log']) {
    route.value = name
    await settle()
    expect(contents(container)).not.toContain('正在读取设备')
    expect(state.create).toHaveBeenCalledOnce()
    expect(state.create.mock.results[0].value).toBe(entry)
    expect(entry.destroy).not.toHaveBeenCalled()
    expect(contents(entry.content())).toContain('正在读取设备')
    expect(client.get).toHaveBeenCalledOnce()
  }
  expect(client.post).not.toHaveBeenCalled()
})

it('shows refresh loading on the same notification and ignores repeated clicks while busy', async () => {
  client.get.mockResolvedValue({ data: recoveryStatus() })
  await mount()
  const entry = state.create.mock.results[0].value
  expect(findButton(entry.action()).props.loading).toBe(false)

  let finishRefresh
  client.get.mockReturnValueOnce(new Promise((resolve) => (finishRefresh = resolve)))
  const refreshing = findButton(entry.action()).props.onClick()
  await settle()
  expect(findButton(entry.action()).props.loading).toBe(true)
  expect(state.create).toHaveBeenCalledOnce()
  expect(entry.destroy).not.toHaveBeenCalled()
  expect(client.get).toHaveBeenCalledTimes(2)

  await findButton(entry.action()).props.onClick()
  expect(client.get).toHaveBeenCalledTimes(2)
  expect(findButton(entry.action()).props.loading).toBe(true)

  finishRefresh({ data: recoveryStatus({ message: '刷新完成' }) })
  await refreshing
  await settle()
  expect(findButton(entry.action()).props.loading).toBe(false)
  expect(contents(entry.content())).toContain('刷新完成')
  expect(state.create).toHaveBeenCalledOnce()
  expect(state.create.mock.results[0].value).toBe(entry)
  expect(entry.destroy).not.toHaveBeenCalled()
  expect(client.post).not.toHaveBeenCalled()
})

it('announces a new recovery after dismissal even when polling never observed an inactive state', async () => {
  client.get.mockResolvedValue({ data: recoveryStatus() })
  await mount()
  const first = state.create.mock.results[0].value
  first.onClose()
  first.onAfterLeave()

  client.get.mockResolvedValue({
    data: recoveryStatus({ occurred_at: secondOccurrence, message: '新的恢复事件' })
  })
  await vi.advanceTimersByTimeAsync(3000)
  await settle()
  expect(state.create).toHaveBeenCalledTimes(2)
  const second = state.create.mock.results[1].value
  expect(contents(second.content())).toContain('新的恢复事件')
  expect(second).not.toBe(first)
  expect(client.post).not.toHaveBeenCalled()
})

it.each([false, true])(
  'preserves the recovery notification while its event identity is unavailable (dismissed: %s)',
  async (dismissed) => {
    client.get.mockResolvedValue({ data: recoveryStatus() })
    await mount()
    const first = state.create.mock.results[0].value
    if (dismissed) {
      first.onClose()
      first.onAfterLeave()
    }

    client.get.mockResolvedValue({
      data: recoveryStatus({ occurred_at: undefined, message: '进程恢复记录暂时无法读取' })
    })
    await vi.advanceTimersByTimeAsync(3000)
    await settle()
    expect(state.create).toHaveBeenCalledOnce()
    expect(first.destroy).not.toHaveBeenCalled()

    client.get.mockResolvedValue({ data: recoveryStatus() })
    await vi.advanceTimersByTimeAsync(3000)
    await settle()
    expect(state.create).toHaveBeenCalledOnce()
    expect(first.destroy).not.toHaveBeenCalled()

    client.get.mockResolvedValue({ data: recoveryStatus({ occurred_at: secondOccurrence }) })
    await vi.advanceTimersByTimeAsync(3000)
    await settle()
    expect(state.create).toHaveBeenCalledTimes(2)
    expect(client.post).not.toHaveBeenCalled()
  }
)

it('keeps an initially unidentified recovery dismissed when its event identity becomes available', async () => {
  client.get.mockResolvedValue({ data: recoveryStatus({ occurred_at: undefined }) })
  await mount()
  const first = state.create.mock.results[0].value
  first.onClose()
  first.onAfterLeave()

  client.get.mockResolvedValue({ data: recoveryStatus() })
  await vi.advanceTimersByTimeAsync(3000)
  await settle()
  expect(state.create).toHaveBeenCalledOnce()

  client.get.mockResolvedValue({ data: recoveryStatus({ occurred_at: secondOccurrence }) })
  await vi.advanceTimersByTimeAsync(3000)
  await settle()
  expect(state.create).toHaveBeenCalledTimes(2)
  expect(client.post).not.toHaveBeenCalled()
})
