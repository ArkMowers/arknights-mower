<script setup>
import { inject } from 'vue'
const show = inject('show_name_editor')

import { storeToRefs } from 'pinia'
import { usePlanStore } from '@/stores/plan'

const plan_store = usePlanStore()
const { sub_plan, backup_plans } = storeToRefs(plan_store)
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
