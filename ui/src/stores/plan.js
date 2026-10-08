import { planBindings, planReplacements } from '@/utils/plan_bindings'
import { OPERATOR_CONF_FIELDS } from '@/utils/plan_edit'
import { defineStore } from 'pinia'
import { ref, watchEffect, computed, inject } from 'vue'
import axios from 'axios'
import { deepcopy } from '@/utils/deepcopy'
import { factory_product_ids } from '@/utils/base_products'

const createPlanStore = (id, endpoint, rescue = false) =>
  defineStore(id, () => {
    const initialized = ref(false)
    let advancedSettingsSource = null
    function set_advanced_settings_source(source) {
      advancedSettingsSource = source
    }
    const ling_xi = ref(1)
    const mood_limits = ref(null)
    const operator_mood_limits = ref({})
    const exhaust_require = ref([])
    const rest_in_full = ref([])
    const ope_resting_priority = ref([])
    const default_dorm_order = ['dormitory_1', 'dormitory_2', 'dormitory_3', 'dormitory_4']
    const dorm_order = ref([...default_dorm_order])
    const resting_priority = ref([])
    const resting_priority_replacement = ref([])
    const free_room_exclusions = ref([])
    const resting_standby = ref([])
    const workaholic = ref([])
    const rescue_free_blacklist = ref([])
    const refresh_trading = ref([])
    const refresh_drained = ref([])

    const plan = ref({})

    const backup_plans = ref([])

    const operators = ref([])

    const left_side_facility = []

    const facility_operator_limit = {
      central: 5,
      meeting: 2,
      factory: 1,
      contact: 1,
      train: 2,
      recycle: 2
    }
    for (let i = 1; i <= 3; ++i) {
      for (let j = 1; j <= 3; ++j) {
        const facility_name = `room_${i}_${j}`
        const display_name = `B${i}0${j}`
        facility_operator_limit[facility_name] = 3
        left_side_facility.push({ label: display_name, value: facility_name })
      }
    }
    for (let i = 1; i <= 4; ++i) {
      facility_operator_limit[`dormitory_${i}`] = 5
    }
    for (let i = 1; i <= 3; ++i) {
      facility_operator_limit[`gaming_${i}`] = 1
    }

    function list2str(data) {
      return data.join(',')
    }

    function str2list(data) {
      return data && data != '' ? data.split(',') : []
    }

    function normalizeDormOrder(data) {
      const result = []
      for (const value of str2list(data)) {
        const match = value.match(/^(dormitory_[1-4])(?:_(low|\d+))?$/)
        const option = match && (match[2] === 'low' ? `${match[1]}_low` : match[1])
        if (option && !result.includes(option)) result.push(option)
      }
      return result.concat(default_dorm_order.filter((room) => !result.includes(room)))
    }

    function normalizeBackupDormOrder(conf) {
      const raw = conf.dorm_order
      const normalized = raw ? normalizeDormOrder(raw) : []
      const hasOverride =
        Object.prototype.hasOwnProperty.call(conf, 'dorm_order_override') &&
        conf.dorm_order_override != null
      const override = hasOverride
        ? Boolean(conf.dorm_order_override)
        : normalized.length > 0 && normalized.join(',') !== default_dorm_order.join(',')
      conf.dorm_order_override = override
      return override ? normalized : []
    }

    const backup_conf_convert_list = [...OPERATOR_CONF_FIELDS, 'dorm_order']

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
          } else if (full_plan[i].name == '贸易站') {
            if (!['lmd', 'orundum'].includes(full_plan[i].product)) {
              full_plan[i].product = 'lmd'
            }
          } else if (full_plan[i].name == '制造站') {
            if (!factory_product_ids.includes(full_plan[i].product)) {
              full_plan[i].product = 'gold'
            }
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
      if (['贸易站', '制造站'].includes(input.name)) {
        result.product = input.product
      }
      for (const i of input.plans) {
        if (i.agent) {
          result.plans.push(i)
        }
      }
      return result
    }

    function strip_plan(plan, backup = false) {
      const plan1 = {}

      for (const i in facility_operator_limit) {
        if (rescue && i.startsWith('dormitory')) {
          if (!backup || plan[i].plans.some((slot) => slot.agent)) {
            plan1[i] = {
              name: plan[i].name,
              plans: plan[i].plans.map((slot) => ({
                agent: slot.agent || (backup ? 'Current' : 'Free'),
                group: '',
                replacement: slot.replacement || []
              }))
            }
          }
          continue
        }
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
      const response = await axios.get(`${import.meta.env.VITE_HTTP_URL}/${endpoint}`)
      ling_xi.value = response.data.conf.ling_xi
      mood_limits.value = response.data.conf.mood_limits ?? null
      operator_mood_limits.value = response.data.conf.operator_mood_limits ?? {}
      exhaust_require.value = str2list(response.data.conf.exhaust_require)
      rest_in_full.value = str2list(response.data.conf.rest_in_full)
      ope_resting_priority.value = str2list(response.data.conf.ope_resting_priority)
      dorm_order.value =
        rescue && !response.data.conf.dorm_order
          ? []
          : normalizeDormOrder(response.data.conf.dorm_order)
      resting_priority.value = str2list(response.data.conf.resting_priority)
      resting_priority_replacement.value = str2list(response.data.conf.resting_priority_replacement)
      free_room_exclusions.value = str2list(response.data.conf.free_room_exclusions)
      resting_standby.value = str2list(response.data.conf.resting_standby)
      workaholic.value = str2list(response.data.conf.workaholic)
      rescue_free_blacklist.value = str2list(response.data.conf.free_blacklist)
      refresh_trading.value = str2list(response.data.conf.refresh_trading)
      refresh_drained.value = str2list(response.data.conf.refresh_drained)
      const gamings = ['gaming_1', 'gaming_2', 'gaming_3']
      for (const key of gamings) {
        if (!response.data.plan1[key]) {
          response.data.plan1[key] = { plans: [] }
        }
      }
      for (const key of gamings) {
        for (const b of response.data.backup_plans) {
          if (!b.conf[key]) {
            b.conf[key] = { plans: [] }
          }
        }
      }
      plan.value = fill_empty(response.data.plan1)

      backup_plans.value = response.data.backup_plans ?? []
      for (let b of backup_plans.value) {
        b.conf.mood_limits ??= null
        b.conf.operator_mood_limits ??= {}
        b.conf.removed_operators = Object.fromEntries(
          OPERATOR_CONF_FIELDS.map((field) => [field, str2list(b.conf.removed_operators?.[field])])
        )
        delete b.trigger_timing
        delete b.exit_trigger_timing
        for (const i of backup_conf_convert_list) {
          b.conf[i] = i === 'dorm_order' ? normalizeBackupDormOrder(b.conf) : str2list(b.conf[i])
        }
        b.plan = fill_empty(b.plan)
      }
      initialized.value = true
    }

    async function import_main_plan() {
      const { data } = await axios.get(`${import.meta.env.VITE_HTTP_URL}/plan`)
      plan.value = fill_empty(deepcopy(data.plan1))
      sub_plan.value = 'main'
    }

    function clear_rescue_bindings() {
      if (!rescue) return
      const runners = new Set(['但书', '龙舌兰', '佩佩', '可露希尔'])
      const fia_positions = new Set()
      for (const roster of [plan.value, ...backup_plans.value.map((backup) => backup.plan)]) {
        for (const [room, facility] of Object.entries(roster)) {
          for (const [index, slot] of facility.plans.entries()) {
            const replacements = planReplacements(slot)
            slot.group = ''
            delete slot.group_bindings
            const position = `${room}:${index}`
            if (slot.agent === '菲亚梅塔') fia_positions.add(position)
            if (
              slot.agent === '菲亚梅塔' ||
              (slot.agent === 'Current' && fia_positions.has(position))
            )
              continue
            slot.replacement = replacements.filter((name) => runners.has(name))
          }
        }
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
          mood_limits: deepcopy(mood_limits.value),
          operator_mood_limits: deepcopy(operator_mood_limits.value),
          exhaust_require: list2str(exhaust_require.value),
          rest_in_full: list2str(rest_in_full.value),
          ope_resting_priority: list2str(ope_resting_priority.value),
          dorm_order: list2str(dorm_order.value),
          resting_priority: list2str(resting_priority.value),
          resting_priority_replacement: list2str(resting_priority_replacement.value),
          free_room_exclusions: list2str(free_room_exclusions.value),
          resting_standby: list2str(resting_standby.value),
          workaholic: list2str(workaholic.value),
          ...(rescue ? { free_blacklist: list2str(rescue_free_blacklist.value) } : {}),
          refresh_trading: list2str(refresh_trading.value),
          refresh_drained: list2str(refresh_drained.value)
        },
        backup_plans: deepcopy(backup_plans.value)
      }
      if (!rescue && advancedSettingsSource) result.advanced_settings = advancedSettingsSource()
      for (const b of result.backup_plans) {
        b.conf.removed_operators = Object.fromEntries(
          OPERATOR_CONF_FIELDS.map((field) => [
            field,
            list2str(b.conf.removed_operators?.[field] ?? [])
          ]).filter(([, names]) => names)
        )
        delete b.trigger_timing
        delete b.exit_trigger_timing
        for (const i of backup_conf_convert_list) {
          b.conf[i] = list2str(b.conf[i])
        }
        b.plan = strip_plan(b.plan, true)
      }

      return result
    }

    const loaded = inject('loaded')
    const autosave_paused = ref(false)
    let planSaveRequest = Promise.resolve()

    function save_plan() {
      const payload = JSON.parse(JSON.stringify(build_plan()))
      planSaveRequest = planSaveRequest
        .catch(() => {})
        .then(() => axios.post(`${import.meta.env.VITE_HTTP_URL}/${endpoint}`, payload))
      return planSaveRequest
    }

    watchEffect(() => {
      if ((rescue ? initialized.value : loaded.value) && !autosave_paused.value) {
        save_plan().catch((error) => console.error('排班保存失败', error))
      }
    })

    const groups = computed(() => {
      const result = []
      for (const facility in current_plan.value) {
        for (const p of current_plan.value[facility].plans) {
          for (const binding of planBindings(p)) {
            if (binding.group) result.push(binding.group)
          }
        }
      }
      return [...new Set(result)]
    })

    const group_colors = computed(() => {
      const names = new Set()
      for (const table of [plan.value, ...backup_plans.value.map((backup) => backup.plan)]) {
        for (const room of Object.values(table)) {
          for (const slot of room.plans) {
            for (const binding of planBindings(slot)) {
              if (binding.group) names.add(binding.group)
            }
          }
        }
      }
      return Object.fromEntries([
        ['', 'transparent'],
        ...[...names].map((name, index) => [name, `hsl(${(360 / names.size) * index}, 80%, 45%)`])
      ])
    })

    const sub_plan = ref('main')
    const current_plan = computed(() => {
      if (sub_plan.value == 'main') {
        return plan.value
      } else {
        return backup_plans.value[sub_plan.value].plan
      }
    })

    function import_main_facility(facility) {
      if (sub_plan.value === 'main' || !plan.value[facility]) return
      current_plan.value[facility] = deepcopy(plan.value[facility])
    }

    return {
      import_main_facility,
      autosave_paused,
      wait_for_plan_save: () => planSaveRequest,
      save_plan,
      set_advanced_settings_source,
      load_plan,
      import_main_plan,
      clear_rescue_bindings,
      load_operators,
      ling_xi,
      mood_limits,
      operator_mood_limits,
      exhaust_require,
      rest_in_full,
      resting_priority,
      resting_priority_replacement,
      free_room_exclusions,
      resting_standby,
      ope_resting_priority,
      workaholic,
      rescue_free_blacklist,
      refresh_trading,
      refresh_drained,
      dorm_order,
      plan,
      operators,
      facility_operator_limit,
      left_side_facility,
      build_plan,
      groups,
      group_colors,
      backup_plans,
      sub_plan,
      current_plan,
      fill_empty
    }
  })

export const usePlanStore = createPlanStore('plan', 'plan')
export const useRescuePlanStore = createPlanStore('rescuePlan', 'rescue-plan', true)
