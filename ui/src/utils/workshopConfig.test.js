import { describe, expect, it } from 'vitest'
import { createWorkshopState } from './workshopConfig'

const manual = [{ operator: '空爆', items: [] }]
const automatic = [{ operator: '赫拉格', items: [], source: 'mastery' }]
const initial = {
  workshop_settings: manual,
  workshop_generation: 0,
  workshop_manual_settings: manual,
  workshop_manual_revision: 0
}

describe('manual workshop editor', () => {
  it('keeps migration errors local while the manual table remains editable', () => {
    const state = createWorkshopState()
    state.load_workshop_config({ ...initial, workshop_preset_warning: '旧合成配置无法读取' })
    expect(state.workshop_preset_warning.value).toBe('旧合成配置无法读取')
    state.workshop_manual_settings.value = []
    state.apply_workshop_response(
      {
        ...initial,
        workshop_manual_settings: [],
        workshop_manual_revision: 1,
        workshop_preset_warning: ''
      },
      []
    )
    expect(state.workshop_manual_settings.value).toEqual([])
    expect(state.workshop_preset_warning.value).toBe('')
  })

  it('accepts a migration warning from automatic configuration without replacing the manual draft', () => {
    const state = createWorkshopState()
    state.load_workshop_config(initial)
    state.workshop_manual_settings.value = []
    state.apply_workshop_response({ ...initial, workshop_preset_warning: '旧合成配置无法读取' })
    expect(state.workshop_preset_warning.value).toBe('旧合成配置无法读取')
    expect(state.workshop_manual_settings.value).toEqual([])
  })

  it('shows the saved table even while a different runtime table is active', () => {
    const state = createWorkshopState()
    state.load_workshop_config({ ...initial, workshop_settings: automatic })
    expect(state.workshop_manual_settings.value).toEqual(manual)
    expect(state.workshop_settings.value).toEqual(automatic)
    state.workshop_manual_settings.value[0].operator = '年'
    expect(state.workshop_settings.value).toEqual(automatic)
  })

  it('does not replace an empty manual table with automatic recipes', () => {
    const state = createWorkshopState()
    state.load_workshop_config({
      ...initial,
      workshop_manual_settings: [],
      workshop_settings: automatic
    })
    expect(state.workshop_manual_settings.value).toEqual([])
  })

  it('automatic config replies only update runtime, preserving unsaved edits', () => {
    const state = createWorkshopState()
    state.load_workshop_config(initial)
    state.workshop_manual_settings.value = []
    state.apply_workshop_response({
      ...initial,
      workshop_settings: automatic,
      workshop_generation: 2
    })
    expect(state.workshop_settings.value).toEqual(automatic)
    expect(state.workshop_manual_settings.value).toEqual([])
  })

  it('keeps edits made while a previous save is in flight and advances its revision', () => {
    const state = createWorkshopState()
    state.load_workshop_config(initial)
    const sent = [{ operator: '年', items: [] }]
    state.workshop_manual_settings.value = []
    state.apply_workshop_response(
      { ...initial, workshop_manual_settings: sent, workshop_manual_revision: 1 },
      sent
    )
    expect(state.workshop_manual_settings.value).toEqual([])
    expect(state.workshop_manual_settings_revision.value).toBe(1)
  })

  it('reloads the saved form on a stale-tab conflict without resurrecting runtime recipes', () => {
    const state = createWorkshopState()
    state.load_workshop_config(initial)
    state.apply_workshop_response(
      {
        ...initial,
        workshop_manual_settings: [],
        workshop_manual_revision: 1,
        workshop_manual_conflict: true
      },
      manual
    )
    expect(state.workshop_manual_settings.value).toEqual([])
  })
})
