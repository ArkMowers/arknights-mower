import { describe, expect, it, vi } from 'vitest'
import { effectScope } from 'vue'
vi.mock('naive-ui', () => ({ useThemeVars: () => ({ value: { textColor1: '#fff' } }) }))
import GrowthSurveyFilters from './GrowthSurveyFilters.vue'
import { defaultSurveyFilters, surveyThresholds } from '@/utils/growthSurvey'

vi.mock('vue', async (original) => ({
  ...(await original()),
  useSSRContext: () => ({ modules: new Set() })
}))
function setup(filters = defaultSurveyFilters()) {
  const scope = effectScope()
  const emit = vi.fn()
  const component = scope.run(() =>
    GrowthSurveyFilters.setup(
      { modelValue: filters, survey: { operators: [{ own: 10 }] } },
      { expose: vi.fn(), emit }
    )
  )
  scope.stop()
  return { component, emit, filters }
}
describe('固定比例胶囊选择条', () => {
  it('按参考顺序提供90到10与0.325固定节点', () => {
    expect(surveyThresholds).toEqual([90, 80, 70, 60, 50, 40, 30, 20, 10, 0.325])
    const { component, emit, filters } = setup()
    component.updateRate('mastery', 0.325)
    expect(emit).toHaveBeenCalledWith('update:modelValue', { ...filters, mastery: 0.325 })
    expect(filters.mastery).toBeNull()
  })
  it('再次点击已选节点只清除此项，不改变其他筛选', () => {
    const filters = { ...defaultSurveyFilters(), mastery: 90, module: 70, hideCompleted: true }
    const { component, emit } = setup(filters)
    component.updateRate('mastery', 90)
    expect(emit).toHaveBeenCalledWith('update:modelValue', { ...filters, mastery: null })
  })
})
