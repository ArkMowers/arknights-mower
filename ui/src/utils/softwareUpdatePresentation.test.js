import { afterEach, describe, expect, it } from 'vitest'
import { computed, reactive } from 'vue'
import { baseCompile } from '@intlify/message-compiler'
import { i18n } from '@/i18n'
import { softwareUpdateMessages } from '@/i18n/messages/softwareUpdate'
import { softwareUpdateMessage } from './softwareUpdatePresentation'

const pull = ['#', '12345'].join('')

for (const [locale, messages] of Object.entries(softwareUpdateMessages)) {
  i18n.global.mergeLocaleMessage(locale, { softwareUpdate: messages })
}
afterEach(() => {
  i18n.global.locale.value = 'zh-CN'
})

describe('software and MAA update status presentation', () => {
  it('reacts to English, Japanese and Traditional Chinese without changing the original job or its values', () => {
    const job = reactive({
      status: 'success',
      phase: 'success',
      message:
        'MAA v5.10.2-beta.1 公测版已通过 Mirror酱更新完成；已安装 Linux aarch64 完整包；请重启 Mower 后再运行 MAA；无法读取已安装核心版本，请检查 MAA 安装',
      version: 'v5.10.2-beta.1',
      arch: 'aarch64',
      target: 'D:/原始目录/My MAA',
      result: { operation: 'update', channel: 'beta', source: 'mirrorchyan' }
    })
    const original = JSON.stringify(job)
    const display = computed(() => softwareUpdateMessage(job.message))
    expect(display.value).toBe(job.message)
    const results = []
    for (const locale of ['en-US', 'ja-JP', 'zh-TW']) {
      i18n.global.locale.value = locale
      expect(display.value).toContain('v5.10.2-beta.1')
      expect(display.value).toContain('Linux aarch64')
      expect(display.value).toContain('MirrorChyan')
      expect(display.value).not.toContain('无法读取')
      expect(display.value).not.toContain('已安装')
      expect(display.value).not.toBe(job.message)
      results.push(display.value)
      expect(JSON.stringify(job)).toBe(original)
    }
    expect(new Set(results).size).toBe(3)
    i18n.global.locale.value = 'zh-CN'
    expect(display.value).toBe(job.message)
  })

  it.each([
    ['准备完成，开始保存任务并重启全部实例', 'Saving tasks and restarting all instances'],
    ['Python 依赖清单未变化，保留当前环境', 'Keeping the current environment'],
    ['安装前端依赖并构建页面，当前实例继续运行', 'building pages'],
    ['安装未完成，恢复原版本', 'Restoring the original version'],
    ['已取消更新，当前实例继续运行', 'Update cancelled'],
    ['正在取消更新，等待下载或构建进程退出', 'Waiting for download or build processes'],
    [`在临时工作目录合并 PR ${pull}，当前实例继续运行`, `PR ${pull}`],
    ['PR 合并完成：Abc0123deF45678', 'Abc0123deF45678'],
    ['正在通过 Mirror酱获取 MAA 公测版更新信息', 'MAA beta update'],
    ['正在通过 GitHub 获取 MAA 正式版下载信息', 'MAA stable download'],
    ['正在获取 MAA 正式版更新信息', 'MAA stable update'],
    ['正在为 MAA 更新下载 Linux arm64 完整包', 'Linux arm64'],
    ['正在通过 Mirror酱为 MAA 下载下载 Linux x86_64 完整包', 'Linux x86_64'],
    ['正在通过 Mirror酱下载 Windows arm64 OTA 增量包', 'Windows arm64 OTA patch'],
    ['正在下载 Windows x64 完整包', 'Windows x64 full package'],
    ['正在通过 Mirror酱为 MAA 更新下载 macOS 完整包', 'macOS package'],
    ['正在通过 Mirror酱为 MAA 更新下载 Windows arm64 Python 来源包', 'Windows arm64 Python'],
    ['正在为 MAA 下载下载 macOS 运行库', 'macOS runtime'],
    ['正在通过 GitHub下载 MAA 资源包', 'resource package from GitHub'],
    ['当前 MAA v5.10.2 无需更新（正式版）', 'v5.10.2 is up to date'],
    ['MAA v5.10.2 正式版已通过 GitHub下载完成；已安装 Windows x64 完整包', 'Windows x64 package'],
    [
      'MAA v5.10.2 公测版已通过 Mirror酱更新完成；macOS 与 Windows arm64 完整包均已校验',
      'Windows arm64 full packages verified'
    ],
    [
      'MAA v5.10.2 正式版更新完成；Python 文件按需下载 12345 字节（完整 Windows 包 98765 字节）',
      '12345 Python bytes'
    ],
    [
      'MAA 资源 2026-10-27-12-00-00 已通过 Mirror酱更新完成，重启安卓服务后生效',
      'restart the Android service'
    ],
    ['MAA 资源 2026-10-27-12-00-00 已是最新版本', '2026-10-27-12-00-00 are up to date'],
    ['发现 MAA 公测版新版本 v5.10.2-beta.1（GitHub）', 'v5.10.2-beta.1 is available'],
    ['当前 MAA 已是最新正式版', 'stable channel'],
    ['发现 MAA 资源新版本 2026-10-27-12-00-00（Mirror酱）', '2026-10-27-12-00-00 are available']
  ])('translates the backend status %s', (original, expected) => {
    i18n.global.locale.value = 'en-US'
    expect(softwareUpdateMessage(original)).toContain(expected)
    i18n.global.locale.value = 'zh-CN'
    expect(softwareUpdateMessage(original)).toBe(original)
  })

  it.each(['en-US', 'ja-JP', 'zh-TW'])(
    'retains unknown diagnostics and raw dynamic error details in %s',
    (locale) => {
      i18n.global.locale.value = locale
      const diagnostic = 'EPERM: D:\\用户\\MAA\\MaaCore.dll\n原始诊断 | {checksum} @server'
      for (const value of [diagnostic, '日志：准备更新', '未知的更新状态', '', null, undefined])
        expect(softwareUpdateMessage(value)).toBe(value)
      expect(softwareUpdateMessage(diagnostic + '；请重启 Mower 后再运行 MAA')).toBe(
        diagnostic + '；请重启 Mower 后再运行 MAA'
      )
      expect(softwareUpdateMessage(`MAA 更新失败：${diagnostic}`)).toContain(diagnostic)
      expect(
        softwareUpdateMessage(`MAA 更新失败：${diagnostic}；请重启 Mower 后再运行 MAA`)
      ).toContain(diagnostic + '；请重启 Mower 后再运行 MAA')
      expect(softwareUpdateMessage(`MAA 资源更新失败：${diagnostic}`)).toContain(diagnostic)
      expect(softwareUpdateMessage(`OTA 不可用（${diagnostic}），改用完整安装包`)).toContain(
        diagnostic
      )
    }
  )

  it('compiles each locale and preserves the interpolation parameters', () => {
    const baseline = softwareUpdateMessages['zh-CN']
    const parameters = (value) => [...new Set(value.match(/\{[A-Za-z]\w*\}/g) || [])].sort()
    for (const [locale, messages] of Object.entries(softwareUpdateMessages)) {
      expect(Object.keys(messages).sort()).toEqual(Object.keys(baseline).sort())
      for (const [key, value] of Object.entries(messages)) {
        const errors = []
        baseCompile(value, { onError: (error) => errors.push(error) })
        expect(errors, `${locale}.${key}`).toEqual([])
        expect(parameters(value)).toEqual(parameters(baseline[key]))
      }
    }
  })
})
