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

export function reloadImportedConfiguration(
  settings,
  result,
  { storage = localStorage, session = sessionStorage, location = window.location } = {}
) {
  // Set the startup guard before reloading, and keep the existing URL/token.
  session.setItem('mower-config-imported', '1')
  session.setItem(
    'mower-config-import-result',
    JSON.stringify({ message: result.message, recovery_path: result.recovery_path })
  )
  restoreBrowserSettings(settings, storage)
  location.reload()
}

export function consumeImportResult(session = sessionStorage) {
  try {
    const result = JSON.parse(session.getItem('mower-config-import-result'))
    session.removeItem('mower-config-import-result')
    return result
  } catch {
    return null
  }
}
