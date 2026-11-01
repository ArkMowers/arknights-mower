import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { readFileSync } from 'node:fs'
import { parse } from '@vue/compiler-sfc'
import { renderToString } from 'vue/server-renderer'
import { compile, createSSRApp, effectScope, h, nextTick, reactive } from 'vue'
import ProcessControl from './ProcessControl.vue'

const state = vi.hoisted(() => ({
  mounted: [],
  unmounted: [],
  client: null,
  config: null,
  plan: null
}))
vi.mock('vue', async (original) => ({
  ...(await original()),
  useSSRContext: () => ({ modules: new Set() }),
  inject: () => state.client,
  onMounted: (callback) => state.mounted.push(callback),
  onUnmounted: (callback) => state.unmounted.push(callback)
}))
vi.mock('@/stores/config', () => ({ useConfigStore: () => state.config }))
vi.mock('@/stores/plan', () => ({ usePlanStore: () => state.plan }))

describe('process-control recovery across page navigation', () => {
  let scope, component, exposed, session, props

  beforeEach(() => {
    session = new Map()
    vi.stubGlobal('sessionStorage', {
      getItem: (key) => session.get(key) ?? null,
      setItem: (key, value) => session.set(key, value),
      removeItem: (key) => session.delete(key)
    })
    vi.stubGlobal('window', { location: { reload: vi.fn() } })
    props = reactive({ compact: false, resumeOnly: false, running: null })
    state.config = reactive({ autosave_paused: false, flush_config_saves: vi.fn(async () => {}) })
    state.plan = reactive({ autosave_paused: false, wait_for_plan_save: vi.fn(async () => {}) })
    state.client = {
      post: vi.fn(async () => ({ data: { ok: true, id: 'restart-test', message: '已提交' } })),
      get: vi.fn(async (url) => ({
        data: url.endsWith('/info')
          ? { ok: true, supported: true, running: true }
          : { ok: true, status: 'failed', message: '重启失败' }
      }))
    }
  })

  async function mount() {
    state.mounted = []
    state.unmounted = []
    scope = effectScope()
    component = scope.run(() =>
      ProcessControl.setup(props, { expose: (value) => (exposed = value) })
    )
    await Promise.all(state.mounted.map((callback) => callback()))
    await nextTick()
  }

  function unmount() {
    state.unmounted.forEach((callback) => callback())
    scope.stop()
    scope = null
  }

  async function render() {
    const { descriptor } = parse(
      readFileSync(new URL('./ProcessControl.vue', import.meta.url), 'utf8')
    )
    const app = createSSRApp({
      setup: () => ({ ...component, props }),
      render: compile(descriptor.template.content)
    })
    for (const name of ['NText', 'NSpace', 'NButton', 'NCard', 'NPopconfirm', 'NAlert']) {
      app.component(name, {
        setup:
          (_, { attrs, slots }) =>
          () =>
            h(name === 'NButton' ? 'button' : 'div', attrs, [slots.trigger?.(), slots.default?.()])
      })
    }
    return renderToString(app)
  }

  afterEach(() => {
    if (scope) unmount()
    vi.unstubAllGlobals()
  })

  it.each(['failed', 'lost response', 'timeout'])(
    'retains the pause prompt and reload action after %s and remounting',
    async (failure) => {
      await mount()
      if (failure === 'lost response') state.client.post.mockRejectedValueOnce(new Error('offline'))
      if (failure === 'timeout') {
        session.set(
          'mower-process-control:/process-control',
          JSON.stringify({ id: 'old', action: 'restart', startedAt: Date.now() - 300000 })
        )
        unmount()
        await mount()
      } else {
        await component.submit('restart')
      }
      expect(session.size).toBe(0)
      expect(state.config.autosave_paused).toBe(true)
      expect(state.plan.autosave_paused).toBe(true)
      unmount()
      await mount()
      // These are the template conditions for the recovery alert and button.
      expect(component.savesPaused.value).toBe(true)
      expect(component.busy.value).toBe(false)
      const requests = state.client.post.mock.calls.length
      await component.submit('restart')
      expect(state.client.post).toHaveBeenCalledTimes(requests)
      component.reload()
      expect(window.location.reload).toHaveBeenCalledOnce()
      expect(state.config.autosave_paused).toBe(true)
    }
  )

  it('keeps compact process actions synchronized with the live running prop', async () => {
    props.compact = true
    props.running = false
    await mount()
    expect(component.effectiveRunning.value).toBe(false)

    props.running = true
    await nextTick()
    expect(component.effectiveRunning.value).toBe(true)

    props.running = false
    await nextTick()
    expect(component.effectiveRunning.value).toBe(false)
  })

  it('shows and hides continuation in the full panel when the live running state changes', async () => {
    state.client.get.mockResolvedValue({
      data: { ok: true, supported: true, running: false }
    })
    props.running = false
    await mount()
    expect(await render()).not.toContain('data-settings-label="重启续接"')

    props.running = true
    await nextTick()
    expect(await render()).toContain('data-settings-label="重启续接"')
    expect(exposed.canRunProcessAction.value).toBe(true)

    props.running = false
    await nextTick()
    expect(await render()).not.toContain('data-settings-label="重启续接"')
    await exposed.restartResume()
    expect(state.client.post).not.toHaveBeenCalled()
  })

  it('keeps only continuation in the resume-only panel and uses the existing save flow', async () => {
    props.resumeOnly = true
    props.running = true
    await mount()
    const html = await render()
    expect(html).toContain('data-settings-label="重启续接"')
    expect(html).not.toContain('data-settings-label="重启 Mower 进程"')
    expect(html).not.toContain('data-settings-label="结束 Mower 进程"')

    await exposed.restartResume()
    expect(state.config.flush_config_saves).toHaveBeenCalled()
    expect(state.plan.wait_for_plan_save).toHaveBeenCalled()
    expect(state.client.post).toHaveBeenCalledWith(
      '/process-control/action',
      { action: 'restart_resume' },
      { headers: { 'X-Mower-Control': '1' } }
    )
    expect(component.message.value).toBe('重启失败')
    expect(component.savesPaused.value).toBe(true)
  })

  it('explains why continuation is unavailable when the resume-only panel has no running task', async () => {
    props.resumeOnly = true
    props.running = false
    await mount()
    const html = await render()
    expect(html).toContain('当前没有运行中的任务，无需重启续接。')
    expect(html).not.toContain('data-settings-label="重启续接"')
    expect(html).not.toContain('data-settings-label="重启 Mower 进程"')
    expect(html).not.toContain('data-settings-label="结束 Mower 进程"')
    await exposed.restartResume()
    expect(state.client.post).not.toHaveBeenCalled()
  })

  it('keeps unsupported instances from continuing through the resume-only panel', async () => {
    props.resumeOnly = true
    props.running = true
    state.client.get.mockResolvedValue({
      data: { ok: true, supported: false, running: true }
    })
    await mount()
    const html = await render()
    expect(html).toContain('data-settings-label="重启续接"')
    expect(html.match(/<button[^>]*>/g)).toEqual(['<button type="primary" disabled>'])
    expect(exposed.canRunProcessAction.value).toBe(false)
    await exposed.restartResume()
    expect(state.client.post).not.toHaveBeenCalled()
  })

  it('retains pending-operation errors and save recovery in the resume-only panel', async () => {
    props.resumeOnly = true
    props.running = true
    session.set(
      'mower-process-control:/process-control',
      JSON.stringify({ id: 'pending', action: 'restart_resume', startedAt: Date.now() })
    )
    await mount()
    const html = await render()
    expect(html).toContain('重启失败')
    expect(html).toContain('配置自动保存已暂停。')
    expect(html).toContain('刷新页面')
    expect(component.savesPaused.value).toBe(true)
    expect(component.busy.value).toBe(false)
    expect(state.client.post).not.toHaveBeenCalled()
    expect(session.size).toBe(0)
  })

  it.each(['restart_resume', 'apply_schedule'])(
    'uses the existing save and pending-job flow for %s',
    async (action) => {
      state.client.get.mockImplementation(async (url) => ({
        data: url.endsWith('/info')
          ? { ok: true, supported: true, running: true }
          : { ok: true, status: 'succeeded', message: '续接完成' }
      }))
      await mount()
      await component.submit(action)
      expect(state.client.post).toHaveBeenCalledWith(
        '/process-control/action',
        { action },
        { headers: { 'X-Mower-Control': '1' } }
      )
      expect(state.config.autosave_paused).toBe(true)
      expect(state.plan.autosave_paused).toBe(true)
      expect(window.location.reload).toHaveBeenCalledOnce()
      expect(session.size).toBe(0)
    }
  )

  it.each([
    ['applySchedule', 'apply_schedule'],
    ['restartResume', 'restart_resume']
  ])('allows %s only while running and ready', async (method, action) => {
    props.compact = true
    props.running = false
    await mount()
    expect(exposed.canRunProcessAction.value).toBe(false)
    await exposed[method]()
    expect(state.client.post).not.toHaveBeenCalled()

    props.running = true
    await nextTick()
    expect(exposed.canRunProcessAction.value).toBe(true)
    await exposed[method]()
    expect(state.client.post).toHaveBeenCalledWith(
      '/process-control/action',
      { action },
      { headers: { 'X-Mower-Control': '1' } }
    )
  })

  it('leaves saving enabled after an explicit rejection and remount', async () => {
    state.client.post.mockResolvedValueOnce({ data: { ok: false, message: '已拒绝' } })
    await mount()
    await component.submit('restart')
    unmount()
    await mount()
    expect(component.savesPaused.value).toBe(false)
    expect(state.config.autosave_paused).toBe(false)
    expect(state.plan.autosave_paused).toBe(false)
  })
})
