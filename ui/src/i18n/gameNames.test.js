import { afterEach, expect, it } from 'vitest'
import { i18n } from './index'
import { operatorDisplayName, itemDisplayName, skillDisplayName } from './gameNames'
import { filterOperatorOption } from '@/utils/op_select'
import names from './data/gameNames.json'

afterEach(() => {
  i18n.global.locale.value = 'zh-CN'
})

it.each([
  ['zh-CN', '能天使', '赤金'],
  ['en-US', 'Exusiai', 'Pure Gold'],
  ['ja-JP', 'エクシア', '純金'],
  ['zh-TW', '能天使', '赤金']
])('uses client names in %s without changing option identities', (locale, operator, gold) => {
  const option = { label: '能天使', value: '能天使' }
  i18n.global.locale.value = locale
  expect(operatorDisplayName(option.value)).toBe(operator)
  expect(itemDisplayName('3003', '赤金')).toBe(gold)
  expect(itemDisplayName('赤金')).toBe(gold)
  expect(filterOperatorOption(operator, option)).toBe(true)
  expect(filterOperatorOption('nengtianshi', option)).toBe(true)
  expect(option).toEqual({ label: '能天使', value: '能天使' })
  expect(operatorDisplayName('自定义干员名')).toBe('自定义干员名')
  expect(itemDisplayName('future-item', '新材料原名')).toBe('新材料原名')
})

it.each([
  ['zh-CN', '三技能·过载模式'],
  ['en-US', 'S3 · Overloading Mode'],
  ['ja-JP', 'スキル3 · オーバーロード'],
  ['zh-TW', '三技能 · 超載模式']
])('shows the client skill name in %s', (locale, expected) => {
  i18n.global.locale.value = locale
  expect(skillDisplayName('三技能·过载模式')).toBe(expected)
  expect(skillDisplayName('未收录的新技能')).toBe('未收录的新技能')
})

it('provides project display names for current Chinese-only content without changing its Chinese identity', () => {
  const option = { label: '旅骨', value: '旅骨' }
  i18n.global.locale.value = 'en-US'
  expect(operatorDisplayName(option.value)).toBe('Homebound')
  expect(names.projectTranslations.operators['旅骨']['en-US'].type).toBe('cn-appellation')
  expect(skillDisplayName('触礁')).toBe('Reef Strike')
  expect(names.projectTranslations.skills['触礁']['en-US'].type).toBe('project-translation')
  i18n.global.locale.value = 'ja-JP'
  expect(skillDisplayName('触礁')).toBe('岩礁への衝突')
  i18n.global.locale.value = 'zh-TW'
  expect(itemDisplayName('31103')).toBe('液化高能氣體')
  expect(names.projectTranslations.items['31103']['zh-TW'].type).toBe('project-translation')
  expect(option).toEqual({ label: '旅骨', value: '旅骨' })
})

it('uses the playable operator skill name when a trap shares the Chinese name', () => {
  i18n.global.locale.value = 'en-US'
  expect(skillDisplayName('点燃')).toBe('Ignition')
  i18n.global.locale.value = 'ja-JP'
  expect(skillDisplayName('点燃')).toBe('イグニッション')
  expect(names.officialSkillIds['点燃']).toEqual(['skchr_amgoat_2'])
})
