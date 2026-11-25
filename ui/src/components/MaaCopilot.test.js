import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createSSRApp, effectScope, ref, watch } from 'vue'
import { renderToString } from 'vue/server-renderer'
import Component from './MaaCopilot.vue'
import Sss from './MaaSss.vue'

const state = vi.hoisted(() => ({
  config: {},
  client: null,
  mountForRender: false,
  error: vi.fn(),
  warning: vi.fn(),
  success: vi.fn(),
  flush: vi.fn()
}))
vi.mock('vue', async (original) => {
  const vue = await original()
  return {
    ...vue,
    inject: (key) => (key === 'axios' ? state.client : false),
    onMounted: (callback) => {
      if (state.mountForRender) vue.onServerPrefetch(callback)
    },
    useSSRContext: () => ({ modules: new Set() })
  }
})
vi.mock('@/stores/config', () => ({
  useConfigStore: () => ({ ...state.config, flush_config_saves: state.flush })
}))
vi.mock('pinia', () => ({ storeToRefs: (store) => store }))
vi.mock('./MaaTaskStatus.vue', () => ({ default: { render: () => null } }))
vi.mock('naive-ui', async () => {
  const { h } = await import('vue')
  const wrapper = {
    inheritAttrs: false,
    setup:
      (_, { slots }) =>
      () =>
        h('div', slots.default?.())
  }
  return {
    ...Object.fromEntries(
      [
        'NAlert',
        'NButton',
        'NCard',
        'NCheckbox',
        'NDropdown',
        'NEmpty',
        'NFlex',
        'NForm',
        'NFormItem',
        'NImage',
        'NIcon',
        'NTag',
        'NInput',
        'NInputNumber',
        'NRadio',
        'NRadioGroup',
        'NSelect',
        'NSpace',
        'NText',
        'NUpload'
      ].map((name) => [name, wrapper])
    ),
    useThemeVars: () => ({ value: {} }),
    useMessage: () => ({ error: state.error, warning: state.warning, success: state.success })
  }
})
let scope
let component
const first = { id: 'a'.repeat(64), stage_name: '1-7', title: '作业一' }
const second = { id: 'b'.repeat(64), stage_name: 'CE-6', title: '作业二' }
beforeEach(() => {
  state.mountForRender = false
  vi.clearAllMocks()
  state.config = { copilot: ref({ scripts: [], user_additional: [] }), sss: ref({ scripts: [] }) }
  state.client = {
    get: vi.fn(async () => ({ data: { scripts: [first, second] } })),
    post: vi.fn(async () => ({ data: first })),
    delete: vi.fn(async () => ({ data: { ok: true } }))
  }
  scope = effectScope()
  component = scope.run(() => Component.setup({}, { expose: () => {} }))
  component.library.value = [first, second]
})
afterEach(() => {
  scope.stop()
  vi.unstubAllGlobals()
})

describe('backup file count warning', () => {
  const warning = '整机备份文件数接近上限。'
  it.each([
    [Component, {}, 'maa-copilot'],
    [Component, { paradox: true }, 'maa-paradox'],
    [Sss, {}, 'sss-copilot']
  ])('renders the warning returned when the editor loads', async (editor, props, endpoint) => {
    state.config.paradox = ref({ scripts: [] })
    state.mountForRender = true
    state.client.get.mockResolvedValueOnce({ data: { scripts: [], backup_warning: warning } })
    const render = () => renderToString(createSSRApp(editor, props))
    expect(await render()).toContain(warning)
    expect(state.client.get).toHaveBeenCalledWith(
      expect.stringMatching(new RegExp('/' + endpoint + '$'))
    )
    expect(await render()).not.toContain(warning)
  })

  it('updates the warning after upload and clears it after deleting the file', async () => {
    state.client.get.mockResolvedValueOnce({ data: { scripts: [first], backup_warning: warning } })
    await component.upload({
      file: { file: new Blob(['{}']) },
      onFinish: vi.fn(),
      onError: vi.fn()
    })
    expect(component.backupWarning.value).toBe(warning)
    state.config.copilot.value.scripts = []
    await component.delete_script()
    expect(component.backupWarning.value).toBe('')
    expect(state.client.get).toHaveBeenCalledTimes(2)
  })

  it('preserves a successful download when the library refresh fails', async () => {
    state.client.get
      .mockResolvedValueOnce({ data: { data: { content: '{}' } } })
      .mockRejectedValueOnce(new Error('offline'))
    component.code.value = '456'
    await component.download()
    expect(state.config.copilot.value.scripts.map(({ id }) => id)).toEqual([first.id])
    expect(component.failures.value).toEqual([])
    expect(state.success).toHaveBeenCalledOnce()
    expect(state.error).toHaveBeenCalledWith('读取作业失败')
  })
})

