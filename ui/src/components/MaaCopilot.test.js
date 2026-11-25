import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createSSRApp, effectScope, ref, watch } from 'vue'
import { renderToString } from 'vue/server-renderer'
import Component from './MaaCopilot.vue'

const state = vi.hoisted(() => ({
  config: {},
  client: null,
  error: vi.fn(),
  warning: vi.fn(),
  success: vi.fn(),
  flush: vi.fn()
}))
vi.mock('vue', async (original) => ({
  ...(await original()),
  inject: (key) => (key === 'axios' ? state.client : false),
  onMounted: () => {},
  useSSRContext: () => ({ modules: new Set() })
}))
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
        'NEmpty',
        'NFlex',
        'NForm',
        'NFormItem',
        'NInput',
        'NInputNumber',
        'NRadio',
        'NRadioGroup',
        'NSelect',
        'NText',
        'NUpload'
      ].map((name) => [name, wrapper])
    ),
    useMessage: () => ({ error: state.error, warning: state.warning, success: state.success })
  }
})
let scope
let component
const first = { id: 'a'.repeat(64), stage_name: '1-7', title: '作业一' }
const second = { id: 'b'.repeat(64), stage_name: 'CE-6', title: '作业二' }
beforeEach(() => {
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

describe('ordinary Copilot library and queue', () => {
  it('shows the Mower AI setup requirement for ordinary map navigation only', async () => {
    state.config.paradox = ref({ scripts: [], run_id: '' })
    const ordinary = await renderToString(createSSRApp(Component))
    expect(ordinary).toContain('请先在“AI 助手与模型服务”中配置 Mower AI 使用的模型服务')
    expect(ordinary).toContain('导航失败时不启动 MAA')
    const paradox = await renderToString(createSSRApp(Component, { paradox: true }))
    expect(paradox).not.toContain('请先在“AI 助手与模型服务”中配置 Mower AI 使用的模型服务')
  })
  it('offers roster assistance only for ordinary automatic formation', async () => {
    state.config.paradox = ref({ scripts: [] })
    const render = (props = {}) => renderToString(createSSRApp(Component, props))
    expect(await render()).not.toContain('使用干员练度辅助编队')
    state.config.copilot.value.formation = true
    expect(await render()).toContain('使用干员练度辅助编队')
    expect(await render({ paradox: true })).not.toContain('使用干员练度辅助编队')
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
      return { data: { scripts: [first, second] } }
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
      await component.upload_blob(new Blob(['{}']))
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

  it('imports a long set with repeated dual-difficulty members and keeps their order', async () => {
    mock_set([...Array(80).fill('456'), '789'], { 456: 3 })
    state.config.copilot.value.scripts = [{ id: second.id }]
    state.client.post
      .mockResolvedValueOnce({ data: { ...first, difficulty: 3 } })
      .mockResolvedValueOnce({ data: second })
    component.code.value = 's123'
    await component.download()
    expect(state.client.get).toHaveBeenCalledTimes(3)
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
  it('starts a new round only when the user resets the queue', async () => {
    vi.stubGlobal('crypto', { getRandomValues: crypto.getRandomValues.bind(crypto) })
    component.add_script(first.id)
    const scripts = state.config.copilot.value.scripts
    await component.restart_queue()
    const firstRun = state.config.copilot.value.run_id
    expect(firstRun).toMatch(/^[a-f0-9]{32}$/)
    expect(state.flush).toHaveBeenCalledOnce()
    await component.restart_queue()
    expect(state.config.copilot.value.run_id).not.toBe(firstRun)
    expect(state.config.copilot.value.scripts).toEqual(scripts)
  })
})

describe('ParadoxCopilot queue', () => {
  it('keeps set validation and successful members in the paradox editor', async () => {
    state.config.paradox = ref({ scripts: [], run_id: '' })
    const paradox = scope.run(() => Component.setup({ paradox: true }, { expose: () => {} }))
    state.client.get.mockImplementation(async (url) => ({
      data: url.includes('/maa-copilot-set/')
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
    await paradox.upload_blob(new Blob(['{"stage_name":"mem_test_1","actions":[]}']))
    expect(state.client.post).toHaveBeenCalledWith(
      expect.stringMatching(/\/maa-paradox$/),
      expect.any(FormData)
    )
    expect(state.config.paradox.value.scripts).toEqual([{ id: first.id }])
    expect(state.config.copilot.value.scripts).toEqual([])
  })
})
