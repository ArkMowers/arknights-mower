import { i18n } from '@/i18n'
import { planDisplayName } from './plans'
import { getOperatorName, getRoomDisplayName } from '@/riic/vendor/workbench/operatorHelpers'
import { MOWER_INVENTORY_ITEMS } from '@/riic/vendor/domain/simulationInventory'
import { operatorDisplayName } from './gameNames'
import { baseSkillDisplayNameById } from './baseSkillDetails'
import { MOWER_ROOM_IDS } from '@/riic/vendor/domain/roster'

const defaultRoomLabels = new Map(
  MOWER_ROOM_IDS.map((id) => [
    id,
    new Set(
      ['manufacture', 'trading', 'power', undefined].map((type) => getRoomDisplayName(id, type))
    )
  ])
)

export function incomeResourceLabel(resource) {
  const item = MOWER_INVENTORY_ITEMS.find((item) => item.resource === resource)
  return item ? planDisplayName(item.label) : resource
}

export function incomeWeightLabel(key) {
  const labels = {
    exp: 'experience',
    gold: 'pureGold',
    orders: 'trading',
    fragments: 'shards',
    orundum: 'orundum'
  }
  return labels[key] ? i18n.global.t(`plans.${labels[key]}`) : key
}

export function incomeRoomName(id, originalName) {
  const original = getRoomDisplayName(id)
  if (originalName !== undefined && !defaultRoomLabels.get(id)?.has(originalName))
    return originalName
  if (i18n.global.locale.value === 'zh-CN') return originalName ?? original
  const dorm = /^(?:dormitory_|dorm_|宿舍\s*)(\d+)$/.exec(id)
  if (dorm) return i18n.global.t('income.dorm', { number: dorm[1] })
  const activity = /^(?:gaming_|活动室)(\d+)$/.exec(id)
  if (activity) return i18n.global.t('plans.activityRoomNumber', { number: activity[1] })
  const typed = /^(B\d{3}) \((制造站|贸易站|发电站)\)$/.exec(originalName || '')
  return typed ? `${typed[1]} (${planDisplayName(typed[2])})` : planDisplayName(original)
}

const messageTemplates = new Map()
const errorKeys = [
  'dayRange',
  'seedRange',
  'missingDrone',
  'noOperatorCache',
  'emptyOperatorCache',
  'enterOperators',
  'invalidOperatorMode',
  'noWeights',
  'invalidWeights',
  'warmup',
  'sample',
  'imageFailed'
]
const escaped = (value) => value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')

function templatesFor(locale) {
  if (!messageTemplates.has(locale)) {
    const messages = i18n.global.getLocaleMessage(locale).income || {}
    const templates = [
      ...Object.entries(messages.display || {}).map(([key, value]) => [`display.${key}`, value]),
      ...errorKeys.map((key) => [key, messages[key]])
    ]
      .filter(([, value]) => typeof value === 'string')
      .sort(
        ([, left], [, right]) =>
          right.replace(/\{\w+\}/g, '').length - left.replace(/\{\w+\}/g, '').length
      )
      .map(([key, value]) => {
        const names = []
        let position = 0
        let pattern = ''
        for (const match of value.matchAll(/\{(\w+)\}/g)) {
          pattern +=
            escaped(value.slice(position, match.index)) +
            (match[1] === 'span' ? '([\\s\\S]*?)' : '([\\s\\S]+?)')
          names.push(match[1])
          position = match.index + match[0].length
        }
        return {
          key,
          names,
          pattern: new RegExp('^' + pattern + escaped(value.slice(position)) + '$')
        }
      })
    messageTemplates.set(locale, templates)
  }
  return messageTemplates.get(locale)
}

function messageParameter(name, value, params) {
  if (/^operator\d*$/.test(name)) return operatorDisplayName(getOperatorName(value))
  if (name === 'operators') return value.split('、').map(operatorDisplayName).join(', ')
  if (name === 'skill') return baseSkillDisplayNameById(params.id, value)
  if (/^room\d*$/.test(name)) return incomeRoomName(value)
  if (name === 'rooms')
    return value
      .split('、')
      .map((room) => incomeRoomName(room))
      .join(', ')
  if (['message', 'period', 'mode', 'task', 'finding', 'span'].includes(name))
    return incomeDisplayMessage(value)
  if (name === 'type') {
    const types = {
      manufacture: 'factory',
      trading: 'tradingPost',
      power: 'powerPlant',
      central: 'controlCenter',
      dormitory: 'dormitory',
      meeting: 'receptionRoom',
      workshop: 'workshop',
      office: 'office',
      training: 'trainingRoom',
      recycle: 'recycling'
    }
    return types[value] ? i18n.global.t(`plans.${types[value]}`) : value
  }
  return value
}

// Translate known UI observations at the display boundary; persisted engine records stay intact.
export function incomeDisplayMessage(value) {
  if (typeof value !== 'string' || i18n.global.locale.value === 'zh-CN') return value
  const separator = value.indexOf('：')
  if (separator > 0) {
    const prefix = value.slice(0, separator)
    const sourceLabels = i18n.global.getLocaleMessage('zh-CN').income.display
    const eventKey = [
      'shiftOff',
      'shiftOn',
      'fiammetta',
      'backupSwitch',
      'backupTask',
      'releaseDorm',
      'bedTakeover',
      'exhaustSupport'
    ].find((key) => sourceLabels[key] === prefix)
    if (eventKey)
      return `${i18n.global.t(`income.display.${eventKey}`)}${i18n.global.locale.value === 'en-US' ? ': ' : '：'}${value.slice(separator + 1)}`
  }
  const taskLabels = {
    线索任务: 'taskClues',
    公招: 'taskRecruit',
    森空岛签到: 'taskSkland',
    空任务: 'taskEmpty',
    技能专精: 'taskMastery',
    仓库扫描: 'taskDepot',
    加工材料: 'taskWorkshop',
    分解所有重复家具: 'taskFurniture'
  }
  if (taskLabels[value]) return i18n.global.t(`plans.${taskLabels[value]}`)
  const eventLabels = {
    下班休息: 'shiftOff',
    菲亚梅塔充能: 'fiammetta',
    副表任务: 'backupTask',
    离开宿舍: 'releaseDorm',
    宿舍换人: 'bedTakeover',
    用尽支援: 'exhaustSupport'
  }
  if (eventLabels[value]) return i18n.global.t(`income.display.${eventLabels[value]}`)
  if (value === 'MAA信用购物') return `MAA ${i18n.global.t('plans.taskCreditStore')}`
  if (value === '肥鸭') return i18n.global.t('income.display.fiammetta')
  if (value.startsWith('Error: ')) return `Error: ${incomeDisplayMessage(value.slice(7))}`
  for (const locale of i18n.global.availableLocales) {
    for (const { key, names, pattern } of templatesFor(locale)) {
      const match = pattern.exec(value)
      if (match) {
        const params = Object.fromEntries(names.map((name, index) => [name, match[index + 1]]))
        return i18n.global.t(
          `income.${key}`,
          Object.fromEntries(
            names.map((name) => [name, messageParameter(name, params[name], params)])
          )
        )
      }
    }
  }
  if (value.includes('；')) return value.split('；').map(incomeDisplayMessage).join('; ')
  return value
}
