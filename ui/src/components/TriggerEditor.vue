<script setup>
import { i18n } from '@/i18n'
import { localizedPlanOptions } from '@/i18n/plans'
const { t } = i18n.global
const props = defineProps(['data'])
const emit = defineEmits(['update'])
import { computed, ref, watch } from 'vue'
import {
  maintenance_expression,
  maintenance_duration_expression,
  maintenance_duration_options as raw_duration_options,
  maintenance_trigger,
  parse_maintenance_expression,
  parse_maintenance_trigger
} from '@/utils/trigger_maintenance'
import {
  expression_type,
  function_options as raw_function_options,
  new_expression
} from '@/utils/trigger_function'
const function_options = computed(() => localizedPlanOptions(raw_function_options))
const maintenance_duration_options = computed(() => localizedPlanOptions(raw_duration_options))
const left = ref(props.data.left)
const operator = ref(props.data.operator)
const right = ref(props.data.right)
const function_name = ref(props.data.function)
let next_argument_id = 0
const args = ref((props.data.args || []).map((value) => ({ id: next_argument_id++, value })))
const maintenance_hours = computed(() =>
  parse_maintenance_trigger({ left: left.value, operator: operator.value, right: right.value })
)
const maintenance_duration = computed(() => parse_maintenance_expression(left.value))
const duration_hours = ref(maintenance_duration.value?.hours ?? 6)

function update_duration_operator(operator) {
  left.value = maintenance_duration_expression(operator, duration_hours.value)
}

function update_duration_hours(hours) {
  if (hours === null) return
  duration_hours.value = hours
  left.value = maintenance_duration_expression(maintenance_duration.value.operator, hours)
}

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
  const result = function_name.value
    ? { function: function_name.value, args: args.value.map((arg) => arg.value) }
    : { left: left.value, operator: operator.value, right: right.value }
  emit('update', result)
}

watch(
  [left, operator, right, function_name, args],
  () => {
    generate()
  },
  { deep: true }
)

function create_argument() {
  return { id: next_argument_id++, value: '' }
}

function add_argument() {
  args.value.push(create_argument())
}

function update_function(name) {
  function_name.value = name
  if (name === 'abs') args.value = args.value.slice(0, 1)
  if (!args.value.length) add_argument()
}

