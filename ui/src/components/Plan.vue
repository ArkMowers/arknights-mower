<script setup>
import { storeToRefs } from 'pinia'
import { usePlanStore } from '@/stores/plan'
import { ref, computed, nextTick, watch } from 'vue'

const plan_store = usePlanStore()
const { operators, plan } = storeToRefs(plan_store)
const { facility_operator_limit } = plan_store

const facility_types = [
  { label: '贸易站', value: '贸易站' },
  { label: '制造站', value: '制造站' },
  { label: '发电站', value: '发电站' }
]

const facility = ref('')

const button_type = {
  贸易站: 'info',
  制造站: 'warning',
  发电站: 'primary'
}

const operator_limit = computed(() => {
  if (facility.value.startsWith('room') && plan.value[facility.value].name == '发电站') {
    return 1
  }
  return facility_operator_limit[facility.value] || 0
})

function clear() {
  plan.value[facility.value].name = ''
  nextTick(() => {
    const plans = []
    for (let i = 0; i < operator_limit.value; ++i) {
      plans.push({
        agent: '',
        group: '',
        replacement: []
      })
    }
    plan.value[facility.value].plans = plans
  })
}

watch(
  () => {
    if (facility.value.startsWith('room')) {
      return plan.value[facility.value].name
    }
    return ''
  },
  (new_name, old_name) => {
    if (new_name == '发电站') {
      const plans = plan.value[facility.value].plans
      while (plans.length > operator_limit.value) {
        plans.pop()
      }
    } else if (old_name == '发电站') {
      const plans = plan.value[facility.value].plans
      while (plans.length < operator_limit.value) {
        plans.push({ agent: '', group: '', replacement: [] })
      }
    }
  }
)

const operators_with_free = computed(() => {
  return [
    { value: '', label: '' },
    { value: 'Free', label: 'Free' }
  ].concat(operators.value)
})

const right_side_facility_name = computed(() => {
  if (facility.value.startsWith('dormitory')) {
    return '宿舍'
  } else if (facility.value == 'central') {
    return '控制中枢'
  } else if (facility.value == 'contact') {
    return '办公室'
  } else if (facility.value == 'meeting') {
    return '会客室'
  } else if (facility.value == 'factory') {
    return '加工站'
  } else {
    return '未知'
  }
})

const facility_empty = computed(() => {
  let empty = true
  for (const i of plan.value[facility.value].plans) {
    if (i.agent) {
      empty = false
      break
    }
  }
  return empty
})
</script>

<template>
  <div class="plan-container">
    <n-space justify="center">
      <table>
        <tr>
          <td></td>
          <td></td>
          <td></td>
          <td>
            <n-button :secondary="facility != 'central'" class="w90" @click="facility = 'central'"
              >控制中枢</n-button
            >
          </td>
          <td>
            <n-button :secondary="facility != 'meeting'" @click="facility = 'meeting'"
              >会客室</n-button
            >
          </td>
        </tr>
        <tr>
          <td v-for="r in ['room_1_1', 'room_1_2', 'room_1_3']" :key="r">
            <n-button
              :dashed="facility != r"
              :ghost="facility == r"
              :type="facility == r ? 'primary' : ''"
              v-if="!plan[r].name"
              @click="facility = r"
            >
              待建造
            </n-button>
            <n-button
              :secondary="facility != r"
              :ghost="facility == r"
              :type="button_type[plan[r].name]"
              v-else
              @click="facility = r"
            >
              {{ plan[r].name }}
            </n-button>
          </td>
          <td>
            <n-button
              :secondary="facility != 'dormitory_1'"
              class="w90"
              @click="facility = 'dormitory_1'"
              >宿舍</n-button
            >
          </td>
          <td>
            <n-button :secondary="facility != 'factory'" @click="facility = 'factory'"
              >加工站</n-button
            >
          </td>
        </tr>
        <tr>
          <td v-for="r in ['room_2_1', 'room_2_2', 'room_2_3']" :key="r">
            <n-button
              :dashed="facility != r"
              :ghost="facility == r"
              :type="facility == r ? 'primary' : ''"
              v-if="!plan[r].name"
              @click="facility = r"
            >
              待建造
            </n-button>
            <n-button
              :secondary="facility != r"
              :ghost="facility == r"
              :type="button_type[plan[r].name]"
              v-else
              @click="facility = r"
            >
              {{ plan[r].name }}
            </n-button>
          </td>
          <td>
            <n-button
              :secondary="facility != 'dormitory_2'"
              class="w90"
              @click="facility = 'dormitory_2'"
              >宿舍</n-button
            >
          </td>
          <td>
            <n-button :secondary="facility != 'contact'" @click="facility = 'contact'"
              >办公室</n-button
            >
          </td>
        </tr>
        <tr>
          <td v-for="r in ['room_3_1', 'room_3_2', 'room_3_3']" :key="r">
            <n-button
              :dashed="facility != r"
              :ghost="facility == r"
              :type="facility == r ? 'primary' : ''"
              v-if="!plan[r].name"
              @click="facility = r"
            >
              待建造
            </n-button>
            <n-button
              :secondary="facility != r"
              :ghost="facility == r"
              :type="button_type[plan[r].name]"
              v-else
              @click="facility = r"
            >
              {{ plan[r].name }}
            </n-button>
          </td>
          <td>
            <n-button
              :secondary="facility != 'dormitory_3'"
              class="w90"
              @click="facility = 'dormitory_3'"
              >宿舍</n-button
            >
          </td>
          <td>
            <n-button disabled>训练室</n-button>
          </td>
        </tr>
        <tr>
          <td></td>
          <td></td>
          <td></td>
          <td>
            <n-button
              :secondary="facility != 'dormitory_4'"
              class="w90"
              @click="facility = 'dormitory_4'"
              >宿舍</n-button
            >
          </td>
          <td></td>
        </tr>
      </table>
    </n-space>
    <n-divider />
    <n-space justify="center" v-if="facility">
      <table>
        <tr>
          <td>设施类别：</td>
          <td>
            <n-select
              v-model:value="plan[facility].name"
              :options="facility_types"
              class="type-select"
              v-if="facility.startsWith('room')"
            />
            <span v-else class="type-select">{{ right_side_facility_name }}</span>
          </td>
          <td>
            <n-button ghost type="error" @click="clear" :disabled="facility_empty">
              清空此设施内干员
            </n-button>
          </td>
        </tr>
      </table>
    </n-space>
    <n-space justify="center">
      <table>
        <tr v-for="i in operator_limit" :key="i">
          <td class="select-label">干员：</td>
          <td class="table-space">
            <n-select
              filterable
              tag
              :options="operators_with_free"
              class="operator-select"
              v-model:value="plan[facility].plans[i - 1].agent"
            />
          </td>
          <td class="select-label">组：</td>
          <td class="table-space group">
            <n-input v-model:value="plan[facility].plans[i - 1].group"></n-input>
          </td>
          <td class="select-label">替换：</td>
          <td>
            <n-select
              multiple
              filterable
              tag
              :options="operators_with_free"
              class="replacement-select"
              v-model:value="plan[facility].plans[i - 1].replacement"
            />
          </td>
        </tr>
      </table>
    </n-space>
  </div>
</template>

<style scoped>
.w90 {
  width: 90px;
}

.select-label {
  width: 44px;
}

.type-select {
  width: 100px;
  margin-right: 80px;
}

.operator-select {
  width: 150px;
}

.replacement-select {
  min-width: 400px;
}

.plan-container {
  min-width: 850px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.group {
  width: 120px;
}
</style>
