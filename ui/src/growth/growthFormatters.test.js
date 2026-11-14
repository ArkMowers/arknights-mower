import { describe, expect, it } from 'vitest'
import {
  eliteLabel,
  formatCompactNumber,
  formatDuration,
  formatRate,
  goalLabel,
  materialIcon,
  masteryLabel,
  planStatusLabel,
  professionName
} from './growthFormatters'

describe('养成规划展示格式化', () => {
  it('把职业、精英化与专精等级转成界面用语', () => {
    expect(professionName('WARRIOR')).toBe('近卫')
    expect(professionName('CAST')).toBe('CAST')
    expect(eliteLabel(2)).toBe('精二')
    expect(eliteLabel(undefined)).toBe('精零')
    expect(masteryLabel(0)).toBe('未专精')
    expect(masteryLabel(3)).toBe('专三')
    expect(planStatusLabel('manual')).toBe('待完成')
    expect(planStatusLabel('training')).toBe('训练中')
    expect(planStatusLabel('unknown')).toBe('待执行')
  })

  it('格式化时长、比例与紧凑数量', () => {
    expect(formatDuration(0)).toBe('—')
    expect(formatDuration(3600)).toBe('1 小时')
    expect(formatDuration(3900)).toBe('1 小时 5 分')
    expect(formatRate(null)).toBe('暂无样本')
    expect(formatRate(73.14)).toBe('73.1%')
    expect(formatCompactNumber(1450000)).toBe('1.4M')
    expect(formatCompactNumber(23000)).toBe('2.3 万')
    expect(formatCompactNumber(960)).toBe('960')
  })

  it('把养成目标与材料图标映射到界面资源', () => {
    const operator = {
      level_goals: [{ id: 'elite2_model', label: '精二 60 级' }],
      modules: [{ id: 'uniequip_1', name: '战术装备', max_level: 3 }]
    }
    expect(goalLabel(operator, { module_id: 'elite2_model' })).toBe('精二 60 级')
    expect(goalLabel(operator, { module_id: 'elite2' })).toBe('精二 1 级')
    expect(goalLabel(operator, { module_id: 'uniequip_1', target_level: 2 })).toBe(
      '战术装备 · 模组 2 级'
    )
    expect(goalLabel(operator, { module_id: 'unknown' })).toBe('unknown')
    expect(materialIcon({ id: 'growth_exp', name: '作战记录经验' })).toContain('EXP.webp')
    expect(materialIcon({ id: '3303', name: '技巧概要·卷3' })).toContain(
      encodeURIComponent('技巧概要·卷3')
    )
  })
})
