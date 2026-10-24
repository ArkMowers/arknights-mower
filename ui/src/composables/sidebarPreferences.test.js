import { describe, expect, it, vi } from 'vitest'
import axios from 'axios'
import { createSidebarPreferences, SIDEBAR_STORAGE_KEY } from './sidebarPreferences'
import { sidebarNavigationItems } from '@/navigation'
import { createPreviewAdapter, createPreviewData } from '../../preview/mock'
const editableNavigationItems = sidebarNavigationItems.filter((item) => !item.footer)

function memoryStorage(initial = null) {
  const values = new Map(initial === null ? [] : [[SIDEBAR_STORAGE_KEY, initial]])
  return {
    getItem: vi.fn((key) => values.get(key) ?? null),
    setItem: vi.fn((key, value) => values.set(key, value))
  }
}

const keys = (items) => items.map((item) => item.key)
const section = (preferences, key) =>
  preferences.visibleSections.value.find((group) => group.key === key)
const placement = (preferences, key) =>
  preferences.state.value.placements.find((item) => item.key === key)
const snapshot = (preferences) => JSON.parse(JSON.stringify(preferences.state.value))
const remoteTransport = (sidebar = null) => ({
  get: vi.fn().mockResolvedValue({ data: { sidebar } }),
  put: vi.fn().mockResolvedValue({ data: { sidebar } })
})

function deferred() {
  let resolve, reject
  const promise = new Promise((done, fail) => {
    resolve = done
    reject = fail
  })
  return { promise, resolve, reject }
}

