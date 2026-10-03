<script setup lang="jsx">
import { useConfigStore } from '@/stores/config'
import { usePlanStore } from '@/stores/plan'
import { storeToRefs } from 'pinia'
import { computed, inject, onMounted, onUnmounted, ref } from 'vue'

import DeviceSettings from '@/components/DeviceSettings.vue'
import ChatBotSetting from '../components/ChatBotSetting.vue'
import SoftwareUpdate from '../components/SoftwareUpdate.vue'
import NetworkSettings from '../components/NetworkSettings.vue'
import ConfigBackup from '../components/ConfigBackup.vue'
import WorkshopManualSettings from '../components/WorkshopManualSettings.vue'

defineOptions({ name: 'MowerSettings' })

const config_store = useConfigStore()
const plan_store = usePlanStore()

const mobile = inject('mobile')

const {
  run_order_delay,
  performance_mode,
  performance_effective_mode,
  selection_poll_interval,
  selection_transition_timeout,
  drone_room,
  swap_contact_train,
  automatic_rescue_enable,
  start_automatically,
  package_type,
  simulator,
  theme,
  tap_to_launch_game,
  exit_game_when_idle,
  return_home_when_idle,
  close_simulator_when_idle,
  screenshot,
  screenshot_archive_limit_mb,
  screenshot_interval,
  run_order_grandet_mode,
  webview,
  runtime_platform,
  fix_mumu12_adb_disconnect,
  maa_gap,
  waiting_scene,
  enable_party,
  leifeng_mode,
  item_list,
  workshop_manual_settings,
  workshop_preset_warning
} = storeToRefs(config_store)

const archive_limit_gib = computed({
  get: () => screenshot_archive_limit_mb.value / 1024,
  set: (value) => {
    if (Number.isFinite(value))
      screenshot_archive_limit_mb.value = Math.max(0, Math.round(value * 1024))
  }
})

const performance_mode_options = computed(() => [
  { label: '自动', value: 'auto' },
  ...(runtime_platform.value === 'android' ? [] : [{ label: '极高', value: 'xhigh' }]),
  ...(runtime_platform.value === 'android' ? [] : [{ label: '高', value: 'high' }]),
  { label: '中', value: 'medium' },
  { label: '低', value: 'low' }
])
const performance_effective_label = computed(
  () =>
    ({ xhigh: '极高性能', high: '高性能', medium: '中性能', low: '低性能' })[
      performance_effective_mode.value
    ] || performance_effective_mode.value
)

function apply_performance_mode(mode) {
  if (runtime_platform.value === 'android' && ['xhigh', 'high'].includes(mode)) mode = 'medium'
  performance_mode.value = mode
}

const hide_macos_menu_bar = computed({
  get: () => !webview.value.tray,
  set: (hidden) => (webview.value.tray = !hidden)
})

const { operators } = storeToRefs(plan_store)

const { left_side_facility } = plan_store

const facility_with_empty = computed(() => {
  return [{ label: '（加速任意贸易站）', value: '' }].concat(left_side_facility)
})

const launch_options = [
  { label: '使用adb命令启动', value: 'adb' },
  { label: '点击屏幕启动', value: 'tap' },
  { label: '自定义命令启动', value: 'custom' }
]

const defaultLaunchCommand =
  'input keyevent KEYCODE_WAKEUP; wm dismiss-keyguard; am start -n {package}/{activity}'

function reset_launch_command() {
  tap_to_launch_game.value.command = defaultLaunchCommand
}

const scale_marks = {}
const display_marks = [0.5, 1.0, 1.5, 2.0, 3.0]
for (let i = 0.5; i <= 3.0; i += 0.25) {
  scale_marks[i] = display_marks.includes(i) ? `${i * 100}%` : ''
}

const new_scale = ref(webview.value.scale)

const desktopPreferencesReady = ref(false)
const desktopTrayEnabled = ref(true)
const desktopCloseMode = ref('ask')
const desktopLaunchMode = ref('last')
const desktopPreferenceBusy = ref(false)
const desktopPreferenceError = ref('')
const closeOptions = computed(() => [
  { label: '每次询问', value: 'ask' },
  ...(desktopTrayEnabled.value ? [{ label: '收起到托盘', value: 'tray' }] : []),
  { label: '彻底退出', value: 'exit' }
])
const launchOptions = [
  { label: '记住上次', value: 'last' },
  { label: '窗口', value: 'normal' },
  { label: '最大化', value: 'maximized' }
]

