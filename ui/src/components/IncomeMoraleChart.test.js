import { expect, it } from 'vitest'
import { incomeMoraleReport } from '@/riic/incomeMorale'
it('uses main and backup bindings while keeping unbound operators available for custom views', () => {
  const rows = [
    {
      name: '甲',
      points: [
        [0, 24],
        [72, 6],
        [72, 24],
        [744, 12]
      ]
    },
    {
      name: '乙',
      points: [
        [0, 24],
        [744, 0]
      ]
    },
    {
      name: '丙',
      points: [
        [0, 24],
        [744, 12]
      ]
    }
  ]
  const plan = {
    plan1: {
      room_1_1: {
        plans: [
          { agent: '甲', group: '制造', group_bindings: [{ group: '贸易' }] },
          { agent: '乙', group: '制造' }
        ]
      }
    },
    backup_plans: [
      {
        plan: {
          room_1_1: {
            plans: [
              { agent: '甲', group: '制造' },
              { agent: '乙', group: '副表组' }
            ]
          }
        }
      }
    ]
  }
  const original = structuredClone(plan)
  const report = incomeMoraleReport(rows, plan, 72)
  expect(
    report.groups.map((row) => [row.groupName, row.moodData.datasets.map((d) => d.label)])
  ).toEqual([
    ['制造', ['甲', '乙']],
    ['贸易', ['甲']],
    ['副表组', ['乙']]
  ])
  expect(report.catalog.map((row) => row.name)).toEqual(['甲', '乙', '丙'])
  expect(report.series[0].data).toEqual([
    { x: 0, y: 24 },
    { x: 259200000, y: 6 },
    { x: 259200000, y: 24, moodEvent: 'simulation_jump' },
    { x: 2678400000, y: 12 }
  ])
  expect(plan).toEqual(original)
})
