<script setup>
import { inject, ref } from 'vue'
const axios = inject('axios')

import { useConfigStore } from '@/stores/config'
const store = useConfigStore()

import { storeToRefs } from 'pinia'
const { maa_path, maa_adb_path, maa_gap, maa_conn_preset, maa_touch_option } = storeToRefs(store)

import { file_dialog, folder_dialog } from '@/utils/dialog'

async function select_maa_adb_path() {
  const file_path = await file_dialog()
  if (file_path) {
    maa_adb_path.value = file_path
  }
}

async function select_maa_dir() {
  const folder_path = await folder_dialog()
  if (folder_path) {
    maa_path.value = folder_path
  }
}

const maa_msg = ref('')

async function test_maa() {
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
    <p>需要Maa的功能：清理智、线索收集（信用商店购物）、公开招募、集成战略、保全派驻、生息演算。</p>
    <table class="maa-basic">
      <tr>
        <td>Maa目录</td>
        <td>
          <n-input v-model:value="maa_path"></n-input>
        </td>
        <td>
          <n-button @click="select_maa_dir">...</n-button>
        </td>
      </tr>
      <tr>
        <td>adb路径</td>
        <td>
          <n-input v-model:value="maa_adb_path"></n-input>
        </td>
        <td>
          <n-button @click="select_maa_adb_path">...</n-button>
        </td>
      </tr>
    </table>
    <div class="misc-container">
      <n-button @click="test_maa">测试设置</n-button>
      <div>{{ maa_msg }}</div>
    </div>
    <n-divider />
    <table class="maa-conn">
      <tr>
        <td>连接配置</td>
        <td>
          <n-select :options="maa_conn_presets" v-model:value="maa_conn_preset" />
        </td>
        <td>
          <n-button @click="get_maa_conn_presets">刷新</n-button>
        </td>
      </tr>
      <tr>
        <td>触控模式</td>
        <td colspan="2">
          <n-select v-model:value="maa_touch_option" :options="maa_touch_options" />
        </td>
      </tr>
    </table>
    <n-divider />
    <div class="misc-container">
      <div>启动间隔</div>
      <n-input-number class="hour-input" v-model:value="maa_gap" />
      <div>小时（可填小数）</div>
    </div>
  </n-card>
</template>

<style scoped lang="scss">
p {
  margin: 0 0 10px 0;
}

.maa-basic {
  width: 100%;
}

.maa-basic {
  td:nth-child(1) {
    width: 62px;
  }

  td:nth-child(2) {
    padding-right: 6px;
  }

  td:nth-child(3) {
    width: 40px;
  }
}

.misc-container {
  margin-top: 12px;
  display: flex;
  align-items: center;
  gap: 12px;
}

.hour-input {
  width: 120px;
}

.maa-conn {
  width: 100%;

  td {
    &:nth-child(1) {
      width: 62px;
    }
    &:nth-child(3) {
      width: 56px;
    }
  }
}
</style>
