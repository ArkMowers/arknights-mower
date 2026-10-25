import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { readFileSync } from 'node:fs'
import { parse } from '@vue/compiler-sfc'
import { renderToString } from 'vue/server-renderer'
import { compile, createSSRApp, effectScope } from 'vue'
import ManagerTools from './ManagerTools.vue'

const hooks = vi.hoisted(() => ({ mounted: [], unmounted: [] }))
vi.mock('vue', async (original) => ({
  ...(await original()),
  useSSRContext: () => ({ modules: new Set() }),
  onMounted: (callback) => hooks.mounted.push(callback),
  onUnmounted: (callback) => hooks.unmounted.push(callback)
}))

describe('manager maintenance tools', () => {
  let scope, component, api
  beforeEach(async () => {
    vi.useFakeTimers()
    hooks.mounted = []
    hooks.unmounted = []
    api = {
      get_network_settings: vi.fn(async () => ({ http_proxy: '', github_proxy: '' })),
      save_network_settings: vi.fn(async (values) => values),
      get_maa_installations: vi.fn(async () => ({
        groups: [
          {
            target: '/shared/maa',
            instances: ['one', 'two'],
            channels: ['stable'],
            running: false
          }
        ],
        errors: []
      })),
      get_maintenance_status: vi.fn(async () => ({ status: 'idle' })),
      start_maa_maintenance: vi.fn(async () => ({ ok: true })),
      get_storage_usage: vi.fn(async () => ({
        rows: [{ idx: 0, name: 'one', path: '/one', log: 1024, screenshot: 0 }]
      })),
      clean_instance_storage: vi.fn(async () => ({ ok: true, deleted: 2, freed: 1024, errors: [] }))
    }
    scope = effectScope()
    component = scope.run(() => ManagerTools.setup({ api }, { expose() {} }))
    await Promise.all(hooks.mounted.map((callback) => callback()))
  })
  afterEach(() => {
    hooks.unmounted.forEach((callback) => callback())
    scope.stop()
    vi.useRealTimers()
  })
  it('saves proxy edits against their opening snapshot and reports failure without claiming success', async () => {
    component.network.value.http_proxy = 'http://127.0.0.1:7890'
    await component.saveNetwork()
    expect(api.save_network_settings).toHaveBeenCalledWith(
      { http_proxy: 'http://127.0.0.1:7890', github_proxy: '' },
      { http_proxy: '', github_proxy: '' }
    )
    api.save_network_settings.mockRejectedValue(new Error('changed'))
    await component.saveNetwork()
    expect(component.error.value).toBe('changed')
    expect(component.notice.value).toBe('')
  })
  it('requires a matching successful check for the selected directory and component', async () => {
    await component.loadMaa()
    component.job.value = {
      status: 'completed',
      action: 'check',
      target: '/shared/maa',
      channel: 'stable',
      component: 'core',
      result: { available: true }
    }
    expect(component.canUpdate.value).toBe(true)
    component.channel.value = 'beta'
    expect(component.canUpdate.value).toBe(false)
    component.channel.value = 'stable'
    component.groups.value[0].running = true
    expect(component.canUpdate.value).toBe(false)
  })
  it.each([false, undefined])(
    'keeps manager maintenance buttons available regardless of instance update choice %s',
    async (legacyChoice) => {
      await component.loadMaa()
      component.groups.value[0].updates_enabled = legacyChoice
      const { descriptor } = parse(
        readFileSync(new URL('./ManagerTools.vue', import.meta.url), 'utf8')
      )
      const actions = descriptor.template.content
        .match(/<div class="actions">[\s\S]+?<\/div>/g)
        .find((section) => section.includes("maintenance('check')"))
      async function renderActions() {
        const controls = []
        const app = createSSRApp({
          setup: () => ({ ...component }),
          render: compile(actions),
          components: {
            NButton: {
              emits: ['click'],
              setup(_props, { attrs, emit }) {
                controls.push({ disabled: attrs.disabled, emit })
                return () => null
              }
            }
          }
        })
        await renderToString(app)
        return controls
      }
      const [, check, unavailableUpdate] = await renderActions()
      expect(check.disabled).toBe(false)
      expect(unavailableUpdate.disabled).toBe(true)
      check.emit('click')
      await vi.waitFor(() =>
        expect(api.start_maa_maintenance).toHaveBeenCalledWith(
          '/shared/maa',
          'stable',
          'core',
          'check'
        )
      )
      await vi.waitFor(() => expect(component.busy.value).toBe(false))
      component.job.value = {
        status: 'completed',
        action: 'check',
        target: '/shared/maa',
        channel: 'stable',
        component: 'core',
        result: { available: true }
      }
      const [, , update] = await renderActions()
      expect(update.disabled).toBe(false)
      update.emit('click')
      await vi.waitFor(() =>
        expect(api.start_maa_maintenance).toHaveBeenCalledWith(
          '/shared/maa',
          'stable',
          'core',
          'update'
        )
      )
    }
  )
  it('polls only an active maintenance job and stops polling on completion', async () => {
    await component.loadMaa()
    api.get_maintenance_status
      .mockResolvedValueOnce({ status: 'running' })
      .mockResolvedValue({ status: 'completed', message: 'done' })
    await component.maintenance('check')
    expect(api.start_maa_maintenance).toHaveBeenCalledWith('/shared/maa', 'stable', 'core', 'check')
    await vi.advanceTimersByTimeAsync(1000)
    const count = api.get_maintenance_status.mock.calls.length
    await vi.advanceTimersByTimeAsync(5000)
    expect(api.get_maintenance_status).toHaveBeenCalledTimes(count)
    expect(component.job.value.status).toBe('completed')
  })
  it('does not poll after unmount', async () => {
    api.get_maintenance_status.mockResolvedValue({ status: 'running' })
    await component.loadMaa()
    hooks.unmounted.forEach((callback) => callback())
    const count = api.get_maintenance_status.mock.calls.length
    await vi.advanceTimersByTimeAsync(5000)
    expect(api.get_maintenance_status).toHaveBeenCalledTimes(count)
  })
  it('cleans the captured row and explicit categories only after confirmation', async () => {
    await component.loadStorage()
    expect(api.clean_instance_storage).not.toHaveBeenCalled()
    component.cleanup.value = component.storage.value[0]
    component.days.value = 14
    component.categories.value = ['log']
    await component.clean()
    expect(api.clean_instance_storage).toHaveBeenCalledWith(
      0,
      { name: 'one', path: '/one' },
      ['log'],
      14
    )
    expect(component.notice.value).toContain('2 个文件')
    expect(component.cleanup.value).toBeNull()
  })
  it('shows partial cleanup errors together with the actual deleted count', async () => {
    await component.loadStorage()
    component.cleanup.value = component.storage.value[0]
    api.clean_instance_storage.mockResolvedValue({
      ok: true,
      deleted: 1,
      freed: 100,
      errors: ['permission denied']
    })
    await component.clean()
    expect(component.notice.value).toContain('1 个文件')
    expect(component.notice.value).toContain('permission denied')
  })
})