const le_options = computed(() => [
  { label: t('plans.expression'), value: 'expression' },
  { label: t('plans.value'), value: 'string' },
  { label: t('plans.function'), value: 'function' }
])

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
  <div class="trigger-editor">
    <n-table size="small" :single-line="false">
      <template v-if="function_name">
        <tr>
          <th>{{ t('plans.function') }}</th>
          <td>
            <n-select
              :value="function_name"
              :aria-label="t('plans.functionName')"
              style="width: 220px"
              :options="function_options"
              :consistent-menu-width="false"
              @update:value="update_function"
            />
          </td>
        </tr>
        <tr>
          <td colspan="2">
            <n-dynamic-input
              v-model:value="args"
              key-field="id"
              :min="1"
              :max="function_name === 'abs' ? 1 : undefined"
              :on-create="create_argument"
            >
              <template #default="{ value: arg, index }">
                <n-flex align="center" :wrap="false" :size="6" class="argument-row">
                  <n-flex align="center" :wrap="false" :size="6" class="argument-label">
                    <n-select
                      :value="expression_type(arg.value)"
                      :aria-label="t('plans.argumentType', { number: index + 1 })"
                      :options="le_options"
                      :consistent-menu-width="false"
                      @update:value="(type) => (arg.value = new_expression(type))"
                    />
                  </n-flex>
                  <n-flex align="center" :wrap="false" :size="6" class="argument-value">
                    <trigger-editor
                      v-if="typeof arg.value === 'object'"
                      :data="arg.value"
                      :key="expression_type(arg.value)"
                      @update="(value) => (arg.value = value)"
                    />
                    <trigger-string
                      v-else
                      :data="arg.value"
                      @update="(value) => (arg.value = value)"
                    />
                  </n-flex>
                </n-flex>
              </template>
              <template #action="{ index, remove }">
                <n-button
                  v-if="function_name !== 'abs' && index === 0"
                  class="argument-action"
                  :aria-label="t('plans.addArgument')"
                  :title="t('plans.addArgument')"
                  @click="add_argument"
                  >+</n-button
                >
                <n-button
                  v-else-if="function_name !== 'abs'"
                  class="argument-action"
                  :aria-label="t('plans.removeArgumentNumber', { number: index + 1 })"
                  :title="t('plans.removeArgument')"
                  @click="remove(index)"
                  >−</n-button
                >
              </template>
            </n-dynamic-input>
          </td>
        </tr>
      </template>
      <tr v-else-if="maintenance_hours !== null">
        <th>{{ t('plans.timedCondition') }}</th>
        <td>
          <n-flex class="label" align="center" :wrap="false" :size="6">
            <trigger-string :data="left" @update="update_left" />
            <mower-input-number
              :value="maintenance_hours"
              :min="0"
              :step="0.5"
              :aria-label="t('plans.maintenanceLeadHours')"
              style="width: 140px"
              @update:value="update_maintenance_hours"
            />
            <span style="white-space: nowrap">{{ t('plans.activateWithinHours') }}</span>
            <span style="white-space: nowrap">{{ t('plans.downtime') }}</span>
            <n-select
              :value="maintenance_duration.operator"
              :options="maintenance_duration_options"
              :aria-label="t('plans.downtimeOperator')"
              :consistent-menu-width="false"
              style="width: 90px"
              @update:value="update_duration_operator"
            />
            <template v-if="maintenance_duration.operator">
              <mower-input-number
                :value="duration_hours"
                :min="0"
                :step="0.5"
                :aria-label="t('plans.downtimeHours')"
                style="width: 120px"
                @update:value="update_duration_hours"
              />
              <span style="white-space: nowrap">{{ t('plans.hours') }}</span>
            </template>
          </n-flex>
        </td>
      </tr>
      <template v-else>
        <tr>
          <th>
            <n-flex class="label" align="center" :wrap="false" :size="6"
              >{{ t('plans.left')
              }}<n-select
                :value="expression_type(left)"
                :aria-label="t('plans.leftType')"
                :on-update:value="
                  (v) => {
                    left = new_expression(v)
                  }
                "
                :options="le_options"
                :consistent-menu-width="false"
              />
            </n-flex>
          </th>
          <td>
            <trigger-editor
              v-if="typeof left == 'object'"
              :data="left"
              :key="expression_type(left)"
              @update="(d) => (left = d)"
            />
            <n-flex class="label" v-else align="center" :wrap="false" :size="6">
              <trigger-string :data="left" @update="update_left" />
            </n-flex>
          </td>
        </tr>
        <tr>
          <th>{{ t('plans.operator') }}</th>
          <td>
            <n-auto-complete
              v-model:value="operator"
              style="width: 160px"
              :options="operator_tips"
              blur-after-select
              :get-show="() => true"
            />
          </td>
        </tr>
        <tr>
          <th>
            <n-flex class="label" align="center" :wrap="false" :size="6"
              >{{ t('plans.right')
              }}<n-select
                :value="expression_type(right)"
                :aria-label="t('plans.rightType')"
                :on-update:value="
                  (v) => {
                    right = new_expression(v)
                  }
                "
                :options="le_options"
                :consistent-menu-width="false"
              />
            </n-flex>
          </th>
          <td>
            <trigger-editor
              v-if="typeof right == 'object'"
              :key="expression_type(right)"
              :data="right"
              @update="(d) => (right = d)"
            />
            <n-flex class="label" v-else align="center" :wrap="false" :size="6">
              <trigger-string :data="right" @update="update_right" />
            </n-flex>
          </td>
        </tr>
      </template>
    </n-table>
  </div>
</template>

<style scoped lang="scss">
.trigger-editor {
  width: 100%;
  min-width: 0;
  overflow-x: auto;
}

.n-table {
  width: auto;

  th {
    width: 164px;
    box-sizing: border-box;
  }
}

.argument-row,
.argument-value {
  flex: 1;
  min-width: 0;
}

td > .label > *,
.argument-value > :not(.trigger-editor) {
  flex: 0 0 auto;
  width: auto;
}

.argument-label {
  width: 132px;
  flex-shrink: 0;
  white-space: nowrap;
}
.argument-action {
  width: 30px;
  padding: 0 9px;
}
</style>
