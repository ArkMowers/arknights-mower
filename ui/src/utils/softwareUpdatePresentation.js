import { i18n } from '@/i18n'
import { softwareUpdateMessages } from '@/i18n/messages/softwareUpdate'

const exactMessages = new Map(
  Object.entries(softwareUpdateMessages['zh-CN'])
    .filter(([, message]) => !message.includes('{'))
    .map(([key, message]) => [message, key])
)
const text = (key, values) => i18n.global.t(`softwareUpdate.${key}`, values)
const operation = (value) => text(value === '更新' ? 'operationUpdate' : 'operationDownload')
const channel = (value) => text(value === '公测版' ? 'beta' : 'stable')
const source = (value) => (value === 'Mirror酱' ? 'MirrorChyan' : value)
const packageName = (value) => text(value === 'OTA 增量包' ? 'otaPackage' : 'fullPackage')

const patterns = [
  [/^在临时工作目录合并 PR (#\d+)，当前实例继续运行$/, (m) => text('mergePull', { pull: m[1] })],
  [/^PR 合并完成：([a-f\d]{7,64})$/i, (m) => text('mergedPull', { commit: m[1] })],
  [/^OTA 不可用（([\s\S]+)），改用完整安装包$/, (m) => text('otaFallback', { detail: m[1] })],
  [/^自动更新检查未完成：([\s\S]+)$/, (m) => text('autoCheckFailed', { detail: m[1] })],
  [
    /^MAA (更新|下载)失败：([\s\S]+)$/,
    (m) => text('maaFailed', { operation: operation(m[1]), detail: m[2] })
  ],
  [/^MAA 资源更新失败：([\s\S]+)$/, (m) => text('maaResourceFailed', { detail: m[1] })],
  [/^MAA (更新|下载)正在进行中$/, (m) => text('operationBusy', { operation: operation(m[1]) })],
  [
    /^正在(?:通过 (Mirror酱|GitHub)\s*)?获取 MAA (公测版|正式版)(更新|下载)信息$/,
    (m) =>
      text(m[1] ? 'maaCheckingSource' : 'maaChecking', {
        source: source(m[1]),
        channel: channel(m[2]),
        operation: operation(m[3])
      })
  ],
  [
    /^正在(通过 Mirror酱)?为 MAA (更新|下载)下载 Linux ([A-Za-z\d_.-]+) 完整包$/,
    (m) =>
      text(m[1] ? 'downloadLinuxSource' : 'downloadLinux', {
        source: 'MirrorChyan',
        operation: operation(m[2]),
        arch: m[3]
      })
  ],
  [
    /^正在(通过 Mirror酱)?下载 Windows ([A-Za-z\d_.-]+) (OTA 增量包|完整包)$/,
    (m) =>
      text(m[1] ? 'downloadWindowsSource' : 'downloadWindows', {
        source: 'MirrorChyan',
        arch: m[2],
        package: packageName(m[3])
      })
  ],
  [
    /^正在通过 Mirror酱为 MAA (更新|下载)下载 macOS 完整包$/,
    (m) => text('downloadMacFull', { operation: operation(m[1]) })
  ],
  [
    /^正在通过 Mirror酱为 MAA (更新|下载)下载 Windows arm64 Python 来源包$/,
    (m) => text('downloadPythonSource', { operation: operation(m[1]) })
  ],
  [
    /^正在为 MAA (更新|下载)下载 macOS 运行库$/,
    (m) => text('downloadMacRuntime', { operation: operation(m[1]) })
  ],
  [
    /^正在通过 (Mirror酱|GitHub)下载 MAA 资源包$/,
    (m) => text('downloadMaaResources', { source: source(m[1]) })
  ],
  [
    /^当前 MAA (\S+) 无需更新（(公测版|正式版)）$/,
    (m) => text('maaCurrent', { version: m[1], channel: channel(m[2]) })
  ],
  [/^MAA 资源 (\S+) 已是最新版本$/, (m) => text('maaResourceCurrent', { version: m[1] })],
  [
    /^MAA 资源 (\S+) 已通过 (Mirror酱|GitHub)更新完成$/,
    (m) => text('maaResourceSuccess', { version: m[1], source: source(m[2]) })
  ],
  [
    /^MAA (\S+) (公测版|正式版)已通过 (Mirror酱|GitHub)(更新|下载)完成；已安装 (Linux|Windows) ([A-Za-z\d_.-]+) 完整包$/,
    (m) =>
      text('maaInstalledPlatform', {
        version: m[1],
        channel: channel(m[2]),
        source: source(m[3]),
        operation: operation(m[4]),
        platform: m[5],
        arch: m[6]
      })
  ],
  [
    /^MAA (\S+) (公测版|正式版)已通过 Mirror酱(更新|下载)完成；macOS 与 Windows arm64 完整包均已校验$/,
    (m) =>
      text('maaInstalledMacMirror', {
        version: m[1],
        channel: channel(m[2]),
        operation: operation(m[3])
      })
  ],
  [
    /^MAA (\S+) (公测版|正式版)(更新|下载)完成；Python 文件按需下载 (\d+) 字节（完整 Windows 包 (\d+) 字节）$/,
    (m) =>
      text('maaInstalledMacGithub', {
        version: m[1],
        channel: channel(m[2]),
        operation: operation(m[3]),
        downloaded: m[4],
        total: m[5]
      })
  ],
  [
    /^发现 MAA (公测版|正式版)新版本 (\S+)（(Mirror酱|GitHub)）$/,
    (m) => text('maaNewVersion', { channel: channel(m[1]), version: m[2], source: source(m[3]) })
  ],
  [
    /^当前 MAA 已是最新(公测版|正式版)$/,
    (m) => text('maaChannelCurrent', { channel: channel(m[1]) })
  ],
  [
    /^发现 MAA 资源新版本 (\S+)（(Mirror酱|GitHub)）$/,
    (m) => text('maaResourceNewVersion', { version: m[1], source: source(m[2]) })
  ]
]

const suffixes = ['restartMowerSuffix', 'unknownCoreSuffix', 'restartAndroidSuffix'].map((key) => [
  softwareUpdateMessages['zh-CN'][key],
  key
])

export function softwareUpdateMessage(message) {
  if (typeof message !== 'string' || i18n.global.locale.value === 'zh-CN') return message
  const exact = exactMessages.get(message)
  if (exact) return text(exact)
  for (const [pattern, format] of patterns) {
    const match = pattern.exec(message)
    if (match) return format(match)
  }

  let body = message
  const endingKeys = []
  while (true) {
    const suffix = suffixes.find(([ending]) => body.endsWith(ending))
    if (!suffix) break
    body = body.slice(0, -suffix[0].length)
    endingKeys.unshift(suffix[1])
  }
  for (const [pattern, format] of patterns) {
    const match = pattern.exec(body)
    if (match) return format(match) + endingKeys.map((key) => text(key)).join('')
  }
  return message
}
