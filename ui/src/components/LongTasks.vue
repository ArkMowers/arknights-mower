<script setup>
import { inject } from 'vue'
import { storeToRefs } from 'pinia'
import { useConfigStore } from '@/stores/config'
const config_store = useConfigStore()
const { maa_rg_enable, maa_long_task_type, maa_rg_sleep_min, maa_rg_sleep_max } =
  storeToRefs(config_store)

const mobile = inject('mobile')
</script>

<template>
  <n-card>
    <template #header>
      <n-checkbox v-model:checked="maa_rg_enable">
        <div class="card-title">
          大型任务
          <help-text>
            <div>开始与结束时间设置为相同值时全天开启。</div>
            <div>若结束时间早于开始时间，则表示开启至次日。例如：</div>
            <ul>
              <li>23:00开始、8:00结束：表示从23:00至次日8:00执行大型任务；</li>
              <li>10:00开始、14:00结束：表示从10:00至当日14:00执行大型任务。</li>
            </ul>
          </help-text>
        </div>
      </n-checkbox>
    </template>
    <n-form :label-placement="mobile ? 'top' : 'left'" :show-feedback="false">
      <n-grid cols="2">
        <n-form-item-gi label="开始时间">
          <n-time-picker format="H:mm" v-model:formatted-value="maa_rg_sleep_max" />
        </n-form-item-gi>
        <n-form-item-gi label="停止时间">
          <n-time-picker format="H:mm" v-model:formatted-value="maa_rg_sleep_min" />
        </n-form-item-gi>
      </n-grid>
    </n-form>
    <n-tabs
      type="line"
      :value="maa_long_task_type"
      :on-update:value="
        (v) => {
          maa_long_task_type = v
        }
      "
    >
      <n-tab-pane name="rogue" tab="集成战略 (Maa)">
        <maa-rogue />
      </n-tab-pane>
      <n-tab-pane name="sss" tab="保全派驻 (Maa)">
        <maa-sss />
      </n-tab-pane>
      <n-tab-pane name="ra" tab="生息演算">
        <reclamation-algorithm />
      </n-tab-pane>
    </n-tabs>
  </n-card>
</template>

<style scoped>
.card-title {
  font-weight: 500;
  font-size: 18px;
}
</style>
