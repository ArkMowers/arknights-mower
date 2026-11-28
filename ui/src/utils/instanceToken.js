let activeToken
const storageKey = 'mower-relay-instance-token'

export function isRelayPage() {
  return (
    typeof window !== 'undefined' &&
    window.location?.protocol === 'https:' &&
    window.location.port === '58000' &&
    /^[a-z0-9-]+\.free\.mower\.work$/.test(window.location.hostname)
  )
}

export function consumeRelayLinkToken() {
  if (!isRelayPage() || !window.location.hash.startsWith('#token=')) return
  const url = new URL(window.location.href)
  activeToken = new URLSearchParams(url.hash.slice(1)).get('token')
  url.hash = ''
  window.history.replaceState(window.history.state, '', url)
}

export function instanceToken() {
  if (!isRelayPage()) return new URLSearchParams(window.location?.search).get('token')
  return activeToken ?? window.sessionStorage.getItem(storageKey)
}

export function rememberRelayToken(token) {
  activeToken = token
  window.sessionStorage.setItem(storageKey, token)
}

export function relayBuild() {
  return isRelayPage() ? document.querySelector('meta[name="mower-relay-build"]')?.content : null
}

export function relaySocketUrl(url) {
  const build = relayBuild()
  if (!build) return url
  const address = new URL(url)
  address.searchParams.set('relay_build', build)
  return address.href
}
