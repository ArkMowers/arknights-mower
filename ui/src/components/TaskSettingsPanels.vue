<script setup>
import { i18n } from '@/i18n'
const { t } = i18n.global

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
import MaaEventShop from '@/components/MaaEventShop.vue'
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
  const id = ['report', 'skland', 'mail', 'event-sign-in'].includes(props.active)
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
  return [
    {
      get label() {
        return t('tasks.anyEligibleTrade')
      },
      value: ''
    }
  ].concat(left_side_facility)
})

const launch_options = [
  {
    get label() {
      return t('tasks.adbLaunch')
    },
    value: 'adb'
  },
  {
    get label() {
      return t('tasks.tapLaunch')
    },
    value: 'tap'
  },
  {
    get label() {
      return t('tasks.customLaunch')
    },
    value: 'custom'
  }
]

const defaultLaunchCommand =
  'input keyevent KEYCODE_WAKEUP; wm dismiss-keyguard; am start -n {package}/{activity}'

function reset_launch_command() {
  tap_to_launch_game.value.command = defaultLaunchCommand
}

const scene_name = {
  get CONNECTING() {
    return t('tasks.connectingScene')
  },
  get UNKNOWN() {
    return t('tasks.unknown')
  },
  get LOADING() {
    return t('tasks.loading')
  },
  get LOGIN_LOADING() {
    return t('tasks.transitionWaiting')
  },
  get LOGIN_MAIN_NOENTRY() {
    return t('tasks.loginNoEntry')
  },
  get OPERATOR_ONGOING() {
    return t('tasks.autoDeploy')
  }
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
  {
    get label() {
      return t('tasks.doNothing')
    },
    value: 'idle'
  },
  {
    get label() {
      return t('tasks.returnHome')
    },
    value: 'home'
  },
  {
    get label() {
      return t('tasks.exitGame')
    },
    value: 'exit'
  },
  ...(simulatorLifecycleAllowed.value
    ? [
        {
          get label() {
            return t('tasks.closeEmulator')
          },
          value: 'close'
        }
      ]
    : [])
])
</script>