async function loadDesktopPreferences() {
  const api = window.pywebview?.api
  if (!api?.get_close_preference || !api?.get_window_launch_mode) return
  try {
    const [close, launch] = await Promise.all([
      api.get_close_preference(),
      api.get_window_launch_mode()
    ])
    desktopTrayEnabled.value = close.tray_enabled !== false
    desktopCloseMode.value = close.remember ? close.choice : 'ask'
    desktopLaunchMode.value = launch
    desktopPreferencesReady.value = true
    desktopPreferenceError.value = ''
  } catch (error) {
    desktopPreferenceError.value = error.message || '窗口设置读取失败'
  }
}

async function changeCloseMode(value) {
  const api = window.pywebview?.api
  if (!api?.set_close_preference || desktopPreferenceBusy.value) return
  desktopPreferenceBusy.value = true
  try {
    const choice = value === 'ask' ? (desktopTrayEnabled.value ? 'tray' : 'exit') : value
    const ok = await api.set_close_preference(choice, value !== 'ask')
    if (ok !== true) throw new Error('无法保存关闭设置')
    desktopCloseMode.value = value
    desktopPreferenceError.value = ''
  } catch (error) {
    desktopPreferenceError.value = error.message || '关闭设置保存失败'
  } finally {
    desktopPreferenceBusy.value = false
  }
}

async function changeLaunchMode(value) {
  const api = window.pywebview?.api
  if (!api?.set_window_launch_mode || desktopPreferenceBusy.value) return
  desktopPreferenceBusy.value = true
  try {
    const ok = await api.set_window_launch_mode(value)
    if (ok !== true) throw new Error('无法保存启动设置')
    desktopLaunchMode.value = value
    desktopPreferenceError.value = ''
  } catch (error) {
    desktopPreferenceError.value = error.message || '启动设置保存失败'
  } finally {
    desktopPreferenceBusy.value = false
  }
}

onMounted(() => {
  window.addEventListener('pywebviewready', loadDesktopPreferences)
  void loadDesktopPreferences()
})
onUnmounted(() => window.removeEventListener('pywebviewready', loadDesktopPreferences))

const scene_name = {
  CONNECTING: '正在提交反馈至神经',
  UNKNOWN: '未知',
  LOADING: '加载中',
  LOGIN_LOADING: '场景跳转时的等待界面',
  LOGIN_MAIN_NOENTRY: '登录页面（无按钮入口）',
  OPERATOR_ONGOING: '代理作战'
}

const idleAction = computed({
  get: () => {
    if (return_home_when_idle.value) return 'home'
    if (exit_game_when_idle.value) return 'exit'
    return close_simulator_when_idle.value ? 'close' : 'idle'
  },
  set: (value) => {
    return_home_when_idle.value = value === 'home'
    exit_game_when_idle.value = value === 'exit'
    close_simulator_when_idle.value = value === 'close'
  }
})
const networkSettings = ref(null)
const softwareUpdate = ref(null)

const simulatorLifecycleAllowed = computed(
  () => config_store.device_profile?.preset_id !== 'manual.physical'
)
const displayedIdleAction = computed({
  get: () =>
    !simulatorLifecycleAllowed.value && idleAction.value === 'close' ? 'idle' : idleAction.value,
  set: (value) => {
    idleAction.value = value
  }
})
const idleOptions = computed(() => [
  { label: '无操作', value: 'idle' },
  { label: '返回首页', value: 'home' },
  { label: '退出游戏', value: 'exit' },
  ...(simulatorLifecycleAllowed.value ? [{ label: '关闭模拟器', value: 'close' }] : [])
])
</script>

