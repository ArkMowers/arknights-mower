import { defineStore } from 'pinia'
import { ref, watch } from 'vue'
import axios from 'axios'

export const useConfigStore = defineStore('config', () => {
  const adb = ref('')
  const drone_count_limit = ref(0)
  const drone_room = ref('')
  const enable_party = ref(true)
  const free_blacklist = ref([])
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
  const maa_mall_buy = ref('')
  const maa_mall_blacklist = ref('')
  const shop_list = ref([])
  const maa_gap = ref(false)
  const maa_recruitment_time = ref(false)
  const maa_recruit_only_4 = ref(false)
  const simulator = ref({ name: '', index: -1 })
  const resting_threshold = ref(0.5)
  const theme = ref('light')
  const tap_to_launch_game = ref(false)
  const exit_game_when_idle = ref(true)

  async function load_shop() {
    const response = await axios.get(`${import.meta.env.VITE_HTTP_URL}/shop`)
    const mall_list = []
    for (const i of response.data) {
      mall_list.push({
        value: i,
        label: i
      })
    }
    shop_list.value = mall_list
  }

  async function load_config() {
    const response = await axios.get(`${import.meta.env.VITE_HTTP_URL}/conf`)
    adb.value = response.data.adb
    drone_count_limit.value = response.data.drone_count_limit.toString()
    drone_room.value = response.data.drone_room
    enable_party.value = response.data.enable_party != 0
    free_blacklist.value =
      response.data.free_blacklist == '' ? [] : response.data.free_blacklist.split(',')
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
    reload_room.value = response.data.reload_room == '' ? [] : response.data.reload_room.split(',')
    run_mode.value = response.data.run_mode == 2 ? 'orders_only' : 'full'
    run_order_delay.value = response.data.run_order_delay.toString()
    start_automatically.value = response.data.start_automatically
    maa_mall_buy.value =
      response.data.maa_mall_buy == '' ? [] : response.data.maa_mall_buy.split(',')
    maa_mall_blacklist.value =
      response.data.maa_mall_blacklist == '' ? [] : response.data.maa_mall_blacklist.split(',')
    maa_gap.value = response.data.maa_gap
    maa_recruitment_time.value = response.data.maa_recruitment_time
    maa_recruit_only_4.value = response.data.maa_recruit_only_4
    simulator.value = response.data.simulator
    resting_threshold.value = response.data.resting_threshold
    theme.value = response.data.theme
    tap_to_launch_game.value = response.data.tap_to_launch_game
    tap_to_launch_game.value.enable = tap_to_launch_game.value.enable ? 'tap' : 'adb'
    exit_game_when_idle.value = response.data.exit_game_when_idle
  }

  function build_config() {
    return {
      account: account.value,
      adb: adb.value,
      drone_count_limit: parseInt(drone_count_limit.value),
      drone_room: drone_room.value,
      enable_party: enable_party.value ? 1 : 0,
      free_blacklist: free_blacklist.value.join(','),
      maa_adb_path: maa_adb_path.value,
      maa_enable: maa_enable.value ? 1 : 0,
      maa_path: maa_path.value,
      maa_rg_enable: maa_rg_enable.value ? 1 : 0,
      maa_weekly_plan: maa_weekly_plan.value,
      mail_enable: mail_enable.value ? 1 : 0,
      package_type: package_type.value == 'official' ? 1 : 0,
      pass_code: pass_code.value,
      planFile: plan_file.value,
      reload_room: reload_room.value.join(','),
      run_mode: run_mode.value == 'orders_only' ? 2 : 1,
      run_order_delay: parseInt(run_order_delay.value),
      start_automatically: start_automatically.value,
      maa_mall_buy: maa_mall_buy.value.join(','),
      maa_mall_blacklist: maa_mall_blacklist.value.join(','),
      maa_gap: maa_gap.value,
      maa_recruitment_time: maa_recruitment_time.value,
      maa_recruit_only_4: maa_recruit_only_4.value,
      simulator: simulator.value,
      theme: theme.value,
      resting_threshold: resting_threshold.value,
      tap_to_launch_game: {
        enable: tap_to_launch_game.value.enable == 'tap',
        x: tap_to_launch_game.value.x,
        y: tap_to_launch_game.value.y
      },
      exit_game_when_idle: exit_game_when_idle.value
    }
  }

  watch(
    [
      adb,
      drone_count_limit,
      drone_room,
      enable_party,
      free_blacklist,
      maa_adb_path,
      maa_enable,
      maa_path,
      maa_weekly_plan,
      maa_rg_enable,
      mail_enable,
      account,
      pass_code,
      package_type,
      reload_room,
      run_mode,
      run_order_delay,
      start_automatically,
      maa_mall_buy,
      maa_mall_blacklist,
      maa_gap,
      maa_recruitment_time,
      maa_recruit_only_4,
      simulator,
      resting_threshold,
      theme,
      tap_to_launch_game,
      exit_game_when_idle
    ],
    () => {
      axios.post(`${import.meta.env.VITE_HTTP_URL}/conf`, build_config())
    },
    { deep: true }
  )

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
    start_automatically,
    maa_mall_buy,
    maa_mall_blacklist,
    load_shop,
    shop_list,
    maa_gap,
    maa_recruitment_time,
    maa_recruit_only_4,
    build_config,
    simulator,
    resting_threshold,
    theme,
    tap_to_launch_game,
    exit_game_when_idle
  }
})
