<script setup>
import { inject, ref } from 'vue'
const axios = inject('axios')

const mobile = inject('mobile')

import { useConfigStore } from '@/stores/config'
const store = useConfigStore()

import { storeToRefs } from 'pinia'
const { maa_path, maa_conn_preset, maa_touch_option } = storeToRefs(store)

import { folder_dialog } from '@/utils/dialog'

async function select_maa_dir() {
  const folder_path = await folder_dialog()
  if (folder_path) {
    maa_path.value = folder_path
  }
}

const maa_msg = ref('')

async function test_maa() {
  maa_msg.value = '正在测试……'
  const response = await axios.get(`${import.meta.env.VITE_HTTP_URL}/check-maa`)
  maa_msg.value = response.data
}

const maa_conn_presets = ref([])

async function get_maa_conn_presets() {
  const response = await axios.get(`${import.meta.env.VITE_HTTP_URL}/maa-conn-preset`)
  maa_conn_presets.value = response.data.map((x) => {
    return { label: x, value: x }
  })
}

const maa_touch_options = ['maatouch', 'minitouch', 'adb'].map((x) => {
  return { label: x, value: x }
})
</script>

<template>
  <n-card title="Maa设置">
    <template #header>Maa设置<help-text>刷理智、信用相关、领奖励、肉鸽保全等</help-text></template>
    <n-form
      :label-placement="mobile ? 'top' : 'left'"
      :show-feedback="false"
      label-width="96"
      label-align="left"
    >
      <n-form-item label="Maa目录">
        <n-input type="textarea" :autosize="true" v-model:value="maa_path" />
        <n-button @click="select_maa_dir" class="dialog-btn">...</n-button>
      </n-form-item>
      <n-form-item label="连接配置">
        <n-select :options="maa_conn_presets" v-model:value="maa_conn_preset" />
        <n-button @click="get_maa_conn_presets" class="dialog-btn">刷新</n-button>
      </n-form-item>
      <n-form-item label="触控模式">
        <n-select v-model:value="maa_touch_option" :options="maa_touch_options" />
      </n-form-item>
    </n-form>
    <n-divider />
    <div class="misc-container">
      <n-button @click="test_maa">测试设置</n-button>
      <div>{{ maa_msg }}</div>
    </div>
  </n-card>
</template>

<style scoped lang="scss">
p {
  margin: 0 0 10px 0;
}

.misc-container {
  margin-top: 12px;
  display: flex;
  align-items: center;
  gap: 12px;
}
</style>
