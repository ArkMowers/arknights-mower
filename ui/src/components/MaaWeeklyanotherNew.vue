<script setup>
import { storeToRefs } from 'pinia'
import { useConfigStore } from '@/stores/config'

const store = useConfigStore()
const { maa_weekly_plan_new, maa_enable } = storeToRefs(store)

import { NTag } from 'naive-ui'
import { h, ref } from 'vue'
const weekday = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
import { NTooltip } from 'naive-ui'
const plan_map = [
  { label: 'Annihilation', value: 'Annihilation' },
  { label: '', value: '' },
  { label: '点x删除', value: '点x删除' },
  { label: '把鼠标放到问号上查看帮助', value: '把鼠标放到问号上查看帮助' },
  { label: '自定义关卡3', value: '自定义关卡3' },
  { label: '1-7', value: '1-7' },
  { label: 'LS-6', value: 'LS-6' },
  { label: 'CE-6', value: 'CE-6' },
  { label: 'AP-5', value: 'AP-5' },
  { label: 'SK-6', value: 'SK-6' },
  { label: 'CA-5', value: 'CA-5' },
  { label: 'PR-A-2', value: 'PR-A-2' },
  { label: 'PR-A-1', value: 'PR-A-1' },
  { label: 'PR-B-2', value: 'PR-B-2' },
  { label: 'PR-B-1', value: 'PR-B-1' },
  { label: 'PR-C-2', value: 'PR-C-2' },
  { label: 'PR-C-1', value: 'PR-C-1' },
  { label: 'PR-D-2', value: 'PR-D-2' },
  { label: 'PR-D-1', value: 'PR-D-1' }
]
const default_plan = {
  Annihilation: [1, 1, 1, 1, 1, 1, 1],
  '': [1, 1, 1, 1, 1, 1, 1],
  点x删除: [1, 1, 1, 1, 1, 1, 1],
  把鼠标放到问号上查看帮助: [1, 1, 1, 1, 1, 1, 1],
  自定义关卡3: [1, 1, 1, 1, 1, 1, 1],
  '1-7': [1, 1, 1, 1, 1, 1, 1],
  'LS-6': [1, 1, 1, 1, 1, 1, 1],
  'CE-6': [0, 1, 0, 1, 0, 1, 1],
  'AP-5': [1, 0, 0, 1, 0, 1, 1],
  'SK-6': [1, 0, 1, 0, 1, 1, 0],
  'CA-5': [0, 1, 1, 0, 1, 0, 1],
  'PR-A-2': [1, 0, 0, 1, 1, 0, 1],
  'PR-A-1': [1, 0, 0, 1, 1, 0, 1],
  'PR-B-2': [1, 1, 0, 0, 1, 1, 0],
  'PR-B-1': [1, 1, 0, 0, 1, 1, 0],
  'PR-C-2': [0, 0, 1, 1, 0, 1, 1],
  'PR-C-1': [0, 0, 1, 1, 0, 1, 1],
  'PR-D-2': [0, 1, 1, 0, 0, 1, 1],
  'PR-D-1': [0, 1, 1, 0, 0, 1, 1]
}
const renderOption = ({ node, option }) =>
  h(NTooltip, null, {
    trigger: () => node,
    default: () => '你选的是 ' + option.label
  })
const selected_stage = ref({})
</script>

<template>
  <n-table :bordered="false" :single-line="false">
    <thead>
      <tr>
        <th>本</th>
        <th>全选</th>
        <th v-for="day in weekday" :key="day">{{ day }}</th>
      </tr>
    </thead>
    <tbody>
      <tr v-for="choice in 4" :key="choice">
        <td>
          <n-select
            v-model:value="selected_stage[choice]"
            :options="plan_map"
            placeholder="选关"
            style="width: 100px"
          />
        </td>
        <td>√</td>
        <td v-for="daily_check in default_plan[selected_stage[choice]]">{{ daily_check }}</td>
      </tr>
    </tbody>

    {{ selected_stage }}
  </n-table>
</template>

<style></style>
