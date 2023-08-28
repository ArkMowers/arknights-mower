<template>
  <n-config-provider
    :locale="zhCN"
    :date-locale="dateZhCN"
    class="provider"
    :theme="theme == 'dark' ? darkTheme : undefined"
  >
    <n-global-style />
    <n-dialog-provider>
      <n-tabs type="segment" class="tabs">
        <n-tab-pane name="home" tab="日志">
          <home />
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
import { onMounted, inject } from 'vue'
import { storeToRefs } from 'pinia'
import doc from '@/pages/Doc.vue'
import home from '@/pages/Home.vue'
import plan from '@/pages/Plan.vue'
import advanced from '@/pages/Advanced.vue'
import external from '@/pages/External.vue'
import record from '@/pages/record.vue'
import { zhCN, dateZhCN, darkTheme } from 'naive-ui'

import { useConfigStore } from '@/stores/config'
import { usePlanStore } from '@/stores/plan'
import { useMowerStore } from '@/stores/mower'

const config_store = useConfigStore()
const { load_config, load_shop } = config_store
const { start_automatically, theme } = storeToRefs(config_store)

const plan_store = usePlanStore()
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

onMounted(async () => {
  await load_config()
  await load_shop()
  await load_plan()
  await load_operators()
  await get_running()

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
  height: 100vh;
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
  width: 600px;
  margin: 0 auto;
}

.n-checkbox {
  align-items: center;
}
</style>
