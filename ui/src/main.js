import { createApp, ref } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router.js'
import axios from 'axios'
import VueAxios from 'vue-axios'

// 添加全局超时配置
axios.defaults.timeout = 30000  // 30 秒超时

// 添加全局错误拦截器
axios.interceptors.response.use(
  response => response,
  error => {
    console.error('API请求失败：', error)
    return Promise.reject(error)
  }
)

const app = createApp(App)
app.use(router)
app.use(VueAxios, axios)
app.provide('axios', app.config.globalProperties.axios)
app.use(createPinia())
app.provide('loaded', ref(false))

app.mount('#app')
// main.js

import { plugin as Slicksort } from 'vue-slicksort'

// Enables groups and drag and drop functionality
app.use(Slicksort)
