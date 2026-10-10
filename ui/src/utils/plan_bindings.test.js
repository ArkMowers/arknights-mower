import { describe, expect, it } from 'vitest'
import { createPinia } from 'pinia'
import { createApp, ref } from 'vue'
import { usePlanStore } from '@/stores/plan'
import { replace_plan_operators } from './plan_edit'
import {
  addPlanBinding,
  removePlanBinding,
  bindingColorStyle,
  planReplacements
} from './plan_bindings'

describe('operator group bindings', () => {
  it('collects replacements once without changing individual binding candidates', () => {
    const slot = {
      agent: '讯使',
      group: '甲',
      replacement: ['红', '黑角'],
      group_bindings: [
        { group: '乙', replacement: ['黑角', '砾'] },
        { group: '丙', replacement: ['砾', 'Free'] }
      ]
    }
    const before = structuredClone(slot)
    const replacements = planReplacements(slot)
    expect(replacements).toEqual(['红', '黑角', '砾', 'Free'])
    replacements.splice(0)
    expect(slot).toEqual(before)
    expect(planReplacements({})).toEqual([])
  })
  it('adds independent columns and promotes the next column when deleting the first', () => {
    const slot = { agent: '清流', group: '甲', replacement: ['结城理'] }
    addPlanBinding(slot)
    addPlanBinding(slot)
    slot.group_bindings[0].group = '乙'
    slot.group_bindings[0].replacement.push('酒神')
    expect(slot.group_bindings[1]).toEqual({ group: '', replacement: [] })
    expect(slot.replacement).toEqual(['结城理'])
    removePlanBinding(slot, 2)
    removePlanBinding(slot, 0)
    expect(slot).toEqual({ agent: '清流', group: '乙', replacement: ['酒神'] })
  })

  it('uses one equal segment per column, including unfinished columns', () => {
    const slot = { group: '甲', group_bindings: [{ group: '乙' }, { group: '' }] }
    const style = bindingColorStyle(slot, { 甲: 'red', 乙: 'blue' })
    expect(style.backgroundImage).toBe(
      'linear-gradient(to right, red 0%, red 33.333333333333336%, blue 33.333333333333336%, blue 66.66666666666667%, transparent 66.66666666666667%, transparent 100%)'
    )
    expect(style.backgroundSize).toBe('100% 5px')
    expect(style.backgroundRepeat).toBe('no-repeat')
    expect(style.backgroundPosition).toBe('left bottom')
    expect(style.paddingBottom).toBe('5px')
    expect(style).not.toHaveProperty('borderImage')
    expect(bindingColorStyle({ group: '甲' }, { 甲: 'red' })).toEqual({
      borderBottom: '5px solid red'
    })
  })

  it.each(['main', 0])(
    'retains every column in exported plan %s and uses that plan’s groups',
    (subPlan) => {
      const app = createApp({})
      app.use(createPinia())
      app.provide('loaded', ref(false))
      const store = app.runWithContext(() => usePlanStore())
      store.plan = store.fill_empty({})
      store.backup_plans = [
        {
          name: '副表',
          plan: store.fill_empty({}),
          conf: {
            ...Object.fromEntries(Object.keys(store.build_plan().conf).map((key) => [key, []])),
            free_blacklist: []
          }
        }
      ]
      store.sub_plan = subPlan
      const slot = store.current_plan.contact.plans[0]
      Object.assign(slot, { agent: '清流', group: '甲', replacement: ['结城理'] })
      addPlanBinding(slot)
      Object.assign(slot.group_bindings[0], { group: '乙', replacement: ['酒神'] })
      expect(store.groups).toEqual(['甲', '乙'])
      const exported = store.build_plan()
      const selected = subPlan === 'main' ? exported.plan1 : exported.backup_plans[0].plan
      expect(selected.contact.plans[0].group_bindings).toEqual([
        { group: '乙', replacement: ['酒神'] }
      ])
      expect(store.fill_empty(JSON.parse(JSON.stringify(selected))).contact.plans[0]).toEqual(slot)
      store.$dispose()
    }
  )
})

it('operator replacement updates every binding while retaining groups', () => {
  const plan = {
    contact: {
      plans: [
        {
          agent: '讯使',
          group: '甲',
          replacement: ['红'],
          group_bindings: [{ group: '乙', replacement: ['红', '黑角'] }]
        }
      ]
    }
  }
  replace_plan_operators(plan, '红', '砾')
  expect(plan.contact.plans[0].replacement).toEqual(['砾'])
  expect(plan.contact.plans[0].group_bindings).toEqual([
    { group: '乙', replacement: ['砾', '黑角'] }
  ])
})

it('shares colors across main and backup tables independently of the selected table', () => {
  const app = createApp({})
  app.use(createPinia())
  app.provide('loaded', ref(false))
  const store = app.runWithContext(() => usePlanStore())
  store.plan = store.fill_empty({})
  Object.assign(store.plan.contact.plans[0], {
    agent: '讯使',
    group: '甲',
    group_bindings: [{ group: '乙', replacement: ['黑角'] }]
  })
  store.backup_plans = [{ plan: store.fill_empty({}) }, { plan: store.fill_empty({}) }]
  Object.assign(store.backup_plans[0].plan.central.plans[0], { agent: '银灰', group: '丙' })
  Object.assign(store.backup_plans[0].plan.contact.plans[0], { agent: '讯使', group: '乙' })
  Object.assign(store.backup_plans[1].plan.contact.plans[0], { agent: '讯使', group: '甲' })
  const colors = { ...store.group_colors }
  expect(new Set([colors.甲, colors.乙, colors.丙]).size).toBe(3)
  expect(colors['']).toBe('transparent')
  for (const selected of ['main', 0, 1, 'main']) {
    store.sub_plan = selected
    expect(store.group_colors).toEqual(colors)
    expect(store.all_groups).toEqual(['甲', '乙', '丙'])
  }
  store.sub_plan = 0
  expect(store.groups).toEqual(['丙', '乙'])
  store.backup_plans[1].plan.contact.plans[0].group = '丁'
  expect(store.group_colors).toHaveProperty('丁')
  expect(store.group_colors).toHaveProperty('甲')
  expect(store.all_groups).toEqual(['甲', '乙', '丙', '丁'])
  store.$dispose()
})
