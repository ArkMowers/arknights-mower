import { describe, expect, it, vi } from 'vitest'
import { reactive } from 'vue'
import { CONFIG_GENERATION_HEADER, createConfigProfiles } from './configProfiles'
import { createSaveCoordinator } from '@/utils/configPersistence'

const metadata = () => ({
  ok: true,
  active_id: 'first',
  generation: '0',
  busy: false,
  profiles: [
    { id: 'first', name: '主账号' },
    { id: 'second', name: '备用账号' }
  ],
  groups: [
    {
      key: 'device',
      label: '设备与游戏连接',
      description: '设备身份与截图触控',
      section: '连接与运行'
    },
    { key: 'runtime', label: '运行参数', description: '性能与采样', section: '连接与运行' },
    { key: 'normal_plan', label: '正常排班', description: '主表和副表', section: '排班' }
  ]
})

function deferred() {
  let resolve, reject
  const promise = new Promise((done, fail) => {
    resolve = done
    reject = fail
  })
  return { promise, resolve, reject }
}

async function setup({ beforeChange } = {}) {
  const events = []
  const config = reactive({
    autosave_paused: false,
    flush_config_saves: vi.fn(async () => events.push('config'))
  })
  const plan = reactive({
    autosave_paused: false,
    wait_for_plan_save: vi.fn(async () => events.push('plan'))
  })
  const rescuePlan = reactive({
    autosave_paused: false,
    wait_for_plan_save: vi.fn(async () => events.push('rescue'))
  })
  const axios = {
    defaults: { headers: { common: {} } },
    get: vi.fn(async () => ({ data: metadata() })),
    post: vi.fn(),
    patch: vi.fn()
  }
  const blocked = { value: false }
  const reload = vi.fn()
  const download = vi.fn(async () => events.push('download'))
  const controller = createConfigProfiles({
    axios,
    config,
    plan,
    rescuePlan,
    blocked: () => blocked.value,
    beforeChange,
    reload,
    download
  })
  await controller.bootstrap()
  return { controller, axios, config, plan, rescuePlan, blocked, events, reload, download }
}

