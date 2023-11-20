import { defineStore } from 'pinia'
import { ref, watchEffect, computed, inject } from 'vue'
import axios from 'axios'
import { deepcopy } from '@/utils/deepcopy'
import { useDebounceFn } from '@vueuse/core'

export const usePlanStore = defineStore('plan', () => {
  const ling_xi = ref(1)
  const max_resting_count = ref([])
  const exhaust_require = ref([])
  const rest_in_full = ref([])
  const resting_priority = ref([])
  const workaholic = ref([])
  const refresh_trading = ref([])

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

  function list2str(data) {
    return data.join(',')
  }

  function str2list(data) {
    return data && data != '' ? data.split(',') : []
  }

  const backup_conf_convert_list = [
    'exhaust_require',
    'rest_in_full',
    'resting_priority',
    'workaholic',
    'free_blacklist',
    'refresh_trading'
  ]

  function fill_empty(full_plan) {
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
    return full_plan
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

  function strip_plan(plan) {
    const plan1 = {}

    for (const i in facility_operator_limit) {
      if (i.startsWith('room') && plan[i].name) {
        plan1[i] = remove_empty_agent(plan[i])
      } else {
        let empty = true
        for (const j of plan[i].plans) {
          if (j.agent) {
            empty = false
            break
          }
        }
        if (!empty) {
          plan1[i] = remove_empty_agent(plan[i])
        }
      }
    }

    return plan1
  }

  async function load_plan() {
    const response = await axios.get(`${import.meta.env.VITE_HTTP_URL}/plan`)
    ling_xi.value = response.data.conf.ling_xi
    max_resting_count.value = response.data.conf.max_resting_count
    exhaust_require.value = str2list(response.data.conf.exhaust_require)
    rest_in_full.value = str2list(response.data.conf.rest_in_full)
    resting_priority.value = str2list(response.data.conf.resting_priority)
    workaholic.value = str2list(response.data.conf.workaholic)
    refresh_trading.value = str2list(response.data.conf.refresh_trading)

    plan.value = fill_empty(response.data.plan1)

    backup_plans.value = response.data.backup_plans ?? []
    for (let b of backup_plans.value) {
      for (const i of backup_conf_convert_list) {
        b.conf[i] = str2list(b.conf[i])
      }
      b.plan = fill_empty(b.plan)
    }
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

  function build_plan() {
    const result = {
      default: 'plan1',
      plan1: strip_plan(plan.value),
      conf: {
        ling_xi: ling_xi.value,
        max_resting_count: max_resting_count.value,
        exhaust_require: list2str(exhaust_require.value),
        rest_in_full: list2str(rest_in_full.value),
        resting_priority: list2str(resting_priority.value),
        workaholic: list2str(workaholic.value),
        refresh_trading: list2str(refresh_trading.value)
      },
      backup_plans: deepcopy(backup_plans.value)
    }
    for (const b of result.backup_plans) {
      for (const i of backup_conf_convert_list) {
        b.conf[i] = list2str(b.conf[i])
      }
      b.plan = strip_plan(b.plan)
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

  const loaded = inject('loaded')

  const debounce_post = useDebounceFn((new_plan) => {
    axios.post(`${import.meta.env.VITE_HTTP_URL}/plan`, new_plan)
  }, 1000)

  watchEffect(() => {
    if (loaded.value) {
      const new_plan = build_plan()
      debounce_post(new_plan)
    }
  })

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

  const sub_plan = ref('main')
  const current_plan = computed(() => {
    if (sub_plan.value == 'main') {
      return plan.value
    } else {
      return backup_plans.value[sub_plan.value].plan
    }
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
    refresh_trading,
    plan,
    operators,
    facility_operator_limit,
    left_side_facility,
    build_plan,
    groups,
    backup_plans,
    sub_plan,
    current_plan,
    fill_empty
  }
})
