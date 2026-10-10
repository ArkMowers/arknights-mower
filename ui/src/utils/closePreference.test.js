import { describe, expect, it } from 'vitest'
import { resolveCloseIntent } from './closePreference.js'

describe('desktop close preference', () => {
  it('asks first, preferring the tray when available', () => {
    expect(resolveCloseIntent({ choice: 'tray', remember: false, tray_enabled: true })).toEqual({
      trayAvailable: true,
      choice: 'tray',
      remember: false,
      shouldPrompt: true
    })
  })
  it('uses a remembered explicit exit without showing the choice', () => {
    expect(resolveCloseIntent({ choice: 'exit', remember: true, tray_enabled: true })).toEqual({
      trayAvailable: true,
      choice: 'exit',
      remember: true,
      shouldPrompt: false
    })
  })
  it('never silently converts a remembered tray action into permanent exit', () => {
    expect(resolveCloseIntent({ choice: 'tray', remember: true, tray_enabled: false })).toEqual({
      trayAvailable: false,
      choice: 'exit',
      remember: false,
      shouldPrompt: true
    })
  })
  it('does not trust invalid or absent preferences', () => {
    expect(
      resolveCloseIntent({ choice: 'invalid', remember: true, tray_enabled: true }).shouldPrompt
    ).toBe(true)
    expect(resolveCloseIntent(undefined).shouldPrompt).toBe(true)
  })
})
