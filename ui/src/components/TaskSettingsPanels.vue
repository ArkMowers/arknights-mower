<script setup>
import { useConfigStore } from '@/stores/config'
import { usePlanStore } from '@/stores/plan'
import { storeToRefs } from 'pinia'
import {
  computed,
  inject,
  nextTick,
  onActivated,
  onDeactivated,
  onMounted,
  onScopeDispose,
  ref,
  watch
} from 'vue'
import MowerSettings from '@/pages/Settings.vue'
import DeviceSettings from '@/components/DeviceSettings.vue'
import PerformanceSettings from '@/components/PerformanceSettings.vue'
import WorkshopManualSettings from '@/components/WorkshopManualSettings.vue'
import DailyMission from '@/components/DailyMission.vue'
import Recruit from '@/components/Recruit.vue'
import MaaReward from '@/components/MaaReward.vue'
import Clue from '@/components/Clue.vue'
import MaaWeekly from '@/components/MaaWeekly.vue'
import LongTasks from '@/components/LongTasks.vue'
import SKLand from '@/components/SKLand.vue'
import YituliuSyncSettings from '@/components/YituliuSyncSettings.vue'
import Depotswitch from '@/components/Depotswitch.vue'
import IncomeSettings from '@/components/IncomeSettings.vue'
import MaaBasic from '@/components/MaaBasic.vue'
import TrustSettings from '@/components/TrustSettings.vue'
import '@/styles/settings.css'

defineOptions({ name: 'TaskSettingsPanels' })
const props = defineProps({
  active: { type: String, default: '' }
})
const emit = defineEmits(['select', 'visible-editor'])
const root = ref(null)
let pageActive = true
let scrollParent
let scrollTarget
let viewportWindow
let resizeObserver
let scrollFrame

function directoryEditor(id) {
  return { daily: 'skland', credit: 'visit', idle: 'device' }[id] || id
}

function updateVisibleEditor() {
  scrollFrame = undefined
  if (!pageActive || !scrollParent) return
  const document = root.value.ownerDocument
  const documentScroll = scrollParent === document.scrollingElement
  const bounds = scrollParent.getBoundingClientRect()
  const scale = documentScroll ? 1 : bounds.height / scrollParent.offsetHeight || 1
  const top = documentScroll ? 0 : bounds.top + scrollParent.clientTop * scale
  const bottom =
    top + (documentScroll ? viewportWindow.innerHeight : scrollParent.clientHeight * scale)
  const toggle = root.value.closest('.task-workspace')?.querySelector('.checklist-mobile-toggle')
  const toggleBounds = toggle?.getBoundingClientRect()
  const contentTop =
    toggleBounds?.height && toggleBounds.top <= top + 1 ? Math.max(top, toggleBounds.bottom) : top
  const sections = Array.from(root.value.querySelectorAll('[data-task-editor]'))
    .map((element) => ({ element, bounds: element.getBoundingClientRect() }))
    .filter(({ bounds }) => bounds.height > 0)
  if (!sections.length) return
  const atBottom =
    scrollParent.scrollHeight > scrollParent.clientHeight + 1 &&
    scrollParent.scrollTop + scrollParent.clientHeight >= scrollParent.scrollHeight - 2
  let selected = sections[0]
  for (const section of sections) {
    const margin =
      Number.parseFloat(viewportWindow.getComputedStyle(section.element).scrollMarginTop) || 0
    if (section.bounds.top <= contentTop + margin * scale + 1) selected = section
  }
  if (atBottom && root.value.getBoundingClientRect().bottom <= bottom + 2)
    selected = sections.at(-1)
  const id = directoryEditor(selected.element.getAttribute('data-task-editor'))
  if (id && id !== props.active) emit('visible-editor', id)
}

function scheduleVisibleEditor() {
  if (!pageActive || scrollFrame !== undefined || !viewportWindow?.requestAnimationFrame) return
  scrollFrame = viewportWindow.requestAnimationFrame(updateVisibleEditor)
}

function disconnectScroll() {
  scrollTarget?.removeEventListener('scroll', scheduleVisibleEditor)
  viewportWindow?.removeEventListener('resize', scheduleVisibleEditor)
  if (scrollFrame !== undefined) viewportWindow?.cancelAnimationFrame(scrollFrame)
  scrollFrame = undefined
  resizeObserver?.disconnect()
  resizeObserver = undefined
  scrollParent = undefined
  scrollTarget = undefined
}

