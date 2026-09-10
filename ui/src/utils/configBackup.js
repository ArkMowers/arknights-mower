export const browserSettingKeys = [
  'sc_preview',
  'reportDataOrder',
  'maa-weekly-plan-editor-mode',
  'maa-weekly-plan-table-stage-order',
  'maa-weekly-plan-table-stage-order-version'
]

export function readBrowserSettings(storage = localStorage) {
  return Object.fromEntries(browserSettingKeys.map((key) => [key, storage.getItem(key)]))
}

export function restoreBrowserSettings(settings, storage = localStorage) {
  if (!settings) return
  for (const key of browserSettingKeys) {
    if (!Object.hasOwn(settings, key)) continue
    if (settings[key] === null) storage.removeItem(key)
    else if (typeof settings[key] === 'string') storage.setItem(key, settings[key])
  }
}
