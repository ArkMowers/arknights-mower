<script setup>
import { ref } from 'vue'
import { storeToRefs } from 'pinia'
import { useConfigStore } from '@/stores/config'
const config_store = useConfigStore()
const { maa_rg_enable, maa_long_task_type, maa_rg_sleep_min, maa_rg_sleep_max } =
  storeToRefs(config_store)
</script>

<template>
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
    <n-tabs
      type="line"
      :value="maa_long_task_type"
      :on-update:value="
        (v) => {
          maa_long_task_type = v
        }
      "
    >
      <n-tab-pane name="rogue" tab="集成战略">
        <maa-rogue />
      </n-tab-pane>
      <n-tab-pane name="sss" tab="保全派驻">
        <maa-sss />
      </n-tab-pane>
      <n-tab-pane name="ra" tab="生息演算" disabled></n-tab-pane>
    </n-tabs>
  </n-card>
</template>

<style scoped>
.card-title {
  font-weight: 500;
  font-size: 18px;
}
</style>
