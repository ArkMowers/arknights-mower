<script setup>
import { inject, watch } from 'vue'
const show = inject('show_trigger_editor')

import { storeToRefs } from 'pinia'
import { usePlanStore } from '@/stores/plan'
import { usedepotStore } from '@/stores/depot'
import { useFacilityStore } from '@/stores/facility'

const plan_store = usePlanStore()
const { sub_plan, backup_plans } = storeToRefs(plan_store)
const depot_store = usedepotStore()
const facility_store = useFacilityStore()

watch(show, (visible) => {
  if (visible) {
    depot_store.loadInventory(true).catch(() => {})
    facility_store.load(true).catch(() => {})
  }
})

const triggerTimingOptions = [
  { label: '下班结束', value: 'BEFORE_PLANNING' },
  { label: '上班结束', value: 'AFTER_PLANNING' }
]

function update_trigger(data) {
  backup_plans.value[sub_plan.value].trigger = data
}
</script>

<template>
  <n-modal
    v-model:show="show"
    preset="card"
    title="触发条件"
    :auto-focus="false"
    transform-origin="center"
    style="width: auto; max-width: 90vw"
  >
    <div class="dropdown-container">
      <label class="dropdown-label"
        >最早切表阶段
        <help-text>
          <div>该选项表示最早允许切表的阶段。</div>
          <div>下班结束：适合需要在上班前切换产物或订单的副表。</div>
          <div>上班结束：等本轮换班完成后再允许切表。</div>
          <div>后续检查点仍会复查，条件未变化时不会重复切换。</div>
        </help-text>
      </label>
      <n-select
        v-model:value="backup_plans[sub_plan].trigger_timing"
        :options="triggerTimingOptions"
        placeholder="Select Trigger Timing"
        class="dropdown-select"
      >
      </n-select>
    </div>

    <n-scrollbar style="max-height: 80vh; margin-top: 5px">
      <n-scrollbar x-scrollable>
        <trigger-editor :data="backup_plans[sub_plan].trigger" @update="update_trigger" />
      </n-scrollbar>
      <n-card style="margin-top: 8px" content-style="padding: 8px" embedded>
        <n-code
          :code="JSON.stringify(backup_plans[sub_plan].trigger, null, 2)"
          language="json"
          word-wrap
        />
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
