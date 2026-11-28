import { describe, expect, it, vi } from 'vitest'
import { effectScope, reactive } from 'vue'
import GrowthOverview from './GrowthOverview.vue'

vi.mock('vue', async (original) => ({
  ...(await original()),
  useSSRContext: () => ({ modules: new Set() })
}))

describe('BOX 概览精二率', () => {
  it('仅用可精二的已拥有干员作分母，并随统计更新', () => {
    const scope = effectScope()
    const props = reactive({ rosterStats: { owned: 18, elite2: 3, elite2_eligible: 6 } })
    const component = scope.run(() =>
      GrowthOverview.setup(props, { expose: vi.fn(), emit: vi.fn() })
    )
    try {
      expect(component.elitePercent.value).toBe(50)
      props.rosterStats = { owned: 10, elite2: 2, elite2_eligible: 3 }
      expect(component.elitePercent.value).toBe(67)
      props.rosterStats = { owned: 5, elite2: 0, elite2_eligible: 0 }
      expect(component.elitePercent.value).toBe(0)
      props.rosterStats = { owned: 0, elite2: 0, elite2_eligible: 0 }
      expect(component.elitePercent.value).toBe(0)
    } finally {
      scope.stop()
    }
  })
})
