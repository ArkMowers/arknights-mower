import { defineStore } from 'pinia'
import { ref } from 'vue'
import axios from 'axios'

export const useConfigStore = defineStore('config', () => {
  const adb = ref('')
  const drone_count_limit = ref(0)
  const drone_room = ref('')
  const enable_party = ref(true)
  const free_blacklist = ref('')
  const maa_adb_path = ref('')
  const maa_enable = ref(false)
  const maa_path = ref('')
  const maa_weekly_plan = ref([])
  const maa_rg_enable = ref(0)
  const mail_enable = ref(false)
  const account = ref('')
  const pass_code = ref('')
  const package_type = ref('official')
  const plan_file = ref('')
  const reload_room = ref('')
  const run_mode = ref(1)
  const run_order_delay = ref(10)
  const start_automatically = ref(false)

  async function load_config() {
    const response = await axios.get(`${import.meta.env.VITE_HTTP_URL}/conf`)
    adb.value = response.data.adb
    drone_count_limit.value = response.data.drone_count_limit.toString()
    drone_room.value = response.data.drone_room
    enable_party.value = response.data.enable_party != 0
    free_blacklist.value = response.data.free_blacklist == '' ? [] : response.data.free_blacklist
    maa_adb_path.value = response.data.maa_adb_path
    maa_enable.value = response.data.maa_enable != 0
    maa_path.value = response.data.maa_path
    maa_rg_enable.value = response.data.maa_rg_enable
    maa_weekly_plan.value = response.data.maa_weekly_plan
    mail_enable.value = response.data.mail_enable != 0
    account.value = response.data.account
    pass_code.value = response.data.pass_code
    package_type.value = response.data.package_type == 1 ? 'official' : 'bilibili'
    plan_file.value = response.data.planFile
    reload_room.value = response.data.reload_room
    run_mode.value = response.data.run_mode == 2 ? 'orders_only' : 'full'
    run_order_delay.value = response.data.run_order_delay.toString()
    start_automatically.value = response.data.start_automatically
  }

  return {
    adb,
    load_config,
    drone_count_limit,
    drone_room,
    enable_party,
    free_blacklist,
    maa_adb_path,
    maa_enable,
    maa_path,
    maa_rg_enable,
    maa_weekly_plan,
    mail_enable,
    account,
    pass_code,
    package_type,
    plan_file,
    reload_room,
    run_mode,
    run_order_delay,
    start_automatically
  }
})
