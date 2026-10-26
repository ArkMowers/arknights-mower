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

import {
  compactIncomeNumber,
  incomeImageFilename,
  incomeImageAlgorithmLines,
  incomeImageAnnotationLines
} from './incomeImage'
it('keeps short author and remarks together and omits empty annotations', () => {
  const measure = (text) => Array.from(text).length
  expect(
    incomeImageAnnotationLines({ author: '作者名', remarks: '备注内容' }, measure, 30)
  ).toEqual(['作者：作者名　备注：备注内容'])
  expect(incomeImageAnnotationLines({ author: ' ', remarks: '\n' }, measure, 30)).toEqual([])
  expect(incomeImageAnnotationLines(undefined, measure, 30)).toEqual([])
  expect(
    incomeImageAnnotationLines(
      { author: '作者名', remarks: '备注内容' },
      measure,
      60,
      '82 算法 · 28 天采样'
    )
  ).toEqual(['82 算法 · 28 天采样　作者：作者名　备注：备注内容'])
})
it('wraps annotations within the left columns and retains explicit newlines and Unicode', () => {
  const measure = (text) => Array.from(text).length
  const lines = incomeImageAnnotationLines({ remarks: '甲乙丙丁😀\n下一行' }, measure, 5)
  expect(lines).toEqual(['备注：甲乙', '丙丁😀', '下一行'])
  expect(lines.every((line) => measure(line) <= 5)).toBe(true)
  expect(incomeImageAnnotationLines({ remarks: '甲'.repeat(1000) }, measure, 400)[0]).toHaveLength(
    303
  )
})
it('names JPG exports with the chosen title and completed run income', () => {
  const result = { summary: { totalScore82: 103475.123 }, observedHours: 672 }
  expect(incomeImageFilename(' 我的排班 ', result)).toBe('我的排班_日均收益103475.12_28天.jpg')
  expect(incomeImageFilename('A/B:*', result)).toBe('A_B___日均收益103475.12_28天.jpg')
  expect(incomeImageFilename('A\u0000\u001f\u007f😀. ', result)).toBe(
    'A__\u007f😀_日均收益103475.12_28天.jpg'
  )
})

it('keeps signed daily values compact without hiding small recycling counts', () => {
  expect(compactIncomeNumber(37700)).toBe('37.7k')
  expect(compactIncomeNumber(-1068)).toBe('-1.1k')
  expect(compactIncomeNumber(0.714285)).toBe('0.71')
  expect(compactIncomeNumber(1755500)).toBe('1.8m')
})

it.each([
  [0, '82 算法'],
  [1, '0.245 算法'],
  [2, '0.23456 算法']
])('labels the selected Mower algorithm %s', (mowerAlgorithm, label) => {
  expect(incomeImageAlgorithmLines({ weightMode: 'mower', mowerAlgorithm })).toEqual([label])
})
it.each(['mower', 'custom'])('prints every exact custom weight from %s', (weightMode) => {
  const weights = { exp: 0.9568, gold: 0.76544, orders: 0.23456, fragments: 12.5, orundum: 0 }
  expect(
    incomeImageAlgorithmLines({
      weightMode,
      mowerAlgorithm: -1,
      mowerWeights: weights,
      productionWeights: weights
    })
  ).toEqual(['自定义', '经验 0.9568 · 赤金 0.76544 · 订单 0.23456', '源石碎片 12.5 · 合成玉 0'])
})

import { incomeImageSummaryLine, incomeValuationRows, incomeReportLines } from './incomeImage'
import { defaultIncomeSettings } from './income'

const valuedSummary = (adjustment = -25) => ({
  totalScore82: 100 + adjustment,
  valuation: {
    policy: '按采样边界技能估值',
    completedScore: { daily: 100, total: 200 },
    opening: { amounts: { exp: 500, gold: 1 }, score: { daily: 75, total: 150 } },
    closing: {
      amounts: { exp: 300, gold: 2 },
      score: { daily: 75 + adjustment, total: 150 + adjustment * 2 }
    },
    adjustment: {
      amounts: { exp: -200, gold: 1 },
      score: { daily: adjustment, total: adjustment * 2 }
    }
  }
})
it.each([-25, 0, 25])(
  'marks signed daily WIP adjustment %s without adding it to product quantities',
  (adjustment) => {
    const summary = valuedSummary(adjustment)
    const prefix = incomeImageSummaryLine(
      { summary, observedHours: 48 },
      { weightMode: 'mower', mowerAlgorithm: 0 }
    )
    expect(prefix).toBe(
      `82 算法 · 2 天采样 · 含在制品估值 · 估值净调整（日均）${adjustment > 0 ? '+' : ''}${adjustment}`
    )
    const lines = incomeImageAnnotationLines(
      { author: '作者', remarks: '很长的说明'.repeat(60) },
      (text) => Array.from(text).length,
      20,
      prefix
    )
    expect(lines.every((line) => Array.from(line).length <= 20)).toBe(true)
    expect(lines.join('')).toContain(prefix)
    expect(summary.totalScore82).toBe(100 + adjustment)
  }
)
it('shows boundary resource quantities separately from their weighted valuation', () => {
  expect(incomeValuationRows(valuedSummary())).toEqual([
    { key: 'exp', label: '制造经验', unit: '经验值', opening: 500, closing: 300, adjustment: -200 },
    { key: 'gold', label: '制造赤金', unit: '个', opening: 1, closing: 2, adjustment: 1 }
  ])
  expect(incomeValuationRows({ totalScore82: 42 })).toEqual([])
  expect(
    incomeImageSummaryLine(
      { summary: { totalScore82: 42 }, observedHours: 672 },
      { weightMode: 'mower', mowerAlgorithm: 0 }
    )
  ).toBe('82 算法 · 28 天采样')
})
it('explains WIP boundary subtraction, changing final rewards and physical inventory ownership', () => {
  const result = {
    summary: valuedSummary(),
    observedHours: 48,
    simulationReport: { production: { assumptions: { outputMode: 'settled' } } }
  }
  const settings = {
    ...defaultIncomeSettings(),
    finiteInventory: false,
    operatorMode: 'maximum',
    weightMode: 'custom'
  }
  const plan = {
    default: 'plan1',
    conf: {},
    backup_plans: [],
    plan1: { room_1_1: { name: '制造站', product: 'exp', plans: [] } }
  }
  const lines = incomeReportLines(result, settings, plan, '排班').join('\n')
  expect(lines).toContain('期初加权估值 150，期末 100，净调整 -50，日均贡献 -25')
  expect(lines).toContain('按采样边界的生产进度及技能快照估值')
  expect(lines).toContain('最终完成奖励可能变化')
  expect(lines).toContain('产物数量为采样期产出且已收取量')
  result.simulationReport.production.assumptions.outputMode = 'potential'
  expect(incomeReportLines(result, settings, plan, '排班').join('')).toContain(
    '产物数量为采样期完成量'
  )
  expect(lines).toContain('估值不进入库存，也不触发库存副表')
  expect(lines).toContain('预热期完成后在采样期领取的成品保留在库存收支中，不计入采样收益')
  delete result.summary.valuation
  expect(incomeReportLines(result, settings, plan, '排班').join('\n')).not.toContain('在制品')
})
