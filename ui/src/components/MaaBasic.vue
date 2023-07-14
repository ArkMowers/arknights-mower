<script setup>
import { inject } from 'vue'
const axios = inject('axios')

import { useConfigStore } from '@/stores/config'
const store = useConfigStore()

import { storeToRefs } from 'pinia'
const { maa_path, maa_adb_path, maa_gap } = storeToRefs(store)

async function select_maa_adb_path() {
  const response = await axios.get(`${import.meta.env.VITE_HTTP_URL}/dialog/file`)
  const file_path = response.data
  if (file_path) {
    maa_adb_path.value = file_path
  }
}

async function select_maa_dir() {
  const response = await axios.get(`${import.meta.env.VITE_HTTP_URL}/dialog/folder`)
  const folder_path = response.data
  if (folder_path) {
    maa_path.value = folder_path
  }
}
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
      <n-button disabled>测试设置</n-button>
      <div></div>
    </div>
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
</style>
