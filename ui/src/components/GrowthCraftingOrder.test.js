import { beforeEach, describe, expect, it, vi } from 'vitest'
import { effectScope, nextTick, reactive } from 'vue'
import GrowthCraftingOrder from './GrowthCraftingOrder.vue'

const api = vi.hoisted(() => ({ get: vi.fn(), put: vi.fn(), delete: vi.fn(), post: vi.fn() }))
vi.mock('axios', () => ({ default: api }))
vi.mock('vue', async (original) => ({
  ...(await original()),
  useSSRContext: () => ({ modules: new Set() })
}))
function response() {
  const rows = [
    {
      key: 'skill:active',
      char_id: 'active',
      char_name: '进行中干员',
      label: '技能一 · 专三',
      kind: 'skill',
      locked: true,
      plan_id: 1
    },
    {
      key: 'skill:next',
      char_id: 'next',
      char_name: '待专精干员',
      label: '技能二 · 专二',
      kind: 'skill',
      locked: false,
      plan_id: 2
    },
    {
      key: 'goal:module',
      char_id: 'module',
      char_name: '模组干员',
      label: '模组 X · 模组 3 级',
      kind: 'goal',
      locked: false,
      module_id: 'mod'
    },
    {
      key: 'goal:level',
      char_id: 'level',
      char_name: '等级干员',
      label: '精二 90 级',
      kind: 'goal',
      locked: false,
      module_id: 'elite2_max',
      crafting_required: false,
      reason: '纯等级提升，不需要合成'
    }
  ]
  return {
    data: { planning_items: rows, items: rows.slice(0, 3), prepared_items: [], custom: false }
  }
}
let current
let failures
function setup() {
  const props = reactive({ revision: '', recommendations: [], count: 4 })
  const scope = effectScope()
  const emit = vi.fn()
  const page = scope.run(() => GrowthCraftingOrder.setup(props, { expose: vi.fn(), emit }))
  return { page, props, emit, stop: () => scope.stop() }
}
async function flush() {
  for (let i = 0; i < 5; i++) await nextTick()
}
async function open(page) {
  page.show.value = true
  await flush()
}
function drop(page, source, destination) {
  const rows = [...page.draftItems.value]
  const [item] = rows.splice(source, 1)
  rows.splice(destination, 0, item)
  page.commitDrag(rows)
}
function keys(page) {
  return page.draftItems.value.map((item) => item.key)
}
function orderReads() {
  return api.get.mock.calls.filter(([url]) => url.endsWith('/growth-crafting-order')).length
}
beforeEach(() => {
  vi.resetAllMocks()
  current = response()
  failures = []
  api.get.mockImplementation(async (url) =>
    url.endsWith('/mastery-plan') ? { data: { plans: failures } } : current
  )
  api.put.mockResolvedValue(response())
  api.delete.mockResolvedValue({ data: { status: 'ok' } })
  api.post.mockResolvedValue({ data: { goals: [] } })
})

