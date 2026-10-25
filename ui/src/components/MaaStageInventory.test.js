import { createRenderer, h, reactive, ref, ssrContextKey } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import axios from 'axios'
import MaaStageInventory from './MaaStageInventory.vue'

const state = vi.hoisted(() => ({ refs: {}, resource: null }))
vi.mock('axios', () => ({ default: { get: vi.fn() } }))
vi.mock('@/stores/config', () => ({ useConfigStore: () => ({}) }))
vi.mock('@/stores/resourceVersion', () => ({ useResourceVersionStore: () => state.resource }))
vi.mock('pinia', () => ({ storeToRefs: () => state.refs }))
vi.mock('naive-ui', () => ({ useMessage: () => ({ success: vi.fn(), error: vi.fn() }) }))

let app
beforeEach(() => {
  state.resource = reactive({ info: { current_version: 'current' } })
  state.refs = {
    maa_weekly_plan: ref([{ weekday: '周一', stage: ['1-7'] }]),
    maa_weekly_plan_active: ref('常规'),
    maa_stage_inventory_enable: ref(false),
    maa_stage_limit_rules: ref([{ stage: '1-7', enabled: true, items: [] }]),
    maa_stage_ratio_rules: ref([{ name: '活动比例', enabled: false, members: [] }])
  }
  axios.get.mockReset().mockResolvedValue({
    data: {
      stages: [
        {
          value: 'PR-A-1',
          materials: [
            { id: '3231', name: '重装芯片' },
            { id: '3261', name: '医疗芯片' }
          ]
        }
      ],
      items: []
    }
  })
})
afterEach(() => app?.unmount())

function mountInventory(onChipLimitsApplied) {
  const renderer = createRenderer({
    createElement: () => ({}),
    createText: () => ({}),
    createComment: () => ({}),
    setText() {},
    setElementText() {},
    patchProp() {},
    insert() {},
    remove() {},
    parentNode: () => null,
    nextSibling: () => null
  })
  app = renderer.createApp(
    { ...MaaStageInventory, render: () => h('div') },
    { onChipLimitsApplied }
  )
  app.provide(ssrContextKey, { modules: new Set() })
  app.mount({})
  return app._instance.setupState
}

describe('一键芯片上限启用库存选关', () => {
  it.each([false, true])('原开关为 %s 时应用上限后启用，重复应用保留其他规则', async (enabled) => {
    state.refs.maa_stage_inventory_enable.value = enabled
    const otherRule = state.refs.maa_stage_limit_rules.value[0]
    const ratios = state.refs.maa_stage_ratio_rules.value
    const onApplied = vi.fn(() => {
      expect(state.refs.maa_stage_inventory_enable.value).toBe(true)
    })
    const inventory = mountInventory(onApplied)
    await vi.waitFor(() => expect(inventory.loading).toBe(false))
    expect(state.refs.maa_stage_inventory_enable.value).toBe(enabled)

    inventory.applyChipLimits()

    expect(state.refs.maa_stage_inventory_enable.value).toBe(true)
    expect(state.refs.maa_stage_limit_rules.value).toEqual([
      otherRule,
      {
        stage: 'PR-A-1',
        operator: 'and',
        enabled: true,
        items: [
          { item_id: '3231', item_name: '重装芯片', limit: 5 },
          { item_id: '3261', item_name: '医疗芯片', limit: 5 }
        ]
      }
    ])
    state.refs.maa_stage_inventory_enable.value = false
    inventory.applyChipLimits()
    expect(state.refs.maa_stage_inventory_enable.value).toBe(true)
    expect(state.refs.maa_stage_limit_rules.value).toHaveLength(2)
    expect(state.refs.maa_stage_limit_rules.value[0]).toBe(otherRule)
    expect(state.refs.maa_stage_ratio_rules.value).toBe(ratios)
    expect(onApplied).toHaveBeenCalledTimes(2)
  })
})
