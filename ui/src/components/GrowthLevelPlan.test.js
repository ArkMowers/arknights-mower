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

describe('等级滑条自动保存', () => {
  it('拖动仅更新局部草稿，松开提交最终节点一次', async () => {
    const { props, component, stop } = setup()
    const marks = component.marks.value
    component.dragging.value = true
    component.updateDraft(1)
    component.updateDraft(2)
    await nextTick()
    expect(component.draftChoice.value.label).toBe('精二 90 级')
    expect(component.marks.value).toBe(marks)
    expect(props.applyTarget).not.toHaveBeenCalled()
    await component.finishDrag()
    await component.finishDrag()
    expect(props.applyTarget).toHaveBeenCalledExactlyOnceWith('elite2_max')
    expect(component.draftIndex.value).toBe(2)
    stop()
  })

  it('点击节点及键盘变更保存，保存期间忽略重复交互', async () => {
    const { props, component, stop } = setup()
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

  it('三星隐藏前置节点后仍显示精一目标和独立材料', () => {
    const summary = { materials: [{ id: '4001', count: 10000 }] }
    const { component, stop } = setup({
      operator: {
        char_id: 'low',
        rarity: 3,
        level_goals: [
          { id: 'elite1', elite: 1, level: 1, label: '精一 1 级', summary },
          { id: 'level_max', elite: 1, level: 55, label: '满练', summary: {} }
        ]
      },
      selectedKey: 'elite1',
      requiredKey: 'elite1'
    })
    expect(component.draftIndex.value).toBe(0)
    expect(component.displayedChoice.value.label).toBe('精一 1 级')
    expect(component.displayedChoice.value.summary).toEqual(summary)
    expect(Object.keys(component.marks.value)).toEqual(['0', '1'])
    stop()
  })

  it.each([1, 2, 3])('%i 星只显示未规划和满练节点，保留内部前置', async (rarity) => {
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
    expect(Object.keys(component.marks.value)).toEqual(['0', '1'])
    if (rarity === 3) expect(component.allChoices.value[0].key).toBe('elite1')
    await component.updateDraft(1)
    expect(props.applyTarget).toHaveBeenCalledExactlyOnceWith('level_max')
    stop()
  })
})
