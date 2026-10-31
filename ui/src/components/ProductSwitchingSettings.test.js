import { renderToString } from '@vue/server-renderer'
import { createRenderer, createSSRApp, h, nextTick, ref, ssrContextKey } from 'vue'
import { createPinia } from 'pinia'
import { afterEach, describe, expect, it, vi } from 'vitest'
import PlanAdvancedSettings from './PlanAdvancedSettings.vue'
import TriggerString from './TriggerString.vue'
import { useConfigStore } from '@/stores/config'
import { usePlanStore } from '@/stores/plan'
import { useFacilityStore } from '@/stores/facility'
import { usedepotStore } from '@/stores/depot'
import { useMasteryStore } from '@/stores/mastery'
import {
  facility_expression,
  facility_product_count_expression,
  facility_product_type_count_expression
} from '@/utils/trigger_facility'

vi.mock('naive-ui', async (importOriginal) => ({
  ...(await importOriginal()),
  NForm: {
    setup:
      (_, { slots }) =>
      () =>
        h('form', slots.default?.())
  },
  NFormItem: {
    setup:
      (_, { slots }) =>
      () =>
        h('div', [slots.label?.(), slots.default?.()])
  },
  NCheckbox: {
    setup:
      (_, { slots }) =>
      () =>
        h('label', slots.default?.())
  },
  NSlider: { render: () => h('span') },
  NButton: {
    setup:
      (_, { slots }) =>
      () =>
        h('button', slots.default?.())
  },
  NSelect: {
    props: ['options', 'value', 'defaultValue'],
    setup: (props) => () =>
      h(
        'select',
        { 'data-value': props.value ?? props.defaultValue },
        props.options?.map((option) => h('option', { value: option.value }, option.label))
      )
  },
  NAutoComplete: {
    props: ['value', 'options'],
    setup: (props) => () =>
      h('div', [
        h('input', { value: props.value }),
        ...props.options.map((option) =>
          h('span', typeof option === 'string' ? option : option.displayLabel)
        )
      ])
  }
}))
vi.mock('./HelpText.vue', () => ({ default: { render: () => h('span') } }))
vi.mock('./MowerInputNumber.vue', () => ({ default: { render: () => h('input') } }))
vi.mock('./SlickOperatorSelect.vue', () => ({ default: { render: () => h('select') } }))

const pins = []
afterEach(() => {
  for (const pinia of pins) for (const store of pinia._s.values()) store.$dispose()
  pins.length = 0
  vi.restoreAllMocks()
})

function setup(component, props = {}) {
  const pinia = createPinia()
  pins.push(pinia)
  function app() {
    const instance = createSSRApp(component, props)
    instance.use(pinia)
    instance.provide('mobile', ref(false))
    instance.provide('loaded', ref(false))
    return instance
  }
  const config = app().runWithContext(() => useConfigStore())
  const plan = app().runWithContext(() => usePlanStore())
  plan.plan = plan.fill_empty({
    room_1_1: { name: '贸易站', product: 'lmd', plans: [] },
    room_1_2: { name: '制造站', product: 'gold', plans: [] }
  })
  config.product_switching = {
    enable: true,
    grandet_mode: true,
    max_drones_per_switch: 12,
    waiting_seconds: 4
  }
  return { config, pinia, render: () => renderToString(app()) }
}

