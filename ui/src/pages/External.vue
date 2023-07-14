<script setup>
import { useConfigStore } from '@/stores/config'
import { storeToRefs } from 'pinia'
import { inject, ref } from 'vue'

const axios = inject('axios')

const store = useConfigStore()

const maa_add_task = ref('禁用')

const {
  maa_path,
  maa_rg_enable,
  sleep_min,
  sleep_max,
  sss_type,
  copilot_file_location,
  copilot_loop_times
} = storeToRefs(store)

const sss_option = ref([
  { label: '约翰老妈新建地块', value: 1 },
  { label: '雷神工业测试平台', value: 2 }
])

async function select_maa_dir() {
  const response = await axios.get(`${import.meta.env.VITE_HTTP_URL}/dialog/folder`)
  const folder_path = response.data
  if (folder_path) {
    maa_path.value = folder_path
  }
}

function selectTab(tab) {
  maa_add_task.value = tab
}
</script>

<template>
  <div class="home-container external-container">
    <clue />
    <maa-recruit />
    <maa-weekly />
    <n-card v-if="true">
      <template #header>
        <div class="card-title">MAA</div>
      </template>
      <template #default>
        <table class="maa-table">
          <tr>
            <td class="table-space">肉鸽：</td>
            <td colspan="3">
              <n-radio-group v-model:value="maa_rg_enable">
                <n-space>
                  <n-radio :value="1">启用</n-radio>
                  <n-radio :value="0">禁用</n-radio>
                </n-space>
              </n-radio-group>
            </td>
          </tr>
        </table>
        <div style="border: 1px solid black; width: 500px; padding: 10px">
          <div class="tab-buttons">
            <button @click="selectTab('禁用')" :class="{ active: maa_add_task === '禁用' }">
              禁用
            </button>
            <button @click="selectTab('肉鸽')" :class="{ active: maa_add_task === '肉鸽' }">
              肉鸽
            </button>
            <button @click="selectTab('保全')" :class="{ active: maa_add_task === '保全' }">
              保全
            </button>
            <button @click="selectTab('生息演算')" :class="{ active: maa_add_task === '生息演算' }">
              生息演算
            </button>
          </div>

          <div class="tab-content">
            <div v-if="maa_add_task === '禁用'"></div>
            <div v-if="maa_add_task === '肉鸽'">
              <table>
                <tr>
                  <td class="table-space">休息时间开始</td>
                  <td class="table-space">
                    <n-input v-model:value="sleep_min" placeholder="8:00"></n-input>
                  </td>
                  <td class="table-space">休息时间结束</td>
                  <td class="table-space">
                    <n-input v-model:value="sleep_max" placeholder="10:00"></n-input>
                  </td>
                </tr>
              </table>
            </div>
            <div v-if="maa_add_task === '保全'">
              <table>
                <tr>
                  <td class="select-label">保全派驻关卡：</td>
                  <td class="table-space">
                    <n-select
                      tag
                      :options="sss_option"
                      class="sss-select"
                      v-model:value="sss_type"
                    />
                  </td>
                  <td class="select-label">循环次数：</td>
                  <td style="width: 50px">
                    <n-input v-model:value="copilot_loop_times" placeholder="10">10</n-input>
                  </td>
                </tr>
                <tr>
                  <td class="select-label">作业地址：</td>
                  <td colspan="2" class="input-td">
                    <n-input v-model:value="copilot_file_location"></n-input>
                  </td>
                  <td class="table-space">
                    <n-button @click="select_maa_dir">...</n-button>
                  </td>
                </tr>
              </table>
            </div>
            <div v-if="maa_add_task === '生息演算'">
              <p>生息演算未开放</p>
            </div>
          </div>
        </div>
      </template>
    </n-card>
  </div>
</template>

<style scoped>
.external-container {
  width: 600px;
  margin: 0 auto;
}

.tab-buttons {
  display: flex;
}

.sss-select {
  width: 175px;
}

.tab-buttons button {
  padding: 8px 16px;
  background-color: #f0f0f0;
  border: none;
  border-radius: 4px;
  margin-right: 8px;
  cursor: pointer;
}

.tab-buttons button.active {
  background-color: #ccc;
}

.tab-content {
  margin-top: 16px;
}

.maa-table {
  width: 100%;
}

.maa-table-label {
  width: 70px;
}

.maa-mall {
  width: 70px;
  word-wrap: break-word;
  word-break: break-all;
}
</style>

<style>
.n-checkbox .n-checkbox__label {
  flex-grow: 1;
  display: flex;
  align-items: center;
  padding-right: 0;
}

.n-divider:not(.n-divider--vertical) {
  margin: 14px 0 8px;
}
</style>
