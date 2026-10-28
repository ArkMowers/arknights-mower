import { beforeEach, describe, expect, it, vi } from 'vitest'
import { effectScope, ref } from 'vue'
import Component from './MaaEventShop.vue'
import { createTaskWorkflow, setTaskEnabled } from '@/task-workflow/model'

const state = vi.hoisted(() => ({ config: {}, client: null, error: vi.fn() }))
vi.mock('vue', async (original) => ({
  ...(await original()),
  inject: () => state.client,
  onMounted: () => {},
  useSSRContext: () => ({ modules: new Set() })
}))
vi.mock('@/stores/config', () => ({ useConfigStore: () => state.config }))
vi.mock('pinia', () => ({ storeToRefs: (store) => store }))
vi.mock('naive-ui', async (original) => ({
  ...(await original()),
  useMessage: () => ({ error: state.error })
}))
beforeEach(() => {
  state.config = {
    maa_event_shop: ref({
      enable: false,
      activity: '活动',
      switch_source: '活动方案',
      blacklist: []
    })
  }
  state.client = {
    get: vi.fn(async (url) => ({
      data: url.endsWith('/weekly-plans')
        ? { plans: ['活动方案', '常规'], activity_fallbacks: { 活动方案: '常规' } }
        : { shops: [{ activity: '活动', x: 100, y: 200, confirm_text: '商店' }] }
    }))
  }
})
describe('activity shop configuration', () => {
  it('uses the same fallback target as time switching and clears an optional source to a string', async () => {
    const scope = effectScope()
    const component = scope.run(() => Component.setup({}, { expose: () => {} }))
    await component.refresh()
    expect(component.target.value).toBe('常规')
    expect(component.selected.value.x).toBe(100)
    component.source.value = null
    expect(state.config.maa_event_shop.value.switch_source).toBe('')
    expect(component.target.value).toBe('')
    scope.stop()
  })
  it('has its own daily task switch and preserves other settings', () => {
    const config = {
      maa_event_shop: { enable: false, activity: '活动', switch_source: '活动方案' }
    }
    expect(setTaskEnabled(config, 'event-shop', true)).toBe(true)
    const workflow = createTaskWorkflow(config)
    expect(workflow.tasks.find((item) => item.id === 'event-shop').group).toBe('daily')
    expect(workflow.statuses['event-shop']).toBe(true)
    expect(config.maa_event_shop.activity).toBe('活动')
    expect(config.maa_event_shop.switch_source).toBe('活动方案')
  })
})
