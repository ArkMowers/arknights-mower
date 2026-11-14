import { afterEach, describe, expect, it, vi } from 'vitest'
import { createSSRApp, effectScope, h, ref } from 'vue'
import { renderToString } from 'vue/server-renderer'
import Component from './MaaRogue.vue'

const state = vi.hoisted(() => ({ config: {}, selects: [], checkboxes: [] }))
vi.mock('vue', async (original) => ({
  ...(await original()),
  inject: () => false,
  useSSRContext: () => ({ modules: new Set() })
}))
vi.mock('@/stores/config', () => ({ useConfigStore: () => state.config }))
vi.mock('@/stores/plan', () => ({ usePlanStore: () => ({ operators: { value: [] } }) }))
vi.mock('pinia', () => ({ storeToRefs: (store) => store }))
vi.mock('@/utils/op_select', () => ({ render_op_option: vi.fn(), render_op_label: vi.fn() }))
vi.mock('./HelpText.vue', () => ({ default: { render: () => null } }))
vi.mock('./MaaTaskStatus.vue', () => ({
  default: {
    props: ['kind', 'settings'],
    setup: (props) => () => h('span', { 'data-status-kind': props.kind })
  }
}))
vi.mock('naive-ui', () => {
  const wrapper = {
    setup:
      (_, { slots }) =>
      () =>
        h('div', slots.default?.())
  }
  return {
    ...Object.fromEntries(
      ['NButton', 'NFlex', 'NForm', 'NFormItem', 'NInput', 'NText'].map((name) => [name, wrapper])
    ),
    NCheckbox: {
      props: ['checked'],
      emits: ['update:checked'],
      setup(props, { slots, emit }) {
        return () => {
          const children = slots.default?.()
          state.checkboxes.push({
            label: children?.map((child) => child.children).join(''),
            checked: props.checked,
            update: (value) => emit('update:checked', value)
          })
          return h('label', children)
        }
      }
    },
    NSelect: {
      props: ['options', 'value', 'disabled'],
      setup(props) {
        state.selects.push(props)
        return () => null
      }
    }
  }
})
let scope
afterEach(() => scope?.stop())

