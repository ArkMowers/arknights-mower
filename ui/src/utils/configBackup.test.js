import { describe, expect, it, vi } from 'vitest'
import { consumeImportResult, reloadImportedConfiguration } from './configBackup'

function storage() {
  const entries = new Map()
  return {
    getItem: (key) => entries.get(key) ?? null,
    setItem: (key, value) => entries.set(key, value),
    removeItem: (key) => entries.delete(key)
  }
}

describe('configuration import reload', () => {
  it('keeps the same URL, prevents task autostart and shows recovery result once', () => {
    const session = storage()
    const result = { message: '配置已导入', recovery_path: '/config-backups/before-import.zip' }
    const location = {
      href: 'http://localhost:18080/?token=local-token#/mowersettings',
      reload: vi.fn(() => {
        expect(session.getItem('mower-config-imported')).toBe('1')
        expect(JSON.parse(session.getItem('mower-config-import-result'))).toEqual(result)
      })
    }
    reloadImportedConfiguration({ ...result, token: 'do-not-store' }, { session, location })
    expect(location.reload).toHaveBeenCalledOnce()
    expect(location.href).toBe('http://localhost:18080/?token=local-token#/mowersettings')
    expect(consumeImportResult(session)).toEqual(result)
    expect(consumeImportResult(session)).toBeNull()
    expect(session.getItem('mower-config-imported')).toBe('1')
  })

  it('does not reload without the startup guard when session storage fails', () => {
    const location = { reload: vi.fn() }
    const session = {
      setItem: () => {
        throw new Error('storage unavailable')
      }
    }
    expect(() => reloadImportedConfiguration({}, { session, location })).toThrow(
      'storage unavailable'
    )
    expect(location.reload).not.toHaveBeenCalled()
  })
})
