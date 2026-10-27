import { afterEach, describe, expect, it, vi } from 'vitest'
import { effectScope, ref } from 'vue'
import Component from './MaaRogue.vue'

const state = vi.hoisted(() => ({ config: {} }))
vi.mock('vue', async (original) => ({
  ...(await original()),
  inject: () => false,
  useSSRContext: () => ({ modules: new Set() })
}))
vi.mock('@/stores/config', () => ({ useConfigStore: () => state.config }))
vi.mock('@/stores/plan', () => ({ usePlanStore: () => ({ operators: { value: [] } }) }))
vi.mock('pinia', () => ({ storeToRefs: (store) => store }))
vi.mock('@/utils/op_select', () => ({ render_op_option: vi.fn(), render_op_label: vi.fn() }))
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
})