describe('sidebar preferences', () => {
  it.each([1, 2])(
    'renames the old default title in version %s while preserving custom names',
    (version) => {
      for (const [title, expected] of [
        ['日常任务', '常用'],
        ['我的页面', '我的页面']
      ]) {
        const preferences = createSidebarPreferences({
          storage: memoryStorage(JSON.stringify({ version, groups: [{ key: 'daily', title }] }))
        })
        expect(section(preferences, 'daily').title).toBe(expected)
      }
    }
  )

  it('shows every catalog entry once and keeps the assistant in the default footer', () => {
    const preferences = createSidebarPreferences({ storage: memoryStorage() })
    const displayed = [
      ...preferences.pinnedItems.value,
      ...preferences.visibleSections.value.flatMap((group) => group.items),
      ...preferences.footerItems.value
    ]
    expect(keys(displayed).toSorted()).toEqual(keys(sidebarNavigationItems).toSorted())
    expect(new Set(keys(displayed)).size).toBe(displayed.length)
    expect(keys(preferences.footerItems.value)).toEqual(['chat'])
    expect(keys(preferences.catalog.value)).toEqual(keys(editableNavigationItems))
    expect(preferences.pinnedItems.value).toHaveLength(0)
    expect(keys(preferences.visibleSections.value)).toEqual(['daily', 'reports', 'reference'])
    expect(section(preferences, 'daily').title).toBe('常用')
    expect(section(preferences, 'reference').items.map((item) => item.key)).toContain('arkntools')
    expect(section(preferences, 'reference').items.map((item) => item.key)).toContain('prts')
    expect(section(preferences, 'daily').items[0]).toMatchObject({ key: 'log', id: 'log' })
    expect(section(preferences, 'daily').items[1]).toMatchObject({
      key: 'task-settings',
      id: 'task-settings'
    })
    expect(preferences.state.value.version).toBe(3)
  })

  it.each(['local', 'server'])(
    'removes obsolete page copies from %s layouts and the picker',
    async (source) => {
      const saved = {
        version: 3,
        knownKeys: [...keys(editableNavigationItems), 'rescue-plan', 'mower-settings'],
        groups: [{ key: 'custom', title: '我的页面', collapsed: true }],
        placements: [
          { id: 'my-log', key: 'log', group: 'custom', visible: false, pinned: true },
          { id: 'old-rescue', key: 'rescue-plan', group: 'custom', pinned: true },
          { id: 'old-rescue-copy', key: 'rescue-plan', group: 'custom' },
          { id: 'old-settings', key: 'mower-settings', group: 'footer' },
          { id: 'old-settings-copy', key: 'mower-settings', group: 'custom', pinned: true }
        ]
      }
      const preferences = createSidebarPreferences(
        source === 'local'
          ? { storage: memoryStorage(JSON.stringify(saved)) }
          : { storage: memoryStorage(), transport: remoteTransport(saved) }
      )
      await preferences.initialize()
      expect(preferences.state.value.groups).toEqual(saved.groups)
      expect(preferences.state.value.placements).toEqual([
        saved.placements[0],
        { id: 'chat', key: 'chat', group: 'footer', visible: true, pinned: false }
      ])
      for (const key of ['rescue-plan', 'mower-settings']) {
        expect(preferences.catalog.value.some((item) => item.key === key)).toBe(false)
        expect(preferences.state.value.knownKeys).not.toContain(key)
        expect(preferences.addEntry(key, 'custom')).toBe(false)
      }
    }
  )

  it('keeps hidden entries out of every area and returns unpinned entries to their group', () => {
    const preferences = createSidebarPreferences({ storage: memoryStorage() })
    preferences.toggleGroup('reports')
    preferences.setPinned('record-depot', true)
    expect(section(preferences, 'reports').collapsed).toBe(true)
    expect(keys(preferences.pinnedItems.value)).toEqual(['record-depot'])
    expect(keys(section(preferences, 'reports').items)).not.toContain('record-depot')
    preferences.setVisible('record-depot', false)
    expect(preferences.pinnedItems.value).toHaveLength(0)
    preferences.setPinned('record-depot', false)
    preferences.setVisible('record-depot', true)
    expect(placement(preferences, 'record-depot').group).toBe('reports')
    expect(keys(section(preferences, 'reports').items)).toContain('record-depot')
    expect(preferences.pinnedItems.value).toHaveLength(0)
  })

  it('orders entries across editable groups and the pinned area without duplicating them', () => {
    const preferences = createSidebarPreferences({ storage: memoryStorage() })
    preferences.moveItem('record-depot', 'daily', 'plan')
    expect(keys(section(preferences, 'daily').items).slice(0, 4)).toEqual([
      'log',
      'task-settings',
      'record-depot',
      'plan'
    ])
    preferences.moveItem('record-depot', 'pinned')
    preferences.moveItem('plan', 'pinned', 'record-depot')
    expect(keys(preferences.pinnedItems.value)).toEqual(['plan', 'record-depot'])
    preferences.reorderItem('record-depot', 'plan')
    expect(keys(preferences.pinnedItems.value)).toEqual(['record-depot', 'plan'])
    expect(placement(preferences, 'record-depot')).toMatchObject({ group: 'daily', pinned: true })
    preferences.setPinned('record-depot', false)
    expect(keys(section(preferences, 'daily').items)).toContain('record-depot')
    preferences.moveItem('record-depot', 'reference', 'doc')
    expect(keys(section(preferences, 'reference').items).slice(0, 3)).toEqual([
      'basement-skill',
      'record-depot',
      'doc'
    ])
    expect(keys(preferences.footerItems.value)).toEqual(['chat'])
    expect(placement(preferences, 'record-depot')).toMatchObject({
      group: 'reference',
      pinned: false
    })
    expect(
      preferences.state.value.placements.filter((item) => item.key === 'record-depot')
    ).toHaveLength(1)
  })

  it('restores group and entry preferences through a fresh factory using the saved value', () => {
    const storage = memoryStorage()
    const preferences = createSidebarPreferences({ storage })
    const group = preferences.addGroup('常用')
    preferences.moveItem('arkntools', group)
    preferences.toggleGroup(group)
    preferences.setVisible('doc', false)
    preferences.moveItem('log', group, 'arkntools')
    preferences.setPinned('log', true)
    const restored = createSidebarPreferences({ storage })
    expect(restored.state.value).toEqual(preferences.state.value)
    expect(keys(restored.pinnedItems.value)).toEqual(['log'])
    expect(section(restored, group)).toMatchObject({ title: '常用', collapsed: true })
    expect(keys(section(restored, group).items)).toEqual(['arkntools'])
    expect(placement(restored, 'doc').visible).toBe(false)
    expect(storage.setItem).toHaveBeenLastCalledWith(SIDEBAR_STORAGE_KEY, expect.any(String))
  })

  it('discards saved custom links, unknown and duplicate entries and reserved groups', () => {
    const saved = {
      version: 1,
      groups: [
        { key: 'daily', title: '' },
        { key: 'tools', title: '常用工具', collapsed: true },
        { key: 'tools', title: '重复分组' },
        { key: 'pinned', title: '保留名称' },
        { key: 'footer', title: '保留名称' },
        { key: '<unsafe>', title: '无效名称' }
      ],
      links: [
        { key: 'link-valid', label: ' 本地工具 ', href: ' http://localhost:8000 ' },
        { key: 'log', label: '覆盖内置', href: 'https://example.com/' }
      ],
      placements: [
        { key: 'log', group: 'missing', visible: false },
        { key: 'log', group: 'tools', visible: true },
        { key: 'missing', group: 'tools' },
        { key: 'link-valid', group: 'tools', pinned: true }
      ]
    }
    const preferences = createSidebarPreferences({ storage: memoryStorage(JSON.stringify(saved)) })
    expect(keys(preferences.state.value.groups)).toEqual(['daily', 'tools'])
    expect(preferences.state.value).not.toHaveProperty('links')
    expect(keys(preferences.catalog.value)).toEqual(keys(editableNavigationItems))
    expect(preferences.catalog.value.find((item) => item.key === 'log')).toMatchObject({
      label: '运行日志',
      to: '/'
    })
    expect(placement(preferences, 'log')).toMatchObject({ group: 'daily', visible: false })
    expect(placement(preferences, 'log').id).toBe('log')
    expect(preferences.state.value.version).toBe(3)
    expect(preferences.state.value.knownKeys).toContain('log')
    expect(preferences.state.value.placements.some((item) => item.key === 'missing')).toBe(false)
    expect(preferences.state.value.placements.filter((item) => item.key === 'log')).toHaveLength(1)
    expect(preferences.pinnedItems.value).toHaveLength(0)
    expect(placement(preferences, 'link-valid')).toBeUndefined()
    // A catalog entry absent from an older saved layout appears with its default visibility.
    expect(placement(preferences, 'plan')).toMatchObject({ group: 'daily', visible: true })
    expect(keys(section(preferences, 'daily').items)).toContain('plan')
  })

  it('preserves built-in ordering and visibility after obsolete links in an older layout', () => {
    const preferences = createSidebarPreferences({
      storage: memoryStorage(
        JSON.stringify({
          version: 1,
          groups: [{ key: 'daily', title: '常用页面', collapsed: true }],
          placements: [
            ...Array.from({ length: 100 }, (_, index) => ({ key: `link-old-${index}` })),
            { key: 'plan', group: 'daily', pinned: true },
            { key: 'log', group: 'daily', visible: false },
            { key: 'mastery', group: 'daily' },
            { key: 'rescue-plan', group: 'daily' }
          ]
        })
      )
    })
    expect(section(preferences, 'daily')).toMatchObject({ title: '常用页面', collapsed: true })
    expect(keys(section(preferences, 'daily').items)).toEqual(['task-settings', 'mastery'])
    expect(keys(preferences.pinnedItems.value)).toEqual(['plan'])
    expect(placement(preferences, 'log').visible).toBe(false)
    expect(preferences.state.value.placements).toHaveLength(sidebarNavigationItems.length)
  })

  it('restores the fixed footer and returns older footer entries to editable groups', () => {
    const storage = memoryStorage(
      JSON.stringify({
        version: 1,
        groups: [
          { key: 'daily', title: '常用' },
          { key: 'tools', title: '工具' }
        ],
        placements: [
          { key: 'mower-settings', group: 'daily', visible: false, pinned: true },
          { key: 'doc', group: 'tools' },
          { key: 'log', group: 'footer', visible: false, pinned: true },
          { key: 'record-depot', group: 'footer', pinned: true },
          { key: 'chat', group: 'tools', visible: false, pinned: true },
          { key: 'chat', group: 'daily' }
        ]
      })
    )
    const preferences = createSidebarPreferences({ storage })
    expect(keys(preferences.footerItems.value)).toEqual(['chat'])
    for (const key of ['chat']) {
      expect(placement(preferences, key)).toEqual({
        id: key,
        key,
        group: 'footer',
        visible: true,
        pinned: false
      })
      expect(preferences.state.value.placements.filter((item) => item.key === key)).toHaveLength(1)
    }
    expect(placement(preferences, 'log')).toMatchObject({
      group: 'daily',
      visible: false,
      pinned: true
    })
    expect(placement(preferences, 'record-depot')).toMatchObject({
      group: 'ungrouped',
      visible: true,
      pinned: true
    })
    expect(keys(section(preferences, 'tools').items)).toEqual(['doc'])
    expect(keys(preferences.pinnedItems.value)).toEqual(['record-depot'])
    expect(storage.setItem).not.toHaveBeenCalled()
    preferences.setVisible('log', true)
    expect(createSidebarPreferences({ storage }).state.value).toEqual(preferences.state.value)
  })

  it.each(['', '   ', undefined])('names an older unnamed daily group (%s)', (title) => {
    const preferences = createSidebarPreferences({
      storage: memoryStorage(
        JSON.stringify({ version: 1, groups: [{ key: 'daily', title, collapsed: true }] })
      )
    })
    expect(section(preferences, 'daily')).toMatchObject({ title: '常用', collapsed: true })
  })

  it('adds defaults only for newly introduced pages absent from the saved catalog snapshot', () => {
    const preferences = createSidebarPreferences({
      storage: memoryStorage(
        JSON.stringify({
          version: 2,
          knownKeys: editableNavigationItems
            .filter((item) => item.key !== 'mastery')
            .map((item) => item.key),
          placements: []
        })
      )
    })
    expect(keys(section(preferences, 'daily').items)).toEqual(['mastery'])
    expect(section(preferences, 'daily').items[0].id).toBe('mastery')
    expect(preferences.state.value.knownKeys).toContain('mastery')
    expect(keys(preferences.footerItems.value)).toEqual(['chat'])
  })

  it('inserts task settings after the saved log without reordering or resetting other choices', () => {
    const previous = createSidebarPreferences({ storage: memoryStorage() })
    previous.removeEntry('task-settings')
    previous.moveItem('mastery', 'daily', 'log')
    previous.setVisible('plan', false)
    previous.setPinned('record-depot', true)
    previous.renameGroup('daily', '我的页面')
    const saved = snapshot(previous)
    saved.knownKeys = saved.knownKeys.filter((key) => key !== 'task-settings')
    const preferences = createSidebarPreferences({
      storage: memoryStorage(JSON.stringify(saved))
    })
    expect(section(preferences, 'daily').title).toBe('我的页面')
    expect(keys(section(preferences, 'daily').items)).toEqual(['mastery', 'log', 'task-settings'])
    expect(
      preferences.state.value.placements.filter((item) => item.key !== 'task-settings')
    ).toEqual(saved.placements)
    expect(placement(preferences, 'task-settings')).toMatchObject({
      group: 'daily',
      visible: true,
      pinned: false
    })
    expect(preferences.state.value.knownKeys).toContain('task-settings')
  })

  it('keeps task settings removed after migration and a confirmed edit', () => {
    const saved = snapshot(createSidebarPreferences({ storage: memoryStorage() }))
    saved.placements = saved.placements.filter((item) => item.key !== 'task-settings')
    saved.knownKeys = saved.knownKeys.filter((key) => key !== 'task-settings')
    const storage = memoryStorage(JSON.stringify(saved))
    const preferences = createSidebarPreferences({ storage })
    expect(placement(preferences, 'task-settings')).toBeDefined()
    preferences.removeEntry('task-settings')
    const restored = createSidebarPreferences({ storage })
    expect(placement(restored, 'task-settings')).toBeUndefined()
    expect(restored.state.value.knownKeys).toContain('task-settings')
  })

  it.each(['local', 'server'])(
    'adds task settings below the log in a replacement daily group from %s storage',
    async (source) => {
      const saved = {
        version: 3,
        knownKeys: keys(editableNavigationItems).filter((key) => key !== 'task-settings'),
        groups: [{ key: 'custom-daily', title: '常用', collapsed: false }],
        placements: [
          { id: 'log', key: 'log', group: 'custom-daily', visible: true, pinned: false },
          { id: 'plan', key: 'plan', group: 'custom-daily', visible: true, pinned: false },
          { id: 'mastery', key: 'mastery', group: 'custom-daily', visible: false, pinned: false }
        ]
      }
      const preferences = createSidebarPreferences(
        source === 'local'
          ? { storage: memoryStorage(JSON.stringify(saved)) }
          : { storage: memoryStorage(), transport: remoteTransport(saved) }
      )
      await preferences.initialize()
      expect(keys(section(preferences, 'custom-daily').items)).toEqual([
        'log',
        'task-settings',
        'plan'
      ])
      expect(preferences.standaloneItems.value).toHaveLength(0)
      expect(preferences.state.value.groups).toEqual(saved.groups)
      expect(
        preferences.state.value.placements.filter(
          (item) => !['task-settings', 'chat', 'mower-settings'].includes(item.key)
        )
      ).toEqual(saved.placements)
    }
  )

  it.each(['pinned', 'ungrouped'])(
    'preserves an existing task settings copy in %s after its default group is removed',
    (area) => {
      const previous = createSidebarPreferences({ storage: memoryStorage() })
      previous.moveItem('task-settings', area)
      previous.removeGroup('daily')
      const saved = snapshot(previous)
      const preferences = createSidebarPreferences({
        storage: memoryStorage(JSON.stringify(saved))
      })
      expect(preferences.state.value).toEqual(saved)
    }
  )

  it.each(['pinned', 'ungrouped'])(
    'adds task settings to its default group when the log was moved to %s',
    (logArea) => {
      const previous = createSidebarPreferences({ storage: memoryStorage() })
      previous.removeEntry('task-settings')
      previous.moveItem('log', logArea)
      const saved = snapshot(previous)
      saved.knownKeys = saved.knownKeys.filter((key) => key !== 'task-settings')
      const preferences = createSidebarPreferences({
        storage: memoryStorage(JSON.stringify(saved))
      })
      expect(placement(preferences, 'log')).toEqual(placement(previous, 'log'))
      expect(placement(preferences, 'task-settings')).toMatchObject({
        group: 'daily',
        pinned: false
      })
    }
  )

  it('adds task settings outside groups after the log when its default group was dissolved', () => {
    const previous = createSidebarPreferences({ storage: memoryStorage() })
    previous.removeEntry('task-settings')
    previous.removeGroup('daily')
    const saved = snapshot(previous)
    saved.knownKeys = saved.knownKeys.filter((key) => key !== 'task-settings')
    const preferences = createSidebarPreferences({ storage: memoryStorage(JSON.stringify(saved)) })
    expect(preferences.state.value.groups).toEqual(saved.groups)
    expect(keys(preferences.standaloneItems.value).slice(0, 2)).toEqual(['log', 'task-settings'])
    expect(placement(preferences, 'task-settings').group).toBe('ungrouped')
  })

  it('loads distinct copies while discarding duplicate ids, duplicate areas and invalid copies', () => {
    const preferences = createSidebarPreferences({
      storage: memoryStorage(
        JSON.stringify({
          version: 2,
          knownKeys: editableNavigationItems.map((item) => item.key),
          groups: [
            { key: 'daily', title: '日常任务' },
            { key: 'tools', title: '工具' }
          ],
          placements: [
            { id: 'log', key: 'log', group: 'daily' },
            { id: 'log-copy', key: 'log', group: 'tools' },
            { id: 'log-duplicate', key: 'log', group: 'tools' },
            { id: 'log-copy', key: 'plan', group: 'daily' },
            { id: 'log-pinned', key: 'log', group: 'daily', pinned: true },
            { id: 'log-pinned-again', key: 'log', group: 'tools', pinned: true },
            { id: 'chat', key: 'doc', group: 'daily' },
            { id: 'unknown', key: 'unknown', group: 'daily' }
          ]
        })
      )
    })
    expect(section(preferences, 'daily').items.map((item) => item.id)).toEqual(['log'])
    expect(section(preferences, 'tools').items.map((item) => item.id)).toEqual(['log-copy'])
    expect(preferences.pinnedItems.value.map((item) => item.id)).toEqual(['log-pinned'])
    expect(preferences.state.value.placements).toHaveLength(4)
    expect(keys(preferences.footerItems.value)).toEqual(['chat'])
  })

  it('falls back to the default layout for unreadable JSON or incompatible saved versions', () => {
    for (const saved of ['{broken', 'null', '[]', JSON.stringify({ version: 999, groups: [] })]) {
      const preferences = createSidebarPreferences({ storage: memoryStorage(saved) })
      expect(keys(preferences.footerItems.value)).toEqual(['chat'])
      expect(preferences.state.value.placements).toHaveLength(sidebarNavigationItems.length)
      expect(keys(preferences.visibleSections.value)).toEqual(['daily', 'reports', 'reference'])
    }
  })

  it('keeps editing after storage read or write failures and clears the error after a successful save', () => {
    const storage = {
      getItem: vi.fn(() => {
        throw new Error('Storage blocked')
      }),
      setItem: vi.fn(() => {
        throw new Error('Storage full')
      })
    }
    const preferences = createSidebarPreferences({ storage })
    expect(preferences.persistenceError.value).toBe(true)
    expect(preferences.toggleGroup('reports')).toBe(true)
    expect(section(preferences, 'reports').collapsed).toBe(true)
    expect(preferences.persistenceError.value).toBe(true)
    storage.setItem.mockImplementation(() => {})
    preferences.setVisible('log', false)
    expect(placement(preferences, 'log').visible).toBe(false)
    expect(preferences.persistenceError.value).toBe(false)
    const unavailable = createSidebarPreferences({ storage: null })
    expect(unavailable.setPinned('log', true)).toBe(true)
    expect(keys(unavailable.pinnedItems.value)).toEqual(['log'])
    expect(unavailable.persistenceError.value).toBe(true)
  })

  it('adds, renames, reorders and dissolves groups while retaining their pinned entries', () => {
    const preferences = createSidebarPreferences({ storage: memoryStorage() })
    const group = preferences.addGroup(' 常用 ')
    expect(section(preferences, group).title).toBe('常用')
    expect(preferences.renameGroup(group, ' 报表工具 ')).toBe(true)
    preferences.moveGroup(group, 'reports')
    expect(keys(preferences.visibleSections.value)).toEqual([
      'daily',
      group,
      'reports',
      'reference'
    ])
    preferences.moveItem('record-depot', group)
    preferences.setPinned('record-depot', true)
    expect(preferences.removeGroup(group)).toBe(true)
    expect(section(preferences, group)).toBeUndefined()
    expect(placement(preferences, 'record-depot')).toMatchObject({
      group: 'ungrouped',
      pinned: true
    })
    preferences.setPinned('record-depot', false)
    expect(keys(preferences.standaloneItems.value)).toContain('record-depot')
    expect(preferences.removeGroup('daily')).toBe(true)
    expect(preferences.addGroup('   ')).toBeNull()
    expect(preferences.renameGroup('missing', '工具')).toBe(false)
  })

  it('restores a hidden fixed entry into the selected editable group or pinned area', () => {
    const storage = memoryStorage()
    const preferences = createSidebarPreferences({ storage })
    const group = preferences.addGroup('常用')
    preferences.setVisible('doc', false)
    expect(preferences.addEntry('doc', group)).toBe(true)
    expect(keys(section(preferences, group).items)).toEqual(['doc'])
    preferences.setPinned('record-depot', true)
    preferences.setVisible('record-depot', false)
    expect(preferences.addEntry('record-depot', 'pinned')).toBe(true)
    expect(keys(preferences.pinnedItems.value)).toEqual(['record-depot'])
    expect(placement(preferences, 'record-depot')).toMatchObject({
      group: 'reports',
      visible: true,
      pinned: true
    })
    const restored = createSidebarPreferences({ storage })
    expect(restored.state.value).toEqual(preferences.state.value)
  })

  it('adds independent page copies and edits or removes only the selected copy', () => {
    const storage = memoryStorage()
    const preferences = createSidebarPreferences({ storage })
    expect(preferences.addEntry('log', 'reports')).toBe(true)
    const copy = section(preferences, 'reports').items.find((item) => item.key === 'log')
    expect(copy.id).not.toBe('log')
    expect(keys(section(preferences, 'daily').items)).toContain('log')
    expect(preferences.setPinned(copy.id, true)).toBe(true)
    expect(preferences.pinnedItems.value.map((item) => item.id)).toEqual([copy.id])
    expect(keys(section(preferences, 'daily').items)).toContain('log')
    expect(preferences.setPinned(copy.id, false)).toBe(true)
    expect(preferences.moveItem(copy.id, 'reference', 'doc')).toBe(true)
    expect(section(preferences, 'reference').items.find((item) => item.id === copy.id).key).toBe(
      'log'
    )
    expect(keys(section(preferences, 'daily').items)).toContain('log')
    expect(preferences.removeEntry(copy.id)).toBe(true)
    expect(keys(section(preferences, 'daily').items)).toContain('log')
    expect(preferences.state.value.placements.filter((item) => item.key === 'log')).toHaveLength(1)
    expect(createSidebarPreferences({ storage }).state.value).toEqual(preferences.state.value)
  })

  it('keeps deleting every copy across reloads and creates a new copy only when selected again', () => {
    const storage = memoryStorage()
    const preferences = createSidebarPreferences({ storage })
    preferences.addEntry('log', 'reports')
    for (const copy of preferences.state.value.placements.filter((item) => item.key === 'log'))
      expect(preferences.removeEntry(copy.id)).toBe(true)
    const restored = createSidebarPreferences({ storage })
    expect(restored.state.value.placements.some((item) => item.key === 'log')).toBe(false)
    expect(restored.state.value.knownKeys).toContain('log')
    expect(restored.addEntry('log', 'reports')).toBe(true)
    expect(keys(section(restored, 'daily').items)).not.toContain('log')
    expect(keys(section(restored, 'reports').items)).toContain('log')
  })

  it('restores a hidden target copy without moving another group copy or duplicating the target', () => {
    const storage = memoryStorage()
    const preferences = createSidebarPreferences({ storage })
    preferences.addEntry('log', 'reports')
    const copy = section(preferences, 'reports').items.find((item) => item.key === 'log')
    preferences.setVisible(copy.id, false)
    expect(keys(section(preferences, 'daily').items)).toContain('log')
    expect(preferences.addEntry('log', 'reports')).toBe(true)
    expect(section(preferences, 'reports').items.find((item) => item.key === 'log').id).toBe(
      copy.id
    )
    storage.setItem.mockClear()
    expect(preferences.addEntry('log', 'reports')).toBe(true)
    expect(storage.setItem).not.toHaveBeenCalled()
    expect(preferences.state.value.placements.filter((item) => item.key === 'log')).toHaveLength(2)
  })

  it('rejects copy moves or pin changes that would create duplicate destinations without saving', () => {
    const storage = memoryStorage()
    const preferences = createSidebarPreferences({ storage })
    preferences.addEntry('log', 'reports')
    const copy = section(preferences, 'reports').items.find((item) => item.key === 'log')
    preferences.setPinned(copy.id, true)
    const before = JSON.stringify(preferences.state.value)
    storage.setItem.mockClear()
    expect(preferences.setPinned('log', true)).toBe(false)
    expect(preferences.moveItem('log', 'pinned')).toBe(false)
    expect(preferences.moveItem(copy.id, 'daily')).toBe(false)
    expect(JSON.stringify(preferences.state.value)).toBe(before)
    expect(storage.setItem).not.toHaveBeenCalled()
    expect(preferences.addEntry('log', 'reports')).toBe(true)
    expect(preferences.setPinned(copy.id, false)).toBe(false)
  })

  it('restores default groups, order, visibility and pinning', () => {
    const storage = memoryStorage()
    const preferences = createSidebarPreferences({ storage })
    preferences.addGroup('新分组')
    preferences.addEntry('doc', 'daily')
    preferences.setPinned('plan', true)
    preferences.setVisible('log', false)
    preferences.toggleGroup('reports')
    preferences.reset()
    const reset = createSidebarPreferences({ storage })
    expect(keys(reset.visibleSections.value)).toEqual(['daily', 'reports', 'reference'])
    expect(section(reset, 'daily').title).toBe('常用')
    expect(reset.state.value.placements).toHaveLength(sidebarNavigationItems.length)
    expect(placement(reset, 'log').visible).toBe(true)
    expect(reset.pinnedItems.value).toHaveLength(0)
    expect(section(reset, 'reports').collapsed).toBe(false)
    expect(keys(reset.footerItems.value)).toEqual(['chat'])
  })

  it('ignores invalid movement targets without changing the saved layout', () => {
    const storage = memoryStorage()
    const preferences = createSidebarPreferences({ storage })
    const initial = JSON.stringify(preferences.state.value)
    expect(preferences.moveItem('log', 'missing')).toBe(false)
    expect(preferences.moveItem('missing', 'daily')).toBe(false)
    expect(preferences.moveItem('log', 'pinned', 'log')).toBe(false)
    expect(preferences.reorderItem('log', 'log')).toBe(false)
    expect(preferences.toggleGroup('missing')).toBe(false)
    expect(JSON.stringify(preferences.state.value)).toBe(initial)
    expect(storage.setItem).not.toHaveBeenCalled()
  })

  it('rejects unknown fixed entries and missing groups without changing or saving the layout', () => {
    const storage = memoryStorage()
    const preferences = createSidebarPreferences({ storage })
    preferences.setVisible('log', false)
    const initial = JSON.stringify(preferences.state.value)
    storage.setItem.mockClear()
    expect(preferences.addEntry('missing', 'daily')).toBe(false)
    expect(preferences.addEntry('link-legacy', 'pinned')).toBe(false)
    expect(preferences.addEntry('https://example.com/', 'footer')).toBe(false)
    expect(preferences.addEntry('log', 'missing')).toBe(false)
    expect(preferences.addEntry('log', undefined)).toBe(false)
    expect(JSON.stringify(preferences.state.value)).toBe(initial)
    expect(storage.setItem).not.toHaveBeenCalled()
  })

  it('rejects changes to fixed footer entries and refuses editable entries in the footer', () => {
    const storage = memoryStorage()
    const preferences = createSidebarPreferences({ storage })
    const initial = JSON.stringify(preferences.state.value)
    for (const key of ['chat']) {
      expect(preferences.setVisible(key, false)).toBe(false)
      expect(preferences.setPinned(key, true)).toBe(false)
      expect(preferences.moveItem(key, 'daily')).toBe(false)
      expect(preferences.moveItem(key, 'pinned')).toBe(false)
      expect(preferences.reorderItem(key, 'log')).toBe(false)
      expect(preferences.addEntry(key, 'daily')).toBe(false)
      expect(preferences.addEntry(key, 'pinned')).toBe(false)
      expect(preferences.removeEntry(key)).toBe(false)
    }
    expect(preferences.moveItem('log', 'footer')).toBe(false)
    expect(preferences.moveItem('log', 'reports', 'chat')).toBe(false)
    expect(preferences.reorderItem('log', 'chat')).toBe(false)
    expect(preferences.addEntry('log', 'footer')).toBe(false)
    expect(preferences.toggleGroup('footer')).toBe(false)
    expect(preferences.removeEntry('unknown-copy')).toBe(false)
    expect(JSON.stringify(preferences.state.value)).toBe(initial)
    expect(storage.setItem).not.toHaveBeenCalled()
    expect(keys(preferences.footerItems.value)).toEqual(['chat'])
  })

  it('bounds edited and imported layouts to twenty groups and the fixed entry catalog', () => {
    const preferences = createSidebarPreferences({ storage: memoryStorage() })
    for (let index = 0; index < 17; index += 1) {
      expect(preferences.addGroup(`分组 ${index}`)).toBeTruthy()
    }
    expect(preferences.state.value.groups).toHaveLength(20)
    expect(preferences.addGroup('额外分组')).toBeNull()

    const imported = createSidebarPreferences({
      storage: memoryStorage(
        JSON.stringify({
          version: 1,
          groups: Array.from({ length: 25 }, (_, index) => ({
            key: `import-${index}`,
            title: `导入分组 ${index}`
          })),
          links: Array.from({ length: 105 }, (_, index) => ({
            key: `link-import-${index}`,
            label: `导入工具 ${index}`,
            href: `https://example.com/${index}`
          }))
        })
      )
    })
    expect(imported.state.value.groups).toHaveLength(20)
    expect(keys(imported.state.value.groups)).not.toContain('daily')
    expect(keys(imported.catalog.value)).toEqual(keys(editableNavigationItems))
    expect(new Set(keys(imported.state.value.placements)).size).toBe(sidebarNavigationItems.length)
  })

  it('dissolves every group and restores independent pages without recreating daily on reload', () => {
    const storage = memoryStorage()
    const preferences = createSidebarPreferences({ storage })
    for (const group of [...preferences.state.value.groups])
      expect(preferences.removeGroup(group.key)).toBe(true)
    expect(preferences.state.value.groups).toEqual([])
    expect(keys(preferences.standaloneItems.value).toSorted()).toEqual(
      keys(editableNavigationItems).toSorted()
    )
    const restored = createSidebarPreferences({ storage })
    expect(restored.state.value).toEqual(preferences.state.value)
    expect(restored.visibleSections.value).toEqual([])
    expect(keys(restored.footerItems.value)).toEqual(['chat'])
  })

  it('adds and moves independent copies while preserving copies in other groups and pinned pages', () => {
    const preferences = createSidebarPreferences({ storage: memoryStorage() })
    expect(preferences.addEntry('log', 'ungrouped')).toBe(true)
    const copy = preferences.standaloneItems.value[0]
    expect(copy.key).toBe('log')
    expect(preferences.moveItem('log', 'ungrouped')).toBe(false)
    expect(preferences.addEntry('log', 'pinned')).toBe(true)
    const pinned = preferences.pinnedItems.value[0]
    expect(preferences.removeGroup('daily')).toBe(true)
    expect(preferences.standaloneItems.value.filter((item) => item.key === 'log')).toEqual([copy])
    expect(preferences.pinnedItems.value).toEqual([pinned])
    expect(preferences.addEntry('log', 'reports')).toBe(true)
    const reportCopy = section(preferences, 'reports').items.find((item) => item.key === 'log')
    expect(preferences.removeGroup('reports')).toBe(true)
    expect(preferences.standaloneItems.value.find((item) => item.key === 'log').id).toBe(copy.id)
    expect(preferences.state.value.placements.some((item) => item.id === reportCopy.id)).toBe(false)
    expect(preferences.setPinned(pinned.id, false)).toBe(false)
    expect(preferences.removeEntry(copy.id)).toBe(true)
    expect(preferences.setPinned(pinned.id, false)).toBe(true)
    expect(preferences.standaloneItems.value.find((item) => item.key === 'log').id).toBe(pinned.id)
  })

  it('dissolves a group without modifying an independent copy in another named group', () => {
    const preferences = createSidebarPreferences({ storage: memoryStorage() })
    preferences.addEntry('log', 'reports')
    const reportCopy = section(preferences, 'reports').items.find((item) => item.key === 'log')
    const before = snapshot(preferences).placements.find((item) => item.id === reportCopy.id)
    preferences.removeGroup('daily')
    expect(preferences.standaloneItems.value.find((item) => item.key === 'log').id).toBe('log')
    expect(preferences.state.value.placements.find((item) => item.id === reportCopy.id)).toEqual(
      before
    )
  })

  it.each([1, 2, 3])(
    'loads a version %s layout with no named groups and places new catalog pages outside groups',
    (version) => {
      const preferences = createSidebarPreferences({
        storage: memoryStorage(
          JSON.stringify({
            version,
            groups: [],
            knownKeys: editableNavigationItems
              .filter((item) => item.key !== 'mastery')
              .map((item) => item.key),
            placements: [{ id: 'log', key: 'log', group: 'daily', visible: false }]
          })
        )
      })
      expect(preferences.state.value.version).toBe(3)
      expect(preferences.state.value.groups).toEqual([])
      expect(placement(preferences, 'log')).toMatchObject({ group: 'ungrouped', visible: false })
      expect(keys(preferences.standaloneItems.value)).toContain('mastery')
      if (version !== 1) expect(keys(preferences.standaloneItems.value)).toEqual(['mastery'])
    }
  )

  it('reserves the independent page area key and sanitizes duplicate imported independent copies', () => {
    const preferences = createSidebarPreferences({
      storage: memoryStorage(
        JSON.stringify({
          version: 3,
          groups: [{ key: 'ungrouped', title: '保留区域' }],
          knownKeys: keys(editableNavigationItems),
          placements: [
            { id: 'log', key: 'log', group: 'ungrouped' },
            { id: 'log-copy', key: 'log', group: 'ungrouped' },
            { id: 'log-pinned', key: 'log', group: 'ungrouped', pinned: true }
          ]
        })
      )
    })
    expect(preferences.state.value.groups).toEqual([])
    expect(preferences.standaloneItems.value.map((item) => item.id)).toEqual(['log'])
    expect(preferences.pinnedItems.value.map((item) => item.id)).toEqual(['log-pinned'])
  })
})

