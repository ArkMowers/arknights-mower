import { beforeEach, describe, expect, it, vi } from 'vitest'
import { effectScope, nextTick, reactive } from 'vue'
import GrowthCraftingOrder from './GrowthCraftingOrder.vue'

const api = vi.hoisted(() => ({ get: vi.fn(), put: vi.fn(), delete: vi.fn() }))
vi.mock('axios', () => ({ default: api }))
vi.mock('vue', async (original) => ({
  ...(await original()),
  useSSRContext: () => ({ modules: new Set() })
}))

function response(custom = false) {
  return {
    data: {
      custom,
      items: [
        {
          key: 'skill:active',
          char_name: '进行中干员',
          label: '技能一',
          kind: 'skill',
          locked: true
        },
        {
          key: 'skill:next',
          char_name: '待专精干员',
          label: '技能二',
          kind: 'skill',
          locked: false
        },
        {
          key: 'goal:module',
          char_name: '模组干员',
          label: '模组 X 三级',
          kind: 'goal',
          locked: false
        },
        {
          key: 'goal:level',
          char_name: '等级干员',
          label: '精二 90 级',
          kind: 'goal',
          locked: false
        }
      ]
    }
  }
}
function setup() {
  const props = reactive({ revision: '' })
  const scope = effectScope()
  const emit = vi.fn()
  const page = scope.run(() => GrowthCraftingOrder.setup(props, { expose: vi.fn(), emit }))
  return { page, props, emit, stop: () => scope.stop() }
}
async function open(page) {
  page.show.value = true
  await nextTick()
  await nextTick()
}

beforeEach(() => {
  vi.resetAllMocks()
  api.get.mockResolvedValue(response())
})