describe('product switching master setting', () => {
  it('loads facility data only after the master setting is enabled', async () => {
    const { config, pinia } = setup(TriggerString, { data: 'True' })
    config.product_switching.enable = false
    const facility = useFacilityStore(pinia)
    const load = vi.spyOn(facility, 'load').mockResolvedValue({})
    vi.spyOn(usedepotStore(pinia), 'loadInventory').mockResolvedValue({})
    vi.spyOn(useMasteryStore(pinia), 'loadPlanSummary').mockResolvedValue({})
    const renderer = createRenderer({
      createElement: (type) => ({ type }),
      createText: (text) => ({ text }),
      createComment: (text) => ({ text }),
      insert: (node, parent) => {
        node.parent = parent
      },
      remove: () => {},
      setText: (node, text) => {
        node.text = text
      },
      setElementText: (node, text) => {
        node.text = text
      },
      parentNode: (node) => node.parent,
      nextSibling: () => null,
      patchProp: () => {}
    })
    const app = renderer.createApp({ ...TriggerString, render: () => h('div') }, { data: 'True' })
    app.use(pinia)
    app.provide('loaded', ref(false))
    app.provide(ssrContextKey, {})
    app.mount({})
    try {
      expect(load).not.toHaveBeenCalled()
      config.product_switching.enable = true
      await nextTick()
      expect(load).toHaveBeenCalledTimes(1)
      config.product_switching.enable = false
      await nextTick()
      expect(load).toHaveBeenCalledTimes(1)
    } finally {
      app.unmount()
    }
  })

  it('hides every subordinate setting and restores saved values when enabled again', async () => {
    const { config, render } = setup(PlanAdvancedSettings)
    const subordinate = [
      '切产物单次无人机上限',
      '葛朗台切产物',
      '切出源石碎片时使用无人机',
      '允许无人机不足时直接切换产物',
      '葛朗台无人机损耗容限',
      '葛朗台切产物缓冲时间'
    ]
    let html = await render()
    expect(html.indexOf('自动切换产物与订单')).toBeLessThan(html.indexOf('葛朗台切产物'))
    for (const label of subordinate) expect(html).toContain(label)
    config.product_switching.enable = false
    html = await render()
    expect(html).toContain('自动切换产物与订单')
    expect(html).toContain('无人机使用阈值')
    for (const label of subordinate) expect(html).not.toContain(label)
    expect(config.product_switching.grandet_mode).toBe(true)
    expect(config.product_switching.max_drones_per_switch).toBe(12)
    config.product_switching.enable = true
    for (const label of subordinate) expect(await render()).toContain(label)
  })

  it.each([
    facility_expression('room_1_1'),
    facility_expression('room_1_2'),
    facility_expression('room_1_1', 'type'),
    facility_expression('room_1_2', 'type'),
    facility_product_count_expression('gold'),
    facility_product_type_count_expression
  ])('hides read-dependent choices while preserving saved condition %s', async (data) => {
    const { config, render } = setup(TriggerString, { data })
    expect(await render()).toContain('生产设施统计')
    config.product_switching.enable = false
    const html = await render()
    expect(html).toContain('设施状态')
    expect(html).not.toContain('生产设施统计')
    expect(html).not.toContain('当前产物')
    expect(html).not.toContain('当前订单类型')
    expect(html).not.toContain('设施类型')
    expect(html).not.toContain('制造站')
    expect(html).not.toContain('龙门商法')
    expect(html).not.toContain('赤金')
    expect(html).toContain('干员属性')
    expect(html).toContain('仓库资源')
    expect(html).toContain('data-value="custom"')
    expect(html).toContain(data.replaceAll("'", '&#39;'))
    config.product_switching.enable = true
    expect(await render()).toContain('生产设施统计')
  })

  it.each([
    ['room_1_1', 'operator_count'],
    ['room_1_2', 'operator_count'],
    ['train', 'mastery_plan'],
    ['train', 'training'],
    ['train', 'operator_count']
  ])('keeps independent facility condition %s %s available', async (room, status) => {
    const { config, render } = setup(TriggerString, { data: facility_expression(room, status) })
    config.product_switching.enable = false
    const html = await render()
    expect(html).toContain('data-value="facility"')
    expect(html).toContain(`data-value="${status}"`)
    expect(html).toContain('设施状态')
    expect(html).toContain('当前干员数量')
    expect(html).not.toContain('当前产物')
    expect(html).not.toContain('当前订单类型')
    expect(html).not.toContain('生产设施统计')
    expect(html).not.toContain('设施类型')
    expect(html).not.toContain('当前：赤金')
    expect(html).not.toContain('当前：龙门商法')
    if (room == 'train') {
      expect(html).toContain('是否存在专精计划')
      expect(html).toContain('是否正在训练')
    }
    config.product_switching.enable = true
    const enabled = await render()
    if (room == 'room_1_1') expect(enabled).toContain('当前订单类型')
    if (room == 'room_1_2') expect(enabled).toContain('当前产物')
  })

  it('labels facility types from observations instead of plan configuration', async () => {
    const { pinia, config, render } = setup(TriggerString, {
      data: facility_expression('room_1_2', 'type')
    })
    const facility = useFacilityStore(pinia)
    expect(await render()).toContain('未读取')
    facility.loaded = true
    facility.states = { room_1_2: { facility: 'power', product: null } }
    const html = await render()
    expect(html).toContain('（发电站）')
    expect(html).not.toContain('（制造站；')
    expect(html).not.toContain('当前：赤金')
    config.product_switching.enable = false
    expect(await render()).not.toContain('（发电站）')
  })
})
