import { renderToString } from '@vue/server-renderer'
import { createSSRApp, defineComponent, h, ref } from 'vue'
import { describe, expect, it, vi } from 'vitest'
import Clue from './Clue.vue'

const state = vi.hoisted(() => ({ config: {}, updateThreshold: null, updates: {} }))
vi.mock('@/stores/config', () => ({ useConfigStore: () => ({}) }))
vi.mock('@/stores/plan', () => ({ usePlanStore: () => ({ operators: [] }) }))
vi.mock('pinia', () => ({ storeToRefs: () => state.config }))
vi.mock('./HelpText.vue', () => ({
  default: defineComponent({
    setup:
      (_, { slots }) =>
      () =>
        h('aside', slots.default?.())
  })
}))
vi.mock('naive-ui', () => {
  const container = defineComponent({
    setup:
      (_, { slots }) =>
      () =>
        h('div', slots.default?.())
  })
  const components = Object.fromEntries(
    [
      'NCard',
      'NForm',
      'NFormItem',
      'NRadioGroup',
      'NRadio',
      'NSpace',
      'NDivider',
      'NButton',
      'NSelect',
      'NAvatar',
      'NTag'
    ].map((name) => [name, container])
  )
  return {
    ...components,
    NButton: defineComponent({
      setup: (_, { attrs, slots }) => {
        if (attrs['aria-label']) state.updates[attrs['aria-label']] = attrs.onClick
        return () => h('button', slots.default?.())
      }
    }),
    NFormItem: defineComponent({
      setup:
        (_, { slots }) =>
        () =>
          h('div', [slots.label?.(), slots.default?.()])
    }),
    NRadioGroup: defineComponent({
      props: ['value', 'disabled'],
      setup: (props, { attrs, slots }) => {
        if (attrs['aria-label']) state.updates[attrs['aria-label']] = attrs['onUpdate:value']
        return () =>
          h(
            'fieldset',
            { disabled: props.disabled, 'data-value': String(props.value) },
            slots.default?.()
          )
      }
    }),
    NSelect: defineComponent({
      props: ['multiple', 'value', 'disabled'],
      setup: (props, { attrs }) => {
        if (attrs['aria-label']) state.updates[attrs['aria-label']] = attrs['onUpdate:value']
        return () =>
          h('select', {
            multiple: props.multiple,
            disabled: props.disabled,
            'data-value': String(props.value)
          })
      }
    }),
    NInputNumber: defineComponent({
      props: ['value', 'disabled', 'min', 'step', 'precision', 'inputProps'],
      setup: (props, { attrs }) => {
        state.updateThreshold = attrs['onUpdate:value']
        return () =>
          h('input', {
            ...props.inputProps,
            type: 'number',
            value: props.value,
            disabled: props.disabled,
            min: props.min,
            step: props.step,
            'data-precision': props.precision
          })
      }
    }),
    NCheckbox: defineComponent({
      props: { checked: Boolean, disabled: Boolean },
      setup:
        (props, { slots }) =>
        () =>
          h('label', [
            h('input', { type: 'checkbox', checked: props.checked, disabled: props.disabled }),
            ...(slots.default?.() ?? [])
          ])
    }),
    NTooltip: defineComponent({
      props: { disabled: Boolean },
      setup:
        (props, { slots }) =>
        () =>
          h('div', [slots.trigger?.(), !props.disabled && h('aside', slots.default?.())])
    })
  }
})

async function renderClue(overrides = {}, props = {}) {
  state.updates = {}
  state.config = Object.fromEntries(
    Object.entries({
      visit_friend_enable: true,
      visit_friend_mode: 'mower',
      maa_mall_enable: true,
      maa_mall_mode: 'mower',
      clue_credit_on_demand: true,
      credit_shop_by_value: false,
      credit_shop_value_threshold: 0.045,
      maa_mall_ignore_blacklist_when_full: true,
      credit_fight: { squad: 0 },
      maa_credit_fight: false,
      maa_mall_buy: ['招聘许可'],
      maa_mall_blacklist: ['家具零件'],
      shop_list: [],
      ...overrides
    }).map(([key, value]) => [key, ref(value)])
  )
  const app = createSSRApp(Clue, props)
  app.provide('mobile', false)
  return renderToString(app)
}

