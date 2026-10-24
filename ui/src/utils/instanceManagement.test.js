import axios from 'axios'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { createInstanceManagement } from './instanceManagement.js'

const rows = [{ name: '实例甲', path: '/server/mower', state: 'stopped', editable: true }]
const targets = [{ name: '实例甲', path: '/server/mower' }]

afterEach(() => vi.useRealTimers())

describe('instance management transport', () => {
  it('prefers the desktop bridge and preserves native directory selection', async () => {
    const api = {
      get_instances: vi.fn(async () => rows),
      mark_ready: vi.fn(),
      select_path: vi.fn(async () => ({ ok: true })),
      start: vi.fn(async () => ({ ok: true }))
    }
    const target = new EventTarget()
    target.pywebview = { api }
    const client = { get: vi.fn(), post: vi.fn() }
    const manager = createInstanceManagement({ axios: client, target })
    const render = vi.fn()
    await manager.initialize(render)
    expect(render).toHaveBeenCalledWith(rows)
    expect(api.mark_ready).toHaveBeenCalledOnce()
    expect(manager.nativeDirectoryPicker).toBe(true)
    await manager.api.select_path(0, targets[0])
    await manager.api.start(0, targets[0])
    expect(api.select_path).toHaveBeenCalledWith(0, targets[0])
    expect(api.start).toHaveBeenCalledWith(0, targets[0])
    expect(client.get).not.toHaveBeenCalled()
    expect(client.post).not.toHaveBeenCalled()
  })

  it('waits for a pending desktop bridge instead of sending HTTP requests', async () => {
    vi.useFakeTimers()
    const target = new EventTarget()
    target.pywebview = { api: {} }
    const client = { get: vi.fn(), post: vi.fn() }
    const manager = createInstanceManagement({ axios: client, target })
    const render = vi.fn()
    const pending = manager.initialize(render)
    target.pywebview.api = { get_instances: vi.fn(async () => rows), mark_ready: vi.fn() }
    target.dispatchEvent(new Event('pywebviewready'))
    await pending
    expect(render).toHaveBeenCalledWith(rows)
    expect(client.get).not.toHaveBeenCalled()
  })

  it('uses the authenticated axios client and settings header for browser requests', async () => {
    const sent = []
    const client = axios.create({
      headers: { token: 'existing-session-token' },
      adapter: async (config) => {
        sent.push(config)
        return { data: config.method === 'get' ? rows : { ok: true }, status: 200, config }
      }
    })
    const manager = createInstanceManagement({
      axios: client,
      target: new EventTarget(),
      getTargets: () => targets
    })
    await manager.initialize(vi.fn())
    await manager.api.set_path(0, '/server/new-directory', targets[0])
    expect(manager.nativeDirectoryPicker).toBe(false)
    expect(sent[0].url).toMatch(/\/instances$/)
    expect(sent[0].headers.get('token')).toBe('existing-session-token')
    expect(sent[1].headers.get('token')).toBe('existing-session-token')
    expect(sent[1].headers.get('X-Mower-Settings')).toBe('1')
    expect(JSON.parse(sent[1].data)).toEqual({
      action: 'set_path',
      args: [0, '/server/new-directory', targets[0]]
    })
  })

  it.each([
    ['add', ['新实例', ''], ['新实例', '', targets]],
    ['start_all', [], [targets]],
    ['stop_all', [], [targets]],
    ['rename', [0, '新名称', targets[0]], [0, '新名称', targets[0]]],
    ['remove', [0, targets[0]], [0, targets[0]]],
    ['start', [0, targets[0]], [0, targets[0]]],
    ['stop', [0, targets[0]], [0, targets[0]]],
    ['update_settings', [0, { token: 'new' }, targets[0]], [0, { token: 'new' }, targets[0]]],
    ['update_all_settings', [[], targets], [[], targets]]
  ])('sends captured instance identities with browser %s', async (action, args, expected) => {
    const client = {
      get: vi.fn(async () => ({ data: rows })),
      post: vi.fn(async () => ({ data: { ok: true } }))
    }
    const manager = createInstanceManagement({
      axios: client,
      target: new EventTarget(),
      getTargets: () => targets
    })
    await manager.initialize(vi.fn())
    await manager.api[action](...args)
    expect(client.post).toHaveBeenCalledWith(
      expect.stringMatching(/\/instances\/actions$/),
      { action, args: expected },
      expect.objectContaining({ headers: { 'X-Mower-Settings': '1' } })
    )
  })

  it('explains unsupported backend versions and allows an explicit retry', async () => {
    const client = {
      get: vi
        .fn()
        .mockRejectedValueOnce({ response: { status: 404 } })
        .mockResolvedValueOnce({ data: rows })
    }
    const manager = createInstanceManagement({ axios: client, target: new EventTarget() })
    await expect(manager.initialize(vi.fn())).rejects.toThrow('当前 Mower 版本不支持网页实例管理')
    const render = vi.fn()
    await manager.initialize(render)
    expect(render).toHaveBeenCalledWith(rows)
  })

  it('retains backend rejection messages', async () => {
    const client = {
      post: vi.fn().mockRejectedValue({
        response: { status: 409, data: { message: '实例列表已变化，请刷新后重试' } }
      })
    }
    const manager = createInstanceManagement({ axios: client, target: new EventTarget() })
    await expect(manager.api.remove(0, targets[0])).rejects.toThrow('实例列表已变化，请刷新后重试')
  })
})
