<template>
  <n-config-provider
    :locale="zhCN"
    :date-locale="dateZhCN"
    class="provider"
    :theme="theme == 'dark' ? darkTheme : undefined"
    :theme-overrides="theme == 'dark' ? mowerDarkThemeOverrides : mowerLightThemeOverrides"
    :hljs="hljs"
    :style="{ userSelect: 'none', ...mowerCssVariables }"
    :class="{
      'provider--dark': theme === 'dark',
      'provider--window-shell': windowShellActive
    }"
  >
    <n-global-style />
    <WindowTitlebar
      :active="windowShellActive"
      :title="windowShellTitle"
      :instance-name="windowShell.metadata.instanceName || '默认实例'"
      :theme="theme"
      :control-side="windowShellControlSide"
      :maximized="windowShellState.maximized"
      :controls="windowShellControls"
      :busy="windowShellBusy"
      :sidebar-collapsed="sidebarCollapsed || sidebarHidden"
      :sidebar-visible="sidebarVisible"
      :show-sidebar-toggle="!isMobileNav"
      :mower-port="mowerPort"
      :emulator-name="emulatorName"
      :adb-port="adbPort"
      :connection-test-disabled="running || deviceConnectionNavigation.locked.value"
      :profile-state="configProfiles.state.value"
      :profile-write-disabled="configProfiles.writeDisabled.value"
      :profile-read-disabled="configProfiles.readDisabled.value"
      :on-control="handleWindowControl"
      :on-toggle-maximize="windowShell.toggleMaximize"
      :resizable="windowShellCapabilities.resize === 'html' && !windowShellState.maximized"
      :native-interactions="windowShellCapabilities.move === 'native'"
      :native-controls="windowShellCapabilities.controls === 'native'"
      :on-resize="windowShell.startResize"
      :on-move="windowShell.startMove"
      @toggle-sidebar="toggleSidebar"
      @connection-action="openDeviceConnection"
      @profile-action="configProfiles.open"
      @help-action="openHelp"
      @view-action="handleViewAction"
    />
    <n-notification-provider
      placement="top-right"
      :container-style="windowShellActive ? { top: '48px' } : undefined"
    >
      <n-dialog-provider>
        <n-modal
          v-model:show="closeModal"
          preset="card"
          title="关闭 Mower"
          style="max-width: 430px"
          :mask-closable="!closeBusy"
          :closable="!closeBusy"
        >
          <n-space vertical :size="16">
            <n-text depth="3">关闭窗口不一定会停止后台调度。请选择本次操作：</n-text>
            <n-radio-group v-model:value="closeChoice" :disabled="closeBusy">
              <n-space vertical>
                <n-radio v-if="closeTrayAvailable" value="tray">收起到托盘（继续运行）</n-radio>
                <n-radio value="exit">停止任务并彻底退出</n-radio>
              </n-space>
            </n-radio-group>
            <n-checkbox v-model:checked="closeRemember" :disabled="closeBusy">
              记住我的选择（可在「Mower 设置 → 界面与窗口」中更改）
            </n-checkbox>
            <n-alert v-if="closeError" type="error">{{ closeError }}</n-alert>
            <n-text v-if="closeStatus" depth="3">{{ closeStatus }}</n-text>
            <n-space justify="end">
              <n-button :disabled="closeBusy" @click="closeModal = false">取消</n-button>
              <n-button
                type="primary"
                :loading="closeBusy"
                @click="performWindowClose(closeChoice, closeRemember)"
                >确定</n-button
              >
            </n-space>
          </n-space>
        </n-modal>
        <n-message-provider>
          <ConfigProfilesController :controller="configProfiles" />
          <SidebarEditor v-model:show="sidebarEditorOpen" :request="sidebarEditorRequest" />
          <HelpDialog
            v-model:section="helpSection"
            :version="softwareVersion"
            :resource-version="resourceVersion"
          />
          <n-loading-bar-provider>
            <header
              v-if="!windowShellActive"
              v-show="fallbackAppMenu && appMenuVisible"
              class="app-menu-header"
            >
              <div id="header-app-menu" />
            </header>
            <n-layout :has-sider="!isMobileNav" class="outer-layout">
              <n-layout-sider
                v-if="!isMobileNav"
                v-show="!sidebarHidden"
                :bordered="!windowShellActive"
                collapse-mode="width"
                :collapsed-width="64"
                :width="210"
                :collapsed="sidebarCollapsed"
                content-style="display: flex; flex-direction: column; overflow: hidden"
              >
                <SidebarUpdateChecks
                  v-if="!windowShellActive || !sidebarCollapsed"
                  :collapsed="sidebarCollapsed"
                  :collapsible="!windowShellActive"
                  :show-logo="sidebarCollapsed"
                  :version="softwareVersion"
                  :deployment="deployment"
                  :display-mode="softwareVersionDisplay"
                  :enabled="updates_enabled === true"
                  :resource-version="resourceVersion"
                  :resource-metadata="resource_version_store.info.current_metadata"
                  @toggle="toggleSidebar"
                >
                  <template v-if="!windowShellActive && !sidebarCollapsed" #home>
                    <div id="sidebar-app-menu" />
                  </template>
                </SidebarUpdateChecks>
                <div id="sidebar-navigation" class="sidebar-navigation">
                  <AppSidebar
                    :collapsed="sidebarCollapsed"
                    @open-chat="openChatBot"
                    @expand-sidebar="expandSidebar"
                    @customize="openSidebarEditor"
                  />
                </div>
              </n-layout-sider>
              <n-layout-content class="layout-content-container">
                <n-watermark
                  class="content-watermark"
                  :content="watermarkData"
                  cross
                  :font-size="16"
                  :line-height="32"
                  :width="400"
                  :height="384"
                  :x-offset="12"
                  :y-offset="60"
                  :rotate="-15"
                />
                <ConfigSaveNotice />
                <CrashRecoveryNotice v-if="loaded" />
                <router-view
                  v-if="loaded && contentRoute"
                  v-slot="{ Component }"
                  :route="contentRoute"
                >
                  <keep-alive include="TaskSettings">
                    <component :is="Component" />
                  </keep-alive>
                </router-view>
                <SettingsDialog
                  v-if="loaded"
                  :show="settingsDirectoryMode"
                  :style="mowerCssVariables"
                  @close="leaveSettings"
                />
                <ChatBot v-if="chatBotMounted" v-model:show="showChatBot" />
                <Feedback />
                <GlobalUpdateDrop v-if="loaded && updates_enabled === true" />
                <n-modal
                  v-model:show="showUpdateNoticeModal"
                  preset="card"
                  style="width: min(720px, calc(100vw - 32px))"
                  title="版本更新"
                  :mask-closable="false"
                  :close-on-esc="false"
                  closable
                  @close="handleUpdateNoticeAck"
                >
                  <div style="font-size: 18px; font-weight: 600">
                    {{ `已更新到 ${updateNotice.current_version}` }}
                  </div>
                  <div
                    v-if="updateNotice.previous_version"
                    style="margin-top: 8px; color: var(--n-text-color-3)"
                  >
                    {{ `从 ${updateNotice.previous_version} 更新` }}
                  </div>
                  <div
                    style="margin-top: 16px; max-height: 50vh; overflow: auto; line-height: 1.6"
                    v-html="renderedChangelog"
                  ></div>
                  <div style="margin-top: 20px; display: flex; justify-content: flex-end">
                    <n-button type="primary" @click="handleUpdateNoticeAck">我知道了</n-button>
                  </div>
                </n-modal>
              </n-layout-content>
              <n-layout-footer v-if="isMobileNav" class="navigation-footer">
                <MobileTabBar :more-open="mobileMenuOpen" @more="mobileMenuOpen = true" />
              </n-layout-footer>
            </n-layout>
            <n-drawer
              v-if="isMobileNav"
              v-model:show="mobileMenuOpen"
              placement="left"
              :width="280"
              aria-label="全部页面"
              :style="mowerCssVariables"
            >
              <div class="sidebar-drawer">
                <SidebarUpdateChecks
                  :collapsible="false"
                  :version="softwareVersion"
                  :deployment="deployment"
                  :display-mode="softwareVersionDisplay"
                  :enabled="updates_enabled === true"
                  :resource-version="resourceVersion"
                  :resource-metadata="resource_version_store.info.current_metadata"
                />
                <div class="sidebar-navigation">
                  <AppSidebar
                    mobile
                    @navigate="mobileMenuOpen = false"
                    @open-chat="openChatBot"
                    @customize="openSidebarEditor"
                  />
                </div>
              </div>
            </n-drawer>
            <Teleport
              v-if="!windowShellActive"
              :to="fallbackAppMenu ? '#header-app-menu' : '#sidebar-app-menu'"
              defer
            >
              <AppMenuBar
                mode="brand"
                :active="appMenuVisible"
                v-bind="appMenuProps"
                v-on="appMenuListeners"
              />
            </Teleport>
          </n-loading-bar-provider>
        </n-message-provider>
      </n-dialog-provider>
    </n-notification-provider>
  </n-config-provider>
