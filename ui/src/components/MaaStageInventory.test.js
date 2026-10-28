import { renderToString } from '@vue/server-renderer'
import { createSSRApp, defineComponent, h, reactive, toRefs } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { i18n } from '@/i18n'
import axios from 'axios'
import MaaStageInventory from './MaaStageInventory.vue'
import { WEEKDAYS } from '@/utils/maa_weekly_plan'

const state = vi.hoisted(() => ({ config: null, messageError: vi.fn(), tabs: [], panes: [] }))
vi.mock('axios', () => ({ default: { get: vi.fn() } }))
vi.mock('@/stores/config', () => ({ useConfigStore: () => state.config }))
vi.mock('@/stores/resourceVersion', () => ({
  useResourceVersionStore: () => ({ info: { current_version: 'test' } })
}))
vi.mock('pinia', () => ({ storeToRefs: (store) => toRefs(store) }))
vi.mock('./HelpText.vue', () => ({
  default: defineComponent(
    (_, { slots }) =>
      () =>
        h('div', slots.default?.())
  )
}))
vi.mock('naive-ui', () => {
  const wrapper = defineComponent({
    inheritAttrs: false,
    props: ['title', 'description'],
    setup:
      (props, { slots }) =>
      () =>
        h('div', [
          props.title,
          props.description,
          slots.header?.(),
          slots['header-extra']?.(),
          slots.default?.()
        ])
  })
  return {
    useMessage: () => ({ success: vi.fn(), error: state.messageError }),
    ...Object.fromEntries(
      [
        'NAlert',
        'NButton',
        'NCard',
        'NDivider',
        'NEmpty',
        'NFlex',
        'NInput',
        'NInputNumber',
        'NRadioButton',
        'NRadioGroup',
        'NSelect',
        'NSpace',
        'NSpin',
        'NSwitch',
        'NTabPane',
        'NTabs',
        'NTag',
        'NText'
      ].map((name) => [name, wrapper])
    ),
    NTabs: defineComponent({
      ...wrapper,
      props: ['animated'],
      setup(props, context) {
        state.tabs.push(props)
        return wrapper.setup(props, context)
      }
    }),
    NTabPane: defineComponent({
      ...wrapper,
      props: ['name', 'tab'],
      setup(props, context) {
        state.panes.push(props)
        return wrapper.setup(props, context)
      }
    })
  }
})

const inventory = {
  重装芯片: 32,
  医疗芯片: 22,
  重装芯片组: 22,
  医疗芯片组: 17,
  近卫芯片: 3,
  近卫芯片组: 4
}
const stages = ['PR-A-1', 'PR-A-2', 'PR-D-1', 'PR-D-2', 'AP-5']
const disabledNotice = '库存选关未启用，物品上限和比例规则均不生效，将按原计划执行。'
const stoppedNotice = '全部已选关卡均已达到上限，本轮不刷取，继续其他任务。'

function setPlan(selected) {
  state.config.maa_weekly_plan = WEEKDAYS.map((weekday) => ({ weekday, stage: [...selected] }))
}

async function renderInventory(onChipLimitsApplied) {
  let setup
  const component = {
    ...MaaStageInventory,
    async setup(props, context) {
      setup = MaaStageInventory.setup(props, context)
      await Promise.resolve()
      return setup
    }
  }
  const html = await renderToString(createSSRApp(component, { onChipLimitsApplied }))
  return {
    html,
    preview: html.split('今日执行预览')[1],
    execution: html.split('实际执行')[1],
    refreshInventory: setup.refreshInventory,
    applyChipLimits: setup.applyChipLimits,
    itemOptionsFor: setup.itemOptionsFor,
    updateItem: setup.updateItem
  }
}

beforeEach(() => {
  state.tabs = []
  state.panes = []
  state.config = reactive({
    maa_stage_inventory_enable: false,
    maa_weekly_plan_active: '芯片',
    maa_weekly_plan: [],
    maa_stage_limit_rules: [
      {
        stage: 'PR-A-1',
        enabled: true,
        operator: 'and',
        items: [
          { item_id: '重装芯片', limit: 5 },
          { item_id: '医疗芯片', limit: 5 }
        ]
      },
      {
        stage: 'PR-A-2',
        enabled: true,
        operator: 'and',
        items: [
          { item_id: '重装芯片组', limit: 8 },
          { item_id: '医疗芯片组', limit: 8 }
        ]
      }
    ],
    maa_stage_ratio_rules: [
      {
        name: '近卫芯片比例',
        enabled: true,
        members: [
          { stage: 'PR-D-1', item_id: '近卫芯片', ratio: 1 },
          { stage: 'PR-D-2', item_id: '近卫芯片组', ratio: 1 }
        ]
      }
    ]
  })
  setPlan(stages)
  axios.get.mockReset().mockResolvedValue({
    data: {
      inventory,
      stages: stages.map((value) => ({ value, label: value })),
      items: Object.keys(inventory).map((value) => ({ value, id: value, label: value }))
    }
  })
})

