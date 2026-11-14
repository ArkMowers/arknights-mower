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

describe('信息板功能适用范围', () => {
  it('assigns combined credit fields to their individual searchable task editors', async () => {
    const html = await renderClue()
    for (const editor of ['visit', 'credit-fight', 'shop']) {
      expect(html).toContain(`data-task-editor="${editor}"`)
    }
  })

  it('opens the clue editor from the combined credit settings', async () => {
    const configureClue = vi.fn()
    const html = await renderClue({}, { onConfigureClue: configureClue })
    expect(html).toContain('线索搜集与交流')
    expect(html).not.toContain('#task-base')
    state.updates['配置线索搜集与交流']()
    expect(configureClue).toHaveBeenCalledExactlyOnceWith()
  })

  it('edits an inactive visit task without enabling it', async () => {
    const html = await renderClue(
      { visit_friend_enable: false },
      { task: 'visit', showEnable: false }
    )
    expect(html).toContain('data-value="mower"')
    state.updates['访友执行方式']('maa')
    expect(state.config.visit_friend_mode.value).toBe('maa')
    expect(state.config.visit_friend_enable.value).toBe(false)
  })

  it('edits an inactive shop task without enabling it', async () => {
    const html = await renderClue(
      { maa_mall_enable: false, maa_mall_mode: 'maa' },
      { task: 'shop', showEnable: false }
    )
    expect(html).toContain('只购买折扣物品')
    expect(html).toContain('<select multiple')
    state.updates['购物执行方式']('mower')
    state.updates['优先购买'](['招聘许可', '龙门币'])
    expect(state.config.maa_mall_mode.value).toBe('mower')
    expect(state.config.maa_mall_buy.value).toEqual(['招聘许可', '龙门币'])
    expect(state.config.maa_mall_enable.value).toBe(false)
  })

  it('keeps inactive task parameters hidden in the existing combined editor', async () => {
    const html = await renderClue({ visit_friend_enable: false, maa_mall_enable: false })
    expect(html).not.toContain('由 MAA 进入好友列表')
    expect(html).not.toContain('只购买折扣物品')
    expect(state.updates['访友执行方式']).toBeUndefined()
    expect(state.updates['购物执行方式']).toBeUndefined()
  })

  it('separates credit task editors without changing shared shopping dependencies', async () => {
    const visit = await renderClue({}, { task: 'visit', showEnable: false })
    expect(visit).toContain('data-value="mower"')
    expect(visit).not.toContain('按性价比购物')
    expect(visit).not.toContain('<select')
    expect(state.config.visit_friend_enable.value).toBe(true)

    const fight = await renderClue({}, { task: 'credit-fight', showEnable: false })
    expect(fight).toContain('<select')
    expect(fight).toContain('借助战打OF-1')
    expect(fight).toContain('使用指定编队')
    expect(fight).not.toContain('<fieldset')
    expect(fight).not.toContain('按性价比购物')
    expect(state.config.maa_credit_fight.value).toBe(false)

    const shop = await renderClue(
      { visit_friend_mode: 'maa', credit_shop_by_value: true },
      { task: 'shop', showEnable: false }
    )
    expect(shop).toContain('按性价比购物')
    expect(shop).toContain('需要开启 Mower 访问好友')
    expect(shop).not.toContain('由 MAA 进入好友列表')
    expect(state.config.credit_shop_by_value.value).toBe(true)
    expect(state.config.visit_friend_mode.value).toBe('maa')
  })

  it.each([
    [true, 'mower', true, 'mower', true, true],
    [false, 'mower', true, 'mower', true, false],
    [true, 'maa', true, 'mower', true, false],
    [true, 'mower', false, 'mower', false, false],
    [true, 'mower', true, 'maa', false, false]
  ])(
    '访问好友 %s/%s、购物 %s/%s 时显示为 %s、可勾选为 %s',
    async (visitEnabled, visitMode, mallEnabled, mallMode, visible, enabled) => {
      const html = await renderClue({
        visit_friend_enable: visitEnabled,
        visit_friend_mode: visitMode,
        maa_mall_enable: mallEnabled,
        maa_mall_mode: mallMode,
        credit_shop_by_value: true
      })
      for (const label of ['按需领取信用', '按性价比购物']) {
        expect(html.includes(label)).toBe(visible)
        if (visible) {
          const checkbox = html.match(
            new RegExp(`<label\\b[^>]*>(<input\\b[^>]*>)\\s*${label}\\s*</label>`)
          )
          expect(checkbox).not.toBeNull()
          expect(checkbox[1].includes(' disabled')).toBe(!enabled)
        }
      }
      const threshold = html.match(/<input\b[^>]*type="number"[^>]*>/)
      expect(Boolean(threshold)).toBe(visible)
      if (visible) {
        expect(threshold[0].includes(' disabled')).toBe(!enabled)
      }
      if (mallEnabled) {
        const overflow = html.match(/<fieldset\b[^>]*data-value="true"[^>]*>/)
        expect(overflow).not.toBeNull()
        expect(overflow[0].includes(' disabled')).toBe(enabled)
        const lists = html.match(/<select\b[^>]* multiple[^>]*>/g)
        expect(lists).toHaveLength(2)
        expect(lists.every((select) => !select.includes(' disabled'))).toBe(true)
      }
      expect(html.includes('需要开启 Mower 访问好友')).toBe(visible && !enabled)
      expect(state.config.clue_credit_on_demand.value).toBe(true)
      expect(state.config.credit_shop_by_value.value).toBe(true)
      expect(state.config.maa_mall_ignore_blacklist_when_full.value).toBe(true)
    }
  )
})

describe('按性价比购物设置', () => {
  it.each([true, false])('按需领取信用为 %s 时仍独立控制溢出选项', async (onDemand) => {
    for (const enabled of [true, false]) {
      const html = await renderClue({
        credit_shop_by_value: enabled,
        clue_credit_on_demand: onDemand
      })
      const overflow = html.match(/<fieldset\b[^>]*data-value="true"[^>]*>/)
      expect(overflow[0].includes(' disabled')).toBe(enabled)
      const threshold = html.match(/<input\b[^>]*type="number"[^>]*>/)
      expect(threshold[0].includes(' disabled')).toBe(!enabled)
      expect(state.config.clue_credit_on_demand.value).toBe(onDemand)
      expect(state.config.maa_mall_ignore_blacklist_when_full.value).toBe(true)
      expect(state.config.maa_mall_buy.value).toEqual(['招聘许可'])
      expect(state.config.maa_mall_blacklist.value).toEqual(['家具零件'])
    }
  })

  it('阈值使用三位小数，空值和非法值不会覆盖保存值', async () => {
    const html = await renderClue({ credit_shop_by_value: true })
    const input = html.match(/<input\b[^>]*type="number"[^>]*>/)[0]
    expect(input).toContain('value="0.045"')
    expect(input).toContain('step="0.001"')
    expect(input).toContain('min="0"')
    expect(input).toContain('data-precision="3"')
    state.updateThreshold(0.036)
    expect(state.config.credit_shop_value_threshold.value).toBe(0.036)
    for (const value of [null, NaN, Infinity, -0.001]) {
      state.updateThreshold(value)
      expect(state.config.credit_shop_value_threshold.value).toBe(0.036)
    }
    state.updateThreshold(0)
    expect(state.config.credit_shop_value_threshold.value).toBe(0)
  })
})