function connectScroll() {
  disconnectScroll()
  if (!pageActive || !root.value?.ownerDocument) return
  const document = root.value.ownerDocument
  viewportWindow = document.defaultView
  if (!viewportWindow) return
  for (let ancestor = root.value.parentElement; ancestor; ancestor = ancestor.parentElement) {
    if (/(auto|scroll|overlay)/.test(viewportWindow.getComputedStyle(ancestor).overflowY)) {
      scrollParent = ancestor
      break
    }
  }
  scrollParent ||= document.scrollingElement
  if (!scrollParent) return
  scrollTarget = scrollParent === document.scrollingElement ? viewportWindow : scrollParent
  scrollTarget.addEventListener('scroll', scheduleVisibleEditor, { passive: true })
  viewportWindow.addEventListener('resize', scheduleVisibleEditor, { passive: true })
  if (viewportWindow.ResizeObserver) {
    resizeObserver = new viewportWindow.ResizeObserver(scheduleVisibleEditor)
    resizeObserver.observe(root.value)
    resizeObserver.observe(scrollParent)
  }
  scheduleVisibleEditor()
}

onMounted(connectScroll)
onActivated(() => {
  pageActive = true
  nextTick(connectScroll)
})
function deactivate() {
  pageActive = false
  disconnectScroll()
}
onDeactivated(deactivate)
onScopeDispose(deactivate)

function targetElement(id) {
  if (!id) return null
  return Array.from(root.value?.querySelectorAll('[id]') ?? []).find((element) => element.id === id)
}

function resolveTarget(id) {
  const editor = targetElement(id)?.closest('[data-task-editor]')?.getAttribute('data-task-editor')
  return directoryEditor(editor)
}

function revealActive(target = '') {
  if (!pageActive) return
  const id = ['report', 'skland', 'mail'].includes(props.active)
    ? 'daily'
    : ['visit', 'credit-fight', 'shop'].includes(props.active)
      ? 'credit'
      : props.active
  const destination = targetElement(target)
  const panel =
    destination?.closest('[data-task-editor]') ||
    root.value?.querySelector(`[data-task-editor="${props.active}"]`) ||
    root.value?.querySelector(`[data-task-editor="${id}"]`)
  const scrollTarget = destination || panel
  scrollTarget?.scrollIntoView({ block: 'start', behavior: 'instant' })
  scheduleVisibleEditor()
}

defineExpose({ revealActive, resolveTarget })

