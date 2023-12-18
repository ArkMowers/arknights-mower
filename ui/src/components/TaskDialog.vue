<script setup>
import { inject, ref, watch, computed, h } from 'vue'
const show = inject('show_task')

import { storeToRefs } from 'pinia'
import { usePlanStore } from '@/stores/plan'

const plan_store = usePlanStore()
const { sub_plan, backup_plans, operators } = storeToRefs(plan_store)

const task_list = ref([])

function update_tasks() {
  if (sub_plan.value != 'main') {
    const result = []
    Object.entries(backup_plans.value[sub_plan.value].task).forEach(([room, operators]) => {
      result.push({ room, operators })
    })
    task_list.value = result
  }
}

function new_task() {
  return {
    room: 'room_',
    operators: []
  }
}

watch(
  task_list,
  () => {
    const result = {}
    for (const i of task_list.value) {
      result[i.room] = i.operators
    }
    backup_plans.value[sub_plan.value].task = result
  },
  { deep: true }
)

watch(show, (new_value) => {
  if (new_value) {
    update_tasks()
  }
})

const operators_with_free_current = computed(() => {
  return [
    { value: 'Current', label: 'Current' },
    { value: 'Free', label: 'Free' }
  ].concat(operators.value)
})

import { match } from 'pinyin-pro'
import { render_op_label } from '@/utils/op_select'
</script>

<template>
  <n-modal
    v-model:show="show"
    preset="card"
    title="任务"
    transform-origin="center"
    style="width: 900px"
  >
    <n-scrollbar style="max-height: 80vh">
      <n-dynamic-input v-model:value="task_list" :on-create="new_task">
        <template #create-button-default>添加任务</template>
        <template #default="{ value }">
          <div class="task_row">
            <n-input v-model:value="value.room" />
            <n-dynamic-tags v-model:value="value.operators" :max="5" size="large">
              <template #input="{ submit, deactivate }">
                <n-select
                  v-model:value="value.operators"
                  filterable
                  :options="operators_with_free_current"
                  :on-update:value="
                    (v) => {
                      submit(v)
                    }
                  "
                  :on-blur="deactivate"
                  :filter="(p, o) => match(o.label, p)"
                  :render-label="render_op_label"
                />
              </template>
            </n-dynamic-tags>
          </div>
        </template>
      </n-dynamic-input>
      <n-card style="margin-top: 8px" content-style="padding: 8px" embedded>
        <n-code
          :code="JSON.stringify(backup_plans[sub_plan].task, null, 2)"
          language="json"
          word-wrap
        />
      </n-card>
    </n-scrollbar>
  </n-modal>
</template>

<style scoped lang="scss">
.task_row {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;

  .n-input {
    width: 140px;
  }
}

.n-dynamic-tags {
  align-items: center;
}
</style>