describe('养成材料合成顺序', () => {
  it('关闭时不请求，打开读取当前顺序，计划变更时刷新', async () => {
    const { page, props, stop } = setup()
    props.revision = 'initial'
    await nextTick()
    expect(api.get).not.toHaveBeenCalled()
    await open(page)
    expect(api.get).toHaveBeenCalledTimes(1)
    expect(page.items.value.map((item) => item.key)).toEqual([
      'skill:active',
      'skill:next',
      'goal:module',
      'goal:level'
    ])
    props.revision = 'updated'
    await nextTick()
    await nextTick()
    expect(api.get).toHaveBeenCalledTimes(2)
    page.show.value = false
    props.revision = 'closed update'
    await nextTick()
    expect(api.get).toHaveBeenCalledTimes(2)
    await open(page)
    expect(api.get).toHaveBeenCalledTimes(3)
    stop()
  })

  it('固定进行中的专精，禁止跨越锁定项目及超出边界', async () => {
    const { page, stop } = setup()
    await open(page)
    for (const [index, direction] of [
      [0, 1],
      [1, -1],
      [3, 1],
      [0, -1]
    ]) {
      expect(page.canMove(index, direction)).toBe(false)
      await page.move(index, direction)
    }
    expect(api.put).not.toHaveBeenCalled()
    expect(page.canMove(1, 1)).toBe(true)
    stop()
  })

  it('单个项目跨类别移动提交完整顺序；等待响应期间禁用重复保存', async () => {
    const { page, emit, stop } = setup()
    await open(page)
    let resolve
    api.put.mockImplementation(
      () =>
        new Promise((done) => {
          resolve = done
        })
    )
    const saving = page.move(2, -1)
    expect(api.put).toHaveBeenCalledExactlyOnceWith(
      expect.stringContaining('/growth-crafting-order'),
      { order: ['skill:active', 'goal:module', 'skill:next', 'goal:level'] }
    )
    expect(page.items.value[1].key).toBe('skill:next')
    await page.move(3, -1)
    await page.save()
    expect(api.put).toHaveBeenCalledTimes(1)
    expect(api.delete).not.toHaveBeenCalled()
    const updated = response(true)
    ;[updated.data.items[1], updated.data.items[2]] = [updated.data.items[2], updated.data.items[1]]
    resolve(updated)
    await saving
    expect(page.items.value[1].key).toBe('goal:module')
    expect(page.custom.value).toBe(true)
    expect(page.busy.value).toBe(false)
    expect(emit).toHaveBeenCalledExactlyOnceWith('changed')
    stop()
  })

  it('保存冲突保留原顺序并显示后端提示，恢复默认使用 DELETE', async () => {
    const { page, stop } = setup()
    await open(page)
    const initial = page.items.value
    api.put.mockRejectedValue({ response: { status: 409, data: { error: '计划已变更，请刷新' } } })
    await page.move(2, -1)
    expect(page.items.value).toBe(initial)
    expect(page.feedback.value).toBe('计划已变更，请刷新')
    expect(page.failed.value).toBe(true)
    api.delete.mockResolvedValue(response())
    await page.save()
    expect(api.delete).toHaveBeenCalledExactlyOnceWith(
      expect.stringContaining('/growth-crafting-order')
    )
    expect(page.custom.value).toBe(false)
    expect(page.failed.value).toBe(false)
    stop()
  })

  it('请求期间多次计划变更合并刷新，不并发读取或提交过期顺序', async () => {
    const { page, props, stop } = setup()
    let resolve
    api.get.mockImplementationOnce(
      () =>
        new Promise((done) => {
          resolve = done
        })
    )
    await open(page)
    props.revision = 'one'
    await nextTick()
    props.revision = 'two'
    await nextTick()
    expect(api.get).toHaveBeenCalledTimes(1)
    await page.move(1, 1)
    expect(api.put).not.toHaveBeenCalled()
    resolve(response())
    await nextTick()
    await nextTick()
    expect(api.get).toHaveBeenCalledTimes(2)
    expect(page.loaded.value).toBe(true)
    stop()
  })

  it('读取失败后禁用旧项目移动，手动刷新成功后恢复', async () => {
    const { page, stop } = setup()
    await open(page)
    api.get.mockRejectedValueOnce({ response: { data: { error: '仓库读取失败' } } })
    await page.refresh()
    expect(page.loaded.value).toBe(false)
    expect(page.canMove(2, -1)).toBe(false)
    expect(page.feedback.value).toBe('仓库读取失败')
    await page.refresh()
    expect(page.canMove(2, -1)).toBe(true)
    stop()
  })

  it('缺材料及前置未完成的项目仍可排序并保留后端原因', async () => {
    const data = response()
    data.data.items[2].status = 'waiting'
    data.data.items[2].reason = '材料不足，本轮跳过'
    data.data.items[3].status = 'preparing'
    data.data.items[3].reason = '仅准备材料，前置未完成'
    api.get.mockResolvedValue(data)
    const { page, stop } = setup()
    await open(page)
    expect(page.items.value[2].reason).toBe('材料不足，本轮跳过')
    expect(page.items.value[3].reason).toBe('仅准备材料，前置未完成')
    expect(page.canMove(2, -1)).toBe(true)
    expect(page.canMove(3, -1)).toBe(true)
    stop()
  })

  it('保存期间计划变更只在保存后刷新一次，不用旧响应覆盖新计划', async () => {
    const { page, props, stop } = setup()
    await open(page)
    let resolve
    api.put.mockImplementation(
      () =>
        new Promise((done) => {
          resolve = done
        })
    )
    const saving = page.move(2, -1)
    props.revision = 'first change'
    await nextTick()
    props.revision = 'second change'
    await nextTick()
    expect(api.get).toHaveBeenCalledTimes(1)
    const fresh = response(true)
    fresh.data.items.push({ key: 'goal:new', char_name: '新增干员', label: '满练', locked: false })
    api.get.mockResolvedValue(fresh)
    resolve(response(true))
    await saving
    expect(api.get).toHaveBeenCalledTimes(2)
    expect(page.items.value.at(-1).key).toBe('goal:new')
    expect(page.busy.value).toBe(false)
    stop()
  })
})
