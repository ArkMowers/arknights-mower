import { renderToString } from '@vue/server-renderer'
import { createSSRApp, defineComponent, h, ref } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import MaaWeeklyTable from './MaaWeeklyTable.vue'
import { CHIP_STAGES, formatStageLabel, promoteChipStageOrder } from '@/utils/maa_weekly_plan'

const state = vi.hoisted(() => ({ config: {} }))
vi.mock('@/stores/config', () => ({ useConfigStore: () => ({}) }))
vi.mock('pinia', () => ({ storeToRefs: () => state.config }))
vi.mock('vuedraggable', () => ({
  default: defineComponent({
    props: ['modelValue'],
    setup(props, { slots }) {
      return () =>
        h(
          'tbody',
          props.modelValue.map((element) => slots.item({ element }))
        )
    }
  })
}))
vi.mock('naive-ui', () => ({
  NCheckbox: defineComponent({
    props: ['checked', 'indeterminate'],
    setup: (props) => () => h('input', { type: 'checkbox', checked: props.checked })
  }),
  NSelect: defineComponent({ setup: () => () => h('div') })
}))

function rowCells(html, label) {
  const row = html.match(/<tr\b[^>]*>[\s\S]*?<\/tr>/g).find((row) => row.includes(label))
  return row.match(/<td\b[^>]*>[\s\S]*?<\/td>/g).slice(2)
}

describe('周计划表格开放日显示', () => {
  beforeEach(() => {
    vi.stubGlobal('window', { localStorage: { getItem: () => null, setItem: vi.fn() } })
    state.config = {
      maa_weekly_plan: ref([
        { weekday: '周一', stage: ['1-7'] },
        { weekday: '周二', stage: ['AP-5'] }
      ])
    }
  })
  afterEach(() => vi.unstubAllGlobals())

  it.each([true, false])('过滤为 %s 时占位、样式和编辑状态一致', async (enabled) => {
    const planBefore = JSON.stringify(state.config.maa_weekly_plan.value)
    const html = await renderToString(
      createSSRApp(MaaWeeklyTable, { filterStageByAvailability: enabled })
    )
    const cells = rowCells(html, '红票')
    for (const index of [2, 4]) {
      expect(cells[index].includes('—')).toBe(enabled)
      expect(cells[index].includes('unavailable')).toBe(enabled)
      expect(cells[index].includes('disabled')).toBe(enabled)
    }
    expect(cells[0]).not.toContain('—')
    expect(cells[0]).not.toContain('unavailable')
    expect(cells[0]).not.toContain('disabled')
    expect(cells[1]).toContain('打')
    expect(cells[1]).toContain('selected')
    expect(cells[1]).not.toContain('—')
    expect(cells[1]).not.toContain('disabled')
    expect(rowCells(html, '1-7')[0]).toContain('打')
    expect(JSON.stringify(state.config.maa_weekly_plan.value)).toBe(planBefore)
  })

  it('外部排序将全部芯片排在剿灭之后，所有关卡均有拖动把手', async () => {
    const html = await renderToString(
      createSSRApp(MaaWeeklyTable, {
        stageOrder: promoteChipStageOrder(['1-7']),
        latestActivityOptions: [{ value: 'ACT-9', label: '活动' }]
      })
    )
    const rows = html.match(/<tr\b[^>]*>[\s\S]*?<\/tr>/g).slice(1)
    expect(rows[0]).toContain('当期剿灭')
    expect(rows[0]).toContain('stage-drag-handle')
    for (const [index, stage] of CHIP_STAGES.entries()) {
      expect(rows[index + 1]).toContain(formatStageLabel(stage))
      expect(rows[index + 1]).toContain('stage-drag-handle')
    }
  })

  it('保留手动排序中的剿灭位置，不强制重新置顶', async () => {
    const html = await renderToString(
      createSSRApp(MaaWeeklyTable, {
        stageOrder: ['1-7', 'Annihilation', 'PR-A-1']
      })
    )
    const rows = html.match(/<tr\b[^>]*>[\s\S]*?<\/tr>/g).slice(1)
    expect(rows[0]).toContain('1-7')
    expect(rows[1]).toContain('当期剿灭')
    expect(rows[1]).toContain('stage-drag-handle')
  })
})
