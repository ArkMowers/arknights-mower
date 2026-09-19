import { describe, expect, it } from 'vitest'
import {
  masteryScheduleContext,
  masteryTraineeWarning,
  supportEditableAfter
} from './masterySupport'

const room = (agent, replacement = []) => ({ plans: [{ agent, replacement }] })

describe('专精排班范围', () => {
  for (const name of ['阿斯卡纶', '烛煌', '斩业星熊']) {
    for (const backup of [false, true]) {
      for (const replacement of [false, true]) {
        it(`${name} 在${backup ? '备用' : '主'}排班的中枢${replacement ? '替换' : '主力'}启用加成`, () => {
          const table = { central: replacement ? room('普通干员', [name]) : room(name) }
          const result = masteryScheduleContext(
            backup ? {} : table,
            backup ? [{ plan: table }] : []
          )
          expect(result.centralBonus).toBe(5)
          expect(result.blocked.has(name)).toBe(true)
        })
      }
    }
  }
  it('其他房间的中枢加速干员不触发；训练室人员放行', () => {
    const { blocked, centralBonus } = masteryScheduleContext(
      { train: room('逻各斯', ['艾丽妮']), room_1_1: room('阿斯卡纶', ['乙']) },
      [{ plan: { dormitory_1: room('丙', ['丁']), gaming_1: room('Free', ['Current']) } }]
    )
    expect(centralBonus).toBe(0)
    expect([...blocked]).toEqual(['阿斯卡纶', '乙', '丙', '丁'])
  })
  it('已开始的阶段锁定，后续阶段仍可编辑', () => {
    expect(supportEditableAfter({ status: 'idle', target_level: 3 })).toBe(0)
    expect(
      supportEditableAfter({ status: 'training', target_level: 3, support_runtime: { level: 1 } })
    ).toBe(1)
    expect(supportEditableAfter({ status: 'arranging', target_level: 3 })).toBe(3)
    expect(supportEditableAfter({ status: 'training', target_level: 3 })).toBe(3)
  })
  it('被训练干员排班占用仅生成警告，仍保留非空闲标记和协助者排除名单', () => {
    const { blocked } = masteryScheduleContext(
      { train: room('逻各斯'), room_1_1: room('能天使', ['教官']) },
      [{ plan: { dormitory_1: room('备用干员') } }]
    )
    expect(masteryTraineeWarning('能天使', blocked)).toBe(
      '能天使 出现在非训练室排班中，专精期间可能影响排班，请留意。'
    )
    expect(masteryTraineeWarning('备用干员', blocked)).toContain('可能影响排班')
    expect(masteryTraineeWarning('逻各斯', blocked)).toBe('')
    expect(masteryTraineeWarning(undefined, blocked)).toBe('')
    expect([...blocked]).toEqual(['能天使', '教官', '备用干员'])
  })
})

for (const backup of [false, true]) {
  it(`训练室${backup ? '备用' : '主'}排班的主力和替换仍属于非空闲`, () => {
    const table = { train: room('逻各斯', ['艾丽妮']) }
    const { scheduled, blocked } = masteryScheduleContext(
      backup ? {} : table,
      backup ? [{ plan: table }] : []
    )
    expect([...scheduled]).toEqual(['逻各斯', '艾丽妮'])
    expect([...blocked]).toEqual([])
    expect(masteryTraineeWarning('逻各斯', blocked)).toBe('')
  })
}
