<script setup>
import { inject } from 'vue'
const show = inject('show_trigger_editor')

import { storeToRefs } from 'pinia'
import { usePlanStore } from '@/stores/plan'

const plan_store = usePlanStore()
const { sub_plan, backup_plans } = storeToRefs(plan_store)

const triggerTimingOptions = [
  { label: '任务开始', value: 'BEGINNING' },
  { label: '下班结束', value: 'BEFORE_PLANNING' },
  { label: '上班结束', value: 'AFTER_PLANNING' },
  { label: '任务结束', value: 'END' }
];

function update_trigger(data) {
  backup_plans.value[sub_plan.value].trigger = data
}
</script>

<template>
  <n-modal v-model:show="show" preset="card" title="触发条件" transform-origin="center"
    style="width: auto; max-width: 90vw">
    <div class="dropdown-container">
      <label class="dropdown-label">触发时机
        <help-text>
          <div>任务开始：单个任务开始时</div>
          <div>下班结束：高效组下班任务安排完毕，生成上班时间任务前</div>
          <div>上班结束：高效组上班安排结束时</div>
          <div>任务结束：单个任务结束时</div>
        </help-text>
      </label>
      <n-select v-model:value="backup_plans[sub_plan].trigger_timing" :options="triggerTimingOptions"
        placeholder="Select Trigger Timing" class="dropdown-select">
      </n-select>
    </div>

    <n-scrollbar style="max-height: 80vh;margin-top : 5px;">
      <n-scrollbar x-scrollable>
        <trigger-editor :data="backup_plans[sub_plan].trigger" @update="update_trigger" />
      </n-scrollbar>
      <n-card style="margin-top: 8px" content-style="padding: 8px" embedded>
        <n-code :code="JSON.stringify(backup_plans[sub_plan].trigger, null, 2)" language="json" word-wrap />
      </n-card>
    </n-scrollbar>
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