import { describe, expect, it, vi } from 'vitest'
import {
  confirmForceUpdate,
  confirmSoftwareInstall,
  confirmSourceVersion,
  isVersionDowngrade,
  softwarePackageVersion
} from './softwareUpdate'

describe('release rollback confirmation', () => {
  it.each([
    ['4.1.5', '4.1.6-alpha.4', true],
    ['4.1.6-alpha.4', '4.1.6-alpha.5', true],
    ['4.1.6-alpha.4', '4.1.6', true],
    ['4.1.6-alpha.4', '4.1.6-beta.1', true],
    ['4.1.6-beta.1', '4.1.6-rc.1', true],
    ['4.1.6-alpha.12', '4.1.6-alpha.4', false],
    ['4.1.6', '4.1.6-alpha.4', false],
    ['v4.1.6-alpha.4', '4.1.6-alpha.4+abcdef', false],
    ['4.2.0-alpha.1', '4.1.6', false],
    ['invalid', '4.1.6', false]
  ])('classifies %s relative to %s as downgrade=%s', (target, current, expected) => {
    expect(isVersionDowngrade(target, current)).toBe(expected)
  })

  it.each([
    ['arknights-mower_4.1.5_windows_x64.zip', '4.1.5'],
    ['arknights-mower_4.1.6-alpha.4_macos_arm64.dmg', '4.1.6-alpha.4'],
    ['arknights-mower_4.1.6_linux_x64.tar.gz', '4.1.6'],
    ['resource.zip', undefined],
    ['mower.zip', undefined]
  ])('identifies the version of uploaded and dropped package %s', (filename, expected) => {
    expect(softwarePackageVersion(filename)).toBe(expected)
  })

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