const config_store = useConfigStore()
watch(
  () => config_store.manager_owned_device,
  () => nextTick(scheduleVisibleEditor),
  { flush: 'post' }
)
const plan_store = usePlanStore()
const mobile = inject('mobile', ref(false))
const {
  run_order_delay,
  selection_poll_interval,
  selection_transition_timeout,
  drone_room,
  drone_count_limit,
  drone_interval,
  automatic_rescue_enable,
  start_automatically,
  package_type,
  simulator,
  tap_to_launch_game,
  exit_game_when_idle,
  return_home_when_idle,
  close_simulator_when_idle,
  screenshot_interval,
  run_order_grandet_mode,
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
    if (close_simulator_when_idle.value) return 'close'
    if (exit_game_when_idle.value) return 'exit'
    return return_home_when_idle.value ? 'home' : 'idle'
  },
  set: (value) => {
    return_home_when_idle.value = value === 'home'
    exit_game_when_idle.value = value === 'exit'
    close_simulator_when_idle.value = value === 'close'
  }
})
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
  <div ref="root" class="task-settings-panels task-settings-panels--continuous">
    <section v-if="!config_store.manager_owned_device" id="task-devices" data-task-editor="device">
      <div class="settings-card-grid">
        <div class="settings-card-wide">
          <n-card title="设备连接与性能">
            <n-form
              :label-placement="mobile ? 'top' : 'left'"
              :show-feedback="false"
              label-width="158"
              label-align="left"
            >
              <DeviceSettings v-if="runtime_platform !== 'android'" :expanded="true" />
              <template v-else>
                <n-form-item label="服务器"
                  ><n-radio-group v-model:value="package_type"
                    ><n-space
                      ><n-radio value="official">官服</n-radio
                      ><n-radio value="bilibili">Bilibili 服</n-radio></n-space
                    ></n-radio-group
                  ></n-form-item
                >
                <n-alert :show-icon="false">设备连接由 Android 应用管理。</n-alert>
                <PerformanceSettings :label-width="158" :test-enabled="true" />
              </template>
            </n-form>
          </n-card>
        </div>
      </div>
    </section>

    <section
      data-task-editor="device"
      v-if="!config_store.manager_owned_device && runtime_platform !== 'android'"
    >
      <div class="settings-card-grid">
        <div v-if="runtime_platform !== 'android'" class="settings-card-wide">
          <n-card title="游戏启动">
            <n-form
              class="task-panel-form"
              :label-placement="mobile ? 'top' : 'left'"
              :show-feedback="false"
              label-width="140"
              label-align="left"
            >
              <n-form-item label="启动游戏" v-if="runtime_platform !== 'android'">
                <n-select
                  v-model:value="tap_to_launch_game.mode"
                  :options="launch_options"
                  :consistent-menu-width="false"
                  aria-label="启动游戏"
                />
              </n-form-item>
              <n-form-item
                v-if="runtime_platform !== 'android' && tap_to_launch_game.mode == 'tap'"
                label="点击坐标"
                class="task-panel-field-wide"
              >
                <div class="task-coordinate-grid">
                  <div class="task-coordinate-field">
                    <span>X</span>
                    <mower-input-number
                      v-model:value="tap_to_launch_game.x"
                      :input-props="{ 'aria-label': '启动坐标 X' }"
                    />
                  </div>
                  <div class="task-coordinate-field">
                    <span>Y</span>
                    <mower-input-number
                      v-model:value="tap_to_launch_game.y"
                      :input-props="{ 'aria-label': '启动坐标 Y' }"
                    />
                  </div>
                </div>
              </n-form-item>
              <n-form-item
                v-if="runtime_platform !== 'android' && tap_to_launch_game.mode == 'custom'"
                class="task-panel-field-wide"
              >
                <template #label>
                  <span>启动命令</span>
                  <help-text>
                    <div>
                      在 Android shell 中执行，支持 <code>{package}</code> 和
                      <code>{activity}</code>
                    </div>
                  </help-text>
                </template>
                <n-input
                  v-model:value="tap_to_launch_game.command"
                  type="textarea"
                  :autosize="true"
                  :input-props="{ 'aria-label': '启动命令' }"
                />
                <n-button @click="reset_launch_command">恢复预设命令</n-button>
              </n-form-item>
            </n-form>
          </n-card>
        </div>
      </div>
    </section>

    <section data-task-editor="idle" v-if="!config_store.manager_owned_device">
      <div class="settings-card-grid">
        <n-card title="任务运行">
          <n-form
            class="task-panel-form"
            :label-placement="mobile ? 'top' : 'left'"
            :show-feedback="false"
            label-width="140"
            label-align="left"
          >
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

              <n-select
                v-model:value="displayedIdleAction"
                :disabled="config_store.manager_owned_device"
                :options="idleOptions"
                :consistent-menu-width="false"
                aria-label="任务结束后"
              />
            </n-form-item>
            <n-form-item
              :show-label="false"
              v-if="
                runtime_platform !== 'android' &&
                simulator.name == 'MuMu12' &&
                close_simulator_when_idle
              "
            >
              <n-checkbox
                v-model:checked="fix_mumu12_adb_disconnect"
                :disabled="config_store.manager_owned_device"
              >
                关闭MuMu模拟器12时断开该实例的adb连接
                <help-text>
                  <div>仅执行<code>adb disconnect</code>，断开当前实例的adb端点</div>
                  <div>不结束adb进程，也不影响其他模拟器或工具共用的adb连接</div>
                  <div>使用MuMu模拟器12时，若遇到adb断连问题，可尝试开启此选项</div>
                </help-text>
              </n-checkbox>
            </n-form-item>
            <n-form-item :show-label="false">
              <n-checkbox v-model:checked="start_automatically">启动后自动开始任务</n-checkbox>
            </n-form-item>
          </n-form>
        </n-card>
      </div>
    </section>

    <section id="task-base" data-task-editor="base">
      <div class="settings-card-grid">
        <n-card title="自动救急">
          <n-form
            class="task-panel-form"
            :label-placement="mobile ? 'top' : 'left'"
            :show-feedback="false"
            label-width="140"
            label-align="left"
          >
            <n-form-item :show-label="false">
              <div class="rescue-controls">
                <n-checkbox v-model:checked="automatic_rescue_enable" aria-label="自动救急">
                  自动救急
                  <help-text>
                    初始化时多组主班低于救急线且普通轮休无法安排休息，使用救急排班接管普通工作站。
                    恢复期间冻结正常副表，正常排班可接回周转后退出；双方副表生效后的设施类型、等级或产物不一致时不启动。
                  </help-text>
                </n-checkbox>
                <SessionLink to="/rescue-plan-editor"><n-button>救急排班</n-button></SessionLink>
              </div>
            </n-form-item>
          </n-form>
        </n-card>
      </div>
    </section>

    <section data-task-editor="runorder">
      <div class="settings-card-grid">
        <n-card title="跑单设置">
          <n-form
            class="task-panel-form"
            :label-placement="mobile ? 'top' : 'left'"
            :show-feedback="false"
            label-width="140"
            label-align="left"
          >
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
          </n-form>
        </n-card>
      </div>
    </section>

    <section data-task-editor="drone">
      <div class="settings-card-grid">
        <n-card title="无人机加速">
          <n-form
            class="task-panel-form"
            :label-placement="mobile ? 'top' : 'left'"
            :show-feedback="false"
            label-width="140"
            label-align="left"
          >
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
              <n-select
                :options="facility_with_empty"
                v-model:value="drone_room"
                :consistent-menu-width="false"
                aria-label="无人机使用房间"
              />
            </n-form-item>
            <n-form-item>
              <template #label>
                <span>无人机使用阈值</span>
                <help-text>
                  <div>如加速贸易，推荐大于 贸易站数*10 + 92</div>
                  <div>如加速制造，推荐大于 贸易站数*10</div>
                </help-text>
              </template>
              <mower-input-number v-model:value="drone_count_limit" />
            </n-form-item>
            <n-form-item>
              <template #label>
                <span>无人机加速间隔</span>
                <help-text>
                  <div>可填小数</div>
                </help-text>
              </template>
              <mower-input-number v-model:value="drone_interval">
                <template #suffix>小时</template>
              </mower-input-number>
            </n-form-item>
          </n-form>
        </n-card>
      </div>
    </section>

    <section data-task-editor="clue">
      <div class="settings-card-grid">
        <n-card title="线索搜集与交流">
          <n-form
            class="task-panel-form"
            :label-placement="mobile ? 'top' : 'left'"
            :show-feedback="false"
            label-width="140"
            label-align="left"
          >
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
          </n-form>
        </n-card>
      </div>
    </section>

    <section data-task-editor="workshop">
      <div class="settings-card-grid">
        <n-card title="加工设置">
          <n-form
            class="task-panel-form task-panel-form-stacked"
            :label-placement="mobile ? 'top' : 'left'"
            :show-feedback="false"
            label-width="140"
            label-align="left"
          >
            <WorkshopManualSettings
              v-model="workshop_manual_settings"
              :migration-warning="workshop_preset_warning"
              :operators="operators"
              :item_list="item_list"
            />
          </n-form>
        </n-card>
      </div>
    </section>

    <section data-task-editor="training">
      <div class="settings-card-grid">
        <n-card title="自动专精">
          <div class="task-related-actions">
            <SessionLink to="/mastery-recommendation"
              ><n-button type="primary">养成规划</n-button></SessionLink
            >
            <help-text>专精任务在养成规划中设置，加工材料在加工设置中管理。</help-text>
          </div>
        </n-card>
      </div>
    </section>

    <section data-task-editor="trust">
      <div class="settings-card-grid">
        <TrustSettings :compact-help="true" />
      </div>
    </section>

    <section id="task-daily" data-task-editor="daily">
      <div class="settings-card-grid">
        <DailyMission task="all" @configure-accounts="emit('select', 'accounts')" />
      </div>
    </section>

    <section data-task-editor="recruit">
      <div class="settings-card-grid">
        <Recruit />
      </div>
    </section>

    <section data-task-editor="depot">
      <div class="settings-card-grid">
        <Depotswitch @configure-accounts="emit('select', 'accounts')" />
      </div>
    </section>

    <section data-task-editor="credit">
      <div class="settings-card-grid">
        <Clue task="all" @configure-clue="emit('select', 'clue')" />
      </div>
    </section>

    <section data-task-editor="rewards">
      <div class="settings-card-grid">
        <MaaReward />
      </div>
    </section>

    <section data-task-editor="stage-plan">
      <div class="settings-card-grid">
        <div class="settings-card-wide"><MaaWeekly /></div>
      </div>
    </section>

    <section id="task-long" data-task-editor="long">
      <div class="settings-card-grid">
        <div class="settings-card-wide"><LongTasks /></div>
      </div>
    </section>

    <section data-task-editor="intervals">
      <div class="settings-card-grid">
        <n-card title="执行间隔">
          <n-form
            class="task-panel-form"
            :label-placement="mobile ? 'top' : 'left'"
            :show-feedback="false"
          >
            <n-form-item>
              <template #label>
                <span>日常任务间隔</span>
                <help-text>
                  <div>可填小数</div>
                  <div>
                    MAA 日常、刷理智、仓库扫描和制造站补货共用此间隔；邮件等每日任务按游戏日检查。
                  </div>
                </help-text>
              </template>
              <mower-input-number
                v-model:value="maa_gap"
                :input-props="{ 'aria-label': '日常任务间隔' }"
              >
                <template #suffix>小时</template>
              </mower-input-number>
            </n-form-item>
          </n-form>
        </n-card>
      </div>
    </section>

    <section v-if="!config_store.manager_owned_device" id="task-runtime" data-task-editor="runtime">
      <div class="settings-card-grid">
        <n-card title="采样与等待">
          <n-form
            class="task-panel-form"
            :label-placement="mobile ? 'top' : 'left'"
            :show-feedback="false"
            label-width="140"
            label-align="left"
          >
            <n-form-item v-if="!config_store.manager_owned_device" label="截图最短间隔">
              <mower-input-number
                v-model:value="screenshot_interval"
                :precision="0"
                :disabled="config_store.manager_owned_device"
              >
                <template #suffix>毫秒</template>
              </mower-input-number>
            </n-form-item>
            <n-form-item v-if="!config_store.manager_owned_device" label="选人采样间隔">
              <mower-input-number
                v-model:value="selection_poll_interval"
                :min="0.1"
                :max="2"
                :disabled="config_store.manager_owned_device"
              >
                <template #suffix>秒</template>
              </mower-input-number>
            </n-form-item>
            <n-form-item v-if="!config_store.manager_owned_device" label="操作反馈超时">
              <mower-input-number
                v-model:value="selection_transition_timeout"
                :min="1"
                :max="20"
                :disabled="config_store.manager_owned_device"
              >
                <template #suffix>秒</template>
              </mower-input-number>
            </n-form-item>
            <n-form-item label="等待时间" class="task-panel-field-wide">
              <div class="task-waiting-scroll" tabindex="0" role="region" aria-label="场景等待参数">
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
                          :input-props="{
                            'aria-label': `${scene_name[key] || key}截图间隔（秒）`
                          }"
                        >
                          <template #suffix>秒</template>
                        </mower-input-number>
                      </td>
                      <td>
                        <mower-input-number
                          v-model:value="value[1]"
                          :show-button="false"
                          :precision="0"
                          :input-props="{ 'aria-label': `${scene_name[key] || key}等待次数` }"
                        >
                          <template #suffix>次</template>
                        </mower-input-number>
                      </td>
                    </tr>
                  </tbody>
                </n-table>
              </div>
            </n-form-item>
          </n-form>
        </n-card>
      </div>
    </section>

    <section id="task-accounts" data-task-editor="accounts">
      <div class="settings-card-grid">
        <SKLand />
      </div>
    </section>

    <section data-task-editor="accounts">
      <div class="settings-card-grid">
        <YituliuSyncSettings />
      </div>
    </section>

    <section data-task-editor="accounts">
      <div class="settings-card-grid">
        <div class="settings-card-wide"><IncomeSettings /></div>
      </div>
    </section>

    <section id="task-maa" data-task-editor="maa">
      <div class="settings-card-grid">
        <div class="settings-card-wide"><MaaBasic /></div>
      </div>
    </section>
    <MowerSettings />
  </div>
