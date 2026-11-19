import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  consumeRelayLinkToken,
  instanceToken,
  isRelayPage,
  rememberRelayToken
} from './instanceToken'

function location(url) {
  vi.stubGlobal('window', {
    location: new URL(url),
    sessionStorage: { getItem: vi.fn(() => 'saved'), setItem: vi.fn() },
    history: { state: {}, replaceState: vi.fn() }
  })
}
afterEach(() => vi.unstubAllGlobals())
describe('instance credentials', () => {
  it('uses the existing desktop URL and ignores browser storage on other hosts', () => {
    location('http://127.0.0.1:58123/?token=desktop')
    expect(isRelayPage()).toBe(false)
    expect(instanceToken()).toBe('desktop')
    expect(window.sessionStorage.getItem).not.toHaveBeenCalled()
  })
  it('decodes a relay link fragment without putting the token in the request URL', () => {
    location('https://trial.free.mower.work:58000/#token=a%2Bb%26c%23d')
    consumeRelayLinkToken()
    expect(window.sessionStorage.setItem).not.toHaveBeenCalled()
    expect(instanceToken()).toBe('a+b&c#d')
  })
  it('keeps the verified relay token in this tab and removes it from the address', () => {
    location('https://trial.free.mower.work:58000/log?view=full#token=first')
    consumeRelayLinkToken()
    expect(instanceToken()).toBe('first')
    rememberRelayToken('verified')
    expect(instanceToken()).toBe('verified')
    expect(window.history.replaceState.mock.calls[0][2].hash).toBe('')
    expect(window.history.replaceState.mock.calls[0][2].search).toBe('?view=full')
  })
})
