import { describe, expect, it, vi } from 'vitest'
import { confirmForceUpdate, confirmSoftwareInstall, confirmSourceVersion } from './softwareUpdate'

describe('release rollback confirmation', () => {
  it.each([false, true])(
    'only installs a rollback after confirmation (force=%s)',
    async (force) => {
      const dialogs = { warning: vi.fn() }
      const install = vi.fn()
      const file = { name: 'arknights-mower_4.1.5_macos_arm64.dmg' }
      const selection = { check_id: 'original', file, version: 'v4.1.5', downgrade: true, force }
      confirmSoftwareInstall(dialogs, '4.1.6-alpha.4', selection, 3, install)
      const options = dialogs.warning.mock.calls[0][0]
      expect(options.title).toBe('确认回退版本？')
      expect(options.content).toContain('4.1.6-alpha.4')
      expect(options.content).toContain('v4.1.5')
      expect(options.content).toContain('3 个实例')
      expect(options.content).toContain('重置运行缓存')
      if (force) expect(options.content).toContain('不备份本地修改')
      expect(options.negativeText).toBe('取消')
      expect(options.autoFocus).toBe(false)
      options.onNegativeClick?.()
      options.onClose?.()
      options.onMaskClick?.()
      expect(install).not.toHaveBeenCalled()
      // A new automatic check or file selection cannot change the confirmed target.
      selection.check_id = 'changed'
      selection.file = { name: 'another-package' }
      selection.downgrade = false
      await options.onPositiveClick()
      expect(install).toHaveBeenCalledExactlyOnceWith({
        check_id: 'original',
        file,
        version: 'v4.1.5',
        downgrade: true,
        force,
        confirm_downgrade: true
      })
    }
  )

  it.each(['4.1.6-alpha.4', '4.1.6'])(
    'uses ordinary confirmation for same or newer %s',
    async (version) => {
      const dialogs = { warning: vi.fn() }
      const install = vi.fn()
      confirmSoftwareInstall(dialogs, '4.1.6-alpha.4', { version, downgrade: false }, 1, install)
      const options = dialogs.warning.mock.calls[0][0]
      expect(options.title).toBe('确认安装并重启？')
      expect(options.content).not.toContain('回退')
      await options.onPositiveClick()
      expect(install).toHaveBeenCalledExactlyOnceWith({
        version,
        downgrade: false,
        confirm_downgrade: false
      })
    }
  )
})

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
  it('confirms the latest target branch base alongside the selected PR', () => {
    const dialogs = { warning: vi.fn() }
    confirmSourceVersion(
      dialogs,
      {
        sha: 'c'.repeat(40),
        source_repo: 'personal/mower',
        source_branch: 'alpha',
        base_commit: 'b'.repeat(40),
        source_pr: 7
      },
      3,
      vi.fn()
    )
    const { content } = dialogs.warning.mock.calls[0][0]
    expect(content).toContain('PR #7')
    expect(content).toContain(`目标分支 alpha 的 ${'b'.repeat(40)}`)
    expect(content).toContain('合并所选 PR')
    expect(content).toContain(`PR 提交为 ${'c'.repeat(40)}，合并成功后安装`)
    expect(content).not.toContain('将切换到提交')
  })

  it.each([false, true])(
    'requires confirmation with the immutable target and scope (force=%s)',
    async (force) => {
      const dialogs = { warning: vi.fn() }
      const install = vi.fn()
      const target = {
        sha: 'a'.repeat(40),
        check_id: 'selected',
        force,
        source_repo: 'personal/mower',
        source_pr: 7
      }
      confirmSourceVersion(dialogs, target, 3, install)
      const options = dialogs.warning.mock.calls[0][0]
      expect(options.content).toContain(target.sha)
      expect(options.content).toContain('personal/mower 的 PR #7')
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