</template>

<style scoped>
.rescue-controls {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
}

.task-settings-panels {
  --settings-radius: 12px;
  --settings-card-border: var(--mower-border);
  --settings-control-width: 440px;
  --settings-number-width: 180px;
  padding: 0;
}

.task-settings-panels :deep(.task-panel-form .n-form-item-label__text) {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.task-settings-panels :deep(.task-panel-form > .n-form-item) {
  min-width: 0;
  align-items: center;
  padding: 8px 0;
}

.task-settings-panels :deep(.task-panel-form > .n-form-item:has(> .n-form-item-label)) {
  grid-template-columns: 148px minmax(0, 440px);
  grid-template-areas: 'label blank' 'feedback feedback';
  grid-template-rows: auto auto;
  column-gap: 20px;
}

.task-settings-panels :deep(.task-panel-form > .n-form-item > .n-form-item-label) {
  width: auto !important;
  min-width: 0;
  min-height: 0;
  padding: 0;
  font-size: 13px;
  font-weight: 400;
  line-height: 1.65;
  text-align: left;
  justify-content: flex-start;
}

.task-settings-panels :deep(.task-panel-form > .n-form-item > .n-form-item-blank) {
  min-width: 0;
  width: 100%;
  max-width: 440px;
  justify-self: start;
  justify-content: flex-start;
  flex-wrap: wrap;
  gap: 8px;
}

.task-settings-panels
  :deep(.task-panel-form > .n-form-item > .n-form-item-blank > .n-input-number) {
  max-width: 180px;
}

.task-settings-panels
  :deep(.task-panel-form > .n-form-item:not(:has(> .n-form-item-label)) > .n-form-item-blank) {
  justify-self: stretch;
  max-width: none;
}

.task-settings-panels :deep(.task-panel-form > .n-form-item.task-panel-field-wide),
.task-settings-panels :deep(.task-panel-form.task-panel-form-stacked > .n-form-item) {
  grid-template-columns: minmax(0, 1fr);
  grid-template-areas: 'label' 'blank' 'feedback';
  row-gap: 10px;
}

.task-settings-panels :deep(.task-panel-form > .task-panel-field-wide > .n-form-item-blank),
.task-settings-panels
  :deep(.task-panel-form.task-panel-form-stacked > .n-form-item > .n-form-item-blank) {
  flex-direction: column;
  align-items: stretch;
  justify-self: stretch;
  max-width: none;
}

.task-settings-panels :deep(.task-panel-field-wide .n-form-item-blank > .n-input),
.task-settings-panels :deep(.task-panel-form-stacked .n-form-item-blank > .n-list) {
  width: 100%;
  max-width: none;
}

.task-settings-panels :deep(.task-panel-field-wide .n-form-item-blank > .n-button),
.task-settings-panels :deep(.task-panel-form-stacked .n-form-item-blank > .n-button) {
  align-self: flex-start;
}

.task-coordinate-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: 16px;
  width: 100%;
}