describe('固定的访友与购物策略', () => {
  it('keeps individual searchable task editors in the combined settings', async () => {
    const html = await renderClue()
    for (const editor of ['visit', 'credit-fight', 'shop']) {
      expect(html).toContain(`data-task-editor="${editor}"`)
    }
    expect(html).not.toContain('线索收集')
    for (const removed of [
      '访友执行方式',
      '购物执行方式',
      '购物设置',
      '信用溢出',
      '只购买折扣物品',
      '无视黑名单'
    ]) {
      expect(html).not.toContain(removed)
      expect(state.updates[removed]).toBeUndefined()
    }
    expect(html).not.toContain('<fieldset')
    expect(html.match(/type="checkbox"/g)).toHaveLength(3)
  })

  it('opens the clue editor from the combined credit settings', async () => {
    const configureClue = vi.fn()
    const html = await renderClue({}, { onConfigureClue: configureClue })
    expect(html).toContain('线索搜集与交流')
    state.updates['配置线索搜集与交流']()
    expect(configureClue).toHaveBeenCalledExactlyOnceWith()
  })

  it('describes the fixed Mower visit without enabling the task', async () => {
    const html = await renderClue(
      { visit_friend_enable: false },
      { task: 'visit', showEnable: false }
    )
    expect(html).toContain('由 Mower 访问好友并收取信用')
    expect(html).not.toContain('<select')
    expect(html).not.toContain('<fieldset')
    expect(state.config.visit_friend_enable.value).toBe(false)
  })

  it.each([false, true])(
    'keeps threshold and purchase lists editable with visits %s',
    async (visits) => {
      const html = await renderClue(
        { visit_friend_enable: visits, maa_mall_enable: false },
        { task: 'shop', showEnable: false }
      )
      expect(html).toContain('按性价比购物')
      expect(html).toContain('按需领取信用')
      const threshold = html.match(/<input\b[^>]*type="number"[^>]*>/)[0]
      expect(threshold).not.toContain(' disabled')
      const lists = html.match(/<select\b[^>]* multiple[^>]*>/g)
      expect(lists).toHaveLength(2)
      expect(lists.every((select) => !select.includes(' disabled'))).toBe(true)
      state.updates['优先购买'](['招聘许可', '龙门币'])
      expect(state.config.maa_mall_buy.value).toEqual(['招聘许可', '龙门币'])
      expect(state.config.maa_mall_enable.value).toBe(false)
      expect(state.config.visit_friend_enable.value).toBe(visits)
    }
  )

  it('keeps disabled shopping parameters hidden in combined settings', async () => {
    const html = await renderClue({ maa_mall_enable: false })
    expect(html).not.toContain('type="number"')
    expect(html).not.toContain('<select multiple')
  })

  it('retains the independent credit-fight squad editor', async () => {
    const html = await renderClue({}, { task: 'credit-fight', showEnable: false })
    expect(html).toContain('<select')
    expect(html).toContain('借助战打OF-1')
    expect(html).not.toContain('按性价比购物')
    expect(state.config.maa_credit_fight.value).toBe(false)
  })

  it('accepts three-decimal thresholds and preserves the value on invalid input', async () => {
    const html = await renderClue()
    const input = html.match(/<input\b[^>]*type="number"[^>]*>/)[0]
    for (const attribute of ['value="0.045"', 'step="0.001"', 'min="0"', 'data-precision="3"']) {
      expect(input).toContain(attribute)
    }
    state.updateThreshold(0.036)
    for (const value of [null, NaN, Infinity, -0.001]) {
      state.updateThreshold(value)
      expect(state.config.credit_shop_value_threshold.value).toBe(0.036)
    }
    state.updateThreshold(0)
    expect(state.config.credit_shop_value_threshold.value).toBe(0)
  })
})
