import { readFileSync } from 'node:fs'
import { parse } from '@vue/compiler-sfc'
import { afterEach, expect, it, vi } from 'vitest'
import { compile, createRenderer, h, nextTick, ref, ssrContextKey } from 'vue'
import ResourceActivityTimes from './ResourceActivityTimes.vue'

const { descriptor } = parse(
  readFileSync(new URL('./ResourceActivityTimes.vue', import.meta.url), 'utf8')
)
const ClientTimes = {
  ...ResourceActivityTimes,
  ssrRender: undefined,
  render: compile(descriptor.template.content),
  setup: (props, context) => ({ ...ResourceActivityTimes.setup(props, context) })
}
const renderer = createRenderer({
  createElement: (tag) => ({ tag, children: [] }),
  createText: (text) => ({ text }),
  createComment: () => ({ text: '' }),
  setText: (node, text) => {
    node.text = text
  },
  setElementText: (node, text) => {
    node.text = text
    node.children = []
  },
  patchProp: () => {},
  parentNode: (node) => node.parent,
  nextSibling: () => null,
  insert(node, parent, anchor) {
    node.parent = parent
    const index = parent.children.indexOf(anchor)
    parent.children.splice(index < 0 ? parent.children.length : index, 0, node)
  },
  remove(node) {
    const index = node.parent.children.indexOf(node)
    if (index >= 0) node.parent.children.splice(index, 1)
  }
})
const text = (node) => [node.text || '', ...(node.children || []).map(text)].join(' ')
let app
afterEach(() => {
  app?.unmount()
  app = null
  vi.useRealTimers()
})

it('renders all battle deadlines and removes ended activities as time advances or resources change', async () => {
  vi.useFakeTimers()
  vi.setSystemTime(new Date('2026-11-13T12:00:00+08:00'))
  const now = Date.now() / 1000
  const metadata = ref({
    activities: [
      { name: '较早活动', time: now - 86400, endTime: now + 120 },
      { name: '最新活动', time: now - 3600, endTime: now + 60 },
      { name: '仅商店开放', time: now - 86400, endTime: now }
    ]
  })
  const root = { children: [] }
  app = renderer.createApp({ render: () => h(ClientTimes, { metadata: metadata.value }) })
  app.provide(ssrContextKey, {})
  app.mount(root)
  expect(text(root)).toContain('较早活动')
  expect(text(root)).toContain('最新活动')
  expect(text(root)).toContain('作战关闭：2026/11/13 12:01（北京时间）')
  expect(text(root)).not.toContain('仅商店开放')
  vi.advanceTimersByTime(60000)
  await nextTick()
  expect(text(root)).not.toContain('最新活动')
  expect(text(root)).toContain('较早活动')
  vi.advanceTimersByTime(60000)
  await nextTick()
  expect(text(root)).not.toContain('较早活动')
  expect(vi.getTimerCount()).toBe(0)
  metadata.value = { activities: [{ name: '更新后活动', time: now, endTime: now + 3600 }] }
  await nextTick()
  expect(text(root)).toContain('更新后活动')
  expect(vi.getTimerCount()).toBe(1)
  app.unmount()
  app = null
  expect(vi.getTimerCount()).toBe(0)
})
