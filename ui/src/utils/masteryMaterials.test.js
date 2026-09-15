import { describe, expect, it } from 'vitest'
import { materialQuantityType, materialStatus, materialStatusType } from './masteryMaterials'

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
