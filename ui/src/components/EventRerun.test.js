import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { effectScope, ref } from 'vue'
import Component from './EventRerun.vue'

const state = vi.hoisted(() => ({
  settings: null,
  client: null,
  mount: null,
  unmount: null,
  error: vi.fn()
}))
vi.mock('vue', async (original) => ({
  ...(await original()),
  inject: (key) => (key === 'axios' ? state.client : false),
  onMounted: (callback) => (state.mount = callback),
  onUnmounted: (callback) => (state.unmount = callback),
  useSSRContext: () => ({ modules: new Set() })
}))
vi.mock('pinia', () => ({ storeToRefs: (store) => store }))
vi.mock('naive-ui', async (original) => ({
  ...(await original()),
  useMessage: () => ({ error: state.error })
}))
vi.mock('@/stores/config', () => ({ useConfigStore: () => ({ event_rerun: state.settings }) }))
vi.mock('@/stores/resourceVersion', () => ({ useResourceVersionStore: () => ({ info: {} }) }))

const live = {
  event: {
    key: 'act46sre:100',
    name: '雪山降临1101',
    stages: [{ code: 'OS-1' }, { code: 'OS-10' }],
    raid: { code: 'OS-EX-8 突袭', script_stage_names: ['OS-EX-8', 'act46side_ex08'] }
  },
  stage_seconds: 240,
  progress: { 'OS-1': 'completed', 'OS-10': 'attempted' }
}
let scope
let panel

beforeEach(() => {
  vi.useFakeTimers()
  state.error.mockClear()
  state.settings = ref({
    event_key: 'act10sre:50',
    stages: ['OLD-1'],
    raid_enabled: true,
    script_id: 'old'
  })
  state.client = { get: vi.fn().mockResolvedValue({ data: live }), post: vi.fn() }
  scope = effectScope()
  panel = scope.run(() => Component.setup({}, { expose: () => {} }))
})

afterEach(() => {
  state.unmount?.()
  scope.stop()
  vi.useRealTimers()
})

it('scopes stage and script selection to the current opening and shows saved outcomes', async () => {
  await panel.refreshStatus()
  expect(state.client.get).toHaveBeenCalledWith(
    expect.stringMatching(/\/maa-long-task-status\?kind=event_rerun$/)
  )
  expect(state.settings.value.event_key).toBe('act10sre:50')
  expect(panel.selected.value.stages).toEqual([])
  expect(panel.statusLabel('OS-1')).toBe('已完成')
  expect(panel.statusLabel('OS-10')).toBe('已启动，结算待确认')

  panel.updateSettings({ stages: ['OS-1', 'OS-10'] })
  panel.updateSettings({ raid_enabled: true, script_id: 'raid' })
  expect(state.settings.value).toEqual({
    event_key: 'act46sre:100',
    use_sanity_potion: true,
    stages: ['OS-1', 'OS-10'],
    raid_enabled: true,
    script_id: 'raid'
  })
  expect(panel.expectedMinutes.value).toBe(12)
})

it('retains a disabled potion setting when the next event opens', async () => {
  await panel.refreshStatus()
  panel.updateSettings({ use_sanity_potion: false, stages: ['OS-1'] })
  panel.event.value = { ...live.event, key: 'act47sre:200' }
  expect(panel.selected.value.use_sanity_potion).toBe(false)
  expect(panel.selected.value.stages).toEqual([])
  panel.updateSettings({ raid_enabled: true })
  expect(state.settings.value.use_sanity_potion).toBe(false)
})

it('does not carry an import into a different activity', async () => {
  await panel.refreshStatus()
  panel.updateSettings({ raid_enabled: true })
  const script = { id: 'new', stage_name: 'OS-EX-8' }
  state.client.get.mockResolvedValueOnce({ data: { scripts: [script] } })
  state.client.post.mockResolvedValue({ data: script })
  const done = vi.fn()
  const upload = panel.upload({ file: { file: new Blob() }, onFinish: done, onError: vi.fn() })
  panel.event.value = { ...live.event, key: 'act47sre:200' }
  panel.updateSettings({ raid_enabled: true, script_id: 'next-opening' })
  await upload
  expect(done).toHaveBeenCalledOnce()
  expect(panel.selected.value.script_id).toBe('next-opening')
})

it('offers matching EX-8 scripts from the ordinary Copilot library', async () => {
  await panel.refreshStatus()
  state.client.get.mockResolvedValueOnce({
    data: {
      scripts: [
        { id: 'raid', stage_name: 'act46side_ex08', title: '突袭作业' },
        { id: 'other', stage_name: 'OS-EX-7', title: '其他关卡' }
      ]
    }
  })
  await panel.refreshScripts()
  expect(panel.options.value).toEqual([{ label: 'act46side_ex08 · 突袭作业', value: 'raid' }])
})

it.each(['prts://12345', '12345', 'https://prts.plus/operation/12345'])(
  'imports %s and selects the matching raid script',
  async (source) => {
    await panel.refreshStatus()
    panel.updateSettings({ raid_enabled: true })
    const script = { id: 'raid', stage_name: 'OS-EX-8', title: '突袭作业' }
    const content = JSON.stringify({ stage_name: 'OS-EX-8', actions: [] })
    state.client.get.mockResolvedValueOnce({ data: { data: { content } } })
    state.client.post.mockResolvedValueOnce({ data: script })
    state.client.get.mockResolvedValueOnce({ data: { scripts: [script] } })
    panel.code.value = source
    await panel.download()
    expect(state.client.get).toHaveBeenCalledWith(
      expect.stringMatching(/\/network\/maa-copilot\/12345$/)
    )
    const [url, form] = state.client.post.mock.calls[0]
    expect(url).toMatch(/\/maa-copilot$/)
    expect(await form.get('copilot').text()).toBe(content)
    expect(panel.selected.value.script_id).toBe('raid')
    expect(panel.code.value).toBe('')
  }
)

it('keeps the selected raid script when the downloaded stage differs', async () => {
  await panel.refreshStatus()
  panel.updateSettings({ raid_enabled: true, script_id: 'already-selected' })
  const script = { id: 'another-stage', stage_name: 'OS-EX-7' }
  state.client.get.mockResolvedValueOnce({ data: { data: { content: '{}' } } })
  state.client.post.mockResolvedValueOnce({ data: script })
  state.client.get.mockResolvedValueOnce({ data: { scripts: [script] } })
  panel.code.value = 'prts://12345'
  await panel.download()
  expect(panel.selected.value.script_id).toBe('already-selected')
  expect(state.error).toHaveBeenCalledWith(expect.stringContaining('关卡与本期 EX-8 不符'))
})

it('rejects a set before downloading any scripts', async () => {
  panel.code.value = 'prts://s123'
  await panel.download()
  expect(state.error).toHaveBeenCalledWith(expect.stringContaining('单份作业码'))
  expect(state.client.get).not.toHaveBeenCalled()
  expect(state.client.post).not.toHaveBeenCalled()
})
