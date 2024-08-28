import { createApp, ref } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router.js'
import axios from 'axios'
import VueAxios from 'vue-axios'

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
