<script setup>
import { useConfigStore } from '@/stores/config'
import { usePlanStore } from '@/stores/plan'
import { storeToRefs } from 'pinia'

const config_store = useConfigStore()
const plan_store = usePlanStore()

const {
  run_mode,
  enable_party,
  run_order_delay,
  drone_room,
  drone_count_limit,
  reload_room,
  start_automatically
} = storeToRefs(config_store)

const { ling_xi, max_resting_count, resting_priority, exhaust_require, rest_in_full } =
  storeToRefs(plan_store)

const operators = [
  { label: '孑', value: 'Jaye' },
  { label: '拉普兰德', value: 'Lappland' },
  { label: '德克萨斯', value: 'Texas' },
  { label: '泰拉大陆调查团', value: 'TerraResearchCommission' },
  { label: '但书', value: 'Proviso' },
  { label: '龙舌兰', value: 'Tequila' }
]
</script>

<template>
  <div class="home-container">
    <n-space justify="center">
      <table>
        <tr>
          <td>运行模式：</td>
          <td colspan="3">
            <n-radio-group v-model:value="run_mode">
              <n-space>
                <n-radio value="full">换班模式</n-radio>
                <n-radio value="orders_only">仅跑单模式</n-radio>
              </n-space>
            </n-radio-group>
          </td>
          <td></td>
          <td></td>
        </tr>
        <tr>
          <td>令夕模式（令夕上班时起作用）：</td>
          <td colspan="3">
            <n-radio-group v-model:value="ling_xi">
              <n-space>
                <n-radio :value="1">感知信息</n-radio>
                <n-radio :value="2">人间烟火</n-radio>
                <n-radio :value="3">均衡模式</n-radio>
              </n-space>
            </n-radio-group>
          </td>
          <td></td>
          <td></td>
        </tr>
        <tr>
          <td>线索收集：</td>
          <td colspan="3">
            <n-radio-group v-model:value="enable_party">
              <n-space>
                <n-radio :value="true">启用</n-radio>
                <n-radio :value="false">禁用</n-radio>
              </n-space>
            </n-radio-group>
          </td>
          <td></td>
          <td></td>
        </tr>
        <tr>
          <td>最大组人数：</td>
          <td class="table-space">
            <n-input v-model:value="max_resting_count"></n-input>
          </td>
          <td>跑单前置延时（分钟）：</td>
          <td>
            <n-input v-model:value="run_order_delay"></n-input>
          </td>
        </tr>
        <tr>
          <td>无人机使用房间（room_X_X）：</td>
          <td class="table-space">
            <n-input v-model:value="drone_room"></n-input>
          </td>
          <td>无人机使用阈值：</td>
          <td>
            <n-input v-model:value="drone_count_limit"></n-input>
          </td>
        </tr>
        <tr>
          <td>搓玉补货房间（逗号分隔房间名）：</td>
          <td colspan="3">
            <n-input v-model:value="reload_room"></n-input>
          </td>
          <td></td>
          <td></td>
        </tr>
        <tr>
          <td>需要回满心情的干员：</td>
          <td colspan="3">
            <n-input v-model:value="rest_in_full"></n-input>
          </td>
          <td></td>
          <td></td>
        </tr>
        <tr>
          <td>需要用尽心情的干员：</td>
          <td colspan="3">
            <n-input v-model:value="exhaust_require"></n-input>
          </td>
          <td></td>
          <td></td>
        </tr>
        <tr>
          <td>宿舍低优先级干员：</td>
          <td colspan="3">
            <n-input v-model:value="resting_priority"></n-input>
          </td>
          <td></td>
          <td></td>
        </tr>
        <tr>
          <td colspan="4">
            <n-checkbox v-model:checked="start_automatically">启动mower时自动开始任务</n-checkbox>
          </td>
        </tr>
      </table>
    </n-space>
  </div>
</template>
