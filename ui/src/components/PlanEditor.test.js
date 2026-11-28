import { renderToString } from '@vue/server-renderer'
import { createSSRApp, ref, h } from 'vue'
import { createPinia } from 'pinia'
import { parse as parseHtml } from '@vue/compiler-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import PlanEditor from './PlanEditor.vue'
import { useConfigStore } from '@/stores/config'
import { usePlanStore } from '@/stores/plan'

vi.mock('naive-ui', async (importOriginal) => ({
  ...(await importOriginal()),
  NSelect: {
    props: ['disabled'],
    setup: (props) => () => h('select', { disabled: props.disabled })
  }
}))
vi.mock('./SlickOperatorSelect.vue', () => ({ default: { render: () => h('select') } }))

vi.mock('./HelpText.vue', () => ({ default: { render: () => h('span') } }))

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
    'follows all local room permutations without changing plan %s',
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
      plan.current_plan.recycle.plans[0].agent = '回收干员一'
      plan.current_plan.recycle.plans[1].agent = '回收干员二'
      plan.set_advanced_settings_source(() => config.build_advanced_settings())
      const original = JSON.stringify(plan.build_plan())
      const orders = [
        ['contact', 'train', 'recycle'],
        ['contact', 'recycle', 'train'],
        ['train', 'contact', 'recycle'],
        ['train', 'recycle', 'contact'],
        ['recycle', 'contact', 'train'],
        ['recycle', 'train', 'contact']
      ]
      for (const order of orders) {
        config.right_side_room_order = order
        const html = await renderToString(editorApp())
        const regions = updateDropRegions(html)
        expect(regions.markers).toEqual(['outer'])
        expect(regions.avatars.every((avatar) => avatar.excluded)).toBe(true)
        expect(regions.outsideSpaces).toBeGreaterThan(0)
        const office = html.indexOf('办公室干员.webp')
        const training = html.indexOf('协助干员.webp')
        expect(office).toBeGreaterThan(-1)
        expect(training).toBeGreaterThan(-1)
        const recycling = html.indexOf('回收干员一.webp')
        const positions = { contact: office, train: training, recycle: recycling }
        expect(order.map((room) => positions[room])).toEqual(
          Object.values(positions).sort((a, b) => a - b)
        )
        expect(html).toContain('回收干员二.webp')
        expect(
          html.match(/class="right_contain right-room-draggable" draggable="true"/g)
        ).toHaveLength(3)
        expect(html).toContain('训练干员.webp')
        expect(html).toContain('协助位')
        expect(html).toContain('训练位')
        expect(html.indexOf('会客室')).toBeLessThan(html.indexOf('加工站'))
        expect(html.indexOf('加工站')).toBeLessThan(Math.min(office, training, recycling))
        expect(JSON.stringify(plan.build_plan())).toBe(original)
        expect(plan.build_plan().advanced_settings).not.toHaveProperty('swap_contact_train')
        expect(plan.build_plan().advanced_settings).not.toHaveProperty('right_side_room_order')
        expect(config.build_config().right_side_room_order).toEqual(order)
        expect(config.build_config()).not.toHaveProperty('swap_contact_train')
      }
    }
  )
})

it.each([false, true])('renders group rows, segmented avatar and edit lock %s', async (locked) => {
  const app = createSSRApp(PlanEditor)
  app.use(createPinia())
  app.provide('loaded', ref(false))
  app.provide('facility', ref('contact'))
  app.provide('planEditLocked', ref(locked))
  const config = app.runWithContext(() => useConfigStore())
  const plan = app.runWithContext(() => usePlanStore())
  stores.push(config, plan)
  config.maa_mall_buy = []
  config.maa_mall_blacklist = []
  plan.plan = plan.fill_empty({})
  Object.assign(plan.current_plan.contact.plans[0], {
    agent: '讯使',
    group: '甲',
    replacement: ['红'],
    group_bindings: [{ group: '乙', replacement: ['黑角'] }]
  })
  const html = await renderToString(app)
  expect(
    html.match(new RegExp(`class="right_contain right-room-draggable" draggable="${!locked}"`, 'g'))
  ).toHaveLength(3)
  expect(html).toContain('rowspan="2"')
  expect(html).toContain('linear-gradient(to right')
  expect(html).toContain('50%')
  expect(html).toContain('background-size:100% 5px')
  expect(html).not.toContain('border-image')
  const buttons = html.match(/<button\b[^>]*aria-label="(?:新增绑组|删除此绑组)"[^>]*>/g)
  expect(buttons).toHaveLength(2)
  expect(buttons.every((button) => /\bdisabled(?:[\s=>])/.test(button))).toBe(locked)
  expect(html).toContain('value="甲"')
  expect(html).toContain('value="乙"')
})

it.each(['main', 0])(
  'shows facility import only in backup %s and copies independently',
  async (subPlan) => {
    const app = createSSRApp(PlanEditor)
    app.use(createPinia())
    app.provide('loaded', ref(false))
    app.provide('facility', ref('contact'))
    const locked = ref(false)
    app.provide('planEditLocked', locked)
    const config = app.runWithContext(() => useConfigStore())
    const plan = app.runWithContext(() => usePlanStore())
    stores.push(config, plan)
    config.maa_mall_buy = []
    config.maa_mall_blacklist = []
    plan.plan = plan.fill_empty({})
    Object.assign(plan.plan.contact, {
      name: '办公室',
      product: '',
      plans: [
        {
          agent: '讯使',
          group: '甲',
          replacement: ['红'],
          group_bindings: [{ group: '乙', replacement: ['黑角'] }]
        }
      ]
    })
    plan.backup_plans = [{ plan: plan.fill_empty({}), trigger: { left: 'True' } }]
    plan.sub_plan = subPlan
    const before = JSON.stringify(plan.plan)
    const untouched = JSON.stringify(plan.backup_plans[0].plan.meeting)
    for (const value of [false, true]) {
      locked.value = value
      const html = await renderToString(app)
      expect(html.includes('从主表导入此设施')).toBe(subPlan !== 'main')
      if (subPlan !== 'main') {
        const button = html.match(
          /<button\b[^>]*title="用主表此设施的配置覆盖当前副表的此设施"[^>]*>/
        )[0]
        expect(/\bdisabled(?:[\s=>])/.test(button)).toBe(value)
      }
    }
    plan.import_main_facility('contact')
    expect(JSON.stringify(plan.plan)).toBe(before)
    if (subPlan !== 'main') {
      expect(plan.current_plan.contact).toEqual(plan.plan.contact)
      plan.current_plan.contact.plans[0].group_bindings[0].replacement.push('砾')
      expect(JSON.stringify(plan.plan)).toBe(before)
      expect(JSON.stringify(plan.backup_plans[0].plan.meeting)).toBe(untouched)
      expect(plan.backup_plans[0].trigger).toEqual({ left: 'True' })
    }
  }
)