.task-coordinate-field {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  font-size: 13px;
}

.task-coordinate-field :deep(.n-input-number) {
  flex: 1;
  min-width: 0;
}

.task-related-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.task-plan-actions {
  margin-top: 8px;
}

.task-waiting-scroll {
  width: 100%;
  max-width: 100%;
  overflow-x: auto;
  border-radius: 8px;
}

.task-waiting-scroll:focus-visible {
  outline: 2px solid var(--mower-primary);
  outline-offset: 2px;
}

.task-settings-panels :deep([data-task-editor='stage-plan'] .weekly-plan-editors .n-tab-pane) {
  overflow-x: auto;
}

.task-settings-panels :deep([data-task-editor='long'] .n-grid) {
  column-gap: 12px !important;
}

.waiting-table {
  width: 100%;
  min-width: 360px;
}

.waiting-table th,
.waiting-table td {
  padding: 8px;
  width: 112px;
  font-size: 12px;
}

.waiting-table th:first-child,
.waiting-table td:first-child {
  width: auto;
}

@container main-content (max-width: 480px) {
  .task-settings-panels
    :deep(:is(.settings-card-grid, .settings-card-wide) > .n-card > .n-card-content) {
    padding: 0;
  }

  .task-settings-panels :deep(.task-panel-form > .n-form-item:has(> .n-form-item-label)) {
    grid-template-columns: minmax(0, 1fr);
    grid-template-areas: 'label' 'blank' 'feedback';
    row-gap: 8px;
  }

  .task-settings-panels :deep(.task-panel-form > .n-form-item > .n-form-item-blank) {
    justify-self: stretch;
    max-width: none;
  }

  .task-settings-panels
    :deep(.task-panel-form > .n-form-item > .n-form-item-blank > .n-input-number) {
    width: 100%;
    max-width: none;
  }

  .task-settings-panels :deep([data-task-editor='stage-plan'] .weekly-plan-toolbar) {
    flex-wrap: wrap;
  }
}

