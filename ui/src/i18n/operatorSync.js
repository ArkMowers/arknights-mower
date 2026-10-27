import { i18n } from '@/i18n'
import { operatorSyncMessages } from './messages/operatorSync'

const keysBySource = new Map(
  Object.entries(operatorSyncMessages['zh-CN'])
    .filter(([, message]) => !message.includes('{'))
    .map(([key, message]) => [message, key])
)

function knownMessage(message) {
  const key = keysBySource.get(message)
  return key ? i18n.global.t(`operatorSync.${key}`) : message
}

export function operatorSyncMessage(message) {
  const prefix = '请从森空岛同步干员数据：'
  if (typeof message === 'string' && message.startsWith(prefix)) {
    return i18n.global.t('operatorSync.recommendationUnavailable', {
      detail: knownMessage(message.slice(prefix.length))
    })
  }
  return knownMessage(message)
}