describe('BlackFlow opening configuration', () => {
  function setup() {
    state.config = {
      maa_rg_theme: ref('BlackFlow'),
      rogue: ref({
        mode: 30003,
        squad: '',
        blackflow_start_rewards: 0,
        blackflow_start_animals: []
      })
    }
    scope = effectScope()
    return scope.run(() => Component.setup({}, { expose: () => {} }))
  }
  it('saves selected rewards as the documented mask and restores their names', () => {
    const component = setup()
    component.blackflow_reward_values.value = ['unnumbered_item', 'golden_crow']
    expect(state.config.rogue.value.blackflow_start_rewards).toBe(2049)
    state.config.rogue.value.blackflow_start_rewards = 3
    expect(component.blackflow_reward_values.value).toEqual(['unnumbered_item', 'survey_advance'])
  })
  it('preserves duplicate animal requirements and supports clearing either slot', () => {
    const component = setup()
    component.set_animal(0, 'swaddled_cat')
    component.set_animal(1, 'swaddled_cat')
    expect(state.config.rogue.value.blackflow_start_animals).toEqual([
      'swaddled_cat',
      'swaddled_cat'
    ])
    component.set_animal(0, null)
    expect(state.config.rogue.value.blackflow_start_animals).toEqual(['swaddled_cat'])
  })
  it('applies flight controls only to their own mode and preserves custom openings', () => {
    const component = setup()
    const rogue = state.config.rogue.value
    rogue.squad = '指挥分队'
    rogue.blackflow_fast_flight = true
    rogue.blackflow_start_run_fast_flight = true
    expect(component.prep_flight.value).toBe(true)
    expect(component.exp_flight.value).toBe(false)
    rogue.mode = 0
    expect(component.exp_flight.value).toBe(true)
    expect(component.prep_flight.value).toBe(false)
    rogue.blackflow_fast_flight = false
    expect(component.exp_flight.value).toBe(false)
    expect(rogue.squad).toBe('指挥分队')
    state.config.maa_rg_theme.value = 'Sami'
    expect(component.exp_flight.value).toBe(false)
    expect(component.prep_flight.value).toBe(false)
  })
  it('starts a new opening round only through an explicit request', () => {
    const component = setup()
    expect(state.config.rogue.value.blackflow_start_run_id).toBeUndefined()
    component.restart_blackflow()
    const first = state.config.rogue.value.blackflow_start_run_id
    expect(first).toMatch(/^[a-f0-9]{32}$/)
    component.restart_blackflow()
    expect(state.config.rogue.value.blackflow_start_run_id).not.toBe(first)
  })
  it('keeps boss and opening rounds independent and does not restart on pause toggles', () => {
    const component = setup()
    const rogue = state.config.rogue.value
    rogue.mode = 0
    rogue.stop_at_final_boss = true
    expect(component.boss_stop.value).toBe(true)
    expect(rogue.blackflow_boss_run_id).toBeUndefined()
    component.restart_blackflow('boss')
    const boss = rogue.blackflow_boss_run_id
    expect(boss).toMatch(/^[a-f0-9]{32}$/)
    expect(rogue.blackflow_start_run_id).toBeUndefined()
    rogue.stop_at_final_boss = false
    expect(component.boss_stop.value).toBe(false)
    rogue.stop_at_final_boss = true
    expect(component.boss_stop.value).toBe(true)
    expect(rogue.blackflow_boss_run_id).toBe(boss)
    component.restart_blackflow()
    expect(rogue.blackflow_boss_run_id).toBe(boss)
    expect(rogue.blackflow_start_run_id).toMatch(/^[a-f0-9]{32}$/)
    rogue.blackflow_fast_flight = true
    expect(component.boss_stop.value).toBe(false)
  })
  it.each([
    ['burn', true, false],
    ['burn_with_investment', true, true],
    ['', false, true],
    ['ending2', false, true],
    ['ending3', false, true]
  ])('migrates %s only when selecting BlackFlow exp', (strategy, flight, investment) => {
    setup()
    state.config.maa_rg_theme.value = 'Sami'
    Object.assign(state.config.rogue.value, {
      mode: 0,
      squad: '指挥分队',
      blackflow_strategy: strategy,
      blackflow_fast_flight: false,
      investment_enabled: true
    })
    expect(state.config.rogue.value.blackflow_strategy).toBe(strategy)
    state.config.maa_rg_theme.value = 'BlackFlow'
    expect(state.config.rogue.value.blackflow_strategy).toBe('ending1')
    expect(state.config.rogue.value.blackflow_fast_flight).toBe(flight)
    expect(state.config.rogue.value.investment_enabled).toBe(investment)
    expect(state.config.rogue.value.squad).toBe('指挥分队')
  })
  it.each([false, true])(
    'offers only ending1 and binds flight and boss help (%s)',
    async (flight) => {
      setup()
      state.selects = []
      state.checkboxes = []
      Object.assign(state.config.rogue.value, {
        mode: 0,
        blackflow_strategy: 'ending1',
        blackflow_fast_flight: flight,
        stop_at_final_boss: true
      })
      const html = await renderToString(createSSRApp(Component))
      const ending = state.selects.find(({ value }) => value === 'ending1')
      expect(ending.options).toEqual([{ label: '一结局 · 强制重启', value: 'ending1' }])
      expect(ending.disabled).toBe(flight)
      expect(html).toContain('第五层 BOSS 编队页停止')
      expect(html).toContain('取消快速飞三层后按第一结局推进')
      expect(html.includes('data-status-kind="blackflow_boss"')).toBe(!flight)
      expect(html.includes('重新执行到第五层 BOSS 前')).toBe(!flight)
      const pause = state.checkboxes.find(({ label }) => label === '在第五层 BOSS 前暂停')
      expect(pause.checked).toBe(true)
      pause.update(false)
      expect(state.config.rogue.value.stop_at_final_boss).toBe(false)
      pause.update(true)
      expect(state.config.rogue.value.stop_at_final_boss).toBe(true)
    }
  )
})
