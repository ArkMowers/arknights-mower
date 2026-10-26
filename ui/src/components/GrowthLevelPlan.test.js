import { describe, expect, it, vi } from 'vitest'
import { effectScope, nextTick, reactive } from 'vue'
import GrowthLevelPlan from './GrowthLevelPlan.vue'

vi.mock('vue', async (original) => ({
  ...(await original()),
  useSSRContext: () => ({ modules: new Set() })
}))

function setup(overrides = {}) {
  const props = reactive({
    operator: {
      char_id: 'test',
      rarity: 6,
      elite: 2,
      level: 1,
      level_goals: [
        { id: 'elite2', elite: 2, level: 1, label: '精二 1 级', summary: {} },
        { id: 'elite2_max', elite: 2, level: 90, label: '精二 90 级', summary: {} }
      ]
    },
    selectedKey: null,
    requiredKey: null,
    saving: false,
    applyTarget: vi.fn(async (key) => {
      props.selectedKey = key
    }),
    ...overrides
  })
  const scope = effectScope()
  const component = scope.run(() => GrowthLevelPlan.setup(props, { expose: vi.fn() }))
  return { props, component, stop: () => scope.stop() }
}

describe('等级与精英化里程碑', () => {
  it('点击节点立即提交目标，保存期间忽略重复交互', async () => {
    const { props, component, stop } = setup({
      operator: {
        char_id: 'test',
        rarity: 6,
        level_goals: [
          { id: 'elite2', elite: 2, level: 1, label: '精二 1 级', summary: {} },
          { id: 'elite2_max', elite: 2, level: 90, label: '精二 90 级', summary: {} }
        ]
      },
      selectedKey: null
    })
    const pending = component.updateDraft(1)
    component.updateDraft(2)
    expect(props.applyTarget).toHaveBeenCalledExactlyOnceWith('elite2')
    await pending
    await component.updateDraft(2)
    expect(props.applyTarget).toHaveBeenLastCalledWith('elite2_max')
    props.selectedKey = 'elite2'
    await nextTick()
    expect(component.draftIndex.value).toBe(1)
    stop()
  })

  it('保存被拒绝或失败后恢复已保存目标', async () => {
    const { props, component, stop } = setup({ selectedKey: 'elite2' })
    props.applyTarget = vi.fn(async () => {})
    await component.updateDraft(0)
    expect(component.draftIndex.value).toBe(1)
    props.applyTarget = vi.fn(async () => {
      throw new Error('offline')
    })
    await expect(component.updateDraft(2)).rejects.toThrow('offline')
    expect(component.draftIndex.value).toBe(1)
    expect(component.committing.value).toBe(false)
    stop()
  })

  it('已达成节点标绿，已规划目标节点标红，当前节点标记在轨道上', () => {
    const { component, stop } = setup({ selectedKey: 'elite2_max' })
    const nodes = component.nodeList.value
    expect(nodes.map((node) => node.short)).toEqual(['精二 1', '精二 90'])
    expect(nodes.map((node) => node.done)).toEqual([true, false])
    expect(nodes.map((node) => node.current)).toEqual([true, false])
    expect(nodes.map((node) => node.target)).toEqual([false, true])
    expect(nodes.map((node) => node.selectable)).toEqual([false, false])
    expect(component.railInset.value).toBe('25%')
    expect(component.railFill.value).toBe('0%')
    stop()
  })

  it('可选中节点点击后提交为该目标', async () => {
    const { props, component, stop } = setup()
    const nodes = component.nodeList.value
    expect(nodes.map((node) => node.selectable)).toEqual([false, true])
    const selectableNode = nodes.find((node) => node.selectable)
    await component.selectNode(selectableNode)
    expect(props.applyTarget).toHaveBeenCalledExactlyOnceWith('elite2_max')
    stop()
  })

  it('已完成节点保持惰性，点击不会提交目标也不改变草稿', () => {
    const { props, component, stop } = setup()
    const nodes = component.nodeList.value
    expect(nodes[0].done).toBe(true)
    expect(nodes[0].selectable).toBe(false)
    component.selectNode(nodes[0])
    expect(props.applyTarget).not.toHaveBeenCalled()
    expect(component.draftIndex.value).toBe(0)
    stop()
  })

  it('再次点击当前目标会清除目标', async () => {
    const { props, component, stop } = setup({ selectedKey: 'elite2_max' })
    const targetNode = component.nodeList.value.find((node) => node.target)
    expect(targetNode.selectable).toBe(false)
    await component.selectNode(targetNode)
    expect(props.applyTarget).toHaveBeenCalledExactlyOnceWith(null)
    expect(component.draftIndex.value).toBe(0)
    stop()
  })

  it('已完成的状态不再显示为目标', () => {
    const { component, stop } = setup({ selectedKey: 'elite2' })
    const nodes = component.nodeList.value
    expect(nodes[0].done).toBe(true)
    expect(nodes[0].target).toBe(false)
    stop()
  })

  it('三星隐藏前置节点后仍显示已选精一目标和独立材料', () => {
    const summary = { materials: [{ id: '4001', count: 10000 }] }
    const { component, stop } = setup({
      operator: {
        char_id: 'low',
        rarity: 3,
        elite: 1,
        level: 1,
        level_goals: [
          { id: 'elite1', elite: 1, level: 1, label: '精一 1 级', summary },
          { id: 'level_max', elite: 1, level: 55, label: '满练', summary: {} }
        ]
      },
      selectedKey: 'elite1',
      requiredKey: null
    })
    expect(component.draftIndex.value).toBe(0)
    expect(component.displayedChoice.value.label).toBe('精一 1 级')
    expect(component.displayedChoice.value.summary).toEqual(summary)
    expect(component.nodeList.value.map((node) => node.key)).toEqual(['level_max'])
    stop()
  })

  it.each([1, 2, 3])('%i 星只显示满练节点，保留内部前置', async (rarity) => {
    const prerequisite = { id: 'elite1', elite: 1, level: 1, label: '精一 1 级' }
    const maximum = {
      id: 'level_max',
      elite: rarity === 3 ? 1 : 0,
      level: rarity === 3 ? 55 : 30,
      label: '满练',
      summary: {}
    }
    const { props, component, stop } = setup({
      operator: {
        char_id: 'low',
        rarity,
        level_goals: rarity === 3 ? [prerequisite, maximum] : [maximum]
      },
      requiredKey: rarity === 3 ? 'elite1' : null
    })
    expect(component.choices.value.map((choice) => choice.key)).toEqual(['level_max'])
    expect(component.nodeList.value.map((node) => node.key)).toEqual(['level_max'])
    expect(component.nodeList.value[0].selectable).toBe(true)
    if (rarity === 3) expect(component.allChoices.value[0].key).toBe('elite1')
    await component.updateDraft(1)
    expect(props.applyTarget).toHaveBeenCalledExactlyOnceWith('level_max')
    stop()
  })

  it('当前等级介于两个里程碑之间时按等级插值显示进度', () => {
    const { component, stop } = setup({
      operator: {
        char_id: 'mid',
        rarity: 6,
        elite: 2,
        level: 80,
        level_goals: [
          { id: 'elite2', elite: 2, level: 1, label: '精二 1 级', summary: {} },
          { id: 'elite2_module', elite: 2, level: 60, label: '精二 60 级', summary: {} },
          { id: 'elite2_max', elite: 2, level: 90, label: '精二 90 级', summary: {} }
        ]
      },
      selectedKey: 'elite2_max'
    })
    expect(component.progress.value.ratio).toBeCloseTo(0.8333, 3)
    expect(component.progress.value.done).toBe(false)
    expect(parseFloat(component.railFill.value)).toBeCloseTo(83.33, 1)
    expect(component.idle.value).toBe(false)
    expect(component.currentOnNode.value).toBe(false)
    stop()
  })

  it('当前练度正好落在节点上时不叠加当前点', () => {
    const { component, stop } = setup({
      operator: {
        char_id: 'node',
        rarity: 6,
        elite: 2,
        level: 1,
        level_goals: [
          { id: 'elite1', elite: 1, level: 1, label: '精一 1 级', summary: {} },
          { id: 'elite2', elite: 2, level: 1, label: '精二 1 级', summary: {} },
          { id: 'elite2_max', elite: 2, level: 90, label: '精二 90 级', summary: {} }
        ]
      },
      selectedKey: 'elite2_max'
    })
    expect(component.currentOnNode.value).toBe(true)
    stop()
  })

  it('当前等级到目标等级之间留出待完成区间', () => {
    const { component, stop } = setup({
      operator: {
        char_id: 'mid',
        rarity: 6,
        elite: 2,
        level: 80,
        level_goals: [
          { id: 'elite2', elite: 2, level: 1, label: '精二 1 级', summary: {} },
          { id: 'elite2_module', elite: 2, level: 60, label: '精二 60 级', summary: {} },
          { id: 'elite2_max', elite: 2, level: 90, label: '精二 90 级', summary: {} }
        ]
      },
      selectedKey: 'elite2_max'
    })
    const segment = component.goalSegment.value
    expect(segment).not.toBeNull()
    expect(parseFloat(segment.left)).toBeCloseTo(83.33, 1)
    expect(parseFloat(segment.width)).toBeCloseTo(16.67, 1)
    stop()
  })

  it('无练度且未选目标时进入待规划状态', () => {
    const { component, stop } = setup({
      operator: {
        char_id: 'fresh',
        rarity: 6,
        elite: 0,
        level: 1,
        level_goals: [
          { id: 'elite1', elite: 1, level: 1, label: '精一 1 级', summary: {} },
          { id: 'elite2', elite: 2, level: 1, label: '精二 1 级', summary: {} }
        ]
      }
    })
    expect(component.idle.value).toBe(true)
    expect(component.progress.value.ratio).toBe(0)
    expect(component.nodeList.value.every((node) => !node.done && !node.target)).toBe(true)
    expect(component.nodeList.value.every((node) => node.selectable)).toBe(true)
    stop()
  })
})
