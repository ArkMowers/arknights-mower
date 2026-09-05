import { describe, expect, it, vi } from 'vitest'
import { confirmForceUpdate, confirmSourceVersion } from './softwareUpdate'

describe('force update confirmation', () => {
  it('only submits after the second confirmation, showing the target and scope', async () => {
    const dialogs = { warning: vi.fn() }
    const install = vi.fn().mockResolvedValue(undefined)
    confirmForceUpdate(dialogs, 'alpha@abc1234', 3, install)
    expect(install).not.toHaveBeenCalled()
    const options = dialogs.warning.mock.calls[0][0]
    expect(options.content).toContain('alpha@abc1234')
    expect(options.content).toContain('3 个实例')
    expect(options.content).toContain('不备份本地修改')
    expect(options.content).toContain('本地修改也不会恢复')
    await options.onPositiveClick()
    expect(install).toHaveBeenCalledOnce()
  })

  it('cancelling or dismissing the dialog never submits the update', () => {
    const dialogs = { warning: vi.fn() }
    const install = vi.fn()
    confirmForceUpdate(dialogs, 'v4.2.0', 1, install)
    const options = dialogs.warning.mock.calls[0][0]
    expect(options.negativeText).toBe('取消')
    options.onNegativeClick?.()
    options.onClose?.()
    options.onMaskClick?.()
    expect(install).not.toHaveBeenCalled()
    expect(options.autoFocus).toBe(false)
  })
})

describe('source version confirmation', () => {
  it.each([false, true])(
    'requires confirmation with the immutable target and scope (force=%s)',
    async (force) => {
      const dialogs = { warning: vi.fn() }
      const install = vi.fn()
      const target = { sha: 'a'.repeat(40), check_id: 'selected', force }
      confirmSourceVersion(dialogs, target, 3, install)
      const options = dialogs.warning.mock.calls[0][0]
      expect(options.content).toContain(target.sha)
      expect(options.content).toContain('3 个实例')
      expect(options.content).toContain('关闭软件自动更新')
      expect(options.content).toContain('专精计划和数据库记录保留')
      if (force) expect(options.content).toContain('不备份本地修改')
      options.onNegativeClick?.()
      options.onClose?.()
      expect(install).not.toHaveBeenCalled()
      await options.onPositiveClick()
      expect(install).toHaveBeenCalledOnce()
    }
  )
})
