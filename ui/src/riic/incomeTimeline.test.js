import { afterEach, beforeAll, expect, it, vi } from 'vitest'
import { createSSRApp, effectScope, h } from 'vue'
import { renderToString } from 'vue/server-renderer'
import Gantt from './vendor/components/workbench/ScheduleTimelineGantt.vue'
import { calculateIncome } from './incomeWorker'
import { defaultIncomeSettings } from './income'

vi.mock('vue', async (original) => ({
  ...(await original()),
  useSSRContext: () => ({ modules: new Set() })
}))
vi.mock('html-to-image', () => ({ toPng: vi.fn(), toBlob: vi.fn() }))

let result
const scopes = []
beforeAll(() => {
  result = calculateIncome(
    {
      default: 'plan1',
      conf: {},
      backup_plans: [],
      facility_levels: { dormitory_1: 5 },
      plan1: {
        room_1_1: {
          name: '制造站',
          product: 'gold',
          plans: [{ agent: '芬', replacement: ['香草'] }]
        },
        room_1_3: { name: '发电站', plans: [] },
        room_2_3: { name: '发电站', plans: [] },
        dormitory_1: { name: '', plans: Array.from({ length: 5 }, () => ({ agent: 'Free' })) }
      }
    },
    {
      ...defaultIncomeSettings(),
      operatorMode: 'maximum',
      finiteInventory: false,
      weightMode: 'custom',
      warmupDays: 1,
      sampleDays: 4
    }
  )
  expect(result.success, result.error).toBe(true)
})
afterEach(() => scopes.splice(0).forEach((scope) => scope.stop()))
const props = () => ({
  report: result.simulationReport,
  timelineData: result.timelineData,
  initialWindowHours: 24,
  initiallyCollapsed: true
})
function setup() {
  const scope = effectScope()
  scopes.push(scope)
  return scope.run(() => Gantt.setup(props(), { expose: vi.fn(), emit: vi.fn() }))
}

it('renders the source Gantt controls and both track views from actual worker output', async () => {
  const render = (overrides) =>
    renderToString(createSSRApp({ render: () => h(Gantt, { ...props(), ...overrides }) }))
  const collapsed = await render({})
  expect(collapsed).toContain('data-test="export-gantt-btn"')
  expect(collapsed).toContain('展开图表')
  expect(collapsed).not.toContain('data-test="gantt-container"')
  const expanded = await render({ initiallyCollapsed: false })
  expect(expanded).toContain('data-test="gantt-container"')
  expect(expanded).toContain('设施分道')
  expect(expanded).toContain('干员分道')
  expect(expanded).toContain('data-test="gantt-overview-scrubber"')
  expect(expanded).toContain('芬')
})

it('keeps source zoom, filtering and long-window export behavior', () => {
  const original = structuredClone(result)
  const page = setup()
  expect(page.dataset.value).toBe(result.timelineData)
  expect(page.isTimelineExpanded.value).toBe(false)
  expect(page.customWindowStart.value).toBe(0)
  expect(page.customWindowEnd.value).toBe(24)
  page.setZoomPreset('6')
  page.panWindow(12)
  expect(page.customWindowStart.value).toBe(12)
  expect(page.customWindowEnd.value).toBe(18)
  page.jumpToEnd()
  expect(page.customWindowEnd.value).toBeCloseTo(96, 8)
  page.viewMode.value = 'operator'
  page.searchQuery.value = '芬'
  expect(page.filteredOperatorTracks.value.map((track) => track.operatorName)).toEqual(['芬'])
  page.openExportModal()
  expect(page.showExportModal.value).toBe(true)
  expect(page.viewMode.value).toBe('facility')
  expect(page.activeExportDuration.value).toBeCloseTo(96, 8)
  expect(page.exportVolumes.value).toHaveLength(2)
  page.exportScopeMode.value = 'volume'
  page.exportSelectedVolumeIndex.value = 1
  expect(page.activeExportStart.value).toBe(72)
  expect(page.activeExportEnd.value).toBeCloseTo(96, 8)
  expect(page.getExportFilename()).toContain('第2卷_T+72h-96h.png')
  expect(result).toEqual(original)
})
