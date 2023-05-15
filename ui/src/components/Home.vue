<script setup>
import { useConfigStore } from '@/stores/config'
import { useMowerStore } from '@/stores/mower'
import { storeToRefs } from 'pinia'
import { onMounted, inject, nextTick, watch } from 'vue'

const config_store = useConfigStore()
const mower_store = useMowerStore()

const { adb, package_type, free_blacklist, plan_file } = storeToRefs(config_store)
const { log, ws } = storeToRefs(mower_store)
const { listen_ws } = mower_store

const axios = inject('axios')

const running = ref(false)

function scroll_log() {
  nextTick(() => {
    document.querySelector('pre:last-child')?.scrollIntoView()
  })
}

watch(log, (new_log, old_log) => {
  scroll_log()
})

onMounted(() => {
  scroll_log()
  if (!ws.value) {
    listen_ws()
  }
})

function send_hello() {
  ws.value.send('Hello!')
}

function start() {
  running.value = true
  axios.get('http://localhost:8000/start')
}

function stop() {
  running.value = false
  axios.get('http://localhost:8000/stop')
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
          <n-input v-model:value="free_blacklist"></n-input>
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