describe('库存选关生效状态', () => {
  afterEach(() => {
    i18n.global.locale.value = 'zh-CN'
  })
  it('keeps inventory tab identities and non-animated panels while translating their labels', async () => {
    const original = JSON.stringify(state.config)
    for (const [locale, label] of [
      ['zh-CN', '物品上限'],
      ['en-US', 'Item limits'],
      ['ja-JP', 'アイテム上限'],
      ['zh-TW', '物品上限']
    ]) {
      i18n.global.locale.value = locale
      await renderInventory()
      expect(state.panes.findLast((props) => props.name === 'limit')).toMatchObject({ tab: label })
      expect(JSON.stringify(state.config)).toBe(original)
    }
    expect(state.tabs).toHaveLength(4)
    expect(state.tabs.every((props) => !props.animated)).toBe(true)
    expect(axios.get).toHaveBeenCalledTimes(4)
    expect(axios.get.mock.calls.every(([url]) => url.endsWith('/stage/inventory-rules'))).toBe(true)
  })

  it('translates the shared sync failure shown by inventory refresh', async () => {
    const { refreshInventory } = await renderInventory()
    const payload = { success: false, message: '未同步到干员数据，请检查森空岛账号及官服/B服选择' }
    axios.get.mockResolvedValueOnce({ data: payload })
    state.messageError.mockClear()
    i18n.global.locale.value = 'ja-JP'
    await refreshInventory()
    expect(state.messageError).toHaveBeenCalledExactlyOnceWith(
      'オペレーターデータを同期できませんでした。SKLand のアカウントと公式サーバー／Bilibili サーバーの選択を確認してください。'
    )
    expect(payload.message).toBe('未同步到干员数据，请检查森空岛账号及官服/B服选择')
  })

  it('translates item options without writing localized material names or IDs into inventory rules', async () => {
    axios.get.mockResolvedValueOnce({
      data: { stages: [], items: [{ value: '3231', id: '3231', label: '重装芯片' }] }
    })
    const { itemOptionsFor, updateItem } = await renderInventory()
    const item = { item_id: '3231', item_name: '重装芯片', limit: 8 }
    const originalValues = itemOptionsFor(item).map(({ value }) => value)
    for (const locale of ['zh-CN', 'en-US', 'ja-JP', 'zh-TW']) {
      i18n.global.locale.value = locale
      expect(itemOptionsFor(item).map(({ value }) => value)).toEqual(originalValues)
      const edited = { ...item }
      updateItem(edited, '3231')
      expect(edited).toEqual(item)
    }
    i18n.global.locale.value = 'en-US'
    expect(itemOptionsFor(item).find(({ value }) => value === '3231').label).toBe('Defender Chip')
  })
  it('关闭总开关时按原计划执行，不显示跳过或比例选择决策', async () => {
    const plan = [...stages, 'Annihilation']
    setPlan(plan)
    const { html, preview, execution } = await renderInventory()
    expect(html).not.toContain('将跳过')
    expect(html).not.toContain('当前优先')
    expect(html).toContain(disabledNotice)
    expect(preview).not.toContain('达到上限')
    expect(preview).not.toContain('比例选择')
    expect(preview).not.toContain(stoppedNotice)
    const display = [...stages, '当期剿灭']
    for (const [index, stage] of display.entries()) {
      expect(execution).toContain(stage)
      if (index > 0) {
        expect(execution.indexOf(stage)).toBeGreaterThan(execution.indexOf(display[index - 1]))
      }
    }
    expect(axios.get).toHaveBeenCalledOnce()
  })

  it('切换总开关后显示真实跳过和比例选择，保留配置及原计划', async () => {
    const original = JSON.parse(JSON.stringify(state.config))
    await renderInventory()
    state.config.maa_stage_inventory_enable = true
    const { html, preview, execution } = await renderInventory()
    expect(html).toContain('已达上限，将跳过')
    expect(html).toContain('当前优先 PR-D-1')
    expect(preview).toContain('达到上限')
    expect(preview).toContain('比例选择')
    expect(html).not.toContain(disabledNotice)
    expect(execution).toContain('PR-D-1')
    for (const stage of ['PR-A-1', 'PR-A-2', 'PR-D-2', 'AP-5']) {
      expect(execution).not.toContain(stage)
    }
    state.config.maa_stage_inventory_enable = false
    const disabled = await renderInventory()
    for (const stage of stages) expect(disabled.execution).toContain(stage)
    expect(disabled.html).not.toContain('将跳过')
    expect(disabled.html).not.toContain('当前优先')
    expect(state.config).toEqual(original)
  })

  it.each([false, true])('全部关卡达标且总开关为 %s 时正确判断是否停止刷取', async (enabled) => {
    state.config.maa_stage_inventory_enable = enabled
    state.config.maa_stage_ratio_rules = []
    setPlan(['PR-A-1', 'PR-A-2'])
    const { html, preview, execution } = await renderInventory()
    if (enabled) {
      expect(preview).toContain(stoppedNotice)
      expect(execution).not.toContain('PR-A-1')
      expect(execution).not.toContain('PR-A-2')
    } else {
      expect(html).toContain(disabledNotice)
      expect(preview).not.toContain(stoppedNotice)
      expect(html).not.toContain('将跳过')
      expect(execution).toContain('PR-A-1')
      expect(execution).toContain('PR-A-2')
    }
  })

  it('启用后跳过达标芯片关卡，并执行无库存规则的后备关卡', async () => {
    state.config.maa_stage_inventory_enable = true
    state.config.maa_stage_ratio_rules = []
    setPlan(['PR-A-1', 'PR-A-2', 'AP-5'])
    const { preview, execution } = await renderInventory()
    expect(preview).toContain('达到上限')
    expect(preview).not.toContain(stoppedNotice)
    expect(execution).not.toContain('PR-A-1')
    expect(execution).not.toContain('PR-A-2')
    expect(execution).toContain('AP-5')
  })

  it('单条规则关闭时明确显示未启用，并保留原计划', async () => {
    state.config.maa_stage_inventory_enable = true
    for (const rule of [
      ...state.config.maa_stage_limit_rules,
      ...state.config.maa_stage_ratio_rules
    ]) {
      rule.enabled = false
    }
    const { html, preview, execution } = await renderInventory()
    expect(html.match(/规则未启用/g)).toHaveLength(3)
    expect(html).not.toContain('将跳过')
    expect(html).not.toContain('当前优先')
    expect(preview).not.toContain('达到上限')
    expect(preview).not.toContain('比例选择')
    for (const stage of stages) expect(execution).toContain(stage)
  })
})

