import { renderToString } from '@vue/server-renderer'
import { createSSRApp, ref } from 'vue'
import { createPinia } from 'pinia'
import { parse as parseHtml } from '@vue/compiler-dom'
import { afterEach, describe, expect, it } from 'vitest'
import PlanEditor from './PlanEditor.vue'
import { useConfigStore } from '@/stores/config'
import { usePlanStore } from '@/stores/plan'

const stores = []

function updateDropRegions(html) {
  const markers = []
  const avatars = []
  let outsideSpaces = 0
  function walk(node, excluded = false) {
    if (node.type === 1) {
      const attrs = Object.fromEntries(
        node.props.filter((prop) => prop.type === 6).map((prop) => [prop.name, prop.value?.content])
      )
      if (Object.hasOwn(attrs, 'data-no-update-drop')) {
        markers.push(attrs.class)
        excluded = true
      }
      if (node.tag === 'img') avatars.push({ src: attrs.src, excluded })
      if (attrs.class?.split(' ').includes('n-space') && !excluded) outsideSpaces += 1
    }
    for (const child of node.children || []) walk(child, excluded)
  }
  walk(parseHtml(html))
  return { markers, avatars, outsideSpaces }
}

afterEach(() => {
  for (const store of stores) store.$dispose()
  stores.length = 0
})

describe('plan facility display order', () => {
  it.each(['main', 0])(
    'follows local training placement without changing plan %s',
    async (subPlan) => {
      const pinia = createPinia()
      function editorApp() {
        const app = createSSRApp(PlanEditor)
        app.use(pinia)
        app.provide('loaded', ref(false))
        app.provide('facility', ref(''))
        app.provide('planEditLocked', ref(false))
        return app
      }
      const app = editorApp()
      const config = app.runWithContext(() => useConfigStore())
      const plan = app.runWithContext(() => usePlanStore())
      stores.push(config, plan)
      config.maa_mall_buy = []
      config.maa_mall_blacklist = []
      plan.plan = plan.fill_empty({})
      const conf = Object.fromEntries(
        Object.entries(plan.build_plan().conf).map(([key, value]) => [
          key,
          typeof value === 'string' ? [] : value
        ])
      )
      conf.free_blacklist = []
      plan.backup_plans = [{ name: '副表', plan: plan.fill_empty({}), conf }]
      plan.sub_plan = subPlan
      plan.current_plan.contact.plans[0].agent = '办公室干员'
      plan.current_plan.train.plans[0].agent = '协助干员'
      plan.current_plan.train.plans[1].agent = '训练干员'
      plan.set_advanced_settings_source(() => config.build_advanced_settings())
      const original = JSON.stringify(plan.build_plan())
      for (const enabled of [false, true, false]) {
        config.swap_contact_train = enabled
        const html = await renderToString(editorApp())
        const regions = updateDropRegions(html)
        expect(regions.markers).toEqual(['outer'])
        expect(regions.avatars.every((avatar) => avatar.excluded)).toBe(true)
        expect(regions.outsideSpaces).toBeGreaterThan(0)
        const office = html.indexOf('办公室干员.webp')
        const training = html.indexOf('协助干员.webp')
        expect(office).toBeGreaterThan(-1)
        expect(training).toBeGreaterThan(-1)
        expect(training < office).toBe(enabled)
        expect(html).toContain('训练干员.webp')
        expect(html).toContain('协助位')
        expect(html).toContain('训练位')
        expect(html.indexOf('会客室')).toBeLessThan(html.indexOf('加工站'))
        expect(html.indexOf('加工站')).toBeLessThan(Math.min(office, training))
        expect(JSON.stringify(plan.build_plan())).toBe(original)
        expect(plan.build_plan().advanced_settings).not.toHaveProperty('swap_contact_train')
        expect(config.build_config().swap_contact_train).toBe(enabled)
      }
    }
  )
})
