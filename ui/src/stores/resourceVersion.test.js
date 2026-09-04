import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

import axios from 'axios'
import { useResourceVersionStore } from './resourceVersion.js'

vi.mock('axios', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn()
  }
}))

describe('resource version store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('returns true and refreshes the version after a successful install', async () => {
    axios.get.mockResolvedValueOnce({
      data: {
        current_version: 'v2026.09.03-aaaaaaa',
        remote_version: 'v2026.09.04-deadbee',
        update_available: true
      }
    })
    axios.post.mockResolvedValue({
      data: { ok: true, message: '资源包安装成功，已生效，无需重启 Mower' }
    })
    axios.get.mockResolvedValueOnce({
      data: {
        current_version: 'v2026.09.04-deadbee',
        update_available: false
      }
    })
    const store = useResourceVersionStore()

    await store.loadResourceVersion()
    expect(store.canInstall).toBe(true)
    await expect(store.installResource()).resolves.toBe(true)
    expect(store.install_message).toBe('资源包安装成功，已生效，无需重启 Mower')
    expect(store.info.current_version).toBe('v2026.09.04-deadbee')
    expect(axios.get).toHaveBeenCalledTimes(2)
  })

  it('does not install before a check finds a new version', async () => {
    const store = useResourceVersionStore()

    await expect(store.installResource()).resolves.toBe(false)
    expect(axios.post).not.toHaveBeenCalled()
    expect(store.install_message).toBe('请先检查更新，发现新版本后再安装')
  })

  it('clears a stale update result when a forced check fails', async () => {
    axios.get.mockResolvedValueOnce({
      data: {
        current_version: 'v2026.09.03-aaaaaaa',
        remote_version: 'v2026.09.04-deadbee',
        update_available: true
      }
    })
    const store = useResourceVersionStore()
    await store.loadResourceVersion()
    expect(store.canInstall).toBe(true)

    axios.get.mockRejectedValueOnce(new Error('network'))
    await store.loadResourceVersion(true)

    expect(store.canInstall).toBe(false)
    expect(store.info.update_available).toBeNull()
    expect(store.info.remote_version).toBe('')
  })

  it('returns false when the checked install request fails', async () => {
    axios.get.mockResolvedValue({
      data: {
        current_version: 'v2026.09.03-aaaaaaa',
        remote_version: 'v2026.09.04-deadbee',
        update_available: true
      }
    })
    axios.post.mockRejectedValue(new Error('network'))
    const store = useResourceVersionStore()

    await store.loadResourceVersion()
    await expect(store.installResource()).resolves.toBe(false)
    expect(store.install_message).toBe('安装失败：网络错误')
  })
})
