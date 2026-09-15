import { describe, expect, it } from 'vitest'
import { masteryLevelLabel } from './masteryLevel'

describe('实际技能等级', () => {
  it.each([1, 2, 3, 4, 5, 6, 7])('未专精时显示基础 %i 级', (level) => {
    expect(masteryLevelLabel(level, 0)).toBe(`${level} 级`)
  })
  it.each([
    [1, '专一'],
    [2, '专二'],
    [3, '专三']
  ])('专精 %i 使用专精名称', (level, label) => {
    expect(masteryLevelLabel(7, level)).toBe(label)
  })
  it.each([undefined, null, 0, true, '7'])('未知基础等级不默认显示 7 级', (level) => {
    expect(masteryLevelLabel(level, 0)).toBe('等级未知')
  })
})
