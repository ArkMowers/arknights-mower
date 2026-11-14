import { describe, expect, it, vi } from 'vitest'
import { effectScope, reactive } from 'vue'
import GrowthMaterialsView from './GrowthMaterialsView.vue'

vi.mock('vue', async (original) => ({
  ...(await original()),
  useSSRContext: () => ({ modules: new Set() })
}))

function setup(summary) {
  const scope = effectScope()
  const component = scope.run(() =>
    GrowthMaterialsView.setup(reactive({ summary }), { expose: vi.fn(), emit: vi.fn() })
  )
  return { component, stop: () => scope.stop() }
}

describe('材料页成品与合成状态', () => {
  it('底料足够但成品未备齐时显示可合成，不能从空原料缺口推断现货充足', () => {
    const { component, stop } = setup({
      available: false,
      craftable: true,
      materials: [{ id: '30013', owned: 0, required: 2 }],
      missing: []
    })
    expect(component.status.value).toBe('可合成')
    expect(component.statusType.value).toBe('warning')
    expect(component.readableLine.value).toContain('成品尚未备齐')
    stop()
  })

  it('仅缺龙门币时保留资源待备提示', () => {
    const { component, stop } = setup({
      available: false,
      craftable: false,
      materials: [
        { id: '30013', owned: 2, required: 2 },
        { id: '4001', owned: 0, required: 10000 }
      ],
      missing: [{ id: '4001', count: 10000 }]
    })
    expect(component.status.value).toBe('资源待备')
    expect(component.statusType.value).toBe('warning')
    expect(component.readableLine.value).toContain('资源缺口 1 项')
    expect(component.readyCount.value).toBe(1)
    expect(component.materialRows.value).toHaveLength(1)
    expect(component.directRows.value).toHaveLength(2)
    stop()
  })

  it('成品库存覆盖需求时显示材料充足', () => {
    const { component, stop } = setup({
      available: true,
      craftable: true,
      materials: [{ id: '30013', owned: 2, required: 2 }],
      missing: []
    })
    expect(component.status.value).toBe('材料充足')
    expect(component.statusType.value).toBe('success')
    expect(component.readableLine.value).toBe('库存可以覆盖当前计划')
    stop()
  })
})
