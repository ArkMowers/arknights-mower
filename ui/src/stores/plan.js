import { defineStore } from 'pinia'
import { ref } from 'vue'
import axios from 'axios'

export const usePlanStore = defineStore('plan', () => {
  const ling_xi = ref(1)
  const max_resting_count = ref('')
  const exhaust_require = ref('')
  const rest_in_full = ref('')
  const resting_priority = ref('')

  const plan = ref({})

  const operators = ref([])

  const left_side_facility = []

  const facility_operator_limit = { central: 5, meeting: 2, factory: 1, contact: 1 }
  for (let i = 1; i <= 3; ++i) {
    for (let j = 1; j <= 3; ++j) {
      const facility_name = `room_${i}_${j}`
      facility_operator_limit[facility_name] = 3
      left_side_facility.push({ label: facility_name, value: facility_name })
    }
  }
  for (let i = 0; i <= 4; ++i) {
    facility_operator_limit[`dormitory_${i}`] = 5
  }

  async function load_plan() {
    const response = await axios.get(`${import.meta.env.VITE_HTTP_URL}/plan`)
    ling_xi.value = response.data.conf.ling_xi.toString()
    max_resting_count.value = response.data.conf.max_resting_count.toString()
    exhaust_require.value =
      response.data.conf.exhaust_require == '' ? [] : response.data.conf.exhaust_require.split(',')
    rest_in_full.value =
      response.data.conf.rest_in_full == '' ? [] : response.data.conf.rest_in_full.split(',')
    resting_priority.value =
      response.data.conf.resting_priority == ''
        ? []
        : response.data.conf.resting_priority.split(',')

    const full_plan = response.data.plan1
    for (const i in facility_operator_limit) {
      let count = 0
      if (!full_plan[i]) {
        count = facility_operator_limit[i]
        full_plan[i] = { name: '', plans: [] }
      } else if (full_plan[i].plans.length < facility_operator_limit[i]) {
        count = facility_operator_limit[i] - full_plan[i].plans.length
      }
      for (let j = 0; j < count; ++j) {
        full_plan[i].plans.push({ agent: '', group: '', replacement: [] })
      }
    }
    plan.value = full_plan
  }

  async function load_operators() {
    const response = await axios.get(`${import.meta.env.VITE_HTTP_URL}/operator`)
    const option_list = [
      {
        value: 'Free',
        label: 'Free'
      }
    ]
    for (const i of response.data) {
      option_list.push({
        value: i,
        label: i
      })
    }
    operators.value = option_list
  }

  return {
    load_plan,
    load_operators,
    ling_xi,
    max_resting_count,
    exhaust_require,
    rest_in_full,
    resting_priority,
    plan,
    operators,
    facility_operator_limit,
    left_side_facility
  }
})
