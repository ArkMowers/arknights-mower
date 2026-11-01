import { expect, it } from 'vitest'
import {
  incomeDiagnosticGroups,
  incomeDiagnosticMessage,
  incomeFailureMessage
} from './incomeDiagnostics'

const blocked = (target) => ({
  code: 'group-blocked',
  message: `${target}: insufficient available candidates or beds; original occupants retained`
})
const limit = { code: 'SIMULATION_EVENT_LIMIT', message: '达到 200000 个积分区间，结果未完成' }

it('names affected groups, facilities and positions without claiming an unresolved failure', () => {
  expect(incomeDiagnosticMessage(blocked('group:深海'))).toBe(
    '绑组“深海”曾因可用替班或宿舍床位不足而保留原在岗安排'
  )
  expect(incomeDiagnosticMessage(blocked('slot:recycle_1'))).toContain('回收站第 2 个岗位')
  expect(incomeDiagnosticMessage(blocked('slot:room_1_2_0'))).toContain('B102第 1 个岗位')
  expect(
    incomeDiagnosticMessage({
      code: 'PASSIVE_AUXILIARY_OCCUPANCY',
      message: 'factory / 特克诺：闲置进驻'
    })
  ).toBe('加工站 / 特克诺：闲置进驻')
  expect(incomeDiagnosticMessage({ code: 'new-code', message: '未知原因：完整信息' })).toBe(
    '未知原因：完整信息'
  )
})

it('separates model explanations, historical constraints and terminal errors and removes tracker duplicates', () => {
  const groups = incomeDiagnosticGroups([
    { code: 'FINITE_INVENTORY_MODEL', message: '库存连续扣料' },
    { code: 'PASSIVE_AUXILIARY_OCCUPANCY', message: 'train / 桃金娘：闲置进驻' },
    blocked('group:深海'),
    limit,
    { ...limit, message: `演算曾报告：${limit.message}` },
    { code: 'INVALID_ASSUMPTION', severity: 'error', message: '参数无效' }
  ])
  expect(groups.assumptions).toHaveLength(2)
  expect(groups.records).toHaveLength(1)
  expect(groups.failures).toHaveLength(2)
  expect(groups.failures[0].message).toContain('200,000 次')
  expect(groups.failures[1].message).toBe('参数无效')
})

it('summarizes the actual failure and partial progress without concatenating assumptions', () => {
  const diagnostics = [{ code: 'FINITE_INVENTORY_MODEL', message: '库存模型说明' }, limit]
  const result = {
    error: '动态模拟未完成：库存模型说明；达到上限',
    simulationReport: { elapsedHours: 1905.2, observedHours: 1833.2 }
  }
  const message = incomeFailureMessage(result, diagnostics, { warmupDays: 3, sampleDays: 90 })
  expect(message).toContain('统计已算 1,833.2 / 2,160 小时')
  expect(message).toContain('计算次数上限（200,000 次）')
  expect(message).not.toContain('库存模型说明')
  result.simulationReport = { elapsedHours: 12, observedHours: 0 }
  expect(incomeFailureMessage(result, diagnostics, { warmupDays: 3, sampleDays: 90 })).toContain(
    '预热已算 12 / 72 小时'
  )
  expect(incomeFailureMessage({ error: '读取排班失败' }, [], {})).toBe('读取排班失败')
})