<template>
  <div class="grid-two">
    <div class="grid-left">
      <div>
        <n-card title="Mower设置">
          <n-form
            :label-placement="mobile ? 'top' : 'left'"
            :show-feedback="false"
            label-width="120"
            label-align="left"
          >
            <DeviceSettings v-if="runtime_platform !== 'android'" />
            <template v-else>
              <n-form-item label="服务器">
                <n-radio-group v-model:value="package_type">
                  <n-space>
                    <n-radio value="official">官服</n-radio>
                    <n-radio value="bilibili">Bilibili 服</n-radio>
                  </n-space>
                </n-radio-group>
              </n-form-item>
              <n-alert :show-icon="false">设备连接由 Android 应用管理。</n-alert>
            </template>
            <n-form-item label="启动游戏" v-if="runtime_platform !== 'android'">
              <n-select v-model:value="tap_to_launch_game.mode" :options="launch_options" />
            </n-form-item>
            <n-form-item
              v-if="runtime_platform !== 'android' && tap_to_launch_game.mode == 'tap'"
              label="点击坐标"
            >
              <span class="coord-label">X:</span>
              <mower-input-number v-model:value="tap_to_launch_game.x" />
              <span class="coord-label">Y:</span>
              <mower-input-number v-model:value="tap_to_launch_game.y" />
            </n-form-item>
            <n-form-item
              v-if="runtime_platform !== 'android' && tap_to_launch_game.mode == 'custom'"
            >
              <template #label>
                <span>启动命令</span>
                <help-text>
                  <div>
                    在 Android shell 中执行，支持 <code>{package}</code> 和 <code>{activity}</code>
                  </div>
                </help-text>
              </template>
              <n-input
                v-model:value="tap_to_launch_game.command"
                type="textarea"
                :autosize="true"
              />
              <n-button class="dialog-btn" @click="reset_launch_command">预设</n-button>
            </n-form-item>
            <n-form-item v-if="runtime_platform !== 'android'">
              <template #label>
                <span>任务结束后</span>
                <help-text>
                  <div>返回首页：降低功耗</div>
                  <div>退出游戏：降低功耗</div>
                  <div v-if="simulatorLifecycleAllowed">
                    关闭模拟器：减少空闲时的资源占用、避免模拟器长时间运行出现问题
                  </div>
                  <div
                    v-if="
                      ['macos.avd', 'linux.avd'].includes(config_store.device_profile?.preset_id)
                    "
                  >
                    AVD 仅关闭 mower 启动的目标，再次启动需要确认；普通退出 mower 不会关闭 AVD。
                  </div>
                </help-text>
              </template>

              <n-select v-model:value="displayedIdleAction" :options="idleOptions" />
            </n-form-item>
            <n-form-item
              :show-label="false"
              v-if="
                runtime_platform !== 'android' &&
                simulator.name == 'MuMu12' &&
                close_simulator_when_idle
              "
            >
              <n-checkbox v-model:checked="fix_mumu12_adb_disconnect">
                关闭MuMu模拟器12时结束adb进程
                <help-text>
                  <div>运行命令<code>taskkill /f /t /im adb.exe</code></div>
                  <div>使用MuMu模拟器12时，若遇到adb断连问题，可尝试开启此选项</div>
                </help-text>
              </n-checkbox>
            </n-form-item>
            <n-form-item :show-label="false">
              <n-checkbox v-model:checked="start_automatically">启动后自动开始任务</n-checkbox>
            </n-form-item>
            <n-form-item label="设备性能适配">
              <n-radio-group :value="performance_mode" @update:value="apply_performance_mode">
                <n-flex>
                  <n-radio
                    v-for="option in performance_mode_options"
                    :key="option.value"
                    :value="option.value"
                  >
                    {{ option.label }}
                  </n-radio>
                </n-flex>
              </n-radio-group>
              <help-text>
                自动档根据选人操作后的画面反馈和连续失败情况选择{{
                  runtime_platform === 'android' ? '中、低' : '高、中、低'
                }}档；所有平台默认自动。
                极高性能连续点击重排；高性能逐次确认重排点击；中性能等待稳定画面；低性能多确认一帧。时间参数独立设置，切换档位不会修改。当前自动判定：{{
                  performance_effective_label
                }}。
              </help-text>
            </n-form-item>
            <n-form-item label="截图最短间隔">
              <mower-input-number v-model:value="screenshot_interval" :precision="0">
                <template #suffix>毫秒</template>
              </mower-input-number>
            </n-form-item>
            <n-form-item label="选人采样间隔">
              <mower-input-number v-model:value="selection_poll_interval" :min="0.1" :max="2">
                <template #suffix>秒</template>
              </mower-input-number>
            </n-form-item>
            <n-form-item label="操作反馈超时">
              <mower-input-number v-model:value="selection_transition_timeout" :min="1" :max="20">
                <template #suffix>秒</template>
              </mower-input-number>
            </n-form-item>
            <n-form-item
              v-if="runtime_platform !== 'android'"
              :show-feedback="screenshot === 0 || (screenshot > 0 && screenshot < 5 / 60)"
            >
              <template #label>
                <span>截图保存时间</span>
                <help-text
                  >默认保留 1 小时，可填小数；大于 0 且不足 5 分钟时按 5 分钟保留。</help-text
                >
              </template>
              <mower-input-number v-model:value="screenshot" :min="0">
                <template #suffix>小时</template>
              </mower-input-number>
              <template v-if="screenshot === 0" #feedback>
                <span role="status">
                  日常截图不写盘。发生需归档的异常时，保存此前 5 分钟内缓存的全部画面及后续 5
                  分钟截图；内存缓存最多 16 张、32 MiB。
                </span>
              </template>
              <template v-else-if="screenshot > 0 && screenshot < 5 / 60" #feedback>
                <span role="status">截图会正常写盘，实际保存时间按 5 分钟处理。</span>
              </template>
            </n-form-item>
            <n-form-item label="报错归档空间上限">
              <template #label>
                <span>报错归档空间上限</span>
                <help-text>
                  默认 5 GiB。达到上限时优先清理较早的报错归档；设置为 0
                  表示不限容量。普通截图仍按保存时间清理。
                </help-text>
              </template>
              <mower-input-number v-model:value="archive_limit_gib" :min="0" :precision="2">
                <template #suffix>GiB</template>
              </mower-input-number>
            </n-form-item>
            <n-form-item label="等待时间">
              <n-table size="small" class="waiting-table">
                <thead>
                  <tr>
                    <th>场景</th>
                    <th>截图间隔</th>
                    <th>等待次数</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(value, key) in waiting_scene" :key="key">
                    <td>{{ scene_name[key] }}</td>
                    <td>
                      <mower-input-number
                        v-model:value="value[0]"
                        :show-button="false"
                        :precision="0"
                      >
                        <template #suffix>秒</template>
                      </mower-input-number>
                    </td>
                    <td>
                      <mower-input-number
                        v-model:value="value[1]"
                        :show-button="false"
                        :precision="0"
                      >
                        <template #suffix>次</template>
                      </mower-input-number>
                    </td>
                  </tr>
                </tbody>
              </n-table>
              <!-- {{ waiting_scene }} -->
            </n-form-item>
            <n-form-item label="界面缩放">
              <div class="desktop-scale-settings">
                <div class="desktop-scale-controls">
                  <n-slider
                    v-model:value="new_scale"
                    :step="0.25"
                    :min="0.5"
                    :max="3.0"
                    :marks="scale_marks"
                    :format-tooltip="(x) => `${x * 100}%`"
                  />
                  <n-button
                    class="scale-apply"
                    :disabled="new_scale == webview.scale"
                    @click="webview.scale = new_scale"
                  >
                    应用
                  </n-button>
                </div>
                <div v-if="desktopPreferencesReady" class="desktop-pref-inline">
                  <div class="desktop-pref-item">
                    <span>关闭窗口</span>
                    <n-select
                      :value="desktopCloseMode"
                      :options="closeOptions"
                      :disabled="desktopPreferenceBusy"
                      size="small"
                      @update:value="changeCloseMode"
                    />
                  </div>
                  <div class="desktop-pref-item">
                    <span>打开方式</span>
                    <n-select
                      :value="desktopLaunchMode"
                      :options="launchOptions"
                      :disabled="desktopPreferenceBusy"
                      size="small"
                      @update:value="changeLaunchMode"
                    />
                  </div>
                </div>
                <n-text v-if="desktopPreferenceError" type="error" depth="3">
                  {{ desktopPreferenceError }}
                </n-text>
              </div>
            </n-form-item>
            <n-form-item v-if="runtime_platform !== 'android'" :show-label="false">
              <n-checkbox
                v-if="runtime_platform === 'darwin'"
                v-model:checked="hide_macos_menu_bar"
              >
                隐藏菜单栏图标
                <help-text>
                  重启生效。独立启动时不创建托盘进程，关闭窗口后仍在后台运行。多开管理器统一提供托盘，静默重启后也保留托盘入口。
                </help-text>
              </n-checkbox>
              <n-checkbox v-else v-model:checked="webview.tray">
                使用托盘图标
                <help-text>重启生效。多开管理器启动的实例统一使用管理器托盘。</help-text>
              </n-checkbox>
            </n-form-item>
            <n-form-item label="显示主题" v-if="runtime_platform !== 'android'">
              <n-radio-group v-model:value="theme">
                <n-space>
                  <n-radio value="light">亮色</n-radio>
                  <n-radio value="dark">暗色</n-radio>
                </n-space>
              </n-radio-group>
            </n-form-item>
            <n-form-item>
              <template #label>
                <span>日常任务间隔</span>
                <help-text>
                  <div>可填小数</div>
                  <div>清理智、日常/周常任务领取、借助战打OF-1</div>
                </help-text>
              </template>
              <mower-input-number v-model:value="maa_gap">
                <template #suffix>小时</template>
              </mower-input-number>
            </n-form-item>
          </n-form>
        </n-card>
      </div>
      <div>
        <SKLand />
      </div>
      <div>
        <Depotswitch />
      </div>
      <div>
        <DailyMission />
      </div>
    </div>

    <div class="grid-right">
      <div>
        <n-card title="基建设置">
          <n-form
            :label-placement="mobile ? 'top' : 'left'"
            :show-feedback="false"
            label-width="140"
            label-align="left"
          >
            <n-form-item :show-label="false">
              <n-space align="center">
                <n-checkbox v-model:checked="automatic_rescue_enable" aria-label="自动救急">
                  自动救急
                  <help-text>
                    初始化时多组主班低于救急线且普通轮休无法安排休息，使用救急排班接管普通工作站。
                    恢复期间冻结正常副表，正常排班可接回周转后退出；设施类型或等级不一致时不启动。
                  </help-text>
                </n-checkbox>
                <router-link to="/rescue-plan-editor"><n-button>救急排班</n-button></router-link>
              </n-space>
            </n-form-item>
            <n-form-item :show-label="false">
              <n-checkbox v-model:checked="swap_contact_train"> 训练室在办公室上方 </n-checkbox>
            </n-form-item>
            <n-form-item>
              <n-flex>
                <n-checkbox v-model:checked="enable_party">
                  <div class="item">线索收集</div>
                </n-checkbox>
                <n-checkbox v-model:checked="leifeng_mode">
                  雷锋模式
                  <help-text>
                    <div>开启时，向好友赠送多余的线索；</div>
                    <div>关闭则超过9个线索才送好友。</div>
                  </help-text>
                </n-checkbox>
              </n-flex>
            </n-form-item>
            <n-alert v-if="runtime_platform === 'android'" :show-icon="false">
              Android
              默认使用自动性能适配。自动档依据选人操作的画面反馈和连续失败情况调节；各项时间参数可独立设置。
            </n-alert>
            <n-form-item>
              <template #label>
                <span>跑单前置延时</span>
                <help-text>
                  <div>推荐范围5-10</div>
                  <div>可填小数</div>
                </help-text>
              </template>
              <mower-input-number v-model:value="run_order_delay">
                <template #suffix>分钟</template>
              </mower-input-number>
            </n-form-item>
            <n-form-item :show-label="false">
              <n-checkbox v-model:checked="run_order_grandet_mode.enable">葛朗台跑单</n-checkbox>
            </n-form-item>
            <n-form-item>
              <template #label>
                <span>葛朗台缓冲时间</span>
                <help-text>推荐范围：15-30</help-text>
              </template>
              <mower-input-number
                v-model:value="run_order_grandet_mode.buffer_time"
                :disabled="!run_order_grandet_mode.enable"
              >
                <template #suffix>秒</template>
              </mower-input-number>
            </n-form-item>
            <n-form-item v-if="run_order_grandet_mode.enable" :show-label="false">
              <n-checkbox v-model:checked="run_order_grandet_mode.back_to_index">
                跑单前返回主界面以保持登录状态
              </n-checkbox>
            </n-form-item>
            <n-form-item>
              <template #label>
                <span>无人机使用房间</span>
                <help-text>
                  <div>加速制造站为指定制造站加速</div>
                  <div>（加速任意贸易站）只会加速有跑单人员作备班的站</div>
                  <div>例：没填龙舌兰但书的卖玉站 （加速任意贸易站） 不会被加速</div>
                  <div>如需要加速特定某个贸易站请指定对应房间</div>
                </help-text>
              </template>
              <n-select :options="facility_with_empty" v-model:value="drone_room" />
            </n-form-item>
            <WorkshopManualSettings
              v-model="workshop_manual_settings"
              :migration-warning="workshop_preset_warning"
              :operators="operators"
              :item_list="item_list"
            />
          </n-form>
        </n-card>
      </div>
      <div>
        <Recruit />
      </div>
      <div>
        <email />
      </div>
      <div>
        <ChatBotSetting />
      </div>
    </div>
    <div class="settings-network">
      <NetworkSettings ref="networkSettings" />
    </div>
    <div class="settings-updates">
      <div><SoftwareUpdate ref="softwareUpdate" /></div>
      <div><ResourceUpdate /></div>
    </div>
    <div class="settings-network">
      <ConfigBackup />
    </div>
    <div class="settings-network">
      <ProcessControl v-if="runtime_platform !== 'android'" />
    </div>
  </div>
