import { createI18n } from 'vue-i18n'
import { menuMessages } from './messages/menus'
import { navigationMessages } from './messages/navigation'
import { planMessages } from './messages/plans'
import { taskMessages } from './messages/tasks'
import { settingsMessages } from './messages/settings'
import { deviceMessages } from './messages/devices'
import { incomeMessages } from './messages/income'
import { commonMessages } from './messages/common'
import { timelineMessages } from './messages/timeline'
import { growthMessages } from './messages/growth'
import { reportMessages } from './messages/reports'
import { runtimeMessages } from './messages/runtime'
import { shellMessages } from './messages/shell'
import { baseSkillMessages } from './messages/baseSkills'
import { baseEstimateMessages } from './messages/baseEstimates'
import { additionalMessages } from './locales'
import { referenceMessages } from './messages/reference'
import { updateMessages } from './messages/updates'
import { softwareUpdateMessages } from './messages/softwareUpdate'
import { operatorSyncMessages } from './messages/operatorSync'
import { alphaPageMessages } from './messages/alphaPages'
import { groupRestingMessages } from './messages/groupResting'
import { maaQueueMessages } from './messages/maaQueue'
import { maaActivityMessages } from './messages/maaActivities'
import { growthUpdateMessages } from './messages/growthUpdates'
import {
  DEFAULT_LOCALE,
  INTERFACE_LANGUAGES,
  SYSTEM_LANGUAGE,
  SUPPORTED_LOCALES,
  isSupportedLocale
} from './languagePreference'

export {
  DEFAULT_LOCALE,
  INTERFACE_LANGUAGES,
  SUPPORTED_LOCALES,
  isSupportedLocale
} from './languagePreference'

const appearanceMessages = {
  'zh-CN': {
    followSystem: '跟随系统',
    followSystemDescription:
      '“跟随系统”使用浏览器或桌面窗口提供的语言列表；没有匹配的语言时使用简体中文。',
    loadFailed: '界面语言读取失败，请重试。',
    saveFailed: '界面语言保存失败，已恢复原来的语言。请重试。',
    retry: '重试'
  },
  'en-US': {
    followSystem: 'Follow System',
    followSystemDescription:
      'Follow System uses the language list provided by your browser or desktop window. If no supported language matches, Simplified Chinese is used.',
    loadFailed: 'Could not load the interface language. Please try again.',
    saveFailed:
      'Could not save the interface language. The previous language has been restored. Please try again.',
    retry: 'Retry'
  },
  'ja-JP': {
    followSystem: 'システムに従う',
    followSystemDescription:
      '「システムに従う」はブラウザーまたはデスクトップウィンドウの言語リストを使用します。対応する言語がない場合は簡体字中国語を表示します。',
    loadFailed: '表示言語を読み込めませんでした。もう一度お試しください。',
    saveFailed: '表示言語を保存できなかったため、元の言語に戻しました。もう一度お試しください。',
    retry: '再試行'
  },
  'zh-TW': {
    followSystem: '跟隨系統',
    followSystemDescription:
      '「跟隨系統」使用瀏覽器或桌面視窗提供的語言清單；沒有相符的語言時使用簡體中文。',
    loadFailed: '介面語言讀取失敗，請重試。',
    saveFailed: '介面語言儲存失敗，已恢復原來的語言。請重試。',
    retry: '重試'
  }
}

export function createMowerI18n() {
  return createI18n({
    legacy: false,
    locale: DEFAULT_LOCALE,
    fallbackLocale: DEFAULT_LOCALE,
    messages: Object.fromEntries(
      SUPPORTED_LOCALES.map((locale) => [
        locale,
        {
          menus: menuMessages[locale],
          navigation: navigationMessages[locale],
          appearance: appearanceMessages[locale],
          plans: planMessages[locale],
          tasks: taskMessages[locale],
          settings: settingsMessages[locale],
          devices: deviceMessages[locale],
          income: incomeMessages[locale],
          common: commonMessages[locale],
          timeline: timelineMessages[locale],
          growth: growthMessages[locale],
          reports: reportMessages[locale],
          runtime: runtimeMessages[locale],
          shell: shellMessages[locale],
          baseSkills: baseSkillMessages[locale],
          baseEstimates: baseEstimateMessages[locale],
          reference: referenceMessages[locale],
          updates: updateMessages[locale],
          softwareUpdate: softwareUpdateMessages[locale],
          operatorSync: operatorSyncMessages[locale],
          alphaPages: alphaPageMessages[locale],
          groupResting: groupRestingMessages[locale],
          maaQueue: maaQueueMessages[locale],
          maaActivities: maaActivityMessages[locale],
          growthUpdates: growthUpdateMessages[locale],
          ...additionalMessages[locale]
        }
      ])
    )
  })
}

export const i18n = createMowerI18n()

export function getInterfaceLanguageOptions() {
  return [
    { value: SYSTEM_LANGUAGE, label: i18n.global.t('appearance.followSystem') },
    ...INTERFACE_LANGUAGES
  ]
}

export function setInterfaceLocale(value) {
  if (!isSupportedLocale(value)) return false
  i18n.global.locale.value = value
  return true
}