</template>

<script setup>
import { storeToRefs } from 'pinia'
import {
  computed,
  defineAsyncComponent,
  inject,
  nextTick,
  onBeforeUnmount,
  onMounted,
  provide,
  ref,
  shallowRef,
  watch,
  watchPostEffect
} from 'vue'
import AppSidebar from '@/components/AppSidebar.vue'
import SettingsDialog from '@/components/SettingsDialog.vue'
import Feedback from '@/components/Feedback.vue'
import GlobalUpdateDrop from '@/components/GlobalUpdateDrop.vue'
import CrashRecoveryNotice from '@/components/CrashRecoveryNotice.vue'
import ConfigSaveNotice from '@/components/ConfigSaveNotice.vue'
import MobileTabBar from '@/components/MobileTabBar.vue'
import WindowTitlebar from '@/components/WindowTitlebar.vue'
import AppMenuBar from '@/components/AppMenuBar.vue'
import HelpDialog from '@/components/HelpDialog.vue'
import ConfigProfilesController from '@/components/ConfigProfilesController.vue'
import SidebarUpdateChecks from '@/components/SidebarUpdateChecks.vue'
import SidebarEditor from '@/components/SidebarEditor.vue'
import { useSidebarPreferences } from '@/composables/sidebarPreferences'
import { useResolvedTheme } from '@/composables/theme'
import {
  mowerDarkCssVariables,
  mowerDarkThemeOverrides,
  mowerLightCssVariables,
  mowerLightThemeOverrides
} from '@/theme/mower'
import '@/theme/mower.css'
import '@/styles/breakpoints.css'
import {
  createWindowShellAdapter,
  formatWindowTitle,
  formatEmulatorLabel
} from '@/window-shell/adapter.js'
import { createSaveCoordinator } from '@/utils/configPersistence'
import { createConfigProfiles } from '@/composables/configProfiles'
import { readProcessActionStatus, submitProcessAction } from '@/utils/processAction'
import { resolveCloseIntent } from '@/utils/closePreference'
import {
  isNavigationFailure,
  loadRouteLocation,
  NavigationFailureType,
  useRoute,
  useRouter
} from 'vue-router'
import { createSettingsNavigation, settingsNavigationKey } from '@/composables/settingsNavigation'
import {
  createDeviceConnectionNavigation,
  deviceConnectionNavigationKey
} from '@/composables/deviceConnectionNavigation'
import { installModalDragging } from '@/utils/modal-drag.js'

const ChatBot = defineAsyncComponent(() => import('@/components/ChatBot.vue'))
const windowShell = createWindowShellAdapter({
  onCloseRequested: () => handleWindowControl('close')
})
const closeModal = ref(false)
const closeBusy = ref(false)
const closeTrayAvailable = ref(true)
const closeChoice = ref('tray')
const closeRemember = ref(false)
const closeError = ref('')
const closeStatus = ref('')
let closePollTimer = null
const {
  active: windowShellActive,
  busy: windowShellBusy,
  controls: windowShellControls,
  controlSide: windowShellControlSide,
  capabilities: windowShellCapabilities,
  state: windowShellState
} = windowShell

let disposeModalDrag = null