describe('configuration profile operations', () => {
  it('bootstraps the generation before allowing operations and leaves it fixed on list refresh', async () => {
    const { controller, axios, config, plan, rescuePlan } = await setup()
    expect(axios.defaults.headers.common[CONFIG_GENERATION_HEADER]).toBe('0')
    axios.get.mockResolvedValueOnce({
      data: { ...metadata(), active_id: 'second', generation: 'next' }
    })
    await controller.refresh()
    expect(controller.state.value.active_id).toBe('second')
    expect(axios.defaults.headers.common[CONFIG_GENERATION_HEADER]).toBe('0')
    expect(controller.stale.value).toBe(true)
    for (const store of [config, plan, rescuePlan]) expect(store.autosave_paused).toBe(true)
    expect(controller.writeDisabled.value).toBe(true)
  })

  it('uses backend groups for section selection, new defaults and complete copies', async () => {
    const { controller } = await setup()
    controller.open('create')
    expect(controller.selected.value).toEqual([])
    expect(controller.sections.value.map((section) => section.label)).toEqual([
      '连接与运行',
      '排班'
    ])
    controller.toggleSection(controller.sections.value[0], true)
    expect(controller.selected.value).toEqual(['device', 'runtime'])
    controller.toggleSection(controller.sections.value[0], false)
    expect(controller.selected.value).toEqual([])
    controller.open('copy')
    expect(controller.selected.value).toEqual(['device', 'runtime', 'normal_plan'])
    expect(controller.name.value).toBe('主账号 副本')
  })

  it('drains all three stores before creating and keeps them paused through reload', async () => {
    const { controller, axios, config, plan, rescuePlan, events, reload } = await setup()
    axios.post.mockImplementation(async () => {
      events.push('create')
      for (const store of [config, plan, rescuePlan]) expect(store.autosave_paused).toBe(true)
      return { data: { ...metadata(), active_id: 'new', generation: 'next' } }
    })
    controller.open('create')
    controller.name.value = '新档案'
    controller.selected.value = ['device']
    await controller.submit()
    expect(events).toEqual(['config', 'plan', 'rescue', 'config', 'create'])
    expect(axios.post).toHaveBeenCalledWith(
      expect.stringContaining('/config-profiles'),
      { name: '新档案', inherit: ['device'] },
      {
        headers: {
          'X-Mower-Settings': '1',
          [CONFIG_GENERATION_HEADER]: '0'
        }
      }
    )
    expect(controller.pendingReload.value).toBe(true)
    expect(reload).toHaveBeenCalledOnce()
    for (const store of [config, plan, rescuePlan]) expect(store.autosave_paused).toBe(true)
  })

  it('sends selected current content as keep when switching to a different profile', async () => {
    const { controller, axios } = await setup()
    axios.post.mockResolvedValue({
      data: { ...metadata(), active_id: 'second', generation: 'next' }
    })
    controller.open('activate', 'second')
    controller.selected.value = ['device', 'normal_plan']
    await controller.submit()
    expect(axios.post).toHaveBeenCalledWith(
      expect.stringContaining('/second/activate'),
      { keep: ['device', 'normal_plan'] },
      expect.any(Object)
    )
  })

  it.each(['create', 'copy', 'rename', 'import', 'activate'])(
    'waits for saves and the beforeChange hook before submitting %s',
    async (action) => {
      const pendingSave = deferred()
      const barrier = deferred()
      const beforeChange = vi.fn(() => barrier.promise)
      const { controller, axios, config, plan, rescuePlan, reload } = await setup({ beforeChange })
      config.flush_config_saves.mockReturnValueOnce(pendingSave.promise)
      axios.post.mockResolvedValue({ data: { ...metadata(), generation: 'next' } })
      axios.patch.mockResolvedValue({ data: metadata() })
      controller.open(action, action === 'activate' ? 'second' : null)
      controller.name.value = '新档案'
      if (action === 'import') {
        controller.selectFile({
          target: { files: [new File(['zip'], '备用账号.zip')], value: 'selected' }
        })
      }
      const submitted = controller.submit()
      expect(beforeChange).not.toHaveBeenCalled()
      expect(axios.post).not.toHaveBeenCalled()
      expect(axios.patch).not.toHaveBeenCalled()
      pendingSave.resolve()
      await vi.waitFor(() => expect(beforeChange).toHaveBeenCalledOnce())
      expect(config.flush_config_saves).toHaveBeenCalledTimes(2)
      expect(plan.wait_for_plan_save).toHaveBeenCalledOnce()
      expect(rescuePlan.wait_for_plan_save).toHaveBeenCalledOnce()
      for (const store of [config, plan, rescuePlan]) expect(store.autosave_paused).toBe(true)
      expect(controller.busy.value).toBe(true)
      expect(axios.post).not.toHaveBeenCalled()
      expect(axios.patch).not.toHaveBeenCalled()
      expect(reload).not.toHaveBeenCalled()
      barrier.resolve()
      await submitted
      expect(action === 'rename' ? axios.patch : axios.post).toHaveBeenCalledOnce()
      expect(controller.error.value).toBe('')
    }
  )

  it('resumes saves and keeps the operation editable when beforeChange rejects', async () => {
    const barrier = deferred()
    const beforeChange = vi.fn(() => barrier.promise)
    const { controller, axios, config, plan, rescuePlan, reload } = await setup({ beforeChange })
    controller.open('activate', 'second')
    controller.selected.value = ['device']
    const submitted = controller.submit()
    await vi.waitFor(() => expect(beforeChange).toHaveBeenCalledOnce())
    barrier.reject(new Error('侧边栏尚未保存，请重试后再切换档案'))
    await submitted
    expect(axios.post).not.toHaveBeenCalled()
    expect(axios.patch).not.toHaveBeenCalled()
    expect(reload).not.toHaveBeenCalled()
    expect(controller.error.value).toBe('侧边栏尚未保存，请重试后再切换档案')
    expect(controller.stale.value).toBe(false)
    expect(controller.pendingReload.value).toBe(false)
    expect(controller.busy.value).toBe(false)
    expect(controller.writeDisabled.value).toBe(false)
    expect(controller.dialog.value).toMatchObject({ action: 'activate', target: 'second' })
    expect(controller.selected.value).toEqual(['device'])
    for (const store of [config, plan, rescuePlan]) expect(store.autosave_paused).toBe(false)
    beforeChange.mockResolvedValueOnce()
    axios.post.mockResolvedValue({
      data: { ...metadata(), active_id: 'second', generation: 'next' }
    })
    await controller.submit()
    expect(axios.post).toHaveBeenCalledOnce()
    expect(reload).toHaveBeenCalledOnce()
  })

  it('imports a named ZIP as a new profile with an explicit keep array', async () => {
    const { controller, axios } = await setup()
    axios.post.mockResolvedValue({
      data: { ...metadata(), active_id: 'imported', generation: 'next' }
    })
    controller.open('import')
    const input = { files: [new File(['zip'], '备用账号.zip')], value: 'selected' }
    controller.selectFile({ target: input })
    expect(input.value).toBe('')
    controller.selected.value = ['runtime']
    await controller.submit()
    const [url, form] = axios.post.mock.calls[0]
    expect(url).toContain('/config-profiles/import')
    expect(form.get('name')).toBe('备用账号')
    expect(form.get('keep')).toBe('["runtime"]')
    expect(form.get('backup').name).toBe('备用账号.zip')
  })

  it('renames without reloading or changing the generation', async () => {
    const { controller, axios, config, plan, rescuePlan, reload } = await setup()
    axios.patch.mockResolvedValue({
      data: { ...metadata(), profiles: [{ id: 'first', name: '新名称' }] }
    })
    controller.open('rename')
    controller.name.value = '新名称'
    await controller.submit()
    expect(axios.patch).toHaveBeenCalledWith(
      expect.stringContaining('/first'),
      { name: '新名称' },
      expect.any(Object)
    )
    expect(controller.state.value.profiles[0].name).toBe('新名称')
    expect(controller.message.value).toBe('')
    expect(axios.defaults.headers.common[CONFIG_GENERATION_HEADER]).toBe('0')
    expect(reload).not.toHaveBeenCalled()
    for (const store of [config, plan, rescuePlan]) expect(store.autosave_paused).toBe(false)
  })

  it.each(['code', 'error'])(
    'keeps old stores paused when a generation conflict uses %s',
    async (field) => {
      const { controller, axios, config, plan, rescuePlan } = await setup()
      axios.post.mockRejectedValue({
        response: { status: 409, data: { [field]: 'configuration_changed', message: '档案已变更' } }
      })
      controller.open('activate', 'second')
      await controller.submit()
      expect(controller.stale.value).toBe(true)
      for (const store of [config, plan, rescuePlan]) expect(store.autosave_paused).toBe(true)
    }
  )

  it('retains the form and resumes saving after an explicit validation rejection', async () => {
    const { controller, axios, config } = await setup()
    axios.post.mockRejectedValue({ response: { status: 400, data: { message: '名称已存在' } } })
    controller.open('create')
    controller.name.value = '重复名称'
    await controller.submit()
    expect(config.autosave_paused).toBe(false)
    expect(controller.dialog.value.action).toBe('create')
    expect(controller.name.value).toBe('重复名称')
    expect(controller.error.value).toBe('名称已存在')
    expect(controller.stale.value).toBe(false)
  })

  it('keeps stale stores paused when an overlapping operation releases its pause', async () => {
    const { controller, config, plan, rescuePlan } = await setup()
    const importing = createSaveCoordinator(config, plan)
    await importing.pauseAndDrain()
    await controller.observeFailure({
      response: { status: 409, data: { code: 'configuration_changed' } }
    })
    importing.resume()
    expect(controller.stale.value).toBe(true)
    for (const store of [config, plan, rescuePlan]) expect(store.autosave_paused).toBe(true)
  })

  it.each(['rename-success', 'validation-error', 'before-change-error'])(
    'keeps a generation freeze when %s completes an already paused operation',
    async (outcome) => {
      const pending = deferred()
      const beforeChange =
        outcome === 'before-change-error' ? vi.fn(() => pending.promise) : undefined
      const { controller, axios, config, plan, rescuePlan } = await setup({ beforeChange })
      if (outcome === 'rename-success') axios.patch.mockReturnValueOnce(pending.promise)
      else if (outcome === 'validation-error') axios.post.mockReturnValueOnce(pending.promise)
      controller.open(outcome === 'rename-success' ? 'rename' : 'create')
      controller.name.value = '新名称'
      const submitted = controller.submit()
      await vi.waitFor(() => {
        expect(config.autosave_paused).toBe(true)
        if (outcome !== 'before-change-error')
          expect(outcome === 'rename-success' ? axios.patch : axios.post).toHaveBeenCalledOnce()
        else expect(beforeChange).toHaveBeenCalledOnce()
      })
      await controller.observeFailure({
        response: { status: 409, data: { code: 'configuration_changed' } }
      })
      if (outcome === 'rename-success') pending.resolve({ data: metadata() })
      else if (outcome === 'validation-error')
        pending.reject({ response: { status: 400, data: { message: '名称已存在' } } })
      else pending.reject(new Error('布局保存失败'))
      await submitted
      expect(controller.stale.value).toBe(true)
      for (const store of [config, plan, rescuePlan]) expect(store.autosave_paused).toBe(true)
    }
  )

  it('freezes after a lost response and never replays the submitted action', async () => {
    const { controller, axios, config, reload } = await setup()
    axios.post.mockRejectedValue(new Error('连接中断'))
    controller.open('activate', 'second')
    await controller.submit()
    expect(config.autosave_paused).toBe(true)
    expect(controller.stale.value).toBe(true)
    expect(controller.error.value).toContain('操作结果尚未确认')
    await controller.submit()
    await controller.refresh()
    expect(axios.post).toHaveBeenCalledOnce()
    expect(reload).not.toHaveBeenCalled()
    expect(config.autosave_paused).toBe(true)
  })

  it('keeps reload recovery available when the operation succeeds but reload fails', async () => {
    const { controller, axios, config, reload } = await setup()
    axios.post.mockResolvedValue({ data: { ...metadata(), generation: 'next' } })
    reload.mockImplementationOnce(() => {
      throw new Error('页面刷新失败')
    })
    controller.open('activate', 'second')
    await controller.submit()
    expect(controller.pendingReload.value).toBe(true)
    expect(config.autosave_paused).toBe(true)
    expect(controller.error.value).toContain('页面未能重新加载')
    controller.reloadPage()
    expect(reload).toHaveBeenCalledTimes(2)
    expect(axios.post).toHaveBeenCalledOnce()
  })

  it('disables writes while running but exports after draining without pausing stores', async () => {
    const { controller, blocked, config, events, download } = await setup()
    blocked.value = true
    expect(controller.writeDisabled.value).toBe(true)
    controller.open('create')
    expect(controller.dialog.value).toBe(null)
    await controller.open('export')
    expect(events).toEqual(['config', 'plan', 'rescue', 'config', 'download'])
    expect(download).toHaveBeenCalledWith(
      expect.any(Object),
      expect.stringContaining('/config-profiles/export')
    )
    expect(controller.message.value).toBe('')
    expect(config.autosave_paused).toBe(false)
  })

  it('clears earlier success feedback when a download fails', async () => {
    const { controller, download } = await setup()
    controller.message.value = '档案已重命名。'
    download.mockRejectedValueOnce(new Error('下载请求失败'))
    await controller.open('export')
    expect(controller.message.value).toBe('')
    expect(controller.error.value).toBe('下载请求失败')
  })

  it.each([
    ['config.txt', 4, 'ZIP'],
    ['oversize.zip', 16 * 1024 * 1024 + 1, '16 MB']
  ])(
    'discards the previous ZIP when replacement %s is rejected',
    async (filename, size, reason) => {
      const { controller, axios, config } = await setup()
      controller.open('import')
      controller.selectFile({
        target: { files: [new File(['zip'], '有效备份.zip')], value: 'selected' }
      })
      expect(controller.file.value.name).toBe('有效备份.zip')
      const replacement = new File(['invalid'], filename)
      Object.defineProperty(replacement, 'size', { value: size })
      controller.selectFile({ target: { files: [replacement], value: 'replacement' } })
      expect(controller.file.value).toBe(null)
      expect(controller.error.value).toContain(reason)
      await controller.submit()
      expect(controller.error.value).toBe('请选择 ZIP 档案备份')
      expect(axios.post).not.toHaveBeenCalled()
      expect(config.autosave_paused).toBe(false)
    }
  )

  it('rejects empty names and unsupported upload files before pausing or submitting', async () => {
    const { controller, axios, config } = await setup()
    controller.open('create')
    await controller.submit()
    expect(controller.error.value).toBe('请填写档案名称')
    controller.open('import')
    controller.selectFile({ target: { files: [new File(['text'], 'config.txt')], value: 'file' } })
    expect(controller.file.value).toBe(null)
    expect(controller.error.value).toContain('ZIP')
    expect(config.autosave_paused).toBe(false)
    expect(axios.post).not.toHaveBeenCalled()
  })
})
