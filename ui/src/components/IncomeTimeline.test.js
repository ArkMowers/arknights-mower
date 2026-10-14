import { expect, it, vi } from 'vitest'
import { createSSRApp, h } from 'vue'
import { renderToString } from 'vue/server-renderer'
import IncomeTimeline from './IncomeTimeline.vue'

vi.mock('vue', async (original) => ({
  ...(await original()),
  useSSRContext: () => ({ modules: new Set() })
}))
vi.mock('naive-ui', async (original) => ({
  ...(await original()),
  NCollapse: {
    inheritAttrs: false,
    setup:
      (_, { slots }) =>
      () =>
        slots.default?.()
  },
  NCollapseItem: {
    inheritAttrs: false,
    setup:
      (_, { slots }) =>
      () =>
        slots.default?.()
  }
}))
vi.mock('@/riic/vendor/components/workbench/ScheduleTimelineGantt.vue', () => ({
  default: { render: () => null }
}))

const operator = (overrides = {}) => ({
  operatorId: 'char_123_fang',
  operatorName: '芬',
  mainWorkHours: 9,
  substituteWorkHours: 3,
  workHours: 12,
  exhaustedHours: 2,
  restHours: 6,
  idleHours: 4,
  workFraction: 0.5,
  workRestRatio: 2,
  finalMorale: 0,
  ...overrides
})
const render = (operators) =>
  renderToString(
    createSSRApp({
      render: () =>
        h(IncomeTimeline, {
          report: { observedHours: 24, operators },
          timelineData: { observedHours: 24, operatorTracks: [] }
        })
    })
  )

it('shows source duty statistics and separates zero-mood occupancy from work', async () => {
  const html = await render([operator()])
  for (const label of ['工作占比', '工休比', '主班', '替班', '心情涣散', '期末心情']) {
    expect(html).toContain(label)
  }
  const row = html.match(/<tbody[^>]*>([\s\S]*?)<\/tbody>/)[1]
  const cells = [...row.matchAll(/<td[^>]*>([\s\S]*?)<\/td>/g)].map((match) =>
    match[1].replace(/<[^>]*>/g, '').trim()
  )
  expect(cells).toEqual(['芬', '50%', '2 : 1', '12', '9', '3', '6', '4', '2', '0 / 24'])
})

it('leaves the ratio unavailable when the source reports no rest', async () => {
  const html = await render([operator({ restHours: 0, workRestRatio: null })])
  expect(html).toContain('—')
  expect(html).not.toContain('Infinity')
  expect(html).not.toContain('NaN')
})
