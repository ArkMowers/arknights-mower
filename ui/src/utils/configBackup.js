export function reloadImportedConfiguration(
  result,
  { session = sessionStorage, location = window.location } = {}
) {
  // Set the startup guard before reloading, and keep the existing URL/token.
  session.setItem('mower-config-imported', '1')
  session.setItem(
    'mower-config-import-result',
    JSON.stringify({ message: result.message, recovery_path: result.recovery_path })
  )
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
