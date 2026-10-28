import { afterEach, describe, expect, it } from 'vitest'
import { computed } from 'vue'
import { i18n } from '@/i18n'
import catalog from '../../../arknights_mower/data/building_skill.json'
import terms from '@/pages/basement_skill/buffer.json'
import details from './data/baseSkillDetails.json'
import { baseSkillDisplayNameById, localizedBaseSkill, localizedBaseTerm } from './baseSkillDetails'

const operator = (name) => catalog.find((item) => item.name === name)
afterEach(() => {
  i18n.global.locale.value = 'zh-CN'
})

describe('base skill display copies for the current Chinese rules', () => {
  it.each(['en-US', 'ja-JP', 'zh-TW'])(
    'covers every bundled skill stage and linked term in %s without changing source data or identities',
    (locale) => {
      const before = JSON.stringify(catalog)
      const termBefore = JSON.stringify(terms)
      i18n.global.locale.value = locale
      let stages = 0
      for (const operator of catalog)
        for (const source of operator.child_skill) {
          const display = localizedBaseSkill(operator.name, source)
          expect(display).not.toBe(source)
          expect(display.skillname.length).toBeGreaterThan(0)
          expect(display.des.length).toBeGreaterThan(0)
          for (const key of Object.keys(source).filter(
            (key) => !['skillname', 'des'].includes(key)
          ))
            expect(display[key]).toEqual(source[key])
          const entry = details.operators[operator.name].find(
            (entry) =>
              entry.source.skillname === source.skillname &&
              entry.source.des === source.des &&
              entry.source.phase_level === source.phase_level
          )
          expect(['official', 'project-translation']).toContain(entry.sources[locale].des.type)
          expect(display).toMatchObject(entry.locales[locale])
          if (locale === 'en-US')
            expect(display.des + display.skillname).not.toMatch(/[\u3400-\u9fff]/)
          if (locale === 'ja-JP')
            expect(display.des).not.toMatch(/进驻|制造站|贸易站|线索|额外|干员/)
          if (locale === 'zh-TW')
            expect(display.des).not.toMatch(/进驻|制造站|贸易站|线索|额外|干员/)
          stages++
        }
      expect(stages).toBe(929)
      expect(details.coverage.locales[locale].translated).toBe(stages)
      for (const [id, entry] of Object.entries(details.terms)) {
        expect(localizedBaseTerm(id, terms[id])).toMatchObject(entry.locales[locale])
        expect(entry.locales[locale].termName.length).toBeGreaterThan(0)
        expect(entry.locales[locale].description.length).toBeGreaterThan(0)
        expect(['official', 'project-translation']).toContain(
          entry.sources[locale].description.type
        )
      }
      expect(JSON.stringify(catalog)).toBe(before)
      expect(JSON.stringify(terms)).toBe(termBefore)
    }
  )
  it('updates skill names and descriptions with the locale while preserving raw identifiers, rules and unlock state', () => {
    const source = { ...operator('能天使').child_skill[1], status: 'active' }
    const before = JSON.stringify(source)
    const display = computed(() => localizedBaseSkill('能天使', source))
    expect(display.value).toEqual(source)
    expect(display.value).not.toBe(source)
    i18n.global.locale.value = 'en-US'
    expect(display.value.skillname).toBe('Logistics Expert')
    expect(display.value.des).toContain('+35%')
    expect(display.value.des).toContain('Trading Post')
    expect(display.value).toMatchObject({
      skill_key: source.skill_key,
      skill_level: source.skill_level,
      roomType: '贸易站',
      phase_level: source.phase_level,
      status: 'active'
    })
    i18n.global.locale.value = 'ja-JP'
    expect(display.value.des).toContain('貿易所')
    i18n.global.locale.value = 'zh-TW'
    expect(display.value.des).toContain('貿易站')
    expect(JSON.stringify(source)).toBe(before)
  })

  it('matches original source content rather than a skill slot index, and rejects changed resource rules', () => {
    const source = operator('能天使').child_skill[1]
    i18n.global.locale.value = 'en-US'
    const reordered = { ...source, skill_key: 18, skill_level: 7 }
    expect(localizedBaseSkill('能天使', reordered).skillname).toBe('Logistics Expert')
    const changed = { ...source, des: source.des.replace('35%', '99%') }
    expect(localizedBaseSkill('能天使', changed)).toEqual(changed)
    expect(localizedBaseSkill('未收录的干员', source)).toEqual(source)
    expect(localizedBaseSkill('能天使', { ...source, phase_level: '精0 1级' }).skillname).toBe(
      source.skillname
    )
  })

  it('translates a Chinese-only stage and corrects the regional morale direction from the Chinese rule', () => {
    i18n.global.locale.value = 'en-US'
    const unreleased = operator('旅骨').child_skill[0]
    expect(localizedBaseSkill('旅骨', unreleased).des).toContain(
      'material conversion efficiency +20%'
    )
    expect(details.operators['旅骨'][0].sources['en-US'].des.type).toBe('project-translation')
    const dusk = operator('夕').child_skill[1]
    expect(localizedBaseSkill('夕', dusk).des).toContain('Morale consumed per hour +0.5')
    expect(localizedBaseSkill('夕', dusk).des).not.toContain('decreases')
    expect(details.operators['夕'][1].sources['en-US'].des.type).toBe('project-translation')
    expect(details.operators['夕'][1].officialDifferences['en-US']).toBe(
      'morale-consumption-direction-differs'
    )
    expect(details.revision).toMatch(/^[a-f0-9]{40}$/)
    expect(details.coverage.localSourceMatches).toBe(929)
  })

  it.each(['风笛', '赫拉格', '缪尔赛思', '远牙'])(
    'translates the Chinese beneficiary scope for %s instead of excluding the operator',
    (name) => {
      i18n.global.locale.value = 'en-US'
      const entry = details.operators[name].find(
        (skill) => skill.officialDifferences['en-US'] === 'beneficiary-scope-differs'
      )
      const source = operator(name).child_skill.find(
        (skill) => skill.des === entry.source.des && skill.skillname === entry.source.skillname
      )
      expect(localizedBaseSkill(name, source).des).toContain('including this Operator')
      expect(entry.sources['en-US'].des.type).toBe('project-translation')
      expect(source.des).toContain('所有干员')
    }
  )

  it('keeps the inclusive morale threshold and correct effect targets in project translations', () => {
    i18n.global.locale.value = 'en-US'
    const ling = operator('令').child_skill[1]
    expect(localizedBaseSkill('令', ling).des).toContain('at most 12')
    const uika = operator('三角初华').child_skill.find((skill) => skill.skillname === '羁绊相生')
    expect(localizedBaseSkill('三角初华', uika).des).toContain('recovers an additional +0.1')
    i18n.global.locale.value = 'ja-JP'
    expect(localizedBaseSkill('令', ling).des).toContain('12以下')
    const fuan = operator('骋风').child_skill.find((skill) => skill.skillname === '广交义友')
    expect(localizedBaseSkill('骋风', fuan).des).toContain('手がかり捜索速度+5%')
    expect(localizedBaseSkill('骋风', fuan).des).not.toContain('事務連絡速度')
  })

  it('looks up only a skill name by both buff ID and original name without guessing from a name alone', () => {
    i18n.global.locale.value = 'en-US'
    const entry = details.operators['能天使'][1]
    expect(baseSkillDisplayNameById(entry.buffId, entry.source.skillname)).toBe('Logistics Expert')
    expect(baseSkillDisplayNameById('unknown-buff', entry.source.skillname)).toBe(
      entry.source.skillname
    )
    expect(baseSkillDisplayNameById(entry.buffId, '用户自定义名称')).toBe('用户自定义名称')
  })

  it('updates linked effect explanations and preserves nested term identities and source data', () => {
    const source = terms.cc_bd_a1
    const before = JSON.stringify(source)
    const display = computed(() => localizedBaseTerm('cc_bd_a1', source))
    i18n.global.locale.value = 'en-US'
    expect(display.value.termName).toBe('Perception Information')
    expect(display.value.description).toContain('Soundless Resonance')
    expect(display.value.description).toContain('<$cc.bd_B>')
    expect(display.value.buffer).toEqual(source.buffer)
    i18n.global.locale.value = 'ja-JP'
    expect(display.value.termName).toBe('知覚情報')
    i18n.global.locale.value = 'zh-TW'
    expect(display.value.termName).toBe('感知資訊')
    const changed = { ...source, description: source.description + '新资源规则' }
    expect(localizedBaseTerm('cc_bd_a1', changed)).toEqual(changed)
    expect(JSON.stringify(source)).toBe(before)
  })
})