const showFeedback = ref(false)
provide('show_feedback', showFeedback)
const helpSection = ref('')
function openHelp(action) {
  if (action === 'feedback') showFeedback.value = true
  else if (action === 'documentation') void router.push({ name: 'doc' })
  else if (action === 'about' || action === 'changelog') helpSection.value = action
}
// Desktop sider state. Narrow windows collapse it until the user toggles it by hand.
const sidebarCollapsed = ref(false)
const sidebarHidden = ref(false)
const sidebarPreferences = useSidebarPreferences()
const sidebarEditorOpen = ref(false)
const sidebarEditorRequest = ref({})
function openSidebarEditor(request = {}) {
  sidebarEditorRequest.value = request
  sidebarEditorOpen.value = true
}
const userToggledSidebar = ref(false)
function toggleSidebar() {
  if (sidebarHidden.value) {
    expandSidebar()
    return
  }
  userToggledSidebar.value = true
  sidebarCollapsed.value = !sidebarCollapsed.value
}
function expandSidebar() {
  userToggledSidebar.value = true
  sidebarHidden.value = false
  sidebarCollapsed.value = false
}
// Mobile page drawer holding the full sidebar.
const mobileMenuOpen = ref(false)
const sidebarVisible = computed(() =>
  isMobileNav.value ? mobileMenuOpen.value : !sidebarHidden.value
)
const fallbackAppMenu = computed(
  () => isMobileNav.value || sidebarHidden.value || sidebarCollapsed.value
)
const appMenuVisible = computed(
  () => isMobileNav.value || sidebarHidden.value || !sidebarCollapsed.value
)
function handleViewAction(action) {
  if (action === 'toggle-sidebar') {
    if (isMobileNav.value) mobileMenuOpen.value = !mobileMenuOpen.value
    else sidebarHidden.value = !sidebarHidden.value
  } else if (action === 'edit-sidebar') {
    openSidebarEditor()
  }
}
const route = useRoute()
const router = useRouter()
const settingsDirectoryMode = computed(() => route.meta.settingsSidebar === true)
const settingsReturnTo = ref('/')
const settingsBackgroundRoute = shallowRef(null)
const contentRoute = computed(() =>
  settingsDirectoryMode.value ? settingsBackgroundRoute.value : route
)
watch(
  settingsDirectoryMode,
  async (open) => {
    if (!open || settingsBackgroundRoute.value) return
    try {
      const background = await loadRouteLocation(router.resolve('/'))
      if (!settingsBackgroundRoute.value) settingsBackgroundRoute.value = background
    } catch (error) {
      console.error('设置背景页加载失败', error)
    }
  },
  { immediate: true }
)
const settingsNavigation = createSettingsNavigation()
provide(settingsNavigationKey, settingsNavigation)
const deviceConnectionNavigation = createDeviceConnectionNavigation()
provide(deviceConnectionNavigationKey, deviceConnectionNavigation)
async function openDeviceConnection(action) {
  if (configProfiles.busy.value || configProfiles.stale.value || configProfiles.pendingReload.value)
    return
  if (action === 'test' && (running.value || deviceConnectionNavigation.locked.value)) return
  const failure = await router.push({ name: 'task-settings', hash: '#task-devices' })
  if (failure && !isNavigationFailure(failure, NavigationFailureType.duplicated)) return
  deviceConnectionNavigation.open(action)
}
const removeSettingsHook = router.afterEach((to, from, failure) => {
  if (failure) return
  if (to.meta.settings && !from.meta.settings && from.matched.length) {
    settingsReturnTo.value = from.fullPath
    settingsBackgroundRoute.value = from
  }
})
onBeforeUnmount(removeSettingsHook)
function leaveSettings() {
  void router.push(settingsReturnTo.value)
}
const showChatBot = ref(false)
const chatBotMounted = ref(false)
function openChatBot() {
  mobileMenuOpen.value = false
  chatBotMounted.value = true
  showChatBot.value = true
}

import { darkTheme, dateZhCN, zhCN } from 'naive-ui'

import hljs from 'highlight.js/lib/core'
import json from 'highlight.js/lib/languages/json'

hljs.registerLanguage('json', json)

import { useConfigStore } from '@/stores/config'
import { useMowerStore } from '@/stores/mower'
import { useGuiStore } from '@/stores/gui'
import { usePlanStore, useRescuePlanStore } from '@/stores/plan'
import { useUpdateNoticeStore } from '@/stores/updateNotice'
import { useResourceVersionStore } from '@/stores/resourceVersion'

import { usewatermarkStore } from '@/stores/watermark'

const watermarkStore = usewatermarkStore()
const { getwatermarkinfo } = watermarkStore

const watermarkData = ref('mower')

const config_store = useConfigStore()
const { load_config, load_shop, load_item } = config_store
const {
  resource_update_enable,
  resource_update_auto_update,
  simulator,
  start_automatically,
  theme: themePreference,
  webview,
  adb
} = storeToRefs(config_store)
const theme = useResolvedTheme(themePreference)
// Also applied to the page drawer, which teleports out of the provider element.
const mowerCssVariables = computed(() =>
  theme.value === 'dark' ? mowerDarkCssVariables : mowerLightCssVariables
)
let activeThemeColours = null
let themeControlWrite = false
watch(
  theme,
  () => {
    if (themeControlWrite) return
    if (activeThemeColours) {
      activeThemeColours = null
      document.documentElement.classList.remove('mower-theme-colours')
    }
    document.documentElement.classList.add('mower-theme-changing')
  },
  { flush: 'sync' }
)
watchPostEffect(() => {
  // Track every edit, including a switch back to the initial theme in one frame.
  void theme.value
  const root = document.documentElement
  if (!root.classList.contains('mower-theme-changing')) return
  // Vue must commit component styles before the browser restores transitions.
  void root.offsetWidth
  root.classList.remove('mower-theme-changing')
})

