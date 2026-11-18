import { createApp, h, ref } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router.js'
import axios from 'axios'

import RelayInstanceToken from './components/RelayInstanceToken.vue'
import { isRelayPage, relayBuild } from './utils/instanceToken'

if (isRelayPage()) {
  axios.defaults.headers.common['X-Mower-UI-Build'] = relayBuild()
  axios.interceptors.response.use(undefined, (error) => {
    if (error.response?.headers?.['x-mower-ui-reload'] === '1') window.location.reload()
    return Promise.reject(error)
  })
}
const ready = ref(!isRelayPage())
const app = createApp({
  render: () =>
    ready.value
      ? h(App)
      : h(RelayInstanceToken, {
          onReady: () => {
            ready.value = true
          }
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
