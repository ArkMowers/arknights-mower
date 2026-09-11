import { describe, expect, it, vi } from 'vitest'
import {
  browserSettingKeys,
  consumeImportResult,
  readBrowserSettings,
  reloadImportedConfiguration,
  restoreBrowserSettings
} from './configBackup'

function storage() {
  const entries = new Map()
  return {
    getItem: (key) => entries.get(key) ?? null,
    setItem: (key, value) => entries.set(key, value),
    removeItem: (key) => entries.delete(key)
  }
}

describe('configuration backup browser preferences', () => {
  it('round trips every known preference, including missing values', () => {
    const source = storage()
    source.setItem('maa-weekly-plan-editor-mode', 'table')
    source.setItem('reportDataOrder', '["龙门币"]')
    const saved = readBrowserSettings(source)
    expect(Object.keys(saved)).toEqual(browserSettingKeys)
    const destination = storage()
    destination.setItem('sc_preview', 'true')
    restoreBrowserSettings(saved, destination)
    expect(readBrowserSettings(destination)).toEqual(saved)
  })

  it('leaves unrelated application storage untouched', () => {
    const destination = storage()
    destination.setItem('unrelated', 'keep')
    restoreBrowserSettings({ unrelated: 'replace', sc_preview: 'true' }, destination)
    expect(destination.getItem('unrelated')).toBe('keep')
    expect(destination.getItem('sc_preview')).toBe('true')
    restoreBrowserSettings(undefined, destination)
    expect(destination.getItem('sc_preview')).toBe('true')
  })

  it('automatically reloads with restored preferences, the same URL and a startup guard', () => {
    const destination = storage()
    const session = storage()
    const result = { message: '配置已导入', recovery_path: '/config-backups/before-import.json' }
    const location = {
      href: 'http://localhost:18080/?token=local-token#/mowersettings',
      reload: vi.fn(() => {
        expect(destination.getItem('sc_preview')).toBe('true')
        expect(session.getItem('mower-config-imported')).toBe('1')
        expect(JSON.parse(session.getItem('mower-config-import-result'))).toEqual(result)
      })
    }
    reloadImportedConfiguration(
      { sc_preview: 'true' },
      { ...result, token: 'do-not-store' },
      { storage: destination, session, location }
    )
    expect(location.reload).toHaveBeenCalledOnce()
    expect(location.href).toBe('http://localhost:18080/?token=local-token#/mowersettings')
    expect(consumeImportResult(session)).toEqual(result)
    expect(consumeImportResult(session)).toBeNull()
    // Showing the result must not consume App.vue's automatic task start guard.
    expect(session.getItem('mower-config-imported')).toBe('1')
  })

  it('does not reload without the automatic task start guard when session storage fails', () => {
    const location = { reload: vi.fn() }
    const session = {
      setItem: () => {
        throw new Error('storage unavailable')
      }
    }
    expect(() =>
      reloadImportedConfiguration({}, {}, { storage: storage(), session, location })
    ).toThrow('storage unavailable')
    expect(location.reload).not.toHaveBeenCalled()
  })
})