async function setThemeWithTransition(nextTheme) {
  const root = document.documentElement
  const reduceMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
  if (reduceMotion) {
    activeThemeColours = null
    root.classList.remove('mower-theme-colours')
    root.classList.add('mower-theme-changing')
    themePreference.value = nextTheme
    await nextTick()
    void root.offsetWidth
    root.classList.remove('mower-theme-changing')
    return
  }
  if (nextTheme === themePreference.value) return

  const change = {}
  activeThemeColours = change
  root.classList.add('mower-theme-colours')
  void root.offsetWidth
  try {
    themeControlWrite = true
    try {
      themePreference.value = nextTheme
    } finally {
      themeControlWrite = false
    }
    await nextTick()
    if (activeThemeColours !== change) return
    void root.offsetWidth
    const transitions = document
      .getAnimations()
      .filter((animation) => typeof animation.transitionProperty === 'string')
    await Promise.allSettled(transitions.map((animation) => animation.finished))
  } finally {
    if (activeThemeColours === change) {
      activeThemeColours = null
      root.classList.remove('mower-theme-colours')
    }
  }
}

provide('set_theme_with_transition', setThemeWithTransition)
const windowShellTitle = computed(() =>
  formatWindowTitle({
    version: windowTitleVersion.value,
    instanceName: windowShell.metadata.instanceName
  })
)

// 标题栏副信息：实例@端口 与 模拟器@adb端口。实例名已写进系统窗口标题（formatWindowTitle），
// 这里标题栏内再补两个 @端口：mower 端口 = 前端服务所在端口（webview 与后端同源），
// adb 端口 = ADB 连接地址（形如 127.0.0.1:62001）的端口段。
const mowerPort = computed(() => window.location.port || '')
// 模拟器标题带上多开实例名称：同一模拟器的多个多开实例只写 MuMu12@16384 无法区分。
// 没填实例名称时保持原样。
const emulatorName = computed(() =>
  formatEmulatorLabel({
    name: simulator.value?.name,
    instanceName: config_store.device_profile?.instance_name
  })
)
const adbPort = computed(() => {
  const addr = adb.value || ''
  const idx = addr.lastIndexOf(':')
  return idx === -1 ? '' : addr.slice(idx + 1)
})

const plan_store = usePlanStore()
plan_store.set_advanced_settings_source(() => config_store.build_advanced_settings())
const { operators } = storeToRefs(plan_store)
const { load_plan, load_operators } = plan_store

const mower_store = useMowerStore()
const {
  ws,
  running,
  log_lines,
  auto_start_handled,
  desktop_startup_handled,
  updates_enabled,
  deployment
} = storeToRefs(mower_store)
const { get_running, listen_ws } = mower_store
const guiStore = useGuiStore()
const { softwareVersionDisplay } = storeToRefs(guiStore)

const update_notice_store = useUpdateNoticeStore()
const { notice: updateNotice } = storeToRefs(update_notice_store)
const { ackUpdateNotice, loadUpdateNotice } = update_notice_store
const showUpdateNoticeModal = ref(false)

const resource_version_store = useResourceVersionStore()
const { installResource, loadResourceVersion, loadResourceVersionLocal, loadResourceJob } =
  resource_version_store
const softwareVersion = computed(() => {
  const snapshot =
    windowShell.metadata.version || (watermarkData.value === 'mower' ? '' : watermarkData.value)
  const sep = snapshot.lastIndexOf(' - ')
  return sep === -1 ? snapshot : snapshot.slice(0, sep)
})
const resourceVersion = computed(() => resource_version_store.info.current_display || '')
const windowTitleVersion = computed(() =>
  resourceVersion.value
    ? `${softwareVersion.value} - ${resourceVersion.value}`
    : softwareVersion.value
)

const axios = inject('axios')
const configProfiles = createConfigProfiles({
  axios,
  config: config_store,
  plan: plan_store,
  rescuePlan: useRescuePlanStore(),
  beforeChange: async () => {
    await sidebarPreferences.flush()
    if (sidebarPreferences.initialized.value && sidebarPreferences.persistenceError.value) {
      throw new Error('侧边栏布局尚未保存，请在编辑侧边栏窗口中重试后再切换档案。')
    }
  },
  blocked: () => !loaded.value || running.value || deviceConnectionNavigation.locked.value
})
const appMenuProps = computed(() => ({
  theme: theme.value,
  showInstanceMenu: true,
  instanceName: windowShell.metadata.instanceName || '默认实例',
  mowerPort: mowerPort.value,
  emulatorName: emulatorName.value,
  adbPort: adbPort.value,
  connectionTestDisabled: running.value || deviceConnectionNavigation.locked.value,
  profileState: configProfiles.state.value,
  profileWriteDisabled: configProfiles.writeDisabled.value,
  profileReadDisabled: configProfiles.readDisabled.value,
  sidebarVisible: sidebarVisible.value
}))
const appMenuListeners = {
  'connection-action': openDeviceConnection,
  'profile-action': configProfiles.open,
  'help-action': openHelp,
  'view-action': handleViewAction
}
const profileResponseInterceptor = axios.interceptors?.response?.use(
  (response) => response,
  async (failure) => {
    await configProfiles.observeFailure(failure)
    throw failure
  }
)
onBeforeUnmount(() => {
  if (profileResponseInterceptor !== undefined)
    axios.interceptors.response.eject(profileResponseInterceptor)
})

function finishClosePolling(pendingKey) {
  clearTimeout(closePollTimer)
  closePollTimer = null
  sessionStorage.removeItem(pendingKey)
  closeBusy.value = false
}

async function pollCloseOperation(pending, base, pendingKey) {
  if (Date.now() - pending.startedAt > 240000) {
    closeError.value = '等待退出超时，请检查当前实例和进程操作日志'
    finishClosePolling(pendingKey)
    return
  }
  try {
    const data = await readProcessActionStatus({ axios, base, pending })
    closeStatus.value = data.message || '正在停止当前实例…'
    if (data.status === 'running') {
      closePollTimer = setTimeout(() => pollCloseOperation(pending, base, pendingKey), 1000)
      return
    }
    if (data.status === 'failed') {
      closeError.value = data.message || '彻底退出失败，请检查进程操作日志'
    }
    finishClosePolling(pendingKey)
  } catch (error) {
    if (error.response) {
      closeError.value = error.response.data?.message || error.message
    } else {
      // The old HTTP server normally disappears before the desktop window
      // closes. Connection loss alone cannot prove that the exit succeeded.
      closeStatus.value = '当前实例连接已断开，请确认托盘图标和进程已退出'
    }
    finishClosePolling(pendingKey)
  }
}

