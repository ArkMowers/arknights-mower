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

export function instanceToken() {
  const query = new URLSearchParams(window.location?.search).get('token')
  return isRelayPage() ? (activeToken ?? query ?? window.sessionStorage.getItem(storageKey)) : query
}

export function rememberRelayToken(token) {
  activeToken = token
  window.sessionStorage.setItem(storageKey, token)
  const url = new URL(window.location.href)
  if (url.searchParams.has('token')) {
    url.searchParams.delete('token')
    window.history.replaceState(window.history.state, '', url)
  }
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
