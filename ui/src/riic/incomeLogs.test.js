import { expect, it } from 'vitest'
import { incomeEventLog, incomeLogTime } from './incomeLogs'
it('keeps recent sampled events with names and an explicit total', () => {
  const log = incomeEventLog(
    {
      assumptions: { warmupHours: 72 },
      events: [
        { time: 71, type: 'shift-on', operators: [] },
        { time: 72, type: 'shift-on', operators: ['char_002_amiya'] },
        { time: 73, type: 'backup-plan', operators: [], backupName: '轮班', active: true }
      ],
      production: {
        events: [
          { time: 74, type: 'manufacture-drone', delta: { drone: -20 } },
          { time: 74, type: 'manufacture-drone', roomId: 'room_1_1', amount: 20 }
        ]
      }
    },
    2
  )
  expect(log.total).toBe(3)
  expect(log.entries).toEqual([
    { hours: 2, type: '制造加速', room: 'room_1_1', detail: '数量 20' },
    { hours: 1, type: '副表切换', room: '', detail: '轮班（启用）' }
  ])
  expect(incomeLogTime(25.5)).toBe('第 2 天 01:30')
})

import { incomeImageFilename } from './incomeImage'
it('names JPG exports with the chosen title and completed run income', () => {
  const result = { summary: { totalScore82: 103475.123 }, observedHours: 672 }
  expect(incomeImageFilename(' 我的排班 ', result)).toBe('我的排班_日均收益103475.12_28天.jpg')
  expect(incomeImageFilename('A/B:*', result)).toBe('A_B___日均收益103475.12_28天.jpg')
})
