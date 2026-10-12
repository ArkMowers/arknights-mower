import { beforeEach, describe, expect, it, vi } from 'vitest'
import { effectScope } from 'vue'
import YituliuSyncSettings from './YituliuSyncSettings.vue'

const api = vi.hoisted(() => ({ get: vi.fn(), put: vi.fn(), delete: vi.fn(), post: vi.fn() }))
vi.mock('vue', async (original) => ({
  ...(await original()),
  inject: () => api,
  onMounted: vi.fn(),
  useSSRContext: () => ({ modules: new Set() })
}))
function setup() {
  const scope = effectScope()
  const component = scope.run(() => YituliuSyncSettings.setup({}, { expose: vi.fn() }))
  scope.stop()
  return component
}
beforeEach(() => vi.clearAllMocks())
describe('一图流同步设置', () => {
  it('读取状态不回填密钥，也不触发上传', async () => {
    const page = setup()
    api.get.mockResolvedValue({ data: { configured: true } })
    await page.loadStatus()
    expect(page.status.value.configured).toBe(true)
    expect(page.token.value).toBe('')
    expect(api.post).not.toHaveBeenCalled()
  })
  it('保存只发本次token编辑，成功清空输入，不上传缓存', async () => {
    const page = setup()
    page.token.value = 'write-token-for-test'
    api.put.mockResolvedValue({ data: { configured: true } })
    await page.act('save')
    expect(api.put).toHaveBeenCalledExactlyOnceWith(expect.stringContaining('/growth-sync-token'), {
      token: 'write-token-for-test'
    })
    expect(page.token.value).toBe('')
    expect(page.feedback.value).toContain('下次森空岛刷新')
    expect(api.post).not.toHaveBeenCalled()
  })
  it('清除仅删除本地token并关闭自动同步', async () => {
    const page = setup()
    page.status.value.configured = true
    api.delete.mockResolvedValue({ data: { configured: false } })
    await page.act('clear')
    expect(page.status.value.configured).toBe(false)
    expect(page.feedback.value).toContain('自动同步已停止')
    expect(api.post).not.toHaveBeenCalled()
  })
  it('立即同步只发确认标记，不把token或账号数据交给前端拼装', async () => {
    const page = setup()
    page.status.value.configured = true
    page.status.value.last_sync_error = '旧失败'
    api.post.mockResolvedValue({
      data: { success: true, count: 10, synced_at: 100, message: '已同步' }
    })
    await page.act('sync')
    expect(api.post).toHaveBeenCalledExactlyOnceWith(expect.stringContaining('/growth-sync'), {
      confirmed: true
    })
    expect(page.status.value.last_synced_count).toBe(10)
    expect(page.status.value.last_sync_error).toBeNull()
    expect(page.busy.value).toBe(false)
  })
  it('失败显示后端清理过的错误且保留已保存状态', async () => {
    const page = setup()
    page.status.value.configured = true
    api.post.mockRejectedValue({ response: { data: { message: '请先重新同步一次森空岛' } } })
    await page.act('sync')
    expect(page.feedback.value).toContain('重新同步一次森空岛')
    expect(page.status.value.configured).toBe(true)
    expect(page.failed.value).toBe(true)
    expect(page.busy.value).toBe(false)
  })
})
