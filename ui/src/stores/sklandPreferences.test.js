import { createPinia } from 'pinia'
import { describe, expect, it, vi } from 'vitest'
import { DEFAULT_SKLAND_PREFERENCES, useSklandPreferencesStore } from './sklandPreferences'

const endpoint = expect.stringMatching(/\/gui\/skland$/)
const requestOptions = { timeout: 5000 }

function reply(changes = {}) {
  return { data: { skland: { ...DEFAULT_SKLAND_PREFERENCES, ...changes } } }
}

function setup() {
  return {
    store: useSklandPreferencesStore(createPinia()),
    client: { get: vi.fn().mockResolvedValue(reply()), put: vi.fn() }
  }
}

describe('Skland preferences', () => {
  it('loads once and restores saved view and filters without writing defaults', async () => {
    const { store, client } = setup()
    const saved = {
      account: '138****8000',
      game: '明日方舟官服',
      detailView: 'rewards',
      statsPreset: 'custom',
      statsRange: ['2026-10-01', '2026-11-15']
    }
    client.get.mockResolvedValue(reply(saved))
    expect(await store.update({ game: '终末地官服' }, client)).toBe(false)
    expect(await Promise.all([store.load(client), store.load(client)])).toEqual([true, true])
    expect(await store.load(client)).toBe(true)
    expect(client.get).toHaveBeenCalledExactlyOnceWith(endpoint, requestOptions)
    expect(store.preferences).toMatchObject(saved)
    expect(store.disabled).toBe(false)
    expect(client.put).not.toHaveBeenCalled()
  })

  it('serializes field edits without rolling back newer edits or loading unrelated fields', async () => {
    const { store, client } = setup()
    let finishFirst
    client.put
      .mockImplementationOnce(() => new Promise((resolve) => (finishFirst = resolve)))
      .mockResolvedValueOnce(reply({ account: '139****9000', statsGame: '终末地官服' }))
    await store.load(client)

    const first = store.update({ account: '138****8000' }, client)
    await Promise.resolve()
    const later = store.update({ account: '139****9000', statsGame: '终末地官服' }, client)
    expect(store.preferences.account).toBe('139****9000')
    expect(client.put).toHaveBeenCalledExactlyOnceWith(
      endpoint,
      { skland: { account: '138****8000' } },
      requestOptions
    )
    finishFirst(reply({ account: '138****8000', detailView: 'failures' }))
    expect(await Promise.all([first, later])).toEqual([true, true])
    expect(client.put).toHaveBeenLastCalledWith(
      endpoint,
      { skland: { account: '139****9000', statsGame: '终末地官服' } },
      requestOptions
    )
    expect(store.preferences).toMatchObject({
      account: '139****9000',
      statsGame: '终末地官服',
      detailView: 'day'
    })
  })

  it('keeps failed saves and retries with the most recent pending values only', async () => {
    const { store, client } = setup()
    client.put.mockRejectedValueOnce(new Error('offline'))
    await store.load(client)
    expect(await store.update({ statsPreset: '90' }, client)).toBe(false)
    expect(store.error).toContain('尚未保存')
    expect(store.preferences.statsPreset).toBe('90')
    const next = { statsPreset: 'year', detailView: 'failures' }
    expect(await store.update(next, client)).toBe(false)
    expect(client.put).toHaveBeenCalledTimes(1)
    client.put.mockResolvedValueOnce(reply(next))
    expect(await store.retry(client)).toBe(true)
    expect(store.error).toBe('')
    expect(store.preferences).toMatchObject(next)
    expect(client.put).toHaveBeenLastCalledWith(
      endpoint,
      { skland: { ...next, statsRange: null } },
      requestOptions
    )
  })

  it('saves the date preset and dates as one setting even when just one field changes', async () => {
    const { store, client } = setup()
    const statsRange = ['2026-10-01', '2026-11-15']
    client.get.mockResolvedValueOnce(reply({ statsPreset: 'custom', statsRange }))
    await store.load(client)
    const next = { statsPreset: 'custom', statsRange: ['2026-11-01', '2026-11-15'] }
    client.put.mockResolvedValueOnce(reply(next))
    expect(await store.update({ statsRange: next.statsRange }, client)).toBe(true)
    expect(client.put).toHaveBeenCalledExactlyOnceWith(endpoint, { skland: next }, requestOptions)
  })

  it('allows retry after a failed read without writing', async () => {
    const { store, client } = setup()
    client.get.mockRejectedValueOnce(new Error('offline'))
    expect(await store.load(client)).toBe(false)
    expect(store.disabled).toBe(true)
    expect(store.error).toContain('读取失败')
    expect(await store.retry(client)).toBe(true)
    expect(store.error).toBe('')
    expect(client.put).not.toHaveBeenCalled()
  })
})
