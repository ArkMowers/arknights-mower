import { describe, expect, it } from 'vitest'
import {
  formatMaterialAmount,
  materialQuantityType,
  materialStatus,
  materialStatusType
} from './masteryMaterials'

describe('mastery material colors', () => {
  it.each([
    [{ available: true, craftable: true }, '材料充足', 'success'],
    [{ available: false, craftable: true }, '可合成', 'warning'],
    [{ available: false, craftable: false }, '材料不足', 'error'],
    [null, '待计算', undefined]
  ])('keeps the overall status text and color consistent', (summary, label, color) => {
    expect(materialStatus(summary)).toBe(label)
    expect(materialStatusType(summary)).toBe(color)
  })

  it('colors each shortage independently and keeps stocked materials neutral', () => {
    expect(materialQuantityType({ owned: 2, required: 2, craftable: false })).toBeUndefined()
    expect(materialQuantityType({ owned: 0, required: 2, craftable: true })).toBe('warning')
    expect(materialQuantityType({ owned: 0, required: 2, craftable: false })).toBe('error')
  })
})

describe('材料数量紧凑显示', () => {
  it.each([
    [17501951, '1750.2万'],
    [1042532, '104.3万'],
    [17992000, '1799.2万'],
    [1005000, '100.5万'],
    [573387, '57.3万'],
    [4800000, '480万'],
    [2091119, '209.1万'],
    [1450038, '145万'],
    [13400, '1.3万'],
    [12345, '1.2万'],
    [10000, '1万'],
    [9999, '9,999'],
    [260, '260'],
    [0, '0'],
    [123456789, '1.23亿'],
    [100000000, '1亿'],
    [99999999, '1亿']
  ])('把 %i 显示为 %s', (value, expected) => {
    expect(formatMaterialAmount(value)).toBe(expected)
  })

  it('falls back to zero for values that are not numbers', () => {
    expect(formatMaterialAmount(undefined)).toBe('0')
    expect(formatMaterialAmount(null)).toBe('0')
    expect(formatMaterialAmount('573387')).toBe('57.3万')
  })
})
