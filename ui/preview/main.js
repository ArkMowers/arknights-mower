import { createApp, ref } from 'vue'
import { createPinia } from 'pinia'
import axios from 'axios'
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
params.set('mower_version', '4.1.6-preview')
params.set('instance_name', '离线预览')
const initialPath = location.pathname.startsWith('/preview') ? '/' : location.pathname
history.replaceState(history.state, '', `${initialPath}?${params}${location.hash}`)

const config = createPreviewConfiguration(defaultConfiguration(), params.get('theme'))
const previewData = installPreviewBackend(config)
// 离线截图 / 评审可用 ?watermark=0 关闭示例水印，仅影响预览会话。
if (params.get('watermark') === '0') previewData.appearance.watermark_visible = false
localStorage.setItem('sc_preview', 'true')
await import('../src/main.js')
