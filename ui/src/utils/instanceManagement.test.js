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

  it.each([
    ['get_instances', []],
    ['get_device_settings', [0, targets[0]]],
    ['update_device_settings', [0, {}, targets[0], {}]],
    ['discover_device_settings', [0, {}, targets[0], {}]],
    ['get_common_settings', []],
    ['start_maa_maintenance', ['/MAA', 'stable', 'core', 'update']],
    ['clean_instance_storage', [0, targets[0], ['log'], 7]],
    ['add', ['新实例', '']],
    ['start_all', []],
    ['stop_all', []],
    ['rename', [0, '新名称', targets[0]]],
    ['remove', [0, targets[0]]],
    ['start', [0, targets[0]]],
    ['stop', [0, targets[0]]],
    ['select_path', [0, targets[0]]],
    ['update_settings', [0, { token: 'new' }, targets[0]]],
    ['update_all_settings', [[], targets]]
  ])('refuses browser %s without sending an HTTP request', async (action, args) => {
    const client = {
      get: vi.fn(async () => ({ data: rows })),
      post: vi.fn(async () => ({ data: { ok: true } }))
    }
    const manager = createInstanceManagement({
      axios: client,
      target: new EventTarget(),
      getTargets: () => targets
    })
    await expect(manager.api[action](...args)).rejects.toThrow('本机多开管理器或 Mower 桌面窗口')
    expect(client.get).not.toHaveBeenCalled()
    expect(client.post).not.toHaveBeenCalled()
  })

  it('waits for late native injection even before pywebview exists', async () => {
    const target = new EventTarget()
    const client = {
      get: vi.fn(async () => ({ data: rows })),
      post: vi.fn()
    }
    const manager = createInstanceManagement({ axios: client, target })
    const render = vi.fn()
    const pending = manager.initialize(render)
    expect(render).not.toHaveBeenCalled()
    target.pywebview = { api: { get_instances: vi.fn(async () => rows), mark_ready: vi.fn() } }
    target.dispatchEvent(new Event('pywebviewready'))
    await pending
    expect(render).toHaveBeenCalledWith(rows)
    expect(client.get).not.toHaveBeenCalled()
    expect(client.post).not.toHaveBeenCalled()
  })

  it('retains native rejection messages without falling back to HTTP', async () => {
    const target = new EventTarget()
    target.pywebview = {
      api: {
        get_instances: vi.fn(async () => rows),
        remove: vi.fn().mockRejectedValue(new Error('实例列表已变化，请刷新后重试'))
      }
    }
    const client = { get: vi.fn(), post: vi.fn() }
    const manager = createInstanceManagement({ axios: client, target })
    await expect(manager.api.remove(0, targets[0])).rejects.toThrow('实例列表已变化，请刷新后重试')
    expect(client.get).not.toHaveBeenCalled()
    expect(client.post).not.toHaveBeenCalled()
  })

  it('reports a missing native directory picker without offering HTTP path editing', async () => {
    const target = new EventTarget()
    target.pywebview = { api: { get_instances: vi.fn(async () => rows) } }
    const client = { get: vi.fn(), post: vi.fn() }
    const manager = createInstanceManagement({ axios: client, target })
    await expect(manager.api.select_path(0, targets[0])).rejects.toThrow(
      '当前桌面版本不支持此实例操作'
    )
    expect(client.get).not.toHaveBeenCalled()
    expect(client.post).not.toHaveBeenCalled()
  })
})
