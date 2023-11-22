import { defineStore } from 'pinia'
import { ref, watchEffect, inject } from 'vue'
import axios from 'axios'

export const useConfigStore = defineStore('config', () => {
  const adb = ref('')
  const drone_count_limit = ref(0)
  const drone_room = ref('')
  const drone_interval = ref(4)
  const enable_party = ref(true)
  const free_blacklist = ref([])
  const maa_adb_path = ref('')
  const maa_enable = ref(false)
  const maa_path = ref('')
  const maa_expiring_medicine = ref(true)
  const maa_weekly_plan = ref([])
  const maa_weekly_plan1 = ref([])
  const maa_rg_enable = ref(0)
  const maa_long_task_type = ref('rogue')
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
  const simulator = ref({ name: '', index: -1 })
  const resting_threshold = ref(0.5)
  const theme = ref('light')
  const tap_to_launch_game = ref(false)
  const exit_game_when_idle = ref(true)
  const close_simulator_when_idle = ref(false)
  const maa_conn_preset = ref('General')
  const maa_touch_option = ref('maatouch')
  const maa_mall_ignore_blacklist_when_full = ref(false)
  const maa_rg_sleep_min = ref('00:00')
  const maa_rg_sleep_max = ref('00:00')
  const maa_credit_fight = ref(true)
  const maa_depot_enable = ref(false)
  const maa_rg_theme = ref('Mizuki')
  const rogue = ref({})
  const sss = ref({})
  const screenshot = ref(0)
  const mail_subject = ref('')
  const skland_enable = ref(false)
  const skland_info = ref([])
  const recruit_enable = ref(true)
  const recruitment_time = ref(false)
  const recruitment_permit = ref(30)
  const recruit_robot = ref(true)
  const run_order_grandet_mode = ref({})
  const server_push_enable = ref(false) // Server酱通知开关
  const sendKey = ref('') // Server酱Key值
  const check_mail_enable = ref(true)
  const report_enable = ref(true)
  const recruit_gap = ref(false)
  const recruit_auto_5=ref("hand")

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
    drone_count_limit.value = response.data.drone_count_limit
    drone_room.value = response.data.drone_room
    drone_interval.value = response.data.drone_interval
    enable_party.value = response.data.enable_party != 0
    free_blacklist.value =
      response.data.free_blacklist == '' ? [] : response.data.free_blacklist.split(',')
    maa_adb_path.value = response.data.maa_adb_path
    maa_enable.value = response.data.maa_enable != 0
    maa_path.value = response.data.maa_path
    maa_rg_enable.value = response.data.maa_rg_enable == 1
    maa_long_task_type.value = response.data.maa_long_task_type
    maa_expiring_medicine.value = response.data.maa_expiring_medicine
    maa_weekly_plan.value = response.data.maa_weekly_plan
    maa_weekly_plan1.value = response.data.maa_weekly_plan1
    mail_enable.value = response.data.mail_enable != 0
    account.value = response.data.account
    pass_code.value = response.data.pass_code
    package_type.value = response.data.package_type == 1 ? 'official' : 'bilibili'
    plan_file.value = response.data.planFile
    reload_room.value = response.data.reload_room == '' ? [] : response.data.reload_room.split(',')
    run_mode.value = response.data.run_mode == 2 ? 'orders_only' : 'full'
    run_order_delay.value = response.data.run_order_delay
    start_automatically.value = response.data.start_automatically
    maa_mall_buy.value =
      response.data.maa_mall_buy == '' ? [] : response.data.maa_mall_buy.split(',')
    maa_mall_blacklist.value =
      response.data.maa_mall_blacklist == '' ? [] : response.data.maa_mall_blacklist.split(',')
    maa_gap.value = response.data.maa_gap
    simulator.value = response.data.simulator
    resting_threshold.value = response.data.resting_threshold
    theme.value = response.data.theme
    tap_to_launch_game.value = response.data.tap_to_launch_game
    tap_to_launch_game.value.enable = tap_to_launch_game.value.enable ? 'tap' : 'adb'
    exit_game_when_idle.value = response.data.exit_game_when_idle
    close_simulator_when_idle.value = response.data.close_simulator_when_idle
    maa_conn_preset.value = response.data.maa_conn_preset
    maa_touch_option.value = response.data.maa_touch_option
    maa_mall_ignore_blacklist_when_full.value = response.data.maa_mall_ignore_blacklist_when_full
    maa_rg_sleep_max.value = response.data.maa_rg_sleep_max
    maa_rg_sleep_min.value = response.data.maa_rg_sleep_min
    maa_credit_fight.value = response.data.maa_credit_fight
    maa_depot_enable.value = response.data.maa_depot_enable
    maa_rg_theme.value = response.data.maa_rg_theme
    rogue.value = response.data.rogue
    sss.value = response.data.sss
    screenshot.value = response.data.screenshot
    mail_subject.value = response.data.mail_subject
    skland_enable.value = response.data.skland_enable != 0
    skland_info.value = response.data.skland_info
    recruit_enable.value = response.data.recruit_enable
    recruitment_time.value = response.data.recruitment_time
    recruitment_permit.value = response.data.recruitment_permit
    recruit_robot.value = response.data.recruit_robot
    run_order_grandet_mode.value = response.data.run_order_grandet_mode
    // 新增：加载Server酱的配置
    server_push_enable.value = response.data.server_push_enable != 0
    sendKey.value = response.data.sendKey
    check_mail_enable.value = response.data.check_mail_enable
    report_enable.value = response.data.report_enable
    recruit_gap.value = response.data.recruit_gap
    recruit_auto_5.value=response.data.recruit_auto_5
  }

  function build_config() {
    return {
      account: account.value,
      adb: adb.value,
      drone_count_limit: drone_count_limit.value,
      drone_room: drone_room.value,
      drone_interval: drone_interval.value,
      enable_party: enable_party.value ? 1 : 0,
      free_blacklist: free_blacklist.value.join(','),
      maa_adb_path: maa_adb_path.value,
      maa_enable: maa_enable.value ? 1 : 0,
      maa_path: maa_path.value,
      maa_rg_enable: maa_rg_enable.value ? 1 : 0,
      maa_long_task_type: maa_long_task_type.value,
      maa_expiring_medicine: maa_expiring_medicine.value,
      maa_weekly_plan: maa_weekly_plan.value,
      maa_weekly_plan1: maa_weekly_plan1.value,
      mail_enable: mail_enable.value ? 1 : 0,
      package_type: package_type.value == 'official' ? 1 : 0,
      pass_code: pass_code.value,
      planFile: plan_file.value,
      reload_room: reload_room.value.join(','),
      run_mode: run_mode.value == 'orders_only' ? 2 : 1,
      run_order_delay: run_order_delay.value,
      start_automatically: start_automatically.value,
      maa_mall_buy: maa_mall_buy.value.join(','),
      maa_mall_blacklist: maa_mall_blacklist.value.join(','),
      maa_gap: maa_gap.value,
      simulator: simulator.value,
      theme: theme.value,
      resting_threshold: resting_threshold.value,
      tap_to_launch_game: {
        enable: tap_to_launch_game.value.enable == 'tap',
        x: tap_to_launch_game.value.x,
        y: tap_to_launch_game.value.y
      },
      exit_game_when_idle: exit_game_when_idle.value,
      close_simulator_when_idle: close_simulator_when_idle.value,
      maa_conn_preset: maa_conn_preset.value,
      maa_touch_option: maa_touch_option.value,
      maa_mall_ignore_blacklist_when_full: maa_mall_ignore_blacklist_when_full.value,
      maa_rg_sleep_max: maa_rg_sleep_max.value,
      maa_rg_sleep_min: maa_rg_sleep_min.value,
      maa_credit_fight: maa_credit_fight.value,
      maa_depot_enable: maa_depot_enable.value,
      maa_rg_theme: maa_rg_theme.value,
      rogue: rogue.value,
      sss: sss.value,
      screenshot: screenshot.value,
      mail_subject: mail_subject.value,
      skland_enable: skland_enable.value,
      skland_info: skland_info.value,
      recruit_enable: recruit_enable.value,
      recruitment_time: recruitment_time.value,
      recruitment_permit: recruitment_permit.value,
      recruit_robot: recruit_robot.value,
      run_order_grandet_mode: run_order_grandet_mode.value,
      // 新增：Server酱的配置
      server_push_enable: server_push_enable.value ? 1 : 0,
      sendKey: sendKey.value,
      check_mail_enable: check_mail_enable.value,
      report_enable: report_enable.value,
      recruit_gap: recruit_gap.value,
      recruit_auto_5: recruit_auto_5.value
    }
  }

  const loaded = inject('loaded')

  watchEffect(() => {
    if (loaded.value) {
      axios.post(`${import.meta.env.VITE_HTTP_URL}/conf`, build_config())
    }
  })

  return {
    adb,
    load_config,
    drone_count_limit,
    drone_room,
    drone_interval,
    enable_party,
    free_blacklist,
    maa_adb_path,
    maa_enable,
    maa_path,
    maa_rg_enable,
    maa_long_task_type,
    maa_expiring_medicine,
    maa_weekly_plan,
    maa_weekly_plan1,
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
    build_config,
    simulator,
    resting_threshold,
    theme,
    tap_to_launch_game,
    exit_game_when_idle,
    close_simulator_when_idle,
    maa_conn_preset,
    maa_touch_option,
    maa_mall_ignore_blacklist_when_full,
    maa_rg_sleep_min,
    maa_rg_sleep_max,
    maa_credit_fight,
    maa_depot_enable,
    maa_rg_theme,
    rogue,
    sss,
    screenshot,
    mail_subject,
    recruit_enable,
    recruitment_time,
    recruitment_permit,
    recruit_robot,
    skland_enable,
    skland_info,
    run_order_grandet_mode,
    server_push_enable,
    sendKey,
    check_mail_enable,
    report_enable,
    recruit_gap,
    recruit_auto_5
  }
})
