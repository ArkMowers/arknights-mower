<script setup>
import { storeToRefs } from 'pinia'
import { usePlanStore } from '@/stores/plan'
import { ref, computed } from 'vue'

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
  const plans = []
  for (let i = 0; i < operator_limit.value; ++i) {
    plans.push({
      agent: '',
      group: '',
      replacement: []
    })
  }
  plan.value[facility.value].name = ''
  plan.value[facility.value].plans = plans
}
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
          <td></td>
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
            <n-button :secondary="facility != 'meeting'" @click="facility = 'meeting'"
              >会客室</n-button
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
            <n-button :secondary="facility != 'factory'" @click="facility = 'factory'"
              >加工室</n-button
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
            <n-button :secondary="facility != 'contact'" @click="facility = 'contact'"
              >办公室</n-button
            >
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
    <n-space justify="center" v-if="facility.startsWith('room')">
      <table>
        <tr>
          <td>设施类别：</td>
          <td>
            <n-select
              v-model:value="plan[facility].name"
              :options="facility_types"
              class="type-select"
            />
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
              :options="operators"
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
              :options="operators"
              class="replacement-select"
              v-model:value="plan[facility].plans[i - 1].replacement"
            />
          </td>
        </tr>
      </table>
    </n-space>
    <n-space justify="center" v-if="facility">
      <n-button type="primary">保存</n-button>
      <n-button type="error" @click="clear">清空</n-button>
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
