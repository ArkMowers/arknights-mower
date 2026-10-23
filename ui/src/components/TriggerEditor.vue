<script setup>
const props = defineProps(['data'])
const emit = defineEmits(['update'])
import { computed, ref, watch } from 'vue'
import {
  maintenance_expression,
  maintenance_trigger,
  parse_maintenance_trigger
} from '@/utils/trigger_maintenance'
import {
  expression_type,
  function_options,
  minimum_arguments,
  new_expression
} from '@/utils/trigger_function'
const left = ref(props.data.left)
const operator = ref(props.data.operator)
const right = ref(props.data.right)
const function_name = ref(props.data.function)
let next_argument_id = 0
const args = ref((props.data.args || []).map((value) => ({ id: next_argument_id++, value })))
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

function add_argument() {
  args.value.push({ id: next_argument_id++, value: '' })
}

function update_function(name) {
  function_name.value = name
  if (name === 'abs') args.value = args.value.slice(0, 1)
  while (args.value.length < minimum_arguments(name)) add_argument()
}

const le_options = [
  { label: '表达式', value: 'expression' },
  { label: '值', value: 'string' },
  { label: '函数', value: 'function' }
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
  <div class="trigger-editor">
    <n-table size="small" :single-line="false">
      <template v-if="function_name">
        <tr>
          <th>函数</th>
          <td>
            <n-select
              :value="function_name"
              aria-label="函数名称"
              style="width: 220px"
              :options="function_options"
              :consistent-menu-width="false"
              @update:value="update_function"
            />
          </td>
        </tr>
        <tr v-for="(arg, index) in args" :key="arg.id">
          <th>
            <div class="label">
              <span class="argument-label">第 {{ index + 1 }} 项</span>
              <n-select
                :value="expression_type(arg.value)"
                :aria-label="`第 ${index + 1} 项类型`"
                :options="le_options"
                :consistent-menu-width="false"
                @update:value="(type) => (arg.value = new_expression(type))"
              />
            </div>
          </th>
          <td>
            <div class="argument">
              <div class="argument-value">
                <trigger-editor
                  v-if="typeof arg.value === 'object'"
                  :data="arg.value"
                  :key="expression_type(arg.value)"
                  @update="(value) => (arg.value = value)"
                />
                <trigger-string v-else :data="arg.value" @update="(value) => (arg.value = value)" />
              </div>
              <n-button
                v-if="function_name !== 'abs'"
                quaternary
                size="small"
                :disabled="args.length <= minimum_arguments(function_name)"
                :aria-label="`删除第 ${index + 1} 项`"
                @click="args.splice(index, 1)"
                >−</n-button
              >
            </div>
          </td>
        </tr>
        <tr v-if="function_name !== 'abs'">
          <td colspan="2">
            <n-button block quaternary aria-label="新增项" @click="add_argument">+</n-button>
          </td>
        </tr>
      </template>
      <tr v-else-if="maintenance_hours !== null">
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
                :value="expression_type(left)"
                aria-label="左侧类型"
                :on-update:value="
                  (v) => {
                    left = new_expression(v)
                  }
                "
                :options="le_options"
                :consistent-menu-width="false"
              />
            </div>
          </th>
          <td>
            <trigger-editor
              v-if="typeof left == 'object'"
              :data="left"
              :key="expression_type(left)"
              @update="(d) => (left = d)"
            />
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
              style="width: 160px"
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
                :value="expression_type(right)"
                aria-label="右侧类型"
                :on-update:value="
                  (v) => {
                    right = new_expression(v)
                  }
                "
                :options="le_options"
                :consistent-menu-width="false"
              />
            </div>
          </th>
          <td>
            <trigger-editor
              v-if="typeof right == 'object'"
              :key="expression_type(right)"
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

.label {
  display: flex;
  flex-direction: row;
  align-items: center;
  gap: 6px;
}

.argument {
  display: flex;
  align-items: center;
  gap: 6px;
}

.argument-value {
  display: flex;
  align-items: center;
  gap: 6px;
  flex: 1;
  min-width: 0;
}

td > .label > *,
.argument-value > :not(.trigger-editor) {
  flex: 0 0 auto;
  width: auto;
}

.argument-label {
  white-space: nowrap;
}
</style>
