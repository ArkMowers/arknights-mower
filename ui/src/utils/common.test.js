import { describe, expect, it } from 'vitest'
import { pinyin_match } from './common'

describe('干员拼音搜索中的 ü', () => {
  it.each([
    ['lv', [0]],
    ['LV', [0]],
    ['lü', [0]],
    ['LÜ', [0]],
    ['lvgu', [0, 1]],
    ['lügu', [0, 1]],
    ['lg', [0, 1]]
  ])('旅骨支持 %s 并保留匹配下标', (query, positions) => {
    expect(pinyin_match('旅骨', query)).toEqual(positions)
  })

  it('不把普通 u 与 ü 混同', () => {
    expect(pinyin_match('旅骨', 'lu')).toBeNull()
  })

  it('保留英文和中英文混合名称中的 v', () => {
    expect(pinyin_match('Viviana', 'vi')).toEqual([0, 1])
    expect(pinyin_match('旅Viviana', 'lvviviana')).not.toBeNull()
  })

  it('匹配选项仍控制完整拼音精度', () => {
    expect(pinyin_match('旅骨', 'lg', { precision: 'every' })).toBeNull()
    expect(pinyin_match('旅骨', 'lvgu', { precision: 'every' })).toEqual([0, 1])
  })
})
