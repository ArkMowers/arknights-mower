<template>
  <!-- <n-config-provider :locale="zhCN" :date-locale="dateZhCN" class="provider" :theme="darkTheme"> -->
  <n-config-provider :locale="zhCN" :date-locale="dateZhCN" class="provider">
    <n-global-style />
    <n-dialog-provider>
      <n-tabs type="segment" class="tabs">
        <n-tab-pane name="home" tab="主页">
          <home />
        </n-tab-pane>
        <n-tab-pane name="plan" tab="排班表">
          <plan />
        </n-tab-pane>
        <n-tab-pane name="advanced" tab="高级设置">
          <advanced />
        </n-tab-pane>
        <n-tab-pane name="external" tab="外部调用">
          <external />
        </n-tab-pane>
      </n-tabs>
    </n-dialog-provider>
  </n-config-provider>
</template>

<script setup>
import { onMounted, inject } from 'vue'
import { storeToRefs } from 'pinia'
import home from '@/components/Home.vue'
import plan from '@/components/Plan.vue'
import advanced from '@/components/Advanced.vue'
import external from '@/components/External.vue'
import { zhCN, dateZhCN, darkTheme } from 'naive-ui'

import { useConfigStore } from '@/stores/config'
import { usePlanStore } from '@/stores/plan'
import { useMowerStore } from '@/stores/mower'

const config_store = useConfigStore()
const { load_config } = config_store
const { start_automatically } = storeToRefs(config_store)

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

.n-checkbox {
  align-items: center;
}
</style>
