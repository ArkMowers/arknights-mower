<template>
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
</template>

<script setup>
import { onMounted } from 'vue'
import home from '@/components/Home.vue'
import plan from '@/components/Plan.vue'
import advanced from '@/components/Advanced.vue'
import external from '@/components/External.vue'

import { useConfigStore } from '@/stores/config'
import { usePlanStore } from '@/stores/plan'

const config_store = useConfigStore()
const { load_config } = config_store

const plan_store = usePlanStore()
const { load_plan, load_operators } = plan_store

onMounted(async () => {
  await load_config()
  await load_plan()
  await load_operators()
})
</script>

<style scoped>
.tabs {
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
  overflow: scroll;
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
