import { beforeEach, expect, it, vi } from 'vitest'
import { effectScope, reactive, nextTick } from 'vue'
import Component from './MaaManualCopilot.vue'

const { post, flush, error } = vi.hoisted(() => ({ post: vi.fn(), flush: vi.fn(), error: vi.fn() }))
vi.mock('vue', async (load) => ({
  ...(await load()),
  inject: () => ({ post }),
  useSSRContext: () => ({ modules: new Set() })
}))
vi.mock('naive-ui', () => ({ useMessage: () => ({ success: vi.fn(), error }) }))
vi.mock('@/stores/config', () => ({ useConfigStore: () => ({ flush_config_saves: flush }) }))
beforeEach(() => {
  vi.clearAllMocks()
  post.mockResolvedValue({ data: '添加任务成功！' })
})
const scripts = [
  { id: 'a', is_raid: false },
  { id: 'b', is_raid: true },
  { id: 'a', is_raid: true }
]
function setup() {
  return effectScope().run(() =>
    Component.setup({ scripts, selected: 'b', library: [] }, { expose: () => {} })
  )
}
it('submits checked entries in queue order, including the selected difficulties', async () => {
  const form = setup()
  form.chosen.value = [2, 0]
  await form.submit()
  expect(post.mock.calls[0][1].task.copilot).toEqual({
    mode: 'list',
    scripts: [scripts[0], scripts[2]]
  })
})
it('submits a single library file with the selected loop count and reports scheduler refusal', async () => {
  const form = setup()
  form.mode.value = 'single'
  form.times.value = 4
  post.mockResolvedValue({ data: '请确保Mower正在运行' })
  await form.submit()
  expect(post.mock.calls[0][1].task.copilot).toEqual({ mode: 'single', id: 'b', loop_times: 4 })
  expect(error).toHaveBeenCalledWith('请确保Mower正在运行')
})

it('preserves selection when a queue entry changes or moves', async () => {
  const props = reactive({
    scripts: scripts.map((item) => ({ ...item })),
    selected: 'b',
    library: []
  })
  const form = effectScope().run(() => Component.setup(props, { expose: () => {} }))
  form.chosen.value = [1]
  props.scripts[0].is_raid = true
  props.scripts.reverse()
  await nextTick()
  await form.submit()
  expect(post.mock.calls[0][1].task.copilot.scripts).toEqual([scripts[1]])
})