async function performWindowClose(choice, remember) {
  if (closeBusy.value) return false
  if (choice === 'tray' && !closeTrayAvailable.value) {
    closeError.value = '未启用系统托盘，无法收起窗口'
    return false
  }
  closeBusy.value = true
  closeError.value = ''
  closeStatus.value = ''
  let submitted = false
  try {
    const api = window.pywebview?.api
    if (api?.set_close_preference) {
      const saved = await api.set_close_preference(choice, remember)
      if (saved !== true) throw new Error('关闭偏好保存失败')
    }
    if (choice === 'tray') {
      const closed = await windowShell.close()
      if (!closed) throw new Error('无法关闭当前窗口')
      closeModal.value = false
      return true
    }
    const base = (import.meta.env.VITE_HTTP_URL || '') + '/process-control'
    const pendingKey = 'mower-process-control:' + base
    if (sessionStorage.getItem(pendingKey)) {
      throw new Error('已有进程操作正在进行，请等待完成后重试')
    }
    const saves = createSaveCoordinator(config_store, plan_store)
    const { pending } = await submitProcessAction({
      axios,
      saves,
      action: 'stop',
      base,
      pendingKey
    })
    submitted = true
    closeStatus.value = '彻底退出请求已提交，正在等待任务停止和实例退出…'
    void pollCloseOperation(pending, base, pendingKey)
    return true
  } catch (error) {
    closeError.value =
      error.response?.data?.message || error.message || '退出结果尚未确认，请检查托盘和进程操作状态'
    return false
  } finally {
    if (!submitted) closeBusy.value = false
  }
}

async function handleWindowControl(action) {
  if (action !== 'close') return windowShell.runControl(action)
  if (closeBusy.value) return false
  const api = window.pywebview?.api
  if (!api?.get_close_preference) return windowShell.close()
  try {
    const pref = await api.get_close_preference()
    if (pref.managed === true) return windowShell.close()
    const intent = resolveCloseIntent(pref)
    closeTrayAvailable.value = intent.trayAvailable
    closeChoice.value = intent.choice
    closeRemember.value = intent.remember
    closeStatus.value = ''
    closeError.value = ''
    if (!intent.shouldPrompt) {
      if (intent.choice === 'exit') closeModal.value = true
      return performWindowClose(intent.choice, true)
    }
    closeModal.value = true
    return true
  } catch (error) {
    // An unreadable preference must not silently result in an exit.
    closeTrayAvailable.value = false
    closeChoice.value = 'exit'
    closeRemember.value = false
    closeError.value = error.message || '读取关闭设置失败'
    closeModal.value = true
    return false
  }
}
function start() {
  running.value = true
  log_lines.value = []
  axios.get(`${import.meta.env.VITE_HTTP_URL}/start/0`)
}

function apply_zoom(scale) {
  const s = Number(scale) || 1.0
  document.documentElement.style.zoom = s
  document.documentElement.style.setProperty('--mower-zoom', String(s))
  document.documentElement.style.setProperty('--mower-zoom-inverse', String(1 / s))
  actions_on_resize()
}

const isMobileNav = ref(false)
const mobile = ref(false)
provide('mobile', mobile)
// The page drawer belongs to the mobile layout; widening the window closes it.
watch(isMobileNav, (mobileNav) => {
  if (!mobileNav) {
    mobileMenuOpen.value = false
  }
})

function actions_on_resize() {
  const zoom = Number.parseFloat(document.documentElement.style.zoom) || 1
  const width = (window.innerWidth || document.documentElement.clientWidth) / zoom
  isMobileNav.value = width < 680
  mobile.value = width < 850
  if (!userToggledSidebar.value) {
    sidebarCollapsed.value = width < 850
  }
}

const loaded = inject('loaded')

const renderedChangelog = ref('')
let changelogRendered = false
async function renderChangelog() {
  if (changelogRendered) return
  changelogRendered = true
  const [{ default: markdownit }, { default: externalLink }] = await Promise.all([
    import('markdown-it'),
    import('markdown-it-external-link')
  ])
  const md = markdownit({ html: true, breaks: true }).use(externalLink, {
    externalTarget: '_blank',
    rel: 'noopener noreferrer'
  })
  renderedChangelog.value = md.render(updateNotice.value.changelog)
}

async function handleUpdateNoticeAck() {
  if (!updateNotice.value.current_version) {
    showUpdateNoticeModal.value = false
    return
  }
  try {
    await ackUpdateNotice(updateNotice.value.current_version)
    showUpdateNoticeModal.value = false
  } catch (error) {
    console.error('failed to acknowledge update notice', error)
  }
}

async function loadStartupUpdateNotice() {
  try {
    const notice = await loadUpdateNotice()
    showUpdateNoticeModal.value = notice.should_show
    if (notice.should_show) await renderChangelog()
  } catch (error) {
    console.error('failed to load update notice', error)
    showUpdateNoticeModal.value = false
  }
}

const operators_with_free_current = computed(() => {
  return [
    { value: 'Current', label: 'Current' },
    { value: 'Free', label: 'Free' }
  ].concat(operators.value)
})

