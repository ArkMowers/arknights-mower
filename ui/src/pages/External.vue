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
            <table class="tab-content">
              <tr>
                <td>主题：</td>
                <td>
                  <n-radio-group>
                    <n-space>
                      <n-radio value="phantom">傀影与猩红孤钻</n-radio>
                      <n-radio value="mizuki">水月与深蓝之树</n-radio>
                      <n-radio value="sami">探索者的银凇止境</n-radio>
                    </n-space>
                  </n-radio-group>
                </td>
              </tr>
            </table>
          </n-tab-pane>
          <n-tab-pane name="sss" tab="保全派驻" disabled></n-tab-pane>
          <n-tab-pane name="ra" tab="生息演算" disabled></n-tab-pane>
        </n-tabs>
      </n-card>
      <!-- <table class="maa-table"> -->
      <!--   <tr> -->
      <!--     <td class="table-space">肉鸽：</td> -->
      <!--     <td colspan="3"> -->
      <!--       <n-radio-group v-model:value="maa_rg_enable"> -->
      <!--         <n-space> -->
      <!--           <n-radio :value="1">启用</n-radio> -->
      <!--           <n-radio :value="0">禁用</n-radio> -->
      <!--         </n-space> -->
      <!--       </n-radio-group> -->
      <!--     </td> -->
      <!--   </tr> -->
      <!-- </table> -->
      <!-- <div style="border: 1px solid black; width: 500px; padding: 10px"> -->
      <!--   <div class="tab-buttons"> -->
      <!--     <button @click="selectTab('禁用')" :class="{ active: maa_add_task === '禁用' }"> -->
      <!--       禁用 -->
      <!--     </button> -->
      <!--     <button @click="selectTab('肉鸽')" :class="{ active: maa_add_task === '肉鸽' }"> -->
      <!--       肉鸽 -->
      <!--     </button> -->
      <!--     <button @click="selectTab('保全')" :class="{ active: maa_add_task === '保全' }"> -->
      <!--       保全 -->
      <!--     </button> -->
      <!--     <button @click="selectTab('生息演算')" :class="{ active: maa_add_task === '生息演算' }"> -->
      <!--       生息演算 -->
      <!--     </button> -->
      <!--   </div> -->
      <!---->
      <!--   <div class="tab-content"> -->
      <!--     <div v-if="maa_add_task === '禁用'"></div> -->
      <!--     <div v-if="maa_add_task === '肉鸽'"> -->
      <!--       <table> -->
      <!--         <tr> -->
      <!--           <td class="table-space">休息时间开始</td> -->
      <!--           <td class="table-space"> -->
      <!--             <n-input v-model:value="sleep_min" placeholder="8:00"></n-input> -->
      <!--           </td> -->
      <!--           <td class="table-space">休息时间结束</td> -->
      <!--           <td class="table-space"> -->
      <!--             <n-input v-model:value="sleep_max" placeholder="10:00"></n-input> -->
      <!--           </td> -->
      <!--         </tr> -->
      <!--       </table> -->
      <!--     </div> -->
      <!--     <div v-if="maa_add_task === '保全'"> -->
      <!--       <table> -->
      <!--         <tr> -->
      <!--           <td class="select-label">保全派驻关卡：</td> -->
      <!--           <td class="table-space"> -->
      <!--             <n-select tag :options="sss_option" class="sss-select" v-model:value="sss_type" /> -->
      <!--           </td> -->
      <!--           <td class="select-label">循环次数：</td> -->
      <!--           <td style="width: 50px"> -->
      <!--             <n-input v-model:value="copilot_loop_times" placeholder="10">10</n-input> -->
      <!--           </td> -->
      <!--         </tr> -->
      <!--         <tr> -->
      <!--           <td class="select-label">作业地址：</td> -->
      <!--           <td colspan="2" class="input-td"> -->
      <!--             <n-input v-model:value="copilot_file_location"></n-input> -->
      <!--           </td> -->
      <!--           <td class="table-space"> -->
      <!--             <n-button @click="select_maa_dir">...</n-button> -->
      <!--           </td> -->
      <!--         </tr> -->
      <!--       </table> -->
      <!--     </div> -->
      <!--     <div v-if="maa_add_task === '生息演算'"> -->
      <!--       <p>生息演算未开放</p> -->
      <!--     </div> -->
      <!--   </div> -->
      <!-- </div> -->
    </n-card>
  </div>
</template>

<style scoped lang="scss">
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

.tab-content {
  margin: 0 24px 12px 24px;
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
