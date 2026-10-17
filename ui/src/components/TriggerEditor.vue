<script setup>
const props = defineProps(['data'])
const emit = defineEmits(['update'])
import { computed, ref, watch } from 'vue'
import {
  maintenance_expression,
  maintenance_trigger,
  parse_maintenance_trigger
} from '@/utils/trigger_maintenance'
const left = ref(props.data.left)
const operator = ref(props.data.operator)
const right = ref(props.data.right)
const maintenance_hours = computed(() =>
  parse_maintenance_trigger({ left: left.value, operator: operator.value, right: right.value })
)

function update_left(value) {
  left.value = value
  if (value === maintenance_expression) {
    const trigger = maintenance_trigger()
    operator.value = trigger.operator
    right.value = trigger.right
  }
}

function update_maintenance_hours(hours) {
  if (hours !== null) right.value = String(hours)
}

function update_right(value) {
  if (value === maintenance_expression) update_left(value)
  else right.value = value
}

function generate() {
  const result = { left: left.value, operator: operator.value, right: right.value }
  emit('update', result)
}

watch([left, operator, right], () => {
  generate()
})

const le_options = [
  { label: '表达式', value: 'expression' },
  { label: '值', value: 'string' }
]

const operator_tips = [
  'and',
  'or',
  '==',
  '!=',
  '>',
  '<',
  '>=',
  '<=',
  '+',
  '-',
  '*',
  '/',
  '//',
  '%',
  '**'
]
</script>

<template>
  <n-table size="small" :single-line="false">
    <tr v-if="maintenance_hours !== null">
      <th>定时条件</th>
      <td>
        <div class="label">
          <trigger-string :data="left" @update="update_left" />
          <n-input-number
            :value="maintenance_hours"
            :min="0"
            :step="0.5"
            aria-label="停服大更新提前小时数"
            style="width: 140px"
            @update:value="update_maintenance_hours"
          />
          <span style="white-space: nowrap">小时内生效</span>
        </div>
      </td>
    </tr>
    <template v-else>
      <tr>
        <th>
          <div class="label">
            左
            <n-select
              :default-value="typeof left == 'object' ? 'expression' : 'string'"
              :on-update:value="
                (v) => {
                  left = v == 'string' ? '' : { left: '', operator: '', right: '' }
                }
              "
              :options="le_options"
            />
          </div>
        </th>
        <td>
          <trigger-editor v-if="typeof left == 'object'" :data="left" @update="(d) => (left = d)" />
          <div class="label" v-else>
            <trigger-string :data="left" @update="update_left" />
          </div>
        </td>
      </tr>
      <tr>
        <th>运算符</th>
        <td>
          <n-auto-complete
            v-model:value="operator"
            :options="operator_tips"
            blur-after-select
            :get-show="() => true"
          />
        </td>
      </tr>
      <tr>
        <th>
          <div class="label">
            右
            <n-select
              :default-value="typeof right == 'object' ? 'expression' : 'string'"
              :on-update:value="
                (v) => {
                  right = v == 'string' ? '' : { left: '', operator: '', right: '' }
                }
              "
              :options="le_options"
            />
          </div>
        </th>
        <td>
          <trigger-editor
            v-if="typeof right == 'object'"
            :data="right"
            @update="(d) => (right = d)"
          />
          <div class="label" v-else>
            <trigger-string :data="right" @update="update_right" />
          </div>
        </td>
      </tr>
    </template>
  </n-table>
</template>

<style scoped lang="scss">
.n-table {
  min-width: 100%;

  th {
    width: 124px;
    box-sizing: border-box;
  }
}

.label {
  display: flex;
  flex-direction: row;
  align-items: center;
  gap: 6px;
}
</style>
