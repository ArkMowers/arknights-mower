<script setup>
import { inject, ref, watch } from 'vue'
const show = inject('show_trigger_editor')
const edit_locked = inject('planEditLocked', ref(false))
watch(edit_locked, (locked) => {
  if (locked) show.value = false
})

import { storeToRefs } from 'pinia'
import { usePlanStore } from '@/stores/plan'
import { usedepotStore } from '@/stores/depot'
import { useFacilityStore } from '@/stores/facility'
import { useMasteryStore } from '@/stores/mastery'

const plan_store = inject('planStore', null) || usePlanStore()
const { sub_plan, backup_plans } = storeToRefs(plan_store)
const depot_store = usedepotStore()
const facility_store = useFacilityStore()
const mastery_store = useMasteryStore()

watch(show, (visible) => {
  if (visible) {
    depot_store.loadInventory(true).catch(() => {})
    facility_store.load(true).catch(() => {})
    mastery_store.loadPlanSummary(true).catch(() => {})
  }
})

function update_trigger(data) {
  if (edit_locked.value) return
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
