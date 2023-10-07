import { defineStore } from 'pinia'
import { ref, watch, computed } from 'vue'
import axios from 'axios'

export const usePlanStore = defineStore('plan', () => {
  const ling_xi = ref('1')
  const max_resting_count = ref([])
  const exhaust_require = ref([])
  const rest_in_full = ref([])
  const resting_priority = ref([])
  const workaholic = ref([])

  const plan = ref({})

  const backup_plans = ref([])

  const operators = ref([])

  const left_side_facility = []

  const facility_operator_limit = { central: 5, meeting: 2, factory: 1, contact: 1 }
  for (let i = 1; i <= 3; ++i) {
    for (let j = 1; j <= 3; ++j) {
      const facility_name = `room_${i}_${j}`
      const display_name = `B${i}0${j}`
      facility_operator_limit[facility_name] = 3
      left_side_facility.push({ label: display_name, value: facility_name })
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
    workaholic.value =
      response.data.conf.workaholic == '' ? [] : response.data.conf.workaholic.split(',')
    backup_plans.value = response.data.backup_plans ?? []

    const full_plan = response.data.plan1
    for (const i in facility_operator_limit) {
      let count = 0
      if (!full_plan[i]) {
        count = facility_operator_limit[i]
        full_plan[i] = { name: '', plans: [] }
      } else {
        let limit = facility_operator_limit[i]
        if (full_plan[i].name == '发电站') {
          limit = 1
        }
        if (full_plan[i].plans.length < limit) {
          count = limit - full_plan[i].plans.length
        }
      }
      for (let j = 0; j < count; ++j) {
        full_plan[i].plans.push({ agent: '', group: '', replacement: [] })
      }
    }
    plan.value = full_plan
  }

  async function load_operators() {
    const response = await axios.get(`${import.meta.env.VITE_HTTP_URL}/operator`)
    const option_list = []
    for (const i of response.data) {
      option_list.push({
        value: i,
        label: i
      })
    }
    operators.value = option_list
  }

  function remove_empty_agent(input) {
    const result = {
      name: input.name,
      plans: []
    }
    for (const i of input.plans) {
      if (i.agent) {
        result.plans.push(i)
      }
    }
    return result
  }

  function build_plan() {
    const result = {
      default: 'plan1',
      plan1: {},
      conf: {
        ling_xi: parseInt(ling_xi.value),
        max_resting_count: parseInt(max_resting_count.value),
        exhaust_require: exhaust_require.value.join(','),
        rest_in_full: rest_in_full.value.join(','),
        resting_priority: resting_priority.value.join(','),
        workaholic: workaholic.value.join(',')
      },
      backup_plans: backup_plans.value
    }

    const plan1 = result.plan1

    for (const i in facility_operator_limit) {
      if (i.startsWith('room') && plan.value[i].name) {
        plan1[i] = remove_empty_agent(plan.value[i])
      } else {
        let empty = true
        for (const j of plan.value[i].plans) {
          if (j.agent) {
            empty = false
            break
          }
        }
        if (!empty) {
          plan1[i] = remove_empty_agent(plan.value[i])
        }
      }
    }

    return result
  }

  watch(
    [
      plan,
      ling_xi,
      max_resting_count,
      exhaust_require,
      rest_in_full,
      resting_priority,
      workaholic,
      backup_plans
    ],
    () => {
      axios.post(`${import.meta.env.VITE_HTTP_URL}/plan`, build_plan())
    },
    { deep: true }
  )

  const groups = computed(() => {
    const result = []
    for (const facility in plan.value) {
      for (const p of plan.value[facility].plans) {
        if (p.group) {
          result.push(p.group)
        }
      }
    }
    return [...new Set(result)]
  })

  return {
    load_plan,
    load_operators,
    ling_xi,
    max_resting_count,
    exhaust_require,
    rest_in_full,
    resting_priority,
    workaholic,
    plan,
    operators,
    facility_operator_limit,
    left_side_facility,
    build_plan,
    groups
  }
})
