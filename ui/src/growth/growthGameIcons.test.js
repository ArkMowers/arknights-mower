import { describe, expect, it } from 'vitest'
import { growthGameIcon, moduleIconKey, moduleIconLabel } from './growthGameIcons'

describe('养成规划游戏图标', () => {
  it('使用八大职业、精英阶段和各专精等级的本地图标', () => {
    for (const profession of [
      'PIONEER',
      'WARRIOR',
      'TANK',
      'SNIPER',
      'CASTER',
      'MEDIC',
      'SUPPORT',
      'SPECIAL'
    ]) {
      expect(growthGameIcon('profession', profession).src).toBeTruthy()
    }
    for (const elite of [0, 1, 2]) expect(growthGameIcon('elite', elite).src).toBeTruthy()
    for (const mastery of [0, 1, 2, 3]) expect(growthGameIcon('mastery', mastery).src).toBeTruthy()
  })

  it('保留完整模组型号，并将两种三角符号匹配到游戏的 D 型资源', () => {
    expect(moduleIconKey(' LOR-Δ ')).toBe('lor-d')
    expect(moduleIconKey('LOR-∆')).toBe('lor-d')
    expect(growthGameIcon('module', 'LOR-Δ').src).toBe(growthGameIcon('module', 'LOR-D').src)
    for (const type of ['LOR-X', 'LOR-Y', 'LOR-D', 'ISW-A', 'RA-A', 'SO-A', 'SO-B']) {
      expect(growthGameIcon('module', type).src).toBeTruthy()
    }
    expect(growthGameIcon('module', 'LOR-X').src).not.toBe(growthGameIcon('module', 'SUM-X').src)
  })

  it('遇到未知模组型号时显示原后缀，不套用其他分支的图标', () => {
    expect(growthGameIcon('module', 'NEW-Ω')).toEqual({ src: null, fallback: 'Ω' })
    expect(growthGameIcon('module', 'UNKNOWN-X')).toEqual({ src: null, fallback: 'X' })
    expect(moduleIconLabel(null)).toBe('模组')
    expect(growthGameIcon('profession', 'UNKNOWN')).toEqual({ src: null, fallback: '' })
  })
})
