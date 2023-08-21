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
  maa_rg_sleep_min,
  maa_rg_sleep_max,
  sss_type,
  copilot_file_location,
  copilot_loop_times,
  maa_rg_theme
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

const rogue_themes = [
  { label: '傀影与猩红孤钻', value: 'Phantom' },
  { label: '水月与深蓝之树', value: 'Mizuki' },
  { label: '探索者的银凇止境', value: 'Sami' }
]
</script>

<template>
  <div class="home-container external-container">
    <clue />
    <maa-recruit />
    <maa-weekly />
    <n-card>
      <template #header>
        <n-checkbox v-model:checked="maa_rg_enable">
          <div class="card-title">Maa大型任务</div>
        </n-checkbox>
      </template>
      <p>调用Maa进行作战。仅可从以下任务中选择一项。</p>
      <n-h4>开启时间</n-h4>
      <p>只在开启时间内执行Maa大型任务。开始与结束时间设置为相同值时全天开启。</p>
      <p>若结束时间早于开始时间，则表示开启至次日。例如：</p>
      <ul>
        <li>23:00开始、8:00结束：表示从23:00至次日8:00执行大型任务；</li>
        <li>10:00开始、14:00结束：表示从10:00至当日14:00执行大型任务。</li>
      </ul>
      <table class="time-table">
        <tr>
          <td>开始</td>
          <td>
            <n-time-picker format="H:mm" v-model:formatted-value="maa_rg_sleep_max" />
          </td>
        </tr>
        <tr>
          <td>结束</td>
          <td>
            <n-time-picker format="H:mm" v-model:formatted-value="maa_rg_sleep_min" />
          </td>
        </tr>
      </table>
      <n-card content-style="padding: 0">
        <n-tabs type="segment">
          <n-tab-pane name="rogue" tab="集成战略">
            <maa-rogue />
          </n-tab-pane>
          <n-tab-pane name="sss" tab="保全派驻" disabled></n-tab-pane>
          <n-tab-pane name="ra" tab="生息演算" disabled></n-tab-pane>
        </n-tabs>
      </n-card>
    </n-card>
  </div>
</template>

<style scoped lang="scss">
.external-container {
  width: 600px;
  margin: 0 auto;
}

.sss-select {
  width: 175px;
}

.card-title {
  font-weight: 500;
  font-size: 18px;
}

p {
  margin: 0 0 8px 0;
}

h4 {
  margin: 12px 0 10px 0;
}

ul {
  padding-left: 24px;
  margin: 0 0 10px 0;
}

.time-table {
  width: 100%;
  margin-bottom: 12px;

  td:nth-child(1) {
    width: 40px;
  }
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