@container main-content (max-width: 420px) {
  .task-coordinate-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}

.task-settings-panels--continuous {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  align-items: start;
  gap: 10px;
  width: 100%;
  margin: 0;
}

.task-settings-panels--continuous > section {
  min-width: 0;
}

.task-settings-panels :deep([id]),
.task-settings-panels--continuous > section {
  scroll-margin-top: var(--task-target-scroll-margin, 12px);
}

.task-settings-panels--continuous :deep(.settings-card-grid) {
  gap: 10px;
}

.task-settings-panels.task-settings-panels--continuous
  :deep(:is(.settings-card-grid, .settings-card-wide) > .n-card:not(.n-modal)) {
  display: flex;
  width: 100%;
  box-sizing: border-box;
  margin: 0;
  border: 1px solid var(--settings-card-border, var(--mower-border));
  border-radius: 10px;
  box-shadow: none;
  background: var(--mower-surface);
  transition:
    border-color 180ms ease,
    background-color 180ms ease,
    box-shadow 180ms ease;
}

@media (prefers-reduced-motion: reduce) {
  .task-settings-panels.task-settings-panels--continuous
    :deep(:is(.settings-card-grid, .settings-card-wide) > .n-card:not(.n-modal)) {
    transition: none;
  }
}

.task-settings-panels.task-settings-panels--continuous
  :deep(:is(.settings-card-grid, .settings-card-wide) > .n-card > .n-card-header) {
  display: flex;
  padding: 16px 20px 12px;
}

