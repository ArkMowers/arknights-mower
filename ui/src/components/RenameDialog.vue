<script setup>
import { inject } from 'vue'
const show = inject('show_name_editor')

import { storeToRefs } from 'pinia'
import { usePlanStore } from '@/stores/plan'

const plan_store = usePlanStore()
const { sub_plan, backup_plans } = storeToRefs(plan_store)

const triggerTimingOptions = [
  { label: '任务开始', value: 'BEGINNING' },
  { label: '下班结束', value: 'BEFORE_PLANNING' },
  { label: '上班结束', value: 'AFTER_PLANNING' },
  { label: '任务结束', value: 'END' }
]

function update_trigger(data) {
  backup_plans.value[sub_plan.value].trigger = data
}
</script>

<template>
  <n-modal
    v-model:show="show"
    preset="card"
    title="重命名"
    transform-origin="center"
    style="width: auto; max-width: 90vw"
  >
    <div class="dropdown-container">
      <label class="dropdown-label">副表名称 </label>
      <n-input v-model:value="backup_plans[sub_plan].name"> </n-input>
    </div>
  </n-modal>
</template>

<style>
.dropdown-container {
  display: flex;
  align-items: center;
  margin-top: 5px;
}

.dropdown-label {
  flex: 0 0 40%;
  max-width: 125px;
}

.dropdown-select {
  flex: 1;
}
</style>
