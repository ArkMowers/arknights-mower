import { i18n } from '@/i18n'
import { itemDisplayName, operatorDisplayName } from '@/i18n/gameNames'

const derivedItemLabels = {
  '玉+卷': 'pullBase',
  '玉+卷+石': 'pullOriginium',
  '额外+碎片': 'pullShards',
  '额外+碎片+土': 'pullOrirock',
  '全部经验（计算）': 'totalExpCalculated'
}

export function depotItemDisplayName(name) {
  const key = derivedItemLabels[name]
  return key ? i18n.global.t(`reports.${key}`) : itemDisplayName(name)
}

const chartLabels = {
  赤金: 'pureGold',
  订单质量: 'orderQuality',
  未知订单: 'unknownOrders',
  龙门币订单: 'lmdOrders',
  特殊赤金: 'specialGold',
  经验: 'experience',
  等效理智: 'equivalentSanity'
}
const errorKeys = [
  'moralePreferencesFailed',
  'inventoryReadFailed',
  'historyReadFailed',
  'depotReadFailed',
  'preferencesMigrationFailed',
  'preferencesReadFailed',
  'preferencesSaveFailed',
  'algorithmSaveError',
  'reportReadError',
  'errorRecordsFailed',
  'logsFailed',
  'exportFailed',
  'archiveExportFailed',
  'aiAnalysisFailed',
  'ratioLoadFailed',
  'moraleLoadFailed',
  'observationSaveFailed',
  'recyclingReadFailed',
  'retryUploadFailed',
  'excelExportFailed',
  'invalidObservationName',
  'invalidObservationOperators'
]

export function reportChartLabel(name) {
  const key = chartLabels[name]
  if (key) return i18n.global.t(`reports.${key}`)
  const missed = /^漏单_(1000|1500|2000)$/.exec(name)
  if (missed) return i18n.global.t('reports.missedOrderValue', { value: missed[1] })
  const operatorOrder = /^(但书)_(2000|2500)$/.exec(name)
  return operatorOrder
    ? `${operatorDisplayName(operatorOrder[1])}_${operatorOrder[2]}`
    : operatorDisplayName(name)
}

export function reportErrorMessage(value) {
  if (typeof value !== 'string') return value
  if (value.startsWith('reports.') && i18n.global.te(value)) return i18n.global.t(value)
  for (const locale of i18n.global.availableLocales) {
    const messages = i18n.global.getLocaleMessage(locale).reports
    const key = errorKeys.find((key) => messages?.[key] === value)
    if (key) return i18n.global.t(`reports.${key}`)
  }
  return value
}