.task-settings-panels.task-settings-panels--continuous
  :deep(
    :is(.settings-card-grid, .settings-card-wide) > .n-card > .n-card-header .n-card-header__main
  ) {
  font-size: 16px;
  font-weight: 600;
}

.task-settings-panels.task-settings-panels--continuous
  :deep(:is(.settings-card-grid, .settings-card-wide) > .n-card > .n-card-content) {
  padding: 0 20px 20px;
  border: 0;
  background: transparent;
}

@container task-settings-content (min-width: 900px) {
  .task-settings-panels :deep(.task-panel-form:not(.task-panel-form-stacked)) {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    column-gap: 32px;
    align-items: center;
  }

  .task-settings-panels :deep(.task-panel-form:not(.task-panel-form-stacked) > .n-form-item) {
    margin: 0;
  }

  .task-settings-panels :deep(.task-panel-form > .n-form-item.task-panel-field-wide),
  .task-settings-panels :deep(.task-panel-form > :not(.n-form-item)) {
    grid-column: 1 / -1;
  }

  .task-settings-panels
    :deep(
      .task-panel-form:not(.task-panel-form-stacked)
        > .n-form-item:not(.task-panel-field-wide):has(> .n-form-item-label)
    ) {
    grid-template-columns: 148px minmax(0, 1fr);
    column-gap: 16px;
  }
}

.task-settings-panels :deep(.settings-section) {
  margin-bottom: 0;
  scroll-margin-top: var(--task-target-scroll-margin, 12px);
}

.task-settings-panels :deep(.settings-section-header) {
  margin-bottom: 16px;
}
</style>
