import { defineStore } from 'pinia'
import { ref } from 'vue'
import axios from 'axios'

export const useConfigStore = defineStore('config', () => {
  const adb = ref('')
  const drone_count_limit = ref(0)
  const drone_room = ref('')
  const enable_party = ref(true)
  const exhaust_require = ref('')
  const free_blacklist = ref('')
  const ling_xi = ref(1)
  const maa_adb_path = ref('')
  const maa_enable = ref(false)
  const maa_path = ref('')
  const maa_weekly_plan = ref([])
  const mail_enable = ref(false)
  const account = ref('')
  const pass_code = ref('')
  const max_resting_count = ref(0)
  const package_type = ref('official')
  const plan_file = ref('')
  const reload_room = ref('')
  const rest_in_full = ref('')
  const resting_priority = ref('')
  const run_mode = ref(1)
  const run_order_delay = ref(10)
  const start_automatically = ref(false)

  async function load_config() {
    const response = await axios.get('http://localhost:8000/load-conf')
    adb.value = response.data.adb
    drone_count_limit.value = response.data.drone_count_limit
    drone_room.value = response.data.drone_room
    enable_party.value = response.data.enable_party != 0
    exhaust_require.value = response.data.exhaust_require
    free_blacklist.value = response.data.free_blacklist
    ling_xi.value = response.data.ling_xi
    maa_adb_path.value = response.data.maa_adb_path
    maa_enable.value = response.data.maa_enable
    maa_path.value = response.data.maa_path
    maa_weekly_plan.value = response.data.maa_weekly_plan
    mail_enable.value = response.data.mail_enable != 0
    account.value = response.data.account
    pass_code.value = response.data.pass_code
    max_resting_count.value = response.data.max_resting_count
    package_type.value = response.data.package_type == 1 ? 'official' : 'bilibili'
    plan_file.value = response.data.planFile
    reload_room.value = response.data.reload_room
    rest_in_full.value = response.data.rest_in_full
    resting_priority.value = response.data.resting_priority
    run_mode.value = response.data.run_mode == 1 ? 'orders_only' : 'full'
    run_order_delay.value = response.data.run_order_delay
    start_automatically.value = response.data.start_automatically
  }

  return {
    adb,
    load_config,
    drone_count_limit,
    drone_room,
    enable_party,
    exhaust_require,
    free_blacklist,
    ling_xi,
    maa_adb_path,
    maa_enable,
    maa_path,
    maa_weekly_plan,
    mail_enable,
    account,
    pass_code,
    max_resting_count,
    package_type,
    plan_file,
    reload_room,
    rest_in_full,
    resting_priority,
    run_mode,
    run_order_delay,
    start_automatically
  }
})
