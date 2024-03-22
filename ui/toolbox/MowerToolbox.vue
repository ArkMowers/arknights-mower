<script setup>
import { onMounted, ref } from 'vue'
import PlayIcon from '@vicons/ionicons5/Play'

const loading = ref(true)
const settings = ref({})
const running = ref(false)

const task = ref('ra')

const ra_timeout = ref(30)

onMounted(() => {
  window.addEventListener('pywebviewready', async () => {
    settings.value = await pywebview.api.get_settings()
    loading.value = false
  })
})

function start_task() {
  running.value = true
  pywebview.api.set_settings(settings.value)
  pywebview.api.start_task(task.value)
}
</script>

<template>
  <n-card size="small" v-if="!loading" class="container">
    <n-form :show-feedback="false" label-width="120" label-align="left" label-placement="left">
      <n-form-item label="服务器">
        <n-radio-group v-model:value="settings.package_type">
          <n-space>
            <n-radio value="official">官服</n-radio>
            <n-radio value="bilibili">BiliBili服</n-radio>
          </n-space>
        </n-radio-group>
      </n-form-item>
      <n-form-item label="ADB连接地址">
        <n-input v-model:value="settings.adb" />
      </n-form-item>
    </n-form>
  </n-card>
  <n-tabs placement="left" type="card" class="container" v-model:value="task">
    <n-tab-pane name="ra" tab="生息演算">
      <n-form :show-feedback="false" label-width="72" label-align="left" label-placement="left">
        <n-form-item label="超时时长">
          <n-input-number v-model:value="ra_timeout">
            <template #suffix>秒</template>
          </n-input-number>
        </n-form-item>
      </n-form>
    </n-tab-pane>
  </n-tabs>
  <n-button type="success" class="container" @click="start_task" v-if="!running">
    <template #icon>
      <n-icon>
        <play-icon />
      </n-icon>
    </template>
    开始运行
  </n-button>
</template>

<style scoped>
.container {
  width: auto;
  margin: 8px 8px 0;
  box-sizing: border-box;
}
</style>
