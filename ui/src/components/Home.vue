<script setup>
import { useConfigStore } from '@/stores/config'
import { useMowerStore } from '@/stores/mower'
import { usePlanStore } from '@/stores/plan'
import { storeToRefs } from 'pinia'
import { onMounted, inject, nextTick, watch } from 'vue'
import { useDialog } from 'naive-ui'

const config_store = useConfigStore()
const mower_store = useMowerStore()
const plan_store = usePlanStore()

const { adb, package_type, free_blacklist, plan_file } = storeToRefs(config_store)
const { log, running, first_load, log_lines } = storeToRefs(mower_store)
const { operators } = storeToRefs(plan_store)

const { build_config } = config_store
const { build_plan } = plan_store

const axios = inject('axios')

function scroll_log() {
  nextTick(() => {
    document.querySelector('pre:last-child')?.scrollIntoView()
  })
}

watch(log, (new_log, old_log) => {
  scroll_log()
})

const dialog = useDialog()

onMounted(() => {
  scroll_log()

  if (first_load.value) {
    dialog.warning({
      title: '注意',
      content:
        'Mower的Web UI界面仍不完善，请在使用前备份配置文件（conf.yml）与排班表（plan.json）！',
      negativeText: '我已备份',
      maskClosable: false
    })
    first_load.value = false
  }
})

function start() {
  running.value = true
  log_lines.value = []
  axios
    .post(`${import.meta.env.VITE_HTTP_URL}/conf`, build_config())
    .then(() => {
      return axios.post(`${import.meta.env.VITE_HTTP_URL}/plan`, build_plan())
    })
    .then(() => {
      axios.get(`${import.meta.env.VITE_HTTP_URL}/start`)
    })
}

function stop() {
  running.value = false
  axios.get(`${import.meta.env.VITE_HTTP_URL}/stop`)
}
</script>

<template>
  <div class="home-container">
    <table>
      <tr>
        <td>服务器：</td>
        <td>
          <n-radio-group v-model:value="package_type">
            <n-radio value="official">官服</n-radio>
            <n-radio value="bilibili">BiliBili服</n-radio>
          </n-radio-group>
        </td>
        <td></td>
      </tr>
      <tr>
        <td>adb连接地址：</td>
        <td>
          <n-input v-model:value="adb"></n-input>
        </td>
        <td></td>
      </tr>
      <tr>
        <td>宿舍黑名单：</td>
        <td>
          <n-select multiple filterable tag :options="operators" v-model:value="free_blacklist" />
        </td>
        <td></td>
      </tr>
      <tr>
        <td>排班表：</td>
        <td>
          <n-input v-model:value="plan_file"></n-input>
        </td>
        <td>
          <n-button>...</n-button>
        </td>
      </tr>
    </table>
    <n-log class="log" :log="log" />
    <div>
      <n-button type="error" @click="stop" v-if="running">立即停止</n-button>
      <n-button type="primary" @click="start" v-else>开始执行</n-button>
    </div>
  </div>
</template>

<style scoped>
.home-container {
  padding: 0 12px 12px;
  flex-grow: 1;
  display: flex;
  flex-direction: column;
  gap: 8px;
  overflow: hidden;
}

.log {
  flex-grow: 1;
  overflow: hidden;
  border: 1px solid rgb(224, 224, 230);
  border-radius: 3px;
  padding: 4px;
}
</style>