describe('server sidebar preferences', () => {
  it('shares confirmed layout changes across preview clients with independent origin storage', async () => {
    const data = createPreviewData({ theme: 'light' })
    const makeClient = () =>
      createSidebarPreferences({
        storage: memoryStorage(),
        transport: axios.create({ adapter: createPreviewAdapter(data) }),
        endpoint: '/gui/sidebar'
      })
    const first = makeClient()
    await first.initialize()
    first.moveItem('log', 'ungrouped')
    first.removeGroup('daily')
    await first.flush()
    const second = makeClient()
    expect(await second.initialize()).toBe(true)
    expect(second.state.value).toEqual(first.state.value)
    expect(second.state.value.groups.some((group) => group.key === 'daily')).toBe(false)
    expect(keys(second.standaloneItems.value)).toContain('log')
  })

  it('loads the shared server layout without consulting or updating an old origin layout', async () => {
    const saved = createSidebarPreferences({ storage: memoryStorage() })
    saved.removeGroup('daily')
    saved.addEntry('log', 'reports')
    const storage = memoryStorage(JSON.stringify({ version: 2, groups: [], placements: [] }))
    const transport = remoteTransport(snapshot(saved))
    const preferences = createSidebarPreferences({ storage, transport })
    expect(preferences.initialized.value).toBe(false)
    expect(await preferences.initialize()).toBe(true)
    expect(preferences.state.value).toEqual(saved.state.value)
    expect(storage.getItem).not.toHaveBeenCalled()
    expect(storage.setItem).not.toHaveBeenCalled()
    expect(transport.put).not.toHaveBeenCalled()
    expect(transport.get).toHaveBeenCalledWith(expect.stringMatching(/\/gui\/sidebar$/), {
      timeout: 10000
    })
    expect(await preferences.initialize()).toBe(true)
    expect(transport.get).toHaveBeenCalledTimes(1)
  })

  it.each([1, 2])(
    'migrates version %s local data only when the server has no sidebar layout',
    async (version) => {
      const storage = memoryStorage(
        JSON.stringify({
          version,
          groups: [{ key: 'daily', title: '我的常用', collapsed: true }],
          knownKeys: keys(editableNavigationItems),
          placements: [{ id: 'log', key: 'log', group: 'daily', visible: false }]
        })
      )
      const transport = remoteTransport()
      let serverLayout = null
      transport.get.mockImplementation(async () => ({ data: { sidebar: serverLayout } }))
      transport.put.mockImplementation(async (_, body) => {
        serverLayout = body.sidebar
        return { data: body }
      })
      const preferences = createSidebarPreferences({ storage, transport })
      expect(await preferences.initialize()).toBe(true)
      await preferences.flush()
      expect(preferences.state.value.version).toBe(3)
      expect(section(preferences, 'daily')).toMatchObject({ title: '我的常用', collapsed: true })
      expect(placement(preferences, 'log').visible).toBe(false)
      expect(transport.put).toHaveBeenCalledTimes(1)
      expect(transport.put).toHaveBeenCalledWith(
        expect.any(String),
        { sidebar: snapshot(preferences) },
        { timeout: 10000 }
      )
      storage.getItem.mockClear()
      const secondOrigin = createSidebarPreferences({ storage, transport })
      await secondOrigin.initialize()
      expect(secondOrigin.state.value).toEqual(preferences.state.value)
      expect(storage.getItem).not.toHaveBeenCalled()
      expect(storage.setItem).not.toHaveBeenCalled()
      expect(transport.put).toHaveBeenCalledTimes(1)
    }
  )

  it('migrates a server version 2 layout while preserving removed pages and empty named groups', async () => {
    const transport = remoteTransport({
      version: 2,
      groups: [],
      knownKeys: keys(editableNavigationItems),
      placements: [{ id: 'saved-log', key: 'log', group: 'daily', pinned: true }]
    })
    const preferences = createSidebarPreferences({ transport, storage: memoryStorage() })
    await preferences.initialize()
    await preferences.flush()
    expect(preferences.state.value.groups).toEqual([])
    expect(preferences.pinnedItems.value.map((item) => item.id)).toEqual(['saved-log'])
    expect(preferences.state.value.placements).toHaveLength(2)
    expect(transport.put).toHaveBeenCalledWith(
      expect.any(String),
      { sidebar: snapshot(preferences) },
      { timeout: 10000 }
    )
  })

  it('does not write a default layout until a confirmed edit when no server or local layout exists', async () => {
    const storage = memoryStorage()
    const transport = remoteTransport()
    const preferences = createSidebarPreferences({ transport, storage })
    await preferences.initialize()
    expect(transport.put).not.toHaveBeenCalled()
    expect(preferences.moveItem('log', 'ungrouped')).toBe(true)
    await preferences.flush()
    expect(transport.put).toHaveBeenCalledTimes(1)
    expect(storage.setItem).not.toHaveBeenCalled()
  })

  it('blocks edits during startup and after a failed load, then allows explicit retry', async () => {
    const request = deferred()
    const transport = remoteTransport()
    transport.get.mockReturnValueOnce(request.promise)
    const preferences = createSidebarPreferences({ transport, storage: memoryStorage() })
    const initial = snapshot(preferences)
    const loading = preferences.initialize()
    const sameLoad = preferences.initialize()
    expect(transport.get).toHaveBeenCalledTimes(1)
    expect(preferences.addGroup('过早编辑')).toBeNull()
    expect(preferences.moveItem('log', 'ungrouped')).toBe(false)
    expect(preferences.addEntry('log', 'reports')).toBe(false)
    expect(preferences.removeEntry('log')).toBe(false)
    expect(preferences.setVisible('log', false)).toBe(false)
    expect(preferences.setPinned('log', true)).toBe(false)
    expect(preferences.removeGroup('daily')).toBe(false)
    expect(preferences.renameGroup('daily', '过早编辑')).toBe(false)
    expect(preferences.moveGroup('daily')).toBe(false)
    expect(preferences.toggleGroup('daily')).toBe(false)
    expect(preferences.reorderItem('log')).toBe(false)
    expect(preferences.reset()).toBe(false)
    request.reject(new Error('Unavailable'))
    expect(await loading).toBe(false)
    expect(await sameLoad).toBe(false)
    expect(preferences.initialized.value).toBe(false)
    expect(preferences.persistenceError.value).toBe(true)
    expect(snapshot(preferences)).toEqual(initial)
    expect(transport.put).not.toHaveBeenCalled()
    expect(await preferences.retrySave()).toBe(true)
    expect(preferences.initialized.value).toBe(true)
    expect(preferences.persistenceError.value).toBe(false)
    expect(preferences.moveItem('log', 'ungrouped')).toBe(true)
    await preferences.flush()
    expect(transport.put).toHaveBeenCalledTimes(1)
  })

  it.each([{ data: {} }, { data: { sidebar: { version: 99 } } }])(
    'does not overwrite an incompatible server response',
    async (response) => {
      const transport = remoteTransport()
      transport.get.mockResolvedValue(response)
      const preferences = createSidebarPreferences({ transport, storage: memoryStorage() })
      expect(await preferences.initialize()).toBe(false)
      expect(preferences.initialized.value).toBe(false)
      expect(preferences.persistenceError.value).toBe(true)
      expect(transport.put).not.toHaveBeenCalled()
    }
  )

  it('serializes saves and sends the newest state after an earlier request finishes', async () => {
    const transport = remoteTransport()
    const first = deferred()
    const second = deferred()
    transport.put.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise)
    const preferences = createSidebarPreferences({ transport, storage: memoryStorage() })
    await preferences.initialize()
    preferences.moveItem('log', 'ungrouped')
    preferences.toggleGroup('reports')
    preferences.removeGroup('daily')
    preferences.addEntry('log', 'reports')
    const newest = snapshot(preferences)
    expect(transport.put).toHaveBeenCalledTimes(1)
    expect(transport.put.mock.calls[0][1].sidebar.groups).toHaveLength(3)
    first.resolve({ data: transport.put.mock.calls[0][1] })
    await vi.waitFor(() => expect(transport.put).toHaveBeenCalledTimes(2))
    expect(transport.put.mock.calls[1][1]).toEqual({ sidebar: newest })
    expect(snapshot(preferences)).toEqual(newest)
    second.resolve({ data: transport.put.mock.calls[1][1] })
    await preferences.flush()
    expect(transport.put).toHaveBeenCalledTimes(2)
    expect(preferences.persistenceError.value).toBe(false)
  })

  it('keeps unsaved state after a failed save and retries it explicitly without automatic polling', async () => {
    const transport = remoteTransport()
    transport.put.mockRejectedValueOnce(new Error('Unavailable'))
    const preferences = createSidebarPreferences({ transport, storage: memoryStorage() })
    await preferences.initialize()
    preferences.removeGroup('daily')
    const edited = snapshot(preferences)
    await preferences.flush()
    expect(transport.put).toHaveBeenCalledTimes(1)
    expect(preferences.persistenceError.value).toBe(true)
    expect(snapshot(preferences)).toEqual(edited)
    expect(await preferences.retrySave()).toBe(true)
    expect(transport.put).toHaveBeenCalledTimes(2)
    expect(transport.put.mock.calls[1][1]).toEqual({ sidebar: edited })
    expect(preferences.persistenceError.value).toBe(false)
  })
})
