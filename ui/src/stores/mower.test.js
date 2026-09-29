import { afterEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import ReconnectingWebSocket from 'reconnecting-websocket'
import { useMowerStore } from './mower'

vi.mock('reconnecting-websocket', () => ({
  default: vi.fn(function MockSocket() {
    this.send = vi.fn()
  })
}))

afterEach(() => {
  vi.unstubAllGlobals()
  vi.clearAllMocks()
})

describe('log WebSocket access', () => {
  it.each([
    ['', null],
    ['?token=runtime-secret', 'runtime-secret']
  ])('connects with query %s', (search, token) => {
    vi.stubGlobal('window', { location: { search } })
    vi.stubGlobal('location', { origin: 'http://127.0.0.1:58000' })
    setActivePinia(createPinia())
    const store = useMowerStore()

    store.listen_ws()
    expect(ReconnectingWebSocket).toHaveBeenCalledWith('/log')
    store.ws.onopen()
    if (token) {
      expect(store.ws.send).toHaveBeenCalledWith(JSON.stringify({ token }))
    } else {
      expect(store.ws.send).not.toHaveBeenCalled()
    }
  })
})
