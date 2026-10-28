import { afterEach, expect, it, vi } from 'vitest'
import { effectScope, reactive, ref } from 'vue'
import { i18n } from '@/i18n'
import StartSchedule from './StartSchedule.vue'

const state = vi.hoisted(() => ({ axios: null, scheduled: null }))
vi.mock('vue', async (original) => ({
  ...(await original()),
  useSSRContext: () => ({ modules: new Set() }),
  inject: () => state.axios,
  onMounted: vi.fn(),
  onUnmounted: vi.fn()
}))
vi.mock('pinia', () => ({ storeToRefs: () => ({ scheduled_start_at: state.scheduled }) }))
vi.mock('@/stores/mower', () => ({ useMowerStore: () => ({}) }))
vi.mock('naive-ui', () => ({ useMessage: () => ({ error: vi.fn() }) }))

afterEach(() => {
  i18n.global.locale.value = 'zh-CN'
})

it('keeps schedule commands and request data while live option labels change language', async () => {
  state.scheduled = ref(null)
  state.axios = {
    put: vi.fn().mockResolvedValue({ data: { scheduled_start_at: '2026-10-28T10:00:00Z' } }),
    delete: vi.fn().mockResolvedValue({})
  }
  const start = vi.fn()
  const props = reactive({
    start,
    startOptions: [{ label: '自定义源数据', key: '1' }],
    waiting: false
  })
  const scope = effectScope()
  try {
    const page = scope.run(() => StartSchedule.setup(props, { expose: vi.fn() }))
    page.showModal.value = true
    const before = page.startOptions.value[0].label
    i18n.global.locale.value = 'en-US'
    expect(page.startOptions.value[0].label).not.toBe(before)
    expect(page.startOptions.value.at(-1)).toEqual({ label: '自定义源数据', key: '1' })
    expect(page.showModal.value).toBe(true)
    expect(state.axios.put).not.toHaveBeenCalled()
    await page.schedule(600)
    expect(state.axios.put).toHaveBeenCalledExactlyOnceWith('/scheduled-start', {
      delay_seconds: 600
    })
    page.select('1')
    page.select('start')
    expect(start.mock.calls).toEqual([['1'], ['2']])
    props.waiting = true
    await page.schedule(900)
    expect(state.axios.put).toHaveBeenCalledOnce()
    await page.cancel()
    expect(state.axios.delete).toHaveBeenCalledExactlyOnceWith('/scheduled-start')
  } finally {
    scope.stop()
  }
})
