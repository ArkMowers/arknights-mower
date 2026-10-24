/** Copy full connection diagnostics in desktop WebViews and browsers. */
export async function copyMowerTestText(text) {
  if (!text) return false
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text)
      return true
    }
  } catch {
    // Some desktop WebViews require the legacy fallback.
  }
  const box = document.createElement('textarea')
  box.value = text
  box.readOnly = true
  box.style.cssText = 'position:fixed;left:-10000px;top:0;opacity:0'
  document.body.appendChild(box)
  box.focus()
  box.select()
  let ok = false
  try {
    ok = document.execCommand('copy')
  } catch {
    // The UI keeps the text selectable when copying is denied.
  }
  box.remove()
  return ok
}
