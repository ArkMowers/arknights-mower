import { describe, expect, it } from 'vitest'
import { singleRecommendations } from '@/data/baseGroups'
import { dormRecoveryFor } from './baseDormRecovery'

describe('散件宿舍恢复技能', () => {
  it('覆盖现有全部宿舍恢复干员，未拥有仍按满练假设，制造加成不冒充宿舍技能', () => {
    expect(
      singleRecommendations
        .filter((group) => group.kind === 'single' && dormRecoveryFor(group.core[0]))
        .map((group) => group.title)
        .sort()
    ).toEqual(
      [
        '冻河',
        '虎狼丸',
        '珊比',
        '裂响',
        '响石',
        '遥',
        '缪尔赛思',
        '斥罪',
        '断罪者',
        '阿米娅'
      ].sort()
    )
    expect(dormRecoveryFor('槐琥')).toBeNull()
    expect(dormRecoveryFor('裂响', { ownership: 'unowned', childSkill: [] })).toMatchObject({
      available: true,
      description: '自身+0.55'
    })
  })
  it.each([
    ['裂响', '自身+0.55'],
    ['珊比', '自身+0.7'],
    ['缪尔赛思', '自身+0.55，全体+0.1（同类取最高）'],
    ['断罪者', '其他一名未满心情干员+0.7（同类取最高）'],
    ['虎狼丸', '全体+0.1（同类取最高）']
  ])('%s保留准确速度与恢复对象', (name, description) => {
    expect(dormRecoveryFor(name)).toMatchObject({ available: true, description })
  })
  it('条件恢复保留宿舍等级、未满心情人数和额外招募位条件，不补造总恢复速度', () => {
    expect(dormRecoveryFor('响石').description).toContain('每级宿舍额外+0.02')
    expect(dormRecoveryFor('冻河').description).toContain('每名未满心情干员额外+0.01')
    expect(dormRecoveryFor('斥罪').description).toContain('每个额外招募位+0.05')
  })
  it('读取实际低阶版本，未解锁技能仅提示且不具备优先级', () => {
    const cairn = {
      ownership: 'owned',
      childSkill: [
        { skill_key: 0, skill_level: 0, status: 'active' },
        { skill_key: 0, skill_level: 1, status: 'locked' }
      ]
    }
    expect(dormRecoveryFor('响石', cairn)).toMatchObject({
      available: true,
      description: '全体+0.15（同类取最高）'
    })
    const penance = {
      ownership: 'owned',
      childSkill: [
        { skill_key: 0, skill_level: 0, status: 'active' },
        { skill_key: 1, skill_level: 0, status: 'locked' }
      ]
    }
    expect(dormRecoveryFor('斥罪', penance)).toMatchObject({
      available: false,
      unlock: '精2 1级',
      inactive: '当前未解锁'
    })
    const before = JSON.stringify(penance)
    dormRecoveryFor('斥罪', penance)
    expect(JSON.stringify(penance)).toBe(before)
  })
})