onMounted(async () => {
  void windowShell.initialize()
  disposeModalDrag = installModalDragging()
  actions_on_resize()
  window.addEventListener('resize', () => {
    actions_on_resize()
  })

  const params = new URLSearchParams(document.location.search)
  const token = params.get('token')
  const instanceName = params.get('instance_name')
  provide('token', token)
  axios.defaults.headers.common['token'] = token
  void guiStore.load()
  if (!(await configProfiles.bootstrap())) return
  void sidebarPreferences.initialize()
  // getwatermarkinfo 独立并行，失败不影响主流程（watermark 仅装饰用途）
  getwatermarkinfo()
    .then((info) => {
      watermarkData.value = info
    })
    .catch(() => {})
  const optionListsRequest = Promise.allSettled([load_shop(), load_item()]).then((results) => {
    for (const result of results) {
      if (result.status === 'rejected')
        console.error('failed to load setting options', result.reason)
    }
  })
  await Promise.all([load_config(), load_plan(), load_operators(), get_running()])

  document.title = instanceName
    ? `${instanceName} - arknights-mower`
    : simulator.value?.name
      ? `${simulator.value.name} - arknights-mower`
      : 'arknights-mower'

  if (updates_enabled.value === true)
    axios
      .post(
        `${import.meta.env.VITE_HTTP_URL || ''}/software-update/auto-check`,
        {},
        {
          headers: { 'X-Mower-Update': '1' }
        }
      )
      .catch((error) => console.error('failed to request automatic software check', error))

  // Desktop startup owns automatic installation and task admission.
  const resourceUpdateRequest = (async () => {
    try {
      await optionListsRequest
      if (updates_enabled.value === true && (await loadResourceJob())) {
        await Promise.all([load_shop(), load_item(), load_operators()])
      }
      await loadResourceVersionLocal()
      if (updates_enabled.value === true && resource_update_enable.value) {
        const resourceInfo = await loadResourceVersion()
        if (
          !desktop_startup_handled.value &&
          resource_update_auto_update.value &&
          resourceInfo.update_available === true
        ) {
          if (await installResource()) {
            await Promise.all([load_shop(), load_item(), load_operators()])
          }
        }
      }
    } catch (error) {
      console.error('failed to load resource version', error)
    }
  })()

  loaded.value = true
  void loadStartupUpdateNotice()

  const r = RegExp(operators_with_free_current.value.map((x) => "'" + x.value).join('|'))
  hljs.registerLanguage('mower', () => ({
    contains: [
      {
        begin: r,
        end: /'/,
        className: 'operator',
        relevance: 0
      },
      {
        begin: /宿舍黑名单|重设上次房间为空/,
        relevance: 10
      },
      {
        begin: /\b[0-9]{4}-[0-9]{2}-[0-9]{2}\b/,
        className: 'date'
      },
      {
        begin: /[0-9]+:[0-9]+:[0-9]+((\.|,)[0-9]+)?/,
        className: 'time'
      },
      {
        begin: /room_[0-9]_[0-9]|dormitory_[0-9]|central|contact|factory|meeting/,
        className: 'room'
      },
      {
        begin: /INFO/,
        className: 'info'
      },
      {
        begin: /WARNING/,
        className: 'warning'
      },
      {
        begin: /ERROR/,
        className: 'error'
      },
      {
        begin: /Scene [0-9]+:.*/,
        className: 'scene'
      }
    ]
  }))

  if (!ws.value) {
    listen_ws()
  }

  await resourceUpdateRequest
  const importedConfig = sessionStorage.getItem('mower-config-imported') === '1'
  sessionStorage.removeItem('mower-config-imported')
  if (start_automatically.value && !auto_start_handled.value && !importedConfig) {
    start()
  }
})

onBeforeUnmount(() => {
  clearTimeout(closePollTimer)
  disposeModalDrag?.()
  windowShell.dispose()
  activeThemeColours = null
  document.documentElement.classList.remove('mower-theme-colours')
  document.documentElement.classList.remove('mower-theme-changing')
  delete document.documentElement.dataset.windowShellTheme
  delete document.documentElement.dataset.mowerTheme
})

watch(
  [theme, loaded, windowShellActive],
  ([currentTheme, appLoaded, shellActive]) => {
    document.documentElement.dataset.mowerTheme = currentTheme === 'dark' ? 'dark' : 'light'
    if (appLoaded && shellActive) {
      document.documentElement.dataset.windowShellTheme = currentTheme === 'dark' ? 'dark' : 'light'
      window.scrollTo(0, 0)
    }
  },
  { immediate: true, flush: 'sync' }
)

watch(
  () => webview.value?.scale,
  (newScale) => {
    apply_zoom(newScale)
  },
  { immediate: true }
)
</script>

<style>
.n-avatar {
  pointer-events: none !important;
}

.img {
  pointer-events: none !important;
}
</style>

<style scoped>
.tabs {
  height: 100%;
}

.provider {
  --shell-rail-size: 64px;
  height: 100%;
  display: flex;
  flex-direction: column;
}

.provider > .outer-layout {
  flex: 1 1 auto;
  min-height: 0;
  height: auto;
}

.app-menu-header {
  display: flex;
  flex: 0 0 36px;
  min-width: 0;
  align-items: center;
  padding-left: 16px;
  background: var(--mower-surface);
  border-bottom: 1px solid var(--mower-divider);
}

.layout-container {
  height: 100%;
}
</style>

<style lang="scss">
html,
body {
  width: 100%;
  height: 100%;
  margin: 0;
  padding: 0;
  overflow: hidden;
}

#app {
  height: 100%;
  width: 100%;
}

.provider--window-shell {
  --window-shell-frame-surface: #faf9f7;
  --window-shell-content-surface: #fff;
  --window-shell-content-shadow-left: rgba(63, 55, 47, 0.13);
  --window-shell-content-shadow-top: rgba(63, 55, 47, 0.07);
  --window-shell-content-shadow-corner: rgba(63, 55, 47, 0.09);
  --window-shell-scrollbar-thumb: rgba(46, 43, 40, 0.2);
  --window-shell-scrollbar-thumb-hover: rgba(46, 43, 40, 0.34);
  display: flex;
  flex-direction: column;
  box-sizing: border-box;
  overflow: hidden;
  background: var(--window-shell-frame-surface);
}

html[data-window-shell-theme='dark'] .provider--window-shell {
  --window-shell-frame-surface: #18181c;
  --window-shell-content-surface: #101014;
  --window-shell-content-shadow-left: rgba(0, 0, 0, 0.34);
  --window-shell-content-shadow-top: rgba(0, 0, 0, 0.2);
  --window-shell-content-shadow-corner: rgba(0, 0, 0, 0.26);
  --window-shell-scrollbar-thumb: rgba(255, 255, 255, 0.18);
  --window-shell-scrollbar-thumb-hover: rgba(255, 255, 255, 0.3);
  background: var(--window-shell-frame-surface);
}

