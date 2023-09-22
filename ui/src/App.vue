<template>
  <n-config-provider
    :locale="zhCN"
    :date-locale="dateZhCN"
    class="provider"
    :theme="theme == 'dark' ? darkTheme : undefined"
    :hljs="hljs"
  >
    <n-global-style />
    <n-dialog-provider>
      <n-tabs type="segment" class="tabs">
        <n-tab-pane name="home" tab="日志">
          <home v-if="loaded" />
        </n-tab-pane>
        <n-tab-pane name="basic" tab="设置">
          <advanced />
        </n-tab-pane>
        <n-tab-pane name="plan" tab="排班">
          <plan />
        </n-tab-pane>
        <n-tab-pane name="external" tab="任务">
          <external />
        </n-tab-pane>
        <n-tab-pane name="record" tab="报表">
          <record />
        </n-tab-pane>
        <n-tab-pane name="doc" tab="文档">
          <doc />
        </n-tab-pane>
      </n-tabs>
    </n-dialog-provider>
  </n-config-provider>
</template>

<script setup>
import { onMounted, inject, provide } from 'vue'
import { storeToRefs } from 'pinia'
import doc from '@/pages/Doc.vue'
import home from '@/pages/Home.vue'
import plan from '@/pages/Plan.vue'
import advanced from '@/pages/Advanced.vue'
import external from '@/pages/External.vue'
import record from '@/pages/record.vue'
import { zhCN, dateZhCN, darkTheme } from 'naive-ui'

import hljs from 'highlight.js/lib/core'

import { useConfigStore } from '@/stores/config'
import { usePlanStore } from '@/stores/plan'
import { useMowerStore } from '@/stores/mower'

const config_store = useConfigStore()
const { load_config, load_shop } = config_store
const { start_automatically, theme } = storeToRefs(config_store)

const plan_store = usePlanStore()
const { operators } = storeToRefs(plan_store)
const { load_plan, load_operators } = plan_store

const mower_store = useMowerStore()
const { ws, running, log_lines } = storeToRefs(mower_store)
const { get_running, listen_ws } = mower_store

const axios = inject('axios')

function start() {
  running.value = true
  log_lines.value = []
  axios.get(`${import.meta.env.VITE_HTTP_URL}/start`)
}

function set_window_height() {
  const vh = window.innerHeight * 0.01
  document.documentElement.style.setProperty('--vh', `${vh}px`)
}

const loaded = ref(false)

const mobile = ref(true)
provide('mobile', mobile)

onMounted(async () => {
  set_window_height()
  mobile.value = window.innerWidth < 500
  window.addEventListener('resize', () => {
    set_window_height()
    mobile.value = window.innerWidth < 500
  })

  const params = new URLSearchParams(document.location.search)
  const token = params.get('token')
  axios.defaults.headers.common['token'] = token
  await Promise.all([load_config(), load_shop(), load_operators(), get_running()])

  const r = RegExp(operators.value.map((x) => "'" + x.value).join('|'))
  loaded.value = true

  hljs.registerLanguage('mower', () => ({
    contains: [
      {
        begin: r,
        end: /'/,
        className: 'operator',
        relevance: 0
      },
      {
        begin: /宿舍黑名单|重设上次房间为空/,
        relevance: 10
      },
      {
        begin: /[0-9]+(-[0-9]+)+/,
        className: 'date'
      },
      {
        begin: /[0-9]+:[0-9]+:[0-9]+(\.[0-9]+)?/,
        className: 'time'
      },
      {
        begin: /room_[0-9]_[0-9]|dormitory_[0-9]|central|contact|factory|meeting/,
        className: 'room'
      }
    ]
  }))

  await load_plan()

  if (!ws.value) {
    listen_ws()
  }

  if (start_automatically.value) {
    start()
  }
})
</script>

<style scoped>
.tabs {
  height: 100%;
}

.provider {
  height: 100%;
}
</style>

<style>
#app {
  height: calc(var(--vh, 1vh) * 100);
}

.n-tab-pane {
  flex-grow: 1;
  display: flex;
  flex-direction: column;
  overflow: auto;
}

.n-card-header__main {
  display: flex;
  align-items: center;
  gap: 6px;
}

td {
  height: 34px;
}

.table-space {
  padding-right: 20px;
}

.home-container {
  padding: 0 12px 12px;
  flex-grow: 1;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.external-container {
  max-width: 600px;
  margin: 0 auto;
}

.n-checkbox {
  align-items: center;
}
</style>
