import { describe, expect, it } from 'vitest'
import { browserSettingKeys, readBrowserSettings, restoreBrowserSettings } from './configBackup'

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
})
