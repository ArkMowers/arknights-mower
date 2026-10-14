import { renderToString } from '@vue/server-renderer'
import { createSSRApp, defineComponent, h, ref } from 'vue'
import { describe, expect, it, vi } from 'vitest'
import Clue from './Clue.vue'

const state = vi.hoisted(() => ({ config: {} }))
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

describe('信息板功能适用范围', () => {
  it.each([
    [true, 'mower', true, 'mower', true, true],
    [false, 'mower', true, 'mower', true, false],
    [true, 'maa', true, 'mower', true, false],
    [true, 'mower', false, 'mower', false, false],
    [true, 'mower', true, 'maa', false, false]
  ])(
    '访问好友 %s/%s、购物 %s/%s 时显示为 %s、可勾选为 %s',
    async (visitEnabled, visitMode, mallEnabled, mallMode, visible, enabled) => {
      state.config = {
        visit_friend_enable: ref(visitEnabled),
        visit_friend_mode: ref(visitMode),
        maa_mall_enable: ref(mallEnabled),
        maa_mall_mode: ref(mallMode),
        clue_credit_on_demand: ref(true),
        credit_fight: ref({ squad: 0 }),
        maa_credit_fight: ref(false),
        maa_mall_buy: ref([]),
        maa_mall_blacklist: ref([]),
        shop_list: ref([])
      }
      const app = createSSRApp(Clue)
      app.provide('mobile', false)
      const html = await renderToString(app)
      expect(html.includes('按需领取信用')).toBe(visible)
      if (visible) {
        const checkbox = html.match(/<label\b[^>]*>(<input\b[^>]*>)\s*按需领取信用\s*<\/label>/)
        expect(checkbox).not.toBeNull()
        expect(checkbox[1].includes(' disabled')).toBe(!enabled)
      }
      expect(html.includes('需要开启 Mower 访问好友')).toBe(visible && !enabled)
      expect(state.config.clue_credit_on_demand.value).toBe(true)
    }
  )
})
