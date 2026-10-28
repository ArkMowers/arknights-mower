import { afterEach, describe, expect, it } from 'vitest'
import { i18n } from '@/i18n'
import { depotItemDisplayName, reportChartLabel, reportErrorMessage } from './reports'
import { matchesQuery } from '@/utils/depot_inventory'
import { describeMoodEvent } from '@/utils/mood_rate'

afterEach(() => {
  i18n.global.locale.value = 'zh-CN'
})

describe('report display translations', () => {
  it.each([
    ['en-US', 'Amiya', 'LMD', 'Charged operator: Amiya'],
    ['ja-JP', 'アーミヤ', '龍門幣', '回復対象のオペレーター：アーミヤ']
  ])(
    'uses official %s display names without changing source identities',
    (locale, operator, item, event) => {
      const point = { moodEvent: 'fiammetta_charge', relatedOperator: '阿米娅' }
      const material = { name: '龙门币', number: 100 }
      const before = JSON.stringify({ point, material })
      i18n.global.locale.value = locale
      expect(reportChartLabel('阿米娅')).toBe(operator)
      expect(matchesQuery(material, item)).toBe(true)
      expect(matchesQuery(material, '龙门币')).toBe(true)
      expect(describeMoodEvent(point, '菲亚梅塔')).toBe(event)
      expect(JSON.stringify({ point, material })).toBe(before)
      expect(reportChartLabel('自定义图表名称')).toBe('自定义图表名称')
    }
  )

  it('retranslates local fallback errors while preserving backend errors and log text', () => {
    const localError = i18n.global.t('reports.moralePreferencesFailed')
    i18n.global.locale.value = 'ja-JP'
    expect(reportErrorMessage(localError)).toBe(i18n.global.t('reports.moralePreferencesFailed'))
    expect(reportErrorMessage('后端任务失败：阿米娅')).toBe('后端任务失败：阿米娅')
  })

  it('translates derived depot labels without changing their saved names', () => {
    const item = { name: '全部经验（计算）', number: 100 }
    i18n.global.locale.value = 'en-US'
    expect(depotItemDisplayName(item.name)).toBe(i18n.global.t('reports.totalExpCalculated'))
    expect(matchesQuery(item, 'EXP')).toBe(true)
    i18n.global.locale.value = 'ja-JP'
    expect(depotItemDisplayName('玉+卷')).toBe(i18n.global.t('reports.pullBase'))
    expect(item.name).toBe('全部经验（计算）')
  })
})
