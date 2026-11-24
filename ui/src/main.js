import { createApp, h, ref } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router.js'
import axios from 'axios'

import RelayInstanceToken from './components/RelayInstanceToken.vue'
import { isRelayPage, relayBuild } from './utils/instanceToken'
import { releaseBoot } from './boot/bootScreen'

if (isRelayPage()) {
  axios.defaults.headers.common['X-Mower-UI-Build'] = relayBuild()
  axios.interceptors.response.use(undefined, (error) => {
    if (error.response?.headers?.['x-mower-ui-reload'] === '1') window.location.reload()
    return Promise.reject(error)
  })
}
// 首次导航从 app.use(router) 开始。配置或中转登录结束后再订阅会错过已经发生的加载错误。
const firstPageFailed = ref(false)
router.isReady().catch(() => {
  firstPageFailed.value = true
})
const ready = ref(!isRelayPage())
const app = createApp({
  render: () =>
    ready.value
      ? h(App, { firstPageFailed: firstPageFailed.value })
      : h(RelayInstanceToken, {
          onReady: () => {
            ready.value = true
          },
          // 中转登录表单挂载后即可输入实例 Token。
          onVnodeMounted: () => releaseBoot('app')
        })
})
app.use(router)
app.provide('axios', axios)
app.use(createPinia())
app.provide('loaded', ref(false))

app.mount('#app')
// main.js

import { plugin as Slicksort } from 'vue-slicksort'

// Enables groups and drag and drop functionality
app.use(Slicksort)