describe('ordinary Copilot library and queue', () => {
  it.each([false, true])(
    'offers individual progress without a bulk restart (paradox %s)',
    async (paradox) => {
      state.config.paradox = ref({ scripts: [] })
      const html = await renderToString(createSSRApp(Component, { paradox }))
      expect(html).toContain('点击作业状态')
      expect(html).not.toContain('重新执行整份队列')
      expect(html).not.toContain('执行勾选列表')
      expect(html).not.toContain('当前关卡作业')
      expect(html).not.toContain('执行一次手动任务')
    }
  )

  it('shows ordinary Copilot settings without a model setup warning', async () => {
    const ordinary = await renderToString(createSSRApp(Component))
    expect(ordinary).toContain('队列统一设置')
    expect(ordinary).not.toContain('AI 助手与模型服务')
  })
  it('offers roster assistance only for ordinary automatic formation', async () => {
    state.config.paradox = ref({ scripts: [] })
    const render = (props = {}) => renderToString(createSSRApp(Component, props))
    expect(await render()).not.toContain('使用干员练度辅助编队')
    state.config.copilot.value.formation = true
    expect(await render()).toContain('使用干员练度辅助编队')
    expect(await render({ paradox: true })).not.toContain('使用干员练度辅助编队')
  })
  it('shares one formation policy across ordinary entries and shows a name only for designated support', async () => {
    state.config.copilot.value.scripts = [{ id: first.id }, { id: first.id, is_raid: true }]
    state.config.paradox = ref({ scripts: [{ id: second.id }] })
    const render = (paradox = false) => renderToString(createSSRApp(Component, { paradox }))
    const ordinary = await render()
    expect(ordinary.match(/aria-label="队列统一设置"/g)).toHaveLength(1)
    expect(ordinary.match(/允许使用理智药/g)).toHaveLength(1)
    expect(ordinary).not.toContain('助战方式')
    state.config.copilot.value.formation = true
    state.config.copilot.value.support_unit_name = '能天使'
    for (const usage of [2, 1, 3, 0, 2]) {
      state.config.copilot.value.support_unit_usage = usage
      const html = await render()
      expect(html).toContain('助战方式')
      expect(html.includes('指定助战')).toBe(usage === 2)
    }
    expect(state.config.copilot.value.support_unit_name).toBe('能天使')
    expect(await render(true)).not.toContain('队列统一设置')
  })
  it.each([
    'prts://123',
    '  prts://123  ',
    'maa://123',
    '123',
    'https://prts.plus/operation/123',
    'https://prts.plus/operation/123/?source=share#details'
  ])(
    'downloads %s through the existing proxy and imports into the separate ordinary library',
    async (code) => {
      state.client.get.mockImplementation(async (url) => ({
        data: url.includes('/network/')
          ? { data: { content: '{"stage_name":"1-7","actions":[]}' } }
          : { scripts: [first] }
      }))
      component.code.value = code
      await component.download()
      expect(state.client.get).toHaveBeenCalledWith(
        expect.stringMatching(/\/network\/maa-copilot\/123$/)
      )
      expect(state.client.post).toHaveBeenCalledWith(
        expect.stringMatching(/\/maa-copilot$/),
        expect.any(FormData)
      )
      expect(state.config.copilot.value.scripts).toEqual([
        { id: first.id, nav_name_override: '', is_raid: false }
      ])
      expect(component.loading.value).toBe(false)
    }
  )
  function mock_set(ids = ['456', '789', '456'], difficultyById = {}) {
    state.client.get.mockImplementation(async (url) => {
      if (url.endsWith('/network/maa-copilot-set/123')) return { data: { ids } }
      if (url.includes('/network/maa-copilot/')) {
        return {
          data: {
            data: {
              content: JSON.stringify({
                stage_name: url.endsWith('789') ? 'second' : 'first',
                difficulty: difficultyById[url.split('/').at(-1)],
                actions: []
              })
            }
          }
        }
      }
      return { data: { scripts: [first, second], backup_warning: '整机备份文件数接近上限。' } }
    })
    state.client.post.mockImplementation(async (_url, form) => {
      const content = JSON.parse(await form.get('copilot').text())
      return { data: content.stage_name === 'second' ? second : first }
    })
  }
  it('imports an operation set in member order and preserves repeated entries', async () => {
    mock_set()
    component.add_script(second.id)
    const original = { ...state.config.copilot.value.scripts[0] }
    component.code.value = '  s123  '
    await component.download()
    expect(state.client.get).toHaveBeenCalledWith(
      expect.stringMatching(/\/network\/maa-copilot-set\/123$/)
    )
    expect(
      state.client.get.mock.calls
        .filter(([url]) => url.includes('/network/maa-copilot/'))
        .map(([url]) => url.split('/').at(-1))
    ).toEqual(['456', '789'])
    expect(state.config.copilot.value.scripts).toEqual([
      original,
      { id: first.id, nav_name_override: '', is_raid: false },
      { id: second.id, nav_name_override: '', is_raid: false },
      { id: first.id, nav_name_override: '', is_raid: false }
    ])
    expect(state.success).toHaveBeenCalledOnce()
    expect(state.error).not.toHaveBeenCalled()
    expect(component.code.value).toBe('')
    expect(component.loading.value).toBe(false)
  })
  it('expands each downloaded member in place and preserves existing raid selections', async () => {
    mock_set()
    component.add_script(first.id)
    state.config.copilot.value.scripts[0].is_raid = true
    state.client.post
      .mockResolvedValueOnce({ data: { ...first, difficulty: 3 } })
      .mockResolvedValueOnce({ data: { ...second, difficulty: 2 } })
      .mockResolvedValueOnce({ data: { ...first, difficulty: 3 } })
    component.code.value = 'prts://s123'
    await component.download()
    expect(state.config.copilot.value.scripts.map((item) => [item.id, item.is_raid])).toEqual([
      [first.id, true],
      [first.id, false],
      [first.id, true],
      [second.id, true],
      [first.id, false],
      [first.id, true]
    ])
  })
  it.each([
    [0, [false]],
    [1, [false]],
    [2, [true]],
    [3, [false, true]]
  ])(
    'applies difficulty %i to file uploads and existing library selections',
    async (difficulty, expected) => {
      const info = { ...first, difficulty }
      state.client.post.mockResolvedValue({ data: info })
      state.client.get.mockResolvedValue({ data: { scripts: [info] } })
      await component.upload({
        file: { file: new Blob(['{}']) },
        onFinish: vi.fn(),
        onError: vi.fn()
      })
      component.add_script(first.id)
      expect(state.config.copilot.value.scripts.map((item) => item.is_raid)).toEqual([
        ...expected,
        ...expected
      ])
    }
  )
  it('reports an empty set before requesting any member', async () => {
    mock_set([])
    component.code.value = 'prts://s123'
    await component.download()
    expect(state.client.get).toHaveBeenCalledTimes(1)
    expect(state.client.post).not.toHaveBeenCalled()
    expect(state.error).toHaveBeenCalledWith(expect.stringContaining('作业集为空'))
  })

  it('downloads and validates each member before publishing both queues', async () => {
    const calls = []
    state.client.get.mockImplementation(async (url) => {
      if (url.endsWith('/maa-copilot-set/123'))
        return { data: { ids: ['1', '2', null, '3', '4', '5', '6', '7', '8'] } }
      if (!url.includes('/network/')) return { data: { scripts: [first, second] } }
      const id = url.split('/').at(-1)
      calls.push('get ' + id)
      if (id === '2') {
        expect(state.config.copilot.value.scripts).toHaveLength(0)
        throw new Error('offline')
      }
      const content =
        id === '3'
          ? '{'
          : id === '4'
            ? 'x'.repeat(1024 * 1024 + 1)
            : JSON.stringify({ type: id === '6' || id === '8' ? 'SSS' : undefined, id })
      return { data: { data: { content } } }
    })
    state.client.post.mockImplementation(async (url, form) => {
      const { id } = JSON.parse(await form.get('copilot').text())
      calls.push(url.split('/').at(-1) + ' ' + id)
      if (id === '5') throw { response: { data: { message: '关卡名称无效' } } }
      return { data: { ...(id === '6' ? second : first), difficulty: id === '1' ? 3 : 2 } }
    })
    component.code.value = 'prts://S123'
    await component.download()
    expect(calls).toEqual([
      'get 1',
      'maa-copilot 1',
      'get 2',
      'get 3',
      'get 4',
      'get 5',
      'maa-copilot 5',
      'get 6',
      'sss-copilot 6',
      'get 7',
      'maa-copilot 7',
      'get 8',
      'sss-copilot 8'
    ])
    expect(state.config.copilot.value.scripts.map(({ is_raid }) => is_raid)).toEqual([
      false,
      true,
      true
    ])
    expect(state.config.sss.value.scripts).toEqual(
      [second, first].map(({ id }) => ({ id, type: 1, ec: 1, times: 1 }))
    )
    expect(component.failures.value).toEqual([
      '第 2 份（2）：offline',
      '第 3 份：作业编号无效',
      '第 4 份（3）：作业文件不是有效 JSON',
      '第 5 份（4）：作业文件不能超过 1 MB',
      '第 6 份（5）：关卡名称无效'
    ])
    expect(state.warning).toHaveBeenCalledWith(
      expect.stringContaining('自动战斗 2 份、保全派驻 2 份')
    )
    expect(component.selected.value).toBe(first.id)
    expect(component.code.value).toBe('')
  })

  it('publishes one complete queue after a paused download and keeps concurrent edits', async () => {
    mock_set(['456', '789', '456'])
    const snapshots = []
    scope.run(() =>
      watch(
        () => state.config.copilot.value.scripts.map(({ id }) => id),
        (ids) => snapshots.push(ids),
        { flush: 'sync' }
      )
    )
    const paused = Promise.withResolvers()
    const resume = Promise.withResolvers()
    const get = state.client.get.getMockImplementation()
    state.client.get.mockImplementation(async (url) => {
      if (url.endsWith('/789')) {
        paused.resolve()
        await resume.promise
      }
      return get(url)
    })
    component.code.value = 's123'
    const download = component.download()
    await paused.promise
    expect(snapshots).toEqual([])
    component.add_script(second.id)
    resume.resolve()
    await download
    expect(snapshots).toEqual([[second.id], [second.id, first.id, second.id, first.id]])
  })

  it('protects pending files in both editors until a mixed set publishes its queues', async () => {
    const sss = scope.run(() => Sss.setup({}, { expose: () => {} }))
    const paused = Promise.withResolvers()
    const resume = Promise.withResolvers()
    state.client.get.mockImplementation(async (url) => {
      if (url.endsWith('/maa-copilot-set/123')) return { data: { ids: ['1', '2', '3'] } }
      if (url.endsWith('/3')) {
        paused.resolve()
        await resume.promise
        throw new Error('offline')
      }
      if (url.includes('/network/')) {
        return { data: { data: { content: url.endsWith('/2') ? '{"type":"SSS"}' : '{}' } } }
      }
      return { data: { scripts: [first, second] } }
    })
    state.client.post.mockResolvedValueOnce({ data: { ...first, difficulty: 3 } })
    state.client.post.mockResolvedValueOnce({ data: second })
    component.code.value = 's123'
    const downloading = component.download()
    await paused.promise
    try {
      component.selected.value = first.id
      sss.selected.value = second.id
      expect(state.config.copilot.value.scripts).toEqual([])
      expect(state.config.sss.value.scripts).toEqual([])
      await component.delete_script()
      await sss.delete_script()
      expect(state.client.delete).not.toHaveBeenCalled()
      expect(component.canDelete.value).toBe(false)
      expect(sss.canDelete.value).toBe(false)
    } finally {
      resume.resolve()
      await downloading
    }
    expect(state.config.copilot.value.scripts.map((item) => item.is_raid)).toEqual([false, true])
    expect(state.config.sss.value.scripts.map((item) => item.id)).toEqual([second.id])
    state.config.sss.value.scripts = []
    await sss.delete_script()
    expect(state.client.delete).toHaveBeenCalledOnce()
  })

  it('finishes an in-flight deletion before a new import can restore the same file', async () => {
    const deleting = Promise.withResolvers()
    const finishDelete = Promise.withResolvers()
    state.client.delete.mockImplementationOnce(() => {
      deleting.resolve()
      return finishDelete.promise
    })
    component.selected.value = first.id
    const removal = component.delete_script()
    await deleting.promise
    mock_set(['456'])
    component.code.value = 's123'
    const downloading = component.download()
    await Promise.resolve()
    expect(state.client.get).not.toHaveBeenCalled()
    finishDelete.resolve()
    await Promise.all([downloading, removal])
    expect(state.client.post).toHaveBeenCalledOnce()
    expect(state.config.copilot.value.scripts.map((item) => item.id)).toEqual([first.id])
  })

  it('keeps surviving members and manual edits when another client deletes a stored file', async () => {
    mock_set(['456', '789', '456'])
    state.client.post.mockResolvedValueOnce({ data: { ...first, difficulty: 3 } })
    state.client.post.mockResolvedValueOnce({ data: second })
    const saving = Promise.withResolvers()
    const resume = Promise.withResolvers()
    state.flush.mockImplementationOnce(async () => {
      saving.resolve()
      await resume.promise
      throw {
        response: {
          status: 409,
          data: {
            code: 'copilot_scripts_missing',
            missing_scripts: { copilot: [first.id] }
          }
        }
      }
    })
    component.code.value = 's123'
    const downloading = component.download()
    await Promise.race([saving.promise, downloading])
    expect(state.success).not.toHaveBeenCalled()
    const manual = { id: second.id, nav_name_override: '手动编辑', is_raid: true }
    state.config.copilot.value.scripts.unshift(manual)
    resume.resolve()
    await downloading
    expect(state.config.copilot.value.scripts).toEqual([
      manual,
      { id: second.id, nav_name_override: '', is_raid: false }
    ])
    expect(component.failures.value).toEqual([
      expect.stringContaining('第 1 份（456）'),
      expect.stringContaining('第 3 份（456）')
    ])
    expect(state.success).not.toHaveBeenCalled()
    expect(state.warning).toHaveBeenCalledWith(expect.stringContaining('自动战斗 1 份'))
    expect(state.flush).toHaveBeenCalledTimes(2)
  })

  it('reports an unconfirmed save without adding the imported entries again', async () => {
    mock_set(['456'])
    state.flush.mockRejectedValueOnce(new Error('connection lost'))
    component.code.value = 's123'
    await component.download()
    expect(state.success).not.toHaveBeenCalled()
    expect(state.error).toHaveBeenCalledWith(expect.stringContaining('刷新'))
    expect(state.config.copilot.value.scripts.map((item) => item.id)).toEqual([first.id])
    expect(state.flush).toHaveBeenCalledOnce()
  })

  it('imports a long set with repeated dual-difficulty members and keeps their order', async () => {
    mock_set([...Array(80).fill('456'), '789'], { 456: 3 })
    state.config.copilot.value.scripts = [{ id: second.id }]
    state.client.post
      .mockResolvedValueOnce({ data: { ...first, difficulty: 3 } })
      .mockResolvedValueOnce({ data: second })
    component.code.value = 's123'
    await component.download()
    expect(component.backupWarning.value).toBe('整机备份文件数接近上限。')
    expect(state.client.get).toHaveBeenCalledTimes(4)
    expect(state.client.post).toHaveBeenCalledTimes(2)
    expect(state.config.copilot.value.scripts).toHaveLength(162)
    expect(
      state.config.copilot.value.scripts.slice(1, -1).map(({ id, is_raid }) => [id, is_raid])
    ).toEqual(Array.from({ length: 160 }, (_, i) => [first.id, i % 2 === 1]))
    expect(state.config.copilot.value.scripts.at(-1).id).toBe(second.id)
    expect(component.failures.value).toEqual([])
  })

  it('keeps server library errors separate from adding saved scripts to a long queue', async () => {
    mock_set(['456', '789'])
    const existing = Array.from({ length: 32 }, () => ({ id: second.id, is_raid: true }))
    state.config.copilot.value.scripts = existing
    state.client.post.mockRejectedValueOnce(new Error('作业存储已满'))
    component.code.value = 's123'
    await component.download()
    component.add_script(first.id)
    expect(state.config.copilot.value.scripts.slice(0, existing.length)).toEqual(existing)
    expect(state.config.copilot.value.scripts.slice(existing.length).map(({ id }) => id)).toEqual([
      second.id,
      first.id
    ])
    expect(component.failures.value).toEqual(['第 1 份（456）：作业存储已满'])
  })

  it('ignores a duplicate download action while the current import is pending', async () => {
    mock_set()
    let complete
    const pending = new Promise((resolve) => {
      complete = resolve
    })
    const get = state.client.get.getMockImplementation()
    state.client.get.mockImplementation(async (url) => {
      if (url.endsWith('/network/maa-copilot-set/123')) {
        await pending
      }
      return get(url)
    })
    component.code.value = 'prts://s123'
    const firstDownload = component.download()
    await component.download()
    complete()
    await firstDownload
    expect(state.config.copilot.value.scripts).toHaveLength(3)
    expect(state.client.post).toHaveBeenCalledTimes(2)
  })
  it.each([
    '',
    '../123',
    'prts://abc',
    'https://other.test/operation/123',
    'https://prts.plus.other.test/operation/123',
    'https://prts.plus@other.test/operation/123',
    'https://prts.plus/operation/123/extra'
  ])('rejects invalid code %s without network work', async (code) => {
    component.code.value = code
    await component.download()
    expect(state.client.get).not.toHaveBeenCalled()
    expect(state.client.post).not.toHaveBeenCalled()
    expect(state.config.copilot.value.scripts).toEqual([])
    expect(state.error).toHaveBeenCalledOnce()
  })
  it('preserves the queue on download error', async () => {
    component.code.value = '123'
    state.client.get.mockRejectedValue(new Error('offline'))
    await component.download()
    expect(state.config.copilot.value.scripts).toEqual([])
    expect(state.error).toHaveBeenCalled()
    expect(component.loading.value).toBe(false)
  })
  it('uploads local files, preserves duplicates and reorders with their settings', async () => {
    const finish = vi.fn()
    const failure = vi.fn()
    await component.upload({ file: { file: new Blob(['{}']) }, onFinish: finish, onError: failure })
    expect(finish).toHaveBeenCalledOnce()
    expect(failure).not.toHaveBeenCalled()
    component.add_script(second.id)
    state.config.copilot.value.scripts[1].is_raid = true
    component.move(1, -1)
    expect(state.config.copilot.value.scripts.map((item) => item.id)).toEqual([second.id, first.id])
    expect(state.config.copilot.value.scripts[0].is_raid).toBe(true)
    component.add_script(first.id)
    expect(state.config.copilot.value.scripts).toHaveLength(3)
  })
  it('cannot delete a queued script and flushes removal before deleting an unused file', async () => {
    component.selected.value = first.id
    component.add_script(first.id)
    await component.delete_script()
    expect(state.client.delete).not.toHaveBeenCalled()
    state.config.copilot.value.scripts = []
    await component.delete_script()
    expect(state.flush).toHaveBeenCalledOnce()
    expect(state.flush.mock.invocationCallOrder[0]).toBeLessThan(
      state.client.delete.mock.invocationCallOrder[0]
    )
    expect(state.client.delete).toHaveBeenCalledWith(
      expect.stringMatching(new RegExp('/maa-copilot/' + first.id + '$'))
    )
  })
  it.each([false, true])(
    'updates only the selected row and refreshes after each edit (paradox %s)',
    async (paradox) => {
      const kind = paradox ? 'paradox' : 'copilot'
      const scripts = [false, true, false].map((is_raid) =>
        paradox ? { id: first.id } : { id: first.id, is_raid, nav_name_override: '' }
      )
      state.config[kind] = ref({ scripts })
      const editor = scope.run(() => Component.setup({ paradox }, { expose: () => {} }))
      const detail = {
        queue_key: 'key',
        run_id: '',
        scripts,
        items: ['running', 'completed', 'failed']
      }
      const refresh = vi.fn()
      editor.taskStatus.value = { detail, refresh }
      state.client.patch = vi.fn().mockResolvedValue({})
      await editor.setCompleted(0, true)
      expect(state.client.patch).not.toHaveBeenCalled()
      await editor.setCompleted(1, false)
      state.client.patch.mockRejectedValueOnce({ response: { data: { message: '状态已变更' } } })
      await editor.setCompleted(2, true)
      expect(state.client.patch.mock.calls).toEqual([
        [
          expect.stringContaining('/maa-long-task-status?kind=' + kind),
          { queue_key: 'key', index: 1, expected: 'completed', completed: false }
        ],
        [
          expect.stringContaining('/maa-long-task-status?kind=' + kind),
          { queue_key: 'key', index: 2, expected: 'failed', completed: true }
        ]
      ])
      expect(refresh).toHaveBeenCalledTimes(2)
      expect(state.error).toHaveBeenCalledWith('状态已变更')
      editor.taskStatus.value.detail.scripts = [{ id: second.id }, ...scripts.slice(1)]
      await editor.setCompleted(2, true)
      expect(state.client.patch).toHaveBeenCalledTimes(2)
    }
  )
})