describe('统一养成计划编辑', () => {
  it('仅打开时读取完整计划及失败计划，纯升级保持真实等级且无重复提示', async () => {
    const { page, props, stop } = setup()
    props.revision = 'initial'
    await flush()
    expect(api.get).not.toHaveBeenCalled()
    await open(page)
    expect(orderReads()).toBe(1)
    expect(page.draftItems.value).toHaveLength(4)
    expect(page.draftItems.value[3].label).toBe('精二 90 级')
    expect(page.projectStatus(page.draftItems.value[3])).toBe('纯等级提升，不需要合成')
    stop()
  })

  it('拖动和移除仅修改草稿，取消不写后端', async () => {
    const { page, stop } = setup()
    await open(page)
    drop(page, 2, 1)
    page.remove(page.draftItems.value[3])
    expect(keys(page)).toEqual(['skill:active', 'goal:module', 'skill:next'])
    expect(page.dirty.value).toBe(true)
    expect(api.put).not.toHaveBeenCalled()
    expect(api.post).not.toHaveBeenCalled()
    page.cancel()
    expect(page.show.value).toBe(false)
    expect(page.dirty.value).toBe(false)
    expect(page.draftItems.value).toHaveLength(4)
    stop()
  })

  it('锁定行不能拖动、跨越或移除，清空保留锁定计划', async () => {
    const { page, stop } = setup()
    await open(page)
    const active = page.draftItems.value[0]
    expect(page.canDrag({ draggedContext: { element: active, futureIndex: 1 } })).toBe(false)
    expect(
      page.canDrag({ draggedContext: { element: page.draftItems.value[1], futureIndex: 0 } })
    ).toBe(false)
    drop(page, 1, 0)
    page.remove(active)
    expect(keys(page)[0]).toBe('skill:active')
    expect(page.draftItems.value).toHaveLength(4)
    page.clear()
    expect(keys(page)).toEqual(['skill:active'])
    stop()
  })

  it('搜索时禁止拖拽和职业整理；按项目文本及拼音匹配', async () => {
    const { page, stop } = setup()
    await open(page)
    page.search.value = '模组'
    expect(page.matchesSearch(page.draftItems.value[2])).toBe(true)
    expect(page.matchesSearch(page.draftItems.value[1])).toBe(false)
    expect(
      page.canDrag({ draggedContext: { element: page.draftItems.value[2], futureIndex: 1 } })
    ).toBe(false)
    drop(page, 2, 1)
    page.organize()
    expect(page.dirty.value).toBe(false)
    page.search.value = 'mozu'
    expect(page.matchesSearch(page.draftItems.value[2])).toBe(true)
    stop()
  })

  it('保存包含纯升级在内的完整排列，等待期间禁止重复保存', async () => {
    const { page, emit, stop } = setup()
    await open(page)
    drop(page, 3, 1)
    let resolve
    api.put.mockImplementation(
      () =>
        new Promise((done) => {
          resolve = done
        })
    )
    const saving = page.save()
    await page.save()
    page.clear()
    expect(api.put).toHaveBeenCalledExactlyOnceWith(
      expect.stringContaining('/growth-crafting-order'),
      {
        order: ['skill:active', 'goal:level', 'skill:next', 'goal:module']
      }
    )
    expect(page.draftItems.value).toHaveLength(4)
    resolve(response())
    await saving
    expect(emit).toHaveBeenCalledExactlyOnceWith('changed')
    expect(page.show.value).toBe(false)
    stop()
  })

  it('删除技能和目标后再提交剩余排列，取消前的草稿不发请求', async () => {
    const { page, stop } = setup()
    await open(page)
    page.remove(page.draftItems.value[1])
    page.remove(page.draftItems.value[1])
    expect(api.delete).not.toHaveBeenCalled()
    await page.save()
    expect(api.delete).toHaveBeenCalledExactlyOnceWith(expect.stringContaining('/mastery-plan'), {
      data: { id: 2 }
    })
    expect(api.post).toHaveBeenCalledExactlyOnceWith(expect.stringContaining('/growth-plan'), {
      char_id: 'module',
      module_id: 'mod',
      selected: false
    })
    expect(api.put).toHaveBeenCalledExactlyOnceWith(
      expect.stringContaining('/growth-crafting-order'),
      {
        order: ['skill:active', 'goal:level']
      }
    )
    expect(api.delete.mock.invocationCallOrder[0]).toBeLessThan(
      api.post.mock.invocationCallOrder[0]
    )
    expect(api.post.mock.invocationCallOrder[0]).toBeLessThan(api.put.mock.invocationCallOrder[0])
    stop()
  })

  it('部分删除成功后失败明确提示，重读实际计划并保留弹窗', async () => {
    const { page, emit, stop } = setup()
    await open(page)
    page.remove(page.draftItems.value[1])
    page.remove(page.draftItems.value[1])
    api.delete.mockImplementation(async () => {
      current.data.planning_items = current.data.planning_items.filter((item) => item.plan_id !== 2)
      return { data: { status: 'ok' } }
    })
    api.post.mockRejectedValue({ response: { data: { error: '目标已经变化' } } })
    await page.save()
    expect(api.put).not.toHaveBeenCalled()
    expect(page.feedback.value).toContain('已确认移除 1 项')
    expect(page.feedback.value).toContain('已重新读取实际计划')
    expect(page.feedback.value).toContain('目标已经变化')
    expect(page.show.value).toBe(true)
    expect(keys(page)).toContain('goal:module')
    expect(keys(page)).not.toContain('skill:next')
    expect(page.dirty.value).toBe(false)
    expect(emit).toHaveBeenCalledExactlyOnceWith('changed')
    stop()
  })

  it('保存冲突后读取真实状态失败时禁止再次提交，允许取消后重开', async () => {
    const { page, stop } = setup()
    await open(page)
    drop(page, 2, 1)
    api.put.mockRejectedValue({ response: { status: 409, data: { error: '训练状态已变化' } } })
    api.get.mockRejectedValue(new Error('offline'))
    await page.save()
    expect(page.feedback.value).toContain('实际计划读取失败')
    expect(page.loaded.value).toBe(false)
    await page.save()
    expect(api.put).toHaveBeenCalledTimes(1)
    page.cancel()
    expect(page.show.value).toBe(false)
    stop()
  })

  it('其他位置更新不得覆盖未保存草稿，取消前阻止过期保存', async () => {
    const { page, props, stop } = setup()
    await open(page)
    drop(page, 2, 1)
    props.revision = 'external change'
    await flush()
    expect(keys(page)[1]).toBe('goal:module')
    expect(page.stale.value).toBe(true)
    expect(page.feedback.value).toContain('取消后重新打开')
    await page.save()
    expect(api.put).not.toHaveBeenCalled()
    stop()
  })

  it('无草稿时合并拖动期间的刷新，拖动结束后读取最新状态', async () => {
    const { page, props, stop } = setup()
    await open(page)
    page.dragging.value = true
    props.revision = 'one'
    await flush()
    props.revision = 'two'
    await flush()
    expect(orderReads()).toBe(1)
    await page.finishDrag()
    expect(orderReads()).toBe(2)
    stop()
  })

  it('职业整理和专精优先保留锁定前缀、完整项目与真实状态', async () => {
    const { page, props, stop } = setup()
    props.recommendations = [
      { char_id: 'next', profession: 'WARRIOR' },
      { char_id: 'module', profession: 'WARRIOR' },
      { char_id: 'level', profession: 'MEDIC' }
    ]
    await open(page)
    page.organize()
    expect(keys(page)).toEqual(['skill:active', 'skill:next', 'goal:level', 'goal:module'])
    expect(page.draftItems.value[2].crafting_required).toBe(false)
    drop(page, 3, 1)
    page.prioritizeSkills()
    expect(keys(page)[0]).toBe('skill:active')
    expect(keys(page)[1]).toBe('skill:next')
    expect(new Set(keys(page)).size).toBe(4)
    expect(api.put).not.toHaveBeenCalled()
    stop()
  })

  it('备齐提示独立展示，不改变完整计划与失败计划排序', async () => {
    current.data.prepared_items = [{ ...current.data.planning_items[3], reason: '待升级' }]
    const { page, stop } = setup()
    await open(page)
    expect(page.preparedItems.value).toHaveLength(1)
    expect(page.draftItems.value).toHaveLength(4)
    expect(page.dirty.value).toBe(false)
    stop()
  })

  it('失败计划保留原因且仅草稿删除，不混入排序PUT', async () => {
    failures = [
      {
        id: 9,
        status: 'failed',
        char_id: 'failed',
        name: '失败干员',
        skill_name: '技能',
        target_level: 2,
        failed_reason: '设备读取失败'
      }
    ]
    const { page, stop } = setup()
    await open(page)
    expect(page.draftFailedItems.value[0].reason).toBe('设备读取失败')
    page.remove(page.draftFailedItems.value[0])
    expect(page.dirty.value).toBe(true)
    expect(api.delete).not.toHaveBeenCalled()
    await page.save()
    expect(api.delete).toHaveBeenCalledExactlyOnceWith(expect.stringContaining('/mastery-plan'), {
      data: { id: 9 }
    })
    expect(api.put.mock.calls[0][1].order).toEqual([
      'skill:active',
      'skill:next',
      'goal:module',
      'goal:level'
    ])
    stop()
  })
})
