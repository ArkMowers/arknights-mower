import { createApp, ref } from 'vue'
import { createPinia } from 'pinia'
import axios from 'axios'
import { failBoot } from '@/boot/bootScreen'
import { useConfigStore } from '@/stores/config'
import { createPreviewConfiguration, installPreviewBackend } from './mock.js'

if (import.meta.env.MODE !== 'mock-preview') {
  throw new Error('请通过 npm run preview:mock 或 npm run build:mock 使用离线预览')
}

function defaultConfiguration() {
  let snapshot
  const app = createApp({
    setup() {
      const config = useConfigStore()
      config.maa_mall_buy = []
      config.maa_mall_blacklist = []
      snapshot = JSON.parse(JSON.stringify(config.build_config()))
      config.$dispose()
      return () => null
    }
  })
  app.use(createPinia())
  app.provide('loaded', ref(false))
  app.provide('axios', axios)
  app.mount(document.createElement('div'))
  app.unmount()
  return snapshot
}

const params = new URLSearchParams(location.search)
if (!params.has('window_shell')) params.set('window_shell', '1')
// 预览地址可通过 mower_version 指定显示的软件版本。
if (!params.has('mower_version')) params.set('mower_version', '4.1.6-preview')
params.set('instance_name', '离线预览')
// 桌面窗口在地址里带上配置的主题，页面在读到配置前按它绘制；预览照此模拟。
if (!params.has('window_theme')) params.set('window_theme', params.get('theme') || 'light')
const initialPath = location.pathname.startsWith('/preview') ? '/' : location.pathname
history.replaceState(history.state, '', `${initialPath}?${params}${location.hash}`)

const config = createPreviewConfiguration(defaultConfiguration(), params.get('theme'))
// ?latency=800 让每个接口晚 800 毫秒响应，用来查看启动过程。
const latency = Math.min(Math.max(Number(params.get('latency')) || 0, 0), 10000)
// ?run=idle 以已停止、没有日志和截图的实例打开，用来查看未开始的运行日志页。
const previewData = installPreviewBackend(config, window, {
  latency,
  idle: params.get('run') === 'idle'
})
// 离线截图 / 评审可用 ?watermark=0 关闭示例水印，仅影响预览会话。
if (params.get('watermark') === '0') previewData.appearance.watermark_visible = false
localStorage.setItem('sc_preview', 'true')
try {
  await import('../src/main.js')
} catch (error) {
  console.error('离线预览界面加载失败', error)
  failBoot('界面脚本加载失败，请重新加载。')
}