<template>
  <div ref="root" class="task-settings-panels task-settings-panels--continuous">
    <section v-if="!config_store.manager_owned_device" id="task-devices" data-task-editor="device">
      <div class="settings-card-grid">
        <div class="settings-card-wide">
          <n-card :title="t('tasks.devicePerformance')">
            <n-form
              :label-placement="mobile ? 'top' : 'left'"
              :show-feedback="false"
              label-width="158"
              label-align="left"
            >
              <DeviceSettings v-if="runtime_platform !== 'android'" :expanded="true" />
              <template v-else>
                <n-form-item :label="t('tasks.server')"
                  ><n-radio-group v-model:value="package_type"
                    ><n-space
                      ><n-radio value="official">{{ t('tasks.officialServer') }}</n-radio
                      ><n-radio value="bilibili">{{
                        t('tasks.bilibiliServerLong')
                      }}</n-radio></n-space
                    ></n-radio-group
                  ></n-form-item
                >
                <n-alert :show-icon="false">{{ t('tasks.androidConnection') }}</n-alert>
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
          <n-card :title="t('tasks.gameStartup')">
            <n-form
              class="task-panel-form"
              :label-placement="mobile ? 'top' : 'left'"
              :show-feedback="false"
              label-width="140"
              label-align="left"
            >
              <n-form-item :label="t('tasks.launchGame')" v-if="runtime_platform !== 'android'">
                <n-select
                  v-model:value="tap_to_launch_game.mode"
                  :options="launch_options"
                  :consistent-menu-width="false"
                  :aria-label="t('tasks.launchGame')"
                />
              </n-form-item>
              <n-form-item
                v-if="runtime_platform !== 'android' && tap_to_launch_game.mode == 'tap'"
                :label="t('tasks.tapCoordinates')"
                class="task-panel-field-wide"
              >
                <div class="task-coordinate-grid">
                  <div class="task-coordinate-field">
                    <span>X</span>
                    <mower-input-number
                      v-model:value="tap_to_launch_game.x"
                      :input-props="{ 'aria-label': t('tasks.launchX') }"
                    />
                  </div>
                  <div class="task-coordinate-field">
                    <span>Y</span>
                    <mower-input-number
                      v-model:value="tap_to_launch_game.y"
                      :input-props="{ 'aria-label': t('tasks.launchY') }"
                    />
                  </div>
                </div>
              </n-form-item>
              <n-form-item
                v-if="runtime_platform !== 'android' && tap_to_launch_game.mode == 'custom'"
                class="task-panel-field-wide"
              >
                <template #label>
                  <span>{{ t('tasks.launchCommand') }}</span>
                  <help-text>
                    <div>
                      {{ t('tasks.androidShellHelp') }}<code>{package}</code>{{ t('tasks.and')
                      }}<code>{activity}</code>
                    </div>
                  </help-text>
                </template>
                <n-input
                  v-model:value="tap_to_launch_game.command"
                  type="textarea"
                  :autosize="true"
                  :input-props="{ 'aria-label': t('tasks.launchCommand') }"
                />
                <n-button @click="reset_launch_command">{{ t('tasks.resetCommand') }}</n-button>
              </n-form-item>
            </n-form>
          </n-card>
        </div>
      </div>
    </section>

    <section data-task-editor="idle" v-if="!config_store.manager_owned_device">
      <div class="settings-card-grid">
        <n-card :title="t('tasks.taskExecution')">
          <n-form
            class="task-panel-form"
            :label-placement="mobile ? 'top' : 'left'"
            :show-feedback="false"
            label-width="140"
            label-align="left"
          >
            <n-form-item v-if="runtime_platform !== 'android'">
              <template #label>
                <span>{{ t('tasks.afterTasks') }}</span>
                <help-text>
                  <div>{{ t('tasks.homePower') }}</div>
                  <div>{{ t('tasks.exitPower') }}</div>
                  <div v-if="simulatorLifecycleAllowed">{{ t('tasks.closePower') }}</div>
                  <div
                    v-if="
                      ['macos.avd', 'linux.avd'].includes(config_store.device_profile?.preset_id)
                    "
                  >
                    {{ t('tasks.avdCloseHelp') }}
                  </div>
                </help-text>
              </template>

              <n-select
                v-model:value="displayedIdleAction"
                :disabled="config_store.manager_owned_device"
                :options="idleOptions"
                :consistent-menu-width="false"
                :aria-label="t('tasks.afterTasks')"
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
                >{{ t('tasks.disconnectMumuAdb')
                }}<help-text>
                  <div>
                    {{ t('tasks.onlyExecute') }}<code>adb disconnect</code
                    >{{ t('tasks.disconnectCurrentAdb') }}
                  </div>
                  <div>{{ t('tasks.preserveSharedAdb') }}</div>
                  <div>{{ t('tasks.mumuDisconnectHelp') }}</div>
                </help-text>
              </n-checkbox>
            </n-form-item>
            <n-form-item :show-label="false">
              <n-checkbox v-model:checked="start_automatically">{{
                t('tasks.startAutomatically')
              }}</n-checkbox>
            </n-form-item>
          </n-form>
        </n-card>
      </div>
    </section>

    <section id="task-base" data-task-editor="base">
      <div class="settings-card-grid">
        <n-card :title="t('tasks.automaticRescue')">
          <n-form
            class="task-panel-form"
            :label-placement="mobile ? 'top' : 'left'"
            :show-feedback="false"
            label-width="140"
            label-align="left"
          >
            <n-form-item :show-label="false">
              <div class="rescue-controls">
                <n-checkbox
                  v-model:checked="automatic_rescue_enable"
                  :aria-label="t('tasks.automaticRescue')"
                  >{{ t('tasks.automaticRescue')
                  }}<help-text>{{ t('tasks.rescueHelp') }}</help-text>
                </n-checkbox>
                <SessionLink to="/rescue-plan-editor"
                  ><n-button>{{ t('tasks.rescuePlan') }}</n-button></SessionLink
                >
              </div>
            </n-form-item>
          </n-form>
        </n-card>
      </div>
    </section>

    <section data-task-editor="runorder">
      <div class="settings-card-grid">
        <n-card :title="t('tasks.runOrderSettings')">
          <n-form
            class="task-panel-form"
            :label-placement="mobile ? 'top' : 'left'"
            :show-feedback="false"
            label-width="140"
            label-align="left"
          >
            <n-form-item>
              <template #label>
                <span>{{ t('tasks.runOrderLead') }}</span>
                <help-text>
                  <div>{{ t('tasks.recommended5to10') }}</div>
                  <div>{{ t('tasks.decimalAllowed') }}</div>
                </help-text>
              </template>
              <mower-input-number v-model:value="run_order_delay">
                <template #suffix>{{ t('tasks.minutes') }}</template>
              </mower-input-number>
            </n-form-item>
            <n-form-item :show-label="false">
              <n-checkbox v-model:checked="run_order_grandet_mode.enable">{{
                t('tasks.grandetOrders')
              }}</n-checkbox>
            </n-form-item>
            <n-form-item>
              <template #label>
                <span>{{ t('tasks.grandetBuffer') }}</span>
                <help-text>{{ t('tasks.recommended15to30') }}</help-text>
              </template>
              <mower-input-number
                v-model:value="run_order_grandet_mode.buffer_time"
                :disabled="!run_order_grandet_mode.enable"
              >
                <template #suffix>{{ t('tasks.seconds') }}</template>
              </mower-input-number>
            </n-form-item>
            <n-form-item v-if="run_order_grandet_mode.enable" :show-label="false">
              <n-checkbox v-model:checked="run_order_grandet_mode.back_to_index">{{
                t('tasks.runOrderHome')
              }}</n-checkbox>
            </n-form-item>
          </n-form>
        </n-card>
      </div>
    </section>

    <section data-task-editor="drone">
      <div class="settings-card-grid">
        <n-card :title="t('tasks.droneAcceleration')">
          <n-form
            class="task-panel-form"
            :label-placement="mobile ? 'top' : 'left'"
            :show-feedback="false"
            label-width="140"
            label-align="left"
          >
            <n-form-item>
              <template #label>
                <span>{{ t('tasks.droneRoom') }}</span>
                <help-text>
                  <div>{{ t('tasks.droneFactoryHelp') }}</div>
                  <div>{{ t('tasks.droneAnyTradeHelp') }}</div>
                  <div>{{ t('tasks.droneTradeExample') }}</div>
                  <div>{{ t('tasks.droneSpecificHelp') }}</div>
                </help-text>
              </template>
              <n-select
                :options="facility_with_empty"
                v-model:value="drone_room"
                :consistent-menu-width="false"
                :aria-label="t('tasks.droneRoom')"
              />
            </n-form-item>
            <n-form-item>
              <template #label>
                <span>{{ t('tasks.droneThreshold') }}</span>
                <help-text>
                  <div>{{ t('tasks.droneMinimum') }}</div>
                  <div>{{ t('tasks.droneTradeThreshold') }}</div>
                  <div>{{ t('tasks.droneFactoryThreshold') }}</div>
                </help-text>
              </template>
              <mower-input-number v-model:value="drone_count_limit" :min="20" />
            </n-form-item>
            <n-form-item>
              <template #label>
                <span>{{ t('tasks.droneInterval') }}</span>
                <help-text>
                  <div>{{ t('tasks.decimalAllowed') }}</div>
                </help-text>
              </template>
              <mower-input-number v-model:value="drone_interval">
                <template #suffix>{{ t('tasks.hours') }}</template>
              </mower-input-number>
            </n-form-item>
          </n-form>
        </n-card>
      </div>
    </section>

    <section data-task-editor="clue">
      <div class="settings-card-grid">
        <n-card :title="t('tasks.clueCollectionExchange')">
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
                  <div class="item">{{ t('tasks.clueCollection') }}</div>
                </n-checkbox>
                <n-checkbox v-model:checked="leifeng_mode"
                  >{{ t('tasks.giftSurplusClues')
                  }}<help-text>
                    <div>{{ t('tasks.giftSurplusEnabled') }}</div>
                    <div>{{ t('tasks.giftSurplusDisabled') }}</div>
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
        <n-card :title="t('tasks.workshopSettings')">
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
        <n-card :title="t('tasks.automaticMastery')">
          <div class="task-related-actions">
            <SessionLink to="/mastery-recommendation"
              ><n-button type="primary">{{ t('tasks.growthPlanning') }}</n-button></SessionLink
            >
            <help-text>{{ t('tasks.masteryLocation') }}</help-text>
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

    <section id="task-event-shop" data-task-editor="event-shop">
      <div class="settings-card-grid">
        <MaaEventShop />
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
        <n-card :title="t('tasks.executionIntervals')">
          <n-form
            class="task-panel-form"
            :label-placement="mobile ? 'top' : 'left'"
            :show-feedback="false"
          >
            <n-form-item>
              <template #label>
                <span>{{ t('tasks.dailyInterval') }}</span>
                <help-text>
                  <div>{{ t('tasks.decimalAllowed') }}</div>
                  <div>{{ t('tasks.sharedDailyInterval') }}</div>
                </help-text>
              </template>
              <mower-input-number
                v-model:value="maa_gap"
                :input-props="{ 'aria-label': t('tasks.dailyInterval') }"
              >
                <template #suffix>{{ t('tasks.hours') }}</template>
              </mower-input-number>
            </n-form-item>
          </n-form>
        </n-card>
      </div>
    </section>

    <section v-if="!config_store.manager_owned_device" id="task-runtime" data-task-editor="runtime">
      <div class="settings-card-grid">
        <n-card :title="t('tasks.samplingWaiting')">
          <n-form
            class="task-panel-form"
            :label-placement="mobile ? 'top' : 'left'"
            :show-feedback="false"
            label-width="140"
            label-align="left"
          >
            <n-form-item
              v-if="!config_store.manager_owned_device"
              :label="t('tasks.minimumScreenshotInterval')"
            >
              <mower-input-number
                v-model:value="screenshot_interval"
                :precision="0"
                :disabled="config_store.manager_owned_device"
              >
                <template #suffix>{{ t('tasks.milliseconds') }}</template>
              </mower-input-number>
            </n-form-item>
            <n-form-item
              v-if="!config_store.manager_owned_device"
              :label="t('tasks.operatorSamplingInterval')"
            >
              <mower-input-number
                v-model:value="selection_poll_interval"
                :min="0.1"
                :max="2"
                :disabled="config_store.manager_owned_device"
              >
                <template #suffix>{{ t('tasks.seconds') }}</template>
              </mower-input-number>
            </n-form-item>
            <n-form-item
              v-if="!config_store.manager_owned_device"
              :label="t('tasks.feedbackTimeout')"
            >
              <mower-input-number
                v-model:value="selection_transition_timeout"
                :min="1"
                :max="20"
                :disabled="config_store.manager_owned_device"
              >
                <template #suffix>{{ t('tasks.seconds') }}</template>
              </mower-input-number>
            </n-form-item>
            <n-form-item :label="t('tasks.waitTime')" class="task-panel-field-wide">
              <div
                class="task-waiting-scroll"
                tabindex="0"
                role="region"
                :aria-label="t('tasks.sceneWaiting')"
              >
                <n-table size="small" class="waiting-table">
                  <thead>
                    <tr>
                      <th>{{ t('tasks.scene') }}</th>
                      <th>{{ t('tasks.screenshotInterval') }}</th>
                      <th>{{ t('tasks.attempts') }}</th>
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
                            'aria-label': t('tasks.sceneScreenshotInterval', {
                              scene: scene_name[key] || key
                            })
                          }"
                        >
                          <template #suffix>{{ t('tasks.seconds') }}</template>
                        </mower-input-number>
                      </td>
                      <td>
                        <mower-input-number
                          v-model:value="value[1]"
                          :show-button="false"
                          :precision="0"
                          :input-props="{
                            'aria-label': t('tasks.sceneWaitAttempts', {
                              scene: scene_name[key] || key
                            })
                          }"
                        >
                          <template #suffix>{{ t('tasks.times') }}</template>
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