describe('ParadoxCopilot queue', () => {
  it('keeps set validation and successful members in the paradox editor', async () => {
    state.config.paradox = ref({ scripts: [], run_id: '' })
    const paradox = scope.run(() => Component.setup({ paradox: true }, { expose: () => {} }))
    state.client.get.mockImplementation(async (url) => ({
      data: url.endsWith('/maa-paradox')
        ? { scripts: [first] }
        : url.includes('/maa-copilot-set/')
          ? { ids: ['1', ...Array(40).fill('2')] }
          : {
              data: {
                content: url.endsWith('/2')
                  ? '{"stage_name":"mem_test_1","actions":[]}'
                  : '{"type":"SSS"}'
              }
            }
    }))
    state.client.post.mockRejectedValueOnce(new Error('请导入悖论模拟作业'))
    paradox.code.value = 'S123'
    await paradox.download()
    expect(state.client.post.mock.calls.map(([url]) => url.split('/').at(-1))).toEqual([
      'maa-paradox',
      'maa-paradox'
    ])
    expect(state.config.paradox.value.scripts).toEqual(
      Array.from({ length: 40 }, () => ({ id: first.id }))
    )
    expect(state.config.sss.value.scripts).toEqual([])
    expect(state.config.copilot.value.scripts).toEqual([])
    expect(paradox.failures.value).toEqual(['第 1 份（1）：请导入悖论模拟作业'])
  })
  it('imports through the paradox endpoint and only records the script id', async () => {
    state.config.paradox = ref({ scripts: [], run_id: '' })
    const paradox = scope.run(() => Component.setup({ paradox: true }, { expose: () => {} }))
    await paradox.upload({
      file: { file: new Blob(['{"stage_name":"mem_test_1","actions":[]}']) },
      onFinish: vi.fn(),
      onError: vi.fn()
    })
    expect(state.client.post).toHaveBeenCalledWith(
      expect.stringMatching(/\/maa-paradox$/),
      expect.any(FormData)
    )
    expect(state.config.paradox.value.scripts).toEqual([{ id: first.id }])
    expect(state.config.copilot.value.scripts).toEqual([])
  })
})