</template>

<style scoped lang="scss">
.desktop-scale-settings {
  width: 100%;
  min-width: 0;
}

.desktop-scale-controls {
  display: flex;
  align-items: center;
  gap: 10px;

  .n-slider {
    flex: 1 1 200px;
    min-width: 110px;
  }
}

.desktop-pref-inline {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 16px;
  margin-top: 9px;
  padding: 9px 10px;
  border: 1px solid rgba(112, 153, 127, 0.25);
  border-radius: 6px;
}

.desktop-pref-item {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;

  .n-select {
    width: 128px;
  }
}

.settings-network {
  grid-column: 1 / -1;
  min-width: 0;
  margin-top: 10px;
}

.settings-updates {
  grid-column: 1 / -1;
  display: grid;
  gap: 10px;
  margin-top: 10px;

  > div {
    min-width: 0;
    max-width: 600px;
  }

  @container (min-width: 1180px) {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 5px;
  }

  @supports not (container-type: inline-size) {
    @media (min-width: 1400px) {
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 5px;
    }
  }
}

.mower-basic {
  width: 100%;

  td:nth-child(1) {
    width: 120px;
  }

  td:nth-child(3) {
    padding-left: 6px;
    width: 40px;
  }
}

.riic-conf {
  width: 100%;

  td {
    &:nth-child(1) {
      width: 130px;
    }

    &:nth-child(3) {
      padding-left: 12px;
      width: 120px;
    }
  }
}