.provider--window-shell .outer-layout {
  flex: 1 1 auto;
  min-height: 0;
  height: auto;
  background: var(--window-shell-frame-surface);
}

.sidebar-navigation {
  flex: 1 1 0;
  min-height: 0;
  overflow: hidden;
}

.sidebar-drawer {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}

.provider--window-shell .n-layout-sider {
  background: var(--window-shell-frame-surface);
}

.provider--window-shell .n-layout-sider__border {
  background: transparent;
}

.layout-content-container {
  container-type: inline-size;
  container-name: main-content;
  flex: 1 1 auto;
  min-width: 0;
  min-height: 0;
}

.navigation-footer {
  flex: none;
  z-index: 10;
}

.provider--window-shell .layout-content-container {
  position: relative;
  z-index: 1;
  overflow: hidden;
  background: var(--window-shell-content-surface);
  box-sizing: border-box;
  border-radius: 10px 0 0 0;
  box-shadow:
    -7px 0 18px -14px var(--window-shell-content-shadow-left),
    0 -6px 16px -14px var(--window-shell-content-shadow-top),
    -5px -5px 20px -16px var(--window-shell-content-shadow-corner);
}

/* shadcn / 现代精致输入框（n-input / n-input-number）：
   聚焦时直接高亮边框并添加 2px 贴身高亮环，杜绝过大外扩（4px）被子窗口边框/overflow 裁剪 */
.n-input {
  --n-height: 36px !important;
  --n-border-radius: 8px !important;
  --n-border: 1px solid #e4e4e7 !important;
  --n-border-hover: 1px solid #36ad6a !important;
  --n-border-focus: 1px solid #18a058 !important;
  --n-color: #ffffff !important;
  --n-color-hover: #ffffff !important;
  --n-color-focus: #ffffff !important;
  --n-padding-left: 12px !important;
  --n-padding-right: 12px !important;
  --n-padding-vertical: 0 !important;
  --n-text-color: #09090b !important;
  --n-placeholder-color: #71717a !important;
  --n-box-shadow-focus: 0 0 0 2px rgba(24, 160, 88, 0.2) !important;
}
html[data-mower-theme='dark'] .n-input {
  --n-border: 1px solid #27272a !important;
  --n-border-hover: 1px solid #7fe7c4 !important;
  --n-border-focus: 1px solid #63e2b7 !important;
  --n-color: #101014 !important;
  --n-color-hover: #101014 !important;
  --n-color-focus: #101014 !important;
  --n-text-color: #fafafa !important;
  --n-placeholder-color: #71717a !important;
  --n-box-shadow-focus: 0 0 0 2px rgba(99, 226, 183, 0.25) !important;
}

/* 下拉选择框（n-select）的触发器沿用输入框外观。 */
.n-base-selection {
  --n-height: 36px !important;
  --n-border-radius: 8px !important;
  --n-border: 1px solid #e4e4e7 !important;
  --n-border-hover: 1px solid #36ad6a !important;
  --n-border-focus: 1px solid #18a058 !important;
  --n-border-active: 1px solid #18a058 !important;
  --n-color: #ffffff !important;
  --n-color-active: #ffffff !important;
  --n-box-shadow-focus: 0 0 0 2px rgba(24, 160, 88, 0.2) !important;
  --n-box-shadow-active: 0 0 0 2px rgba(24, 160, 88, 0.2) !important;
  --n-text-color: #09090b !important;
  --n-placeholder-color: #71717a !important;
  --n-padding-single: 0 12px !important;
  --n-font-size: 14px !important;
}
html[data-mower-theme='dark'] .n-base-selection {
  --n-border: 1px solid #27272a !important;
  --n-border-hover: 1px solid #7fe7c4 !important;
  --n-border-focus: 1px solid #63e2b7 !important;
  --n-border-active: 1px solid #63e2b7 !important;
  --n-color: #101014 !important;
  --n-color-active: #101014 !important;
  --n-text-color: #fafafa !important;
  --n-placeholder-color: #71717a !important;
  --n-box-shadow-focus: 0 0 0 2px rgba(99, 226, 183, 0.25) !important;
  --n-box-shadow-active: 0 0 0 2px rgba(99, 226, 183, 0.25) !important;
}

/* 提升处于聚焦/激活状态输入框的层叠层级，避免被相邻单元格、边框或相邻按钮遮挡 */
.n-input:focus-within,
.n-base-selection:focus-within {
  position: relative;
  z-index: 2;
}

/* 只给「含输入框/下拉」的单元格加定位：position:relative 会把单元格提到定位层，
   无输入框的表格（如运行日志页任务表）跟着提层会盖住 .log-bg 背景图 */
.n-table td:has(.n-input, .n-base-selection) {
  position: relative;
}

.n-table td:has(.n-input:focus-within),
.n-table td:has(.n-base-selection:focus-within) {
  z-index: 3;
}

html.mower-theme-changing *,
html.mower-theme-changing *::before,
html.mower-theme-changing *::after {
  transition: none !important;
}

html.mower-theme-colours,
html.mower-theme-colours *,
html.mower-theme-colours *::before,
html.mower-theme-colours *::after {
  transition-property: color, background-color, border-color, box-shadow, fill, stroke !important;
  transition-duration: 180ms !important;
  transition-timing-function: ease-out !important;
  transition-delay: 0s !important;
}

/* naive-ui 弹窗 teleport 到 <body>，不在 .provider--window-shell 内，
   所以上面的滚动条样式和 --window-shell-scrollbar-thumb 变量都够不到它。
   mower.css 已让 .n-modal 的卡片/对话框内容节点滚动（.n-card-content / .n-dialog__content），
   这里把同名滚动条样式应用到这些 body 级浮层，并把变量提到 :root 兜底。 */
:root {
  --window-shell-scrollbar-thumb: rgba(46, 43, 40, 0.2);
  --window-shell-scrollbar-thumb-hover: rgba(46, 43, 40, 0.34);
}
html[data-mower-theme='dark'],
html[data-window-shell-theme='dark'] {
  --window-shell-scrollbar-thumb: rgba(255, 255, 255, 0.22);
  --window-shell-scrollbar-thumb-hover: rgba(255, 255, 255, 0.36);
}

