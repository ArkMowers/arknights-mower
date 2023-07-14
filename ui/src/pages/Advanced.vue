<script setup>
import { useConfigStore } from '@/stores/config'
import { usePlanStore } from '@/stores/plan'
import { storeToRefs } from 'pinia'
import { computed } from 'vue'

const config_store = useConfigStore()
const plan_store = usePlanStore()

const {
  run_mode,
  run_order_delay,
  drone_room,
  drone_count_limit,
  reload_room,
  start_automatically,
  free_blacklist,
  adb,
  package_type,
  simulator,
  theme
} = storeToRefs(config_store)

const {
  ling_xi,
  max_resting_count,
  resting_priority,
  exhaust_require,
  rest_in_full,
  operators,
  workaholic
} = storeToRefs(plan_store)

const { left_side_facility } = plan_store

const facility_with_empty = computed(() => {
  return [{ label: '（加速贸易站）', value: '' }].concat(left_side_facility)
})

const simulator_types = [
  { label: '夜神', value: '夜神' },
  { label: '其它', value: '其它' }
]
</script>

<template>
  <div class="home-container external-container">
    <table>
      <tr>
        <td class="config-label">服务器：</td>
        <td>
          <n-radio-group v-model:value="package_type">
            <n-radio value="official">官服</n-radio>
            <n-radio value="bilibili">BiliBili服</n-radio>
          </n-radio-group>
        </td>
      </tr>
      <tr>
        <td>adb连接地址：</td>
        <td style="width: 150px">
          <n-input v-model:value="adb"></n-input>
        </td>
      </tr>
      <tr>
        <td style="width: 75px">模拟器：</td>
        <td style="width: 150px">
          <n-select v-model:value="simulator.name" :options="simulator_types" class="type-select" />
        </td>
      </tr>
      <tr>
        <td style="width: 75px">多开编号：</td>
        <td style="width: 150px">
          <n-input-number v-model:value="simulator.index"></n-input-number>
        </td>
      </tr>
      <tr>
        <td>运行模式：</td>
        <td>
          <n-radio-group v-model:value="run_mode">
            <n-space>
              <n-radio value="full">换班模式</n-radio>
              <n-radio value="orders_only">仅跑单模式</n-radio>
            </n-space>
          </n-radio-group>
        </td>
      </tr>
      <tr>
        <td>宿舍黑名单：</td>
        <td>
          <n-select multiple filterable tag :options="operators" v-model:value="free_blacklist" />
        </td>
      </tr>
      <tr>
        <td>跑单前置延时（分钟）：</td>
        <td>
          <n-input v-model:value="run_order_delay"></n-input>
        </td>
      </tr>
      <tr>
        <td>无人机使用房间（room_X_X）：</td>
        <td class="table-space">
          <n-select :options="facility_with_empty" v-model:value="drone_room" />
        </td>
      </tr>
      <tr>
        <td>无人机使用阈值：</td>
        <td>
          <n-input v-model:value="drone_count_limit"></n-input>
        </td>
      </tr>
      <tr>
        <td>搓玉补货房间：</td>
        <td>
          <n-select
            multiple
            filterable
            tag
            :options="left_side_facility"
            v-model:value="reload_room"
          />
        </td>
      </tr>
      <tr>
        <td colspan="2">
          <n-checkbox v-model:checked="start_automatically">启动mower时自动开始任务</n-checkbox>
        </td>
      </tr>
      <tr>
        <td>显示主题：</td>
        <td>
          <n-radio-group v-model:value="theme">
            <n-radio value="light">亮色</n-radio>
            <n-radio value="dark">暗色</n-radio>
          </n-radio-group>
        </td>
      </tr>
    </table>
    <email />
    <maa-basic />
  </div>
</template>

<style scoped lang="scss"></style>