.coord {
  td {
    width: 120px;

    &:nth-child(1),
    &:nth-child(3) {
      width: 30px;
    }

    &:nth-child(2) {
      padding-right: 30px;
    }
  }
}

.coord-label {
  width: 40px;
  padding-left: 8px;
}

p {
  margin: 0 0 8px 0;
}

h4 {
  margin: 12px 0 10px 0;
}

.time-table {
  width: 100%;
  margin-bottom: 12px;

  td:nth-child(1) {
    width: 40px;
  }
}

.scale {
  width: 60px;
  text-align: right;
}

.scale-apply {
  margin-left: 24px;
}

.waiting-table {
  width: 100%;
  max-width: 100%;

  th,
  td {
    padding: 4px;
    min-width: 50px;
    width: 80px;

    &:first-child {
      width: auto;
      padding: 4px 8px;
    }
  }
}
</style>

<style>
/* 默认单栏布局（窄屏或可用宽度不足） */
.grid-two {
  margin: 0 0 -10px 0;
  width: 100%;
  max-width: 600px;
}

.grid-left {
  display: grid;
  row-gap: 10px;
  grid-template-columns: 100%;
}

.grid-right {
  display: grid;
  row-gap: 10px;
  grid-template-columns: 100%;
  margin-top: 10px;
}

