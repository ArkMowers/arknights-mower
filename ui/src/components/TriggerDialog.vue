<script setup>
const props = defineProps(['trigger'])

import { inject } from 'vue'
const show = inject('show_trigger_editor')

import { storeToRefs } from 'pinia'
import { usePlanStore } from '@/stores/plan'

const plan_store = usePlanStore()
const { sub_plan, backup_plans } = storeToRefs(plan_store)

function update_trigger(data) {
  console.log(data)
  backup_plans.value[sub_plan.value].trigger = data
}
</script>

<template>
  <n-modal
    v-model:show="show"
    preset="card"
    title="触发条件"
    transform-origin="center"
    style="width: 900px"
  >
    <trigger-editor :data="props.trigger" @update="update_trigger" />
  </n-modal>
</template>
