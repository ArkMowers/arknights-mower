import { describe, expect, it } from 'vitest'
import { planRecommendationConditions } from './baseRecommendationConditions'

const plan = () => ({
  room_1_1: { name: '制造站', product: 'gold', plans: [] },
  room_1_2: { name: '制造站', product: 'exp3', plans: [] },
  room_1_3: { name: '贸易站', plans: [] },
  room_2_1: { name: '发电站', plans: [] },
  room_2_2: { name: '发电站', plans: [] },
  ...Object.fromEntries(
    [1, 2, 3, 4].map((index) => ['dormitory_' + index, { name: '', plans: [{ agent: 'Free' }] }])
  )
})
const levels = {
  room_1_1: 3,
  room_1_2: 3,
  room_1_3: 3,
  room_2_1: 3,
  room_2_2: 3,
  dormitory_1: 1,
  dormitory_2: 3,
  dormitory_3: 1,
  dormitory_4: 1,
  meeting: 2,
  contact: 1
}

describe('推荐条件使用当前主排班', () => {
  it('计入未驻员的已建造设施，宿舍取最高而非平均或最低，总等级独立保留', () => {
    const source = plan()
    const before = JSON.stringify(source)
    expect(planRecommendationConditions(source, levels)).toMatchObject({
      trade: 1,
      factories: 2,
      power: 2,
      dormLevel: 3,
      dormLevels: 6,
      reception: 2,
      recruits: 0,
      formulaKinds: 2,
      goldLines: 1,
      dormLayout: '二电 · 3111宿舍 · 30%'
    })
    expect(JSON.stringify(source)).toBe(before)
  })
  it('显式未建造设施不计数，未知排班不补造条件', () => {
    expect(planRecommendationConditions()).toEqual({})
    expect(planRecommendationConditions(plan(), { ...levels, room_1_1: 0 })).toMatchObject({
      factories: 1,
      goldLines: 0,
      formulaKinds: 1
    })
  })
  it('使用共享设施推断，至简仅匹配四项参考配置', () => {
    const source = plan()
    source.room_2_3 = { name: '发电站', plans: [] }
    expect(planRecommendationConditions(source)).toMatchObject({
      power: 3,
      dormLevel: 5,
      dormLevels: 20,
      dormLayout: '三电 · 40%'
    })
    expect(
      planRecommendationConditions(plan(), { ...levels, dormitory_2: 5 }).dormLayout
    ).toBeUndefined()
  })
})