/* 容器查询：内容区可用宽度足够容纳双栏时（>= 1180px）智能双栏 */
@container (min-width: 1180px) {
  .grid-two {
    display: grid;
    grid-template-columns: minmax(0px, 1fr) minmax(0px, 1fr);
    align-items: flex-start;
    gap: 5px;
    max-width: 1210px;
    margin: 0;
  }

  .grid-left {
    display: grid;
    gap: 5px;
    grid-template-columns: 100%;
    max-width: 600px;
  }

  .grid-right {
    display: grid;
    gap: 5px;
    grid-template-columns: 100%;
    max-width: 600px;
    margin-top: 0;
  }
}

/* 不支持容器查询时的兜底 */
@supports not (container-type: inline-size) {
  @media (min-width: 1400px) {
    .grid-two {
      display: grid;
      grid-template-columns: minmax(0px, 1fr) minmax(0px, 1fr);
      align-items: flex-start;
      gap: 5px;
      max-width: 1210px;
      margin: 0;
    }

    .grid-left {
      display: grid;
      gap: 5px;
      grid-template-columns: 100%;
      max-width: 600px;
    }

    .grid-right {
      display: grid;
      gap: 5px;
      grid-template-columns: 100%;
      max-width: 600px;
      margin-top: 0;
    }
  }
}

.n-divider:not(.n-divider--vertical) {
  margin: 14px 0 8px;
}

/* .results {
  display: grid;
  grid-template-rows: masonry;
  grid-template-columns: repeat(2, 600px);
  gap: 10px 10px ;
  justify-content: center;
} */
/* 实验性瀑布流（firefox nightly） */
</style>
