import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createSSRApp, effectScope, ref } from 'vue'
import { renderToString } from '@vue/server-renderer'
import Component from './MaaEventShop.vue'
import { createTaskWorkflow, setTaskEnabled } from '@/task-workflow/model'
import { i18n } from '@/i18n'

const state = vi.hoisted(() => ({ config: {}, client: null, error: vi.fn() }))
vi.mock('vue', async (original) => ({
  ...(await original()),
  inject: () => state.client,
  onMounted: () => {},
  useSSRContext: () => ({ modules: new Set() })
}))
vi.mock('@/stores/config', () => ({ useConfigStore: () => state.config }))
vi.mock('pinia', () => ({ storeToRefs: (store) => store }))
vi.mock('naive-ui', async () => {
  const { defineComponent, h } = await import('vue')
  const container = defineComponent({
    props: ['title', 'label'],
    setup:
      (props, { slots }) =>
      () =>
        h('section', [props.title, props.label, slots['header-extra']?.(), slots.default?.()])
  })
  return {
    ...Object.fromEntries(
      [
        'NCard',
        'NFlex',
        'NAlert',
        'NForm',
        'NFormItem',
        'NCheckbox',
        'NInputNumber',
        'NInput',
        'NText',
        'NButton',
        'NDynamicTags',
        'NSwitch'
      ].map((name) => [name, container])
    ),
    NSelect: defineComponent({
      props: ['value', 'options'],
      setup: (props) => () =>
        h(
          'select',
          { value: props.value },
          (props.options || []).map(({ label, value }) => h('option', { value }, label))
        )
    }),
    useMessage: () => ({ error: state.error })
  }
})
beforeEach(() => {
  state.error.mockClear()
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
afterEach(() => {
  i18n.global.locale.value = 'zh-CN'
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

  it('translates the shop view in four languages without changing activity, plans or request identities', async () => {
    const scope = effectScope()
    try {
      const component = scope.run(() => Component.setup({}, { expose: () => {} }))
      await component.refresh()
      const saved = JSON.parse(JSON.stringify(state.config.maa_event_shop.value))
      const requests = JSON.parse(JSON.stringify(state.client.get.mock.calls))
      for (const locale of ['zh-CN', 'en-US', 'ja-JP', 'zh-TW']) {
        i18n.global.locale.value = locale
        const html = await renderToString(createSSRApp({ ...Component, setup: () => component }))
        expect(html, locale).toContain(i18n.global.t('maaActivities.eventShopTitle'))
        expect(html, locale).toContain(
          i18n.global.t('maaActivities.targetPlanHelp', { plan: '常规' })
        )
        expect(html, locale).toContain(
          i18n.global.t('maaActivities.resourceEntry', { x: 100, y: 200, text: '商店' })
        )
        expect(component.activityOptions.value).toEqual([{ label: '活动', value: '活动' }])
        expect(component.sourceOptions.value).toEqual([
          { label: '活动方案', value: '活动方案' },
          { label: '常规', value: '常规' }
        ])
        expect(state.config.maa_event_shop.value).toEqual(saved)
        expect(state.client.get.mock.calls).toEqual(requests)
      }
      component.source.value = '常规'
      expect(state.config.maa_event_shop.value).toEqual({ ...saved, switch_source: '常规' })
    } finally {
      scope.stop()
    }
  })

  it.each(['zh-CN', 'en-US', 'ja-JP', 'zh-TW'])(
    'translates fallback failures in %s and preserves raw backend diagnostics',
    async (locale) => {
      i18n.global.locale.value = locale
      const scope = effectScope()
      try {
        const component = scope.run(() => Component.setup({}, { expose: () => {} }))
        state.client.get.mockRejectedValueOnce(new Error('offline'))
        await component.refresh()
        expect(state.error).toHaveBeenLastCalledWith(i18n.global.t('maaActivities.loadFailed'))
        state.client.get.mockRejectedValueOnce({
          response: { data: { message: '资源加载失败：原始诊断' } }
        })
        await component.refresh()
        expect(state.error).toHaveBeenLastCalledWith('资源加载失败：原始诊断')
      } finally {
        scope.stop()
      }
    }
  )
})
