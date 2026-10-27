import { i18n } from '@/i18n'
import { updateMessages } from '@/i18n/messages/updates'

const keys = [
  'resourceConnecting',
  'resourceOtaValidationFallback',
  'resourceOtaDownload',
  'resourceDownload',
  'resourceOtaDownloadFallback',
  'resourceValidating',
  'resourceExtracting',
  'resourceApplying',
  'resourceInstalled',
  'resourceDownloadFailed',
  'resourceInstallRetained',
  'resourceReconstructing',
  'resourceRolledBack',
  'unrecognizedResourcePackage'
]
const messageKeys = new Map(keys.map((key) => [updateMessages['zh-CN'][key], key]))

export function resourceUpdateMessage(message) {
  const key = messageKeys.get(message)
  return key ? i18n.global.t(`updates.${key}`) : message
}