.provider *,
.provider--window-shell *,
.n-modal,
.n-modal *,
.n-drawer,
.n-drawer *,
.n-popover,
.n-popover *,
.n-dropdown-menu,
.n-dropdown-menu *,
.n-select-menu,
.n-select-menu * {
  scrollbar-color: var(--window-shell-scrollbar-thumb) transparent;
  scrollbar-width: thin;
}

.provider *::-webkit-scrollbar,
.provider--window-shell *::-webkit-scrollbar,
.n-modal *::-webkit-scrollbar,
.n-drawer *::-webkit-scrollbar,
.n-popover *::-webkit-scrollbar,
.n-dropdown-menu *::-webkit-scrollbar,
.n-select-menu *::-webkit-scrollbar {
  width: 10px;
  height: 10px;
}

.provider *::-webkit-scrollbar-track,
.provider *::-webkit-scrollbar-corner,
.provider--window-shell *::-webkit-scrollbar-track,
.provider--window-shell *::-webkit-scrollbar-corner,
.n-modal *::-webkit-scrollbar-track,
.n-modal *::-webkit-scrollbar-corner,
.n-drawer *::-webkit-scrollbar-track,
.n-drawer *::-webkit-scrollbar-corner,
.n-popover *::-webkit-scrollbar-track,
.n-popover *::-webkit-scrollbar-corner,
.n-dropdown-menu *::-webkit-scrollbar-track,
.n-dropdown-menu *::-webkit-scrollbar-corner,
.n-select-menu *::-webkit-scrollbar-track,
.n-select-menu *::-webkit-scrollbar-corner {
  background: transparent;
}

.provider *::-webkit-scrollbar-thumb,
.provider--window-shell *::-webkit-scrollbar-thumb,
.n-modal *::-webkit-scrollbar-thumb,
.n-drawer *::-webkit-scrollbar-thumb,
.n-popover *::-webkit-scrollbar-thumb,
.n-dropdown-menu *::-webkit-scrollbar-thumb,
.n-select-menu *::-webkit-scrollbar-thumb {
  min-height: 36px;
  background: var(--window-shell-scrollbar-thumb);
  background-clip: content-box;
  border: 3px solid transparent;
  border-radius: 999px;
}

.provider *::-webkit-scrollbar-thumb:hover,
.provider--window-shell *::-webkit-scrollbar-thumb:hover,
.n-modal *::-webkit-scrollbar-thumb:hover,
.n-drawer *::-webkit-scrollbar-thumb:hover,
.n-popover *::-webkit-scrollbar-thumb:hover,
.n-dropdown-menu *::-webkit-scrollbar-thumb:hover,
.n-select-menu *::-webkit-scrollbar-thumb:hover {
  background: var(--window-shell-scrollbar-thumb-hover);
  background-clip: content-box;
}

.provider *::-webkit-scrollbar-button,
.provider--window-shell *::-webkit-scrollbar-button,
.n-modal *::-webkit-scrollbar-button,
.n-drawer *::-webkit-scrollbar-button,
.n-popover *::-webkit-scrollbar-button,
.n-dropdown-menu *::-webkit-scrollbar-button,
.n-select-menu *::-webkit-scrollbar-button {
  display: none;
  width: 0;
  height: 0;
}

/* 修复界面缩放（CSS zoom）下 Naive UI / vueuc 浮层（popover / dropdown / select / tooltip / date-picker 等）坐标二次缩放漂移 */
.v-binder-follower-container {
  zoom: var(--mower-zoom-inverse, 1);
}

.v-binder-follower-content > * {
  zoom: var(--mower-zoom, 1);
}

.n-tab-pane {
  flex-grow: 1;
  display: flex;
  flex-direction: column;
  overflow: auto;
}

.n-card-header__main {
  display: flex;
  align-items: center;
  gap: 6px;
}

td {
  height: 34px;
}

.table-space {
  padding-right: 20px;
}

.external-container {
  max-width: 600px;
  margin: 0 auto;
}

.n-checkbox {
  align-items: center;
}

.n-form-item {
  margin-top: 12px;

  &:first-child {
    margin-top: 0;
  }
}

.dialog-btn {
  /* 与旁边的路径输入框（36px）对齐：高度拉到 36px；间距 8px 给输入框聚焦 ring(外扩4px) 留空档 */
  margin-left: 8px;
  --n-height: 36px !important;
}

.report-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  /* 让内容在水平方向上居中 */
  justify-content: center;
  /* 让内容在垂直方向上居中 */

  width: 300px;
  height: 200px;
  padding: 20px 20px 80px 20px;
  border: 1px solid #ccc;
}

.n-checkbox .n-checkbox__label {
  flex-grow: 1;
  display: flex;
  align-items: center;
  padding-right: 0;
}

.outer-layout {
  position: relative;
  height: 100%;
}

/* 水印只覆盖内容区，并固定在内容区上，不随页面滚动；侧栏和底部导航保持清晰。 */
.n-watermark-container.content-watermark {
  position: absolute;
  inset: 0;
  pointer-events: none;
}

@media (prefers-reduced-motion: reduce) {
  .outer-layout .n-layout-sider {
    transition: none;
  }
}

.outer-layout > .n-layout-scroll-container {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}

.layout-content-container > .n-layout-scroll-container {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: auto;
  gap: 8px;
  align-items: center;
}

.home-container {
  padding: 12px;
  flex-grow: 1;
  display: flex;
  flex-direction: column;
  gap: 8px;
  width: calc(100% - 24px);
  height: calc(100% - 24px);
  position: relative;
}

pre {
  word-break: break-all !important;
  font-family:
    'Cascadia Mono', Consolas, 'Microsoft YaHei', 'SF Mono', 'Menlo', 'PingFang SC', monospace !important;
}

.n-dynamic-input-item__action {
  align-self: center !important;
}

ul,
ol {
  padding-left: 18px;
  margin: 0;
}

.card-title {
  font-weight: 500;
  font-size: 18px;
  white-space: nowrap;
}
</style>
