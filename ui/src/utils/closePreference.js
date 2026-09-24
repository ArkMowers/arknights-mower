// Resolve the saved desktop close preference at the time the user clicks ×.
// If the tray becomes unavailable, do not turn a remembered tray close into
// an unexpected permanent exit: show the choice again.
export function resolveCloseIntent(preference) {
  const trayAvailable = preference?.tray_enabled !== false
  const validChoice = preference?.choice === 'tray' || preference?.choice === 'exit'
  const staleTray = !trayAvailable && preference?.choice === 'tray'
  const remember = preference?.remember === true && validChoice && !staleTray
  return {
    trayAvailable,
    choice: trayAvailable && preference?.choice !== 'exit' ? 'tray' : 'exit',
    remember,
    shouldPrompt: !remember
  }
}
