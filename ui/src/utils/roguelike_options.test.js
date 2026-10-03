import { describe, expect, it } from 'vitest'

import {
  collectible_start_visible,
  difficulty_options,
  elite_two_visible,
  field_conditions,
  is_field_enabled,
  mode_list,
  modes_for_theme,
  monthly_squad_check_comms_visible,
  only_elite_two_needs_reset,
  only_elite_two_visible,
  professional_squads,
  rogue_themes,
  start_foldartal_visible
} from './roguelike_options'

describe('roguelike_options', () => {
  it('主题含 BlackFlow 及既有主题', () => {
    const values = rogue_themes.map((t) => t.value)
    expect(values).toEqual(
      expect.arrayContaining(['Phantom', 'Mizuki', 'Sami', 'Sarkaz', 'JieGarden', 'BlackFlow'])
    )
    // 黑流树海下拉用游戏内全名（提示文本里才用 MAA 缩写）
    expect(rogue_themes.find((t) => t.value === 'BlackFlow').label).toBe('沉沦者的黑流树海')
  })

  it('模式含 6/7/10001/20001/30001，不含已弃用的 2 与开发中的 3', () => {
    const values = mode_list.map((m) => m.value)
    expect(values).toEqual(expect.arrayContaining([0, 1, 4, 5, 6, 7, 10001, 20001, 30001]))
    expect(values).not.toContain(2)
    expect(values).not.toContain(3)
  })

  it('主题限定模式标注了对应主题', () => {
    const themed = Object.fromEntries(
      mode_list.filter((m) => m.theme).map((m) => [m.value, m.theme])
    )
    expect(themed[10001]).toBe('Sarkaz')
    expect(themed[20001]).toBe('JieGarden')
    expect(themed[30001]).toBe('BlackFlow')
    expect(themed[5]).toBe('Sami')
  })

  it('按主题过滤出可选模式', () => {
    const values = (t) => modes_for_theme(t).map((m) => m.value)
    expect(values('Sarkaz')).toContain(10001)
    expect(values('Sarkaz')).not.toContain(20001)
    expect(values('Sarkaz')).not.toContain(30001)
    expect(values('BlackFlow')).toContain(30001)
    expect(values('BlackFlow')).not.toContain(10001)
    expect(values('Mizuki')).not.toContain(10001)
    expect(values('Mizuki')).not.toContain(20001)
    expect(values('Mizuki')).not.toContain(30001)
    // 通用模式始终可选
    expect(values('Mizuki')).toContain(0)
    expect(values('Mizuki')).toContain(6)
    // 黑流树海用专属策略（0/1/30001），不走通用 4/6/7
    expect(values('BlackFlow')).toContain(0)
    expect(values('BlackFlow')).toContain(1)
    expect(values('BlackFlow')).not.toContain(4)
    expect(values('BlackFlow')).not.toContain(6)
  })

  it('字段条件覆盖协议注明的主题/模式限定字段', () => {
    expect(Object.keys(field_conditions).sort()).toEqual(
      [
        'blackflow_cultivation_target',
        'collectible_mode_shopping',
        'collectible_mode_squad',
        'collectible_mode_start_list',
        'deep_exploration_auto_iterate',
        'expected_collapsal_paradigms',
        'find_playtime_target',
        'first_floor_foldartal',
        'investment_with_more_score',
        'monthly_squad_auto_iterate',
        'monthly_squad_check_comms',
        'only_start_with_elite_two',
        'refresh_trader_with_dice',
        'start_foldartal_list',
        'start_with_elite_two',
        'stop_at_final_boss',
        'stop_at_max_level',
        'stop_when_investment_full'
      ].sort()
    )
  })

  it('stop_at_final_boss 仅非 Phantom 且策略 0 展示', () => {
    expect(is_field_enabled('stop_at_final_boss', 'Mizuki', 0)).toBe(true)
    expect(is_field_enabled('stop_at_final_boss', 'Sami', 5)).toBe(false)
    expect(is_field_enabled('stop_at_final_boss', 'Phantom', 0)).toBe(false)
    expect(is_field_enabled('stop_at_final_boss', 'Mizuki', 4)).toBe(false)
  })

  it('stop_at_max_level 仅策略 0 展示（无主题限制）', () => {
    expect(is_field_enabled('stop_at_max_level', 'Mizuki', 0)).toBe(true)
    expect(is_field_enabled('stop_at_max_level', 'Phantom', 0)).toBe(true)
    expect(is_field_enabled('stop_at_max_level', 'Sami', 5)).toBe(false)
    expect(is_field_enabled('stop_at_max_level', 'Mizuki', 4)).toBe(false)
  })

  it('expected_collapsal_paradigms 仅 Sami + 策略 5 展示', () => {
    expect(is_field_enabled('expected_collapsal_paradigms', 'Sami', 5)).toBe(true)
    expect(is_field_enabled('expected_collapsal_paradigms', 'Sami', 0)).toBe(false)
    expect(is_field_enabled('expected_collapsal_paradigms', 'Mizuki', 5)).toBe(false)
  })

  it('start_with_elite_two/only_start_with_elite_two 仅 Mizuki/Sami + 策略 4 展示', () => {
    expect(is_field_enabled('start_with_elite_two', 'Mizuki', 4)).toBe(true)
    expect(is_field_enabled('start_with_elite_two', 'Sami', 4)).toBe(true)
    expect(is_field_enabled('only_start_with_elite_two', 'Mizuki', 4)).toBe(true)
    expect(is_field_enabled('only_start_with_elite_two', 'Sami', 4)).toBe(true)
    expect(is_field_enabled('start_with_elite_two', 'Sarkaz', 4)).toBe(false)
    expect(is_field_enabled('only_start_with_elite_two', 'Phantom', 4)).toBe(false)
    expect(is_field_enabled('start_with_elite_two', 'Mizuki', 0)).toBe(false)
    expect(is_field_enabled('only_start_with_elite_two', 'Sami', 0)).toBe(false)
  })

  it('collectible_mode_shopping/collectible_mode_squad 仅策略 4 展示', () => {
    expect(is_field_enabled('collectible_mode_shopping', 'BlackFlow', 4)).toBe(true)
    expect(is_field_enabled('collectible_mode_squad', 'Phantom', 4)).toBe(true)
    expect(is_field_enabled('collectible_mode_shopping', 'Sami', 0)).toBe(false)
    expect(is_field_enabled('collectible_mode_squad', 'BlackFlow', 30001)).toBe(false)
  })

  it('collectible_mode_start_list 仅策略 4 展示（无主题限制）', () => {
    expect(is_field_enabled('collectible_mode_start_list', 'Sami', 4)).toBe(true)
    expect(is_field_enabled('collectible_mode_start_list', 'Phantom', 4)).toBe(true)
    expect(is_field_enabled('collectible_mode_start_list', 'Mizuki', 0)).toBe(false)
    expect(is_field_enabled('collectible_mode_start_list', 'Sarkaz', 5)).toBe(false)
  })

  it('refresh_trader_with_dice 仅 Mizuki 展示', () => {
    expect(is_field_enabled('refresh_trader_with_dice', 'Mizuki', 0)).toBe(true)
    expect(is_field_enabled('refresh_trader_with_dice', 'Mizuki', 4)).toBe(true)
    expect(is_field_enabled('refresh_trader_with_dice', 'Sami', 0)).toBe(false)
    expect(is_field_enabled('refresh_trader_with_dice', 'Phantom', 4)).toBe(false)
  })

  it('stop_when_investment_full 仅策略 1 展示', () => {
    expect(is_field_enabled('stop_when_investment_full', 'Sami', 1)).toBe(true)
    expect(is_field_enabled('stop_when_investment_full', 'BlackFlow', 1)).toBe(true)
    expect(is_field_enabled('stop_when_investment_full', 'Mizuki', 4)).toBe(false)
    expect(is_field_enabled('stop_when_investment_full', 'Sami', 0)).toBe(false)
  })

  it('协议未限定主题/模式的字段始终展示', () => {
    expect(is_field_enabled('difficulty', 'Sami', 0)).toBe(true)
    expect(is_field_enabled('difficulty', 'Phantom', 0)).toBe(true)
    expect(is_field_enabled('investment_enabled', 'Sami', 0)).toBe(true)
  })

  it('investment_with_more_score 仅策略 1 且非黑流树海展示', () => {
    expect(is_field_enabled('investment_with_more_score', 'Sami', 1)).toBe(true)
    expect(is_field_enabled('investment_with_more_score', 'BlackFlow', 1)).toBe(false)
    expect(is_field_enabled('investment_with_more_score', 'Mizuki', 0)).toBe(false)
    expect(is_field_enabled('investment_with_more_score', 'Phantom', 4)).toBe(false)
  })

  it('月度小队字段仅策略 6 展示，通信检查需先勾自动切换', () => {
    expect(is_field_enabled('monthly_squad_auto_iterate', 'Sami', 6)).toBe(true)
    expect(is_field_enabled('monthly_squad_auto_iterate', 'Mizuki', 6)).toBe(true)
    expect(is_field_enabled('monthly_squad_auto_iterate', 'Sami', 0)).toBe(false)
    expect(is_field_enabled('monthly_squad_check_comms', 'Mizuki', 6)).toBe(true)
    expect(is_field_enabled('monthly_squad_check_comms', 'Sami', 7)).toBe(false)
    expect(monthly_squad_check_comms_visible('Mizuki', 6, true)).toBe(true)
    expect(monthly_squad_check_comms_visible('Mizuki', 6, false)).toBe(false)
    expect(monthly_squad_check_comms_visible('Sami', 0, true)).toBe(false)
  })

  it('deep_exploration_auto_iterate 仅策略 7 展示', () => {
    expect(is_field_enabled('deep_exploration_auto_iterate', 'Sami', 7)).toBe(true)
    expect(is_field_enabled('deep_exploration_auto_iterate', 'Mizuki', 7)).toBe(true)
    expect(is_field_enabled('deep_exploration_auto_iterate', 'Sami', 6)).toBe(false)
    expect(is_field_enabled('deep_exploration_auto_iterate', 'Sami', 0)).toBe(false)
  })

  it('first_floor_foldartal 仅萨米 + 策略 4 展示', () => {
    expect(is_field_enabled('first_floor_foldartal', 'Sami', 4)).toBe(true)
    expect(is_field_enabled('first_floor_foldartal', 'Sami', 0)).toBe(false)
    expect(is_field_enabled('first_floor_foldartal', 'Mizuki', 4)).toBe(false)
  })

  it('start_foldartal_list 仅萨米 + 策略 4 + 生活至上分队展示', () => {
    expect(is_field_enabled('start_foldartal_list', 'Sami', 4)).toBe(true)
    expect(is_field_enabled('start_foldartal_list', 'Sarkaz', 4)).toBe(false)
    expect(start_foldartal_visible('Sami', 4, '生活至上分队')).toBe(true)
    expect(start_foldartal_visible('Sami', 4, '指挥分队')).toBe(false)
    expect(start_foldartal_visible('Mizuki', 4, '生活至上分队')).toBe(false)
  })

  it('blackflow_cultivation_target 仅黑流树海刷襁褓动物展示', () => {
    expect(is_field_enabled('blackflow_cultivation_target', 'BlackFlow', 30001)).toBe(true)
    expect(is_field_enabled('blackflow_cultivation_target', 'BlackFlow', 0)).toBe(false)
    expect(is_field_enabled('blackflow_cultivation_target', 'JieGarden', 20001)).toBe(false)
  })

  it('find_playtime_target 仅界园刷常乐节点展示', () => {
    expect(is_field_enabled('find_playtime_target', 'JieGarden', 20001)).toBe(true)
    expect(is_field_enabled('find_playtime_target', 'JieGarden', 0)).toBe(false)
    expect(is_field_enabled('find_playtime_target', 'BlackFlow', 30001)).toBe(false)
  })

  it('professional_squads 为四支战术分队', () => {
    expect(professional_squads).toEqual([
      '突击战术分队',
      '堡垒战术分队',
      '远程战术分队',
      '破坏战术分队'
    ])
  })

  it('凹开局直升仅战术分队可见，只凹需先勾直升', () => {
    expect(elite_two_visible('Mizuki', 4, '突击战术分队')).toBe(true)
    expect(elite_two_visible('Mizuki', 4, '指挥分队')).toBe(false)
    expect(elite_two_visible('Sarkaz', 4, '突击战术分队')).toBe(false)
    expect(only_elite_two_visible('Mizuki', 4, '突击战术分队', true)).toBe(true)
    expect(only_elite_two_visible('Mizuki', 4, '突击战术分队', false)).toBe(false)
  })

  it('只凹勾选时奖励选择隐藏（含非 Phantom 主题条件）', () => {
    expect(collectible_start_visible('Sami', 4, '突击战术分队', false, false)).toBe(true)
    expect(collectible_start_visible('Sami', 4, '突击战术分队', true, true)).toBe(false)
    // Phantom 主题没有只凹隐藏项：奖励选择仍显示（与后端撤销下发条件一致）
    expect(collectible_start_visible('Phantom', 4, '突击战术分队', true, true)).toBe(true)
    expect(collectible_start_visible('Mizuki', 0, '突击战术分队', true, true)).toBe(false)
  })

  it('直升取消勾选或不可见时只凹需要清除', () => {
    expect(only_elite_two_needs_reset('Mizuki', 4, '突击战术分队', false, true)).toBe(true)
    expect(only_elite_two_needs_reset('Mizuki', 4, '指挥分队', true, true)).toBe(true)
    expect(only_elite_two_needs_reset('Sarkaz', 4, '突击战术分队', true, true)).toBe(true)
    expect(only_elite_two_needs_reset('Mizuki', 4, '突击战术分队', true, true)).toBe(false)
    expect(only_elite_two_needs_reset('Mizuki', 4, '突击战术分队', true, false)).toBe(false)
  })

  it('难度下拉含不切换、MAX 与当前主题难度范围', () => {
    // 萨卡兹/水月/界园 0-18，其余 0-15；首项恒为不切换(-1)，次项为 MAX（int.MaxValue）
    const rows = {
      Sarkaz: 19,
      Mizuki: 19,
      JieGarden: 19,
      Phantom: 16,
      Sami: 16,
      BlackFlow: 16
    }
    for (const [theme, count] of Object.entries(rows)) {
      expect(difficulty_options(theme).map((o) => o.value)).toEqual([
        -1,
        2147483647,
        ...Array.from({ length: count }, (_, i) => i)
      ])
    }
    // 端档给 N 前缀：最低 N0、最高 N18，中间 N5
    const sarkaz = difficulty_options('Sarkaz')
    expect(sarkaz.find((o) => o.value === 0).label).toBe('N0')
    expect(sarkaz.find((o) => o.value === 18).label).toBe('N18')
    expect(sarkaz.find((o) => o.value === 5).label).toBe('N5')
    expect(sarkaz.find((o) => o.value === 2147483647).label).toBe('MAX (18)')
  })
})