describe('一键芯片上限启用库存选关', () => {
  beforeEach(() => {
    state.config.maa_weekly_plan = [{ weekday: '周一', stage: ['1-7'] }]
    state.config.maa_weekly_plan_active = '常规'
    state.config.maa_stage_limit_rules = [{ stage: '1-7', enabled: true, items: [] }]
    state.config.maa_stage_ratio_rules = [{ name: '活动比例', enabled: false, members: [] }]
    axios.get.mockResolvedValue({
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

  it.each([false, true])('原开关为 %s 时应用上限后启用，重复应用保留其他规则', async (enabled) => {
    state.config.maa_stage_inventory_enable = enabled
    const otherRule = state.config.maa_stage_limit_rules[0]
    const ratios = state.config.maa_stage_ratio_rules
    const onApplied = vi.fn(() => {
      expect(state.config.maa_stage_inventory_enable).toBe(true)
    })
    const { applyChipLimits } = await renderInventory(onApplied)
    expect(state.config.maa_stage_inventory_enable).toBe(enabled)

    applyChipLimits()

    expect(state.config.maa_stage_inventory_enable).toBe(true)
    expect(state.config.maa_stage_limit_rules).toEqual([
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
    state.config.maa_stage_inventory_enable = false
    applyChipLimits()
    expect(state.config.maa_stage_inventory_enable).toBe(true)
    expect(state.config.maa_stage_limit_rules).toHaveLength(2)
    expect(state.config.maa_stage_limit_rules[0]).toBe(otherRule)
    expect(state.config.maa_stage_ratio_rules).toBe(ratios)
    expect(onApplied).toHaveBeenCalledTimes(2)
  })
})
