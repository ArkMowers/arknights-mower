<script setup>
import { useConfigStore } from '@/stores/config'
import { useMowerStore } from '@/stores/mower'
import { storeToRefs } from 'pinia'
import { computed, inject, onMounted, onUnmounted, provide, ref } from 'vue'
import ChatBotSetting from '@/components/ChatBotSetting.vue'
import SoftwareUpdate from '@/components/SoftwareUpdate.vue'
import MaaUpdates from '@/components/MaaUpdates.vue'
import NetworkSettings from '@/components/NetworkSettings.vue'
import ConfigBackup from '@/components/ConfigBackup.vue'
import ConfigProfilesSettings from '@/components/ConfigProfilesSettings.vue'
import { settingsSectionKey } from '@/composables/settingsNavigation'
import SettingsSection from '@/components/SettingsSection.vue'
import SoftwareVersionPreference from '@/components/SoftwareVersionPreference.vue'
import VersionWatermarkPreference from '@/components/VersionWatermarkPreference.vue'
import LogBackgroundPreference from '@/components/LogBackgroundPreference.vue'
import SettingsSegmented from '@/components/SettingsSegmented.vue'
import InterfaceIcon from '@vicons/fluent/es/PaintBrush24Regular'
import NotifyIcon from '@vicons/fluent/es/Alert24Regular'
import UpdateIcon from '@vicons/fluent/es/CloudSync24Regular'
import DataIcon from '@vicons/fluent/es/Database24Regular'
import SunIcon from '@vicons/fluent/es/WeatherSunny24Regular'
import MoonIcon from '@vicons/fluent/es/WeatherMoon24Regular'
import SystemIcon from '@vicons/fluent/es/Desktop24Regular'

defineOptions({ name: 'MowerSettings' })
provide(settingsSectionKey, null)

const sections = [
  {
    id: 'mower-interface',
    title: '界面与窗口',
    icon: InterfaceIcon
  },
  {
    id: 'mower-notifications',
    title: '通知与助手',
    icon: NotifyIcon
  },
  {
    id: 'mower-profiles',
    title: '档案与运行',
    icon: DataIcon
  },
  {
    id: 'mower-updates',
    title: '网络与更新',
    icon: UpdateIcon
  },
  {
    id: 'mower-data',
    title: '数据与维护',
    icon: DataIcon
  }
]
const section = Object.fromEntries(sections.map((item) => [item.id, item]))

const config_store = useConfigStore()
const inheritsFromManager = (key) =>
  config_store.manager_owned_device && config_store.manager_inherited_settings?.includes(key)
const showExtraSettings = computed(
  () => !config_store.manager_owned_device || config_store.extra_settings_visible === true
)
const { updates_enabled, running } = storeToRefs(useMowerStore())
const mobile = inject('mobile')
const { theme, webview, runtime_platform, screenshot, screenshot_archive_limit_mb } =
  storeToRefs(config_store)
const setTheme = inject('set_theme_with_transition', (value) => (theme.value = value))
const themeOptions = [
  { value: 'light', label: '亮色', icon: SunIcon },
  { value: 'dark', label: '暗色', icon: MoonIcon },
  { value: 'system', label: '跟随系统', icon: SystemIcon }
]

const archive_limit_gib = computed({
  get: () => screenshot_archive_limit_mb.value / 1024,
  set: (value) => {
    if (Number.isFinite(value))
      screenshot_archive_limit_mb.value = Math.max(0, Math.round(value * 1024))
  }
})

const hide_macos_menu_bar = computed({
  get: () => !webview.value.tray,
  set: (hidden) => (webview.value.tray = !hidden)
})

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
  { label: '恢复上次状态', value: 'last' },
  { label: '普通窗口', value: 'normal' },
  { label: '最大化窗口', value: 'maximized' }
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
</script>

<template>
  <div class="mower-settings-panels settings-page">
    <SettingsSection v-bind="section['mower-interface']" data-task-editor="mower-interface">
      <n-card id="appearance-settings" title="常规">
        <n-form
          class="settings-row-form"
          :label-placement="mobile ? 'top' : 'left'"
          :show-feedback="false"
          label-width="120"
          label-align="left"
        >
          <n-form-item class="appearance-scale-row">
            <template #label>
              <span class="settings-row-copy">
                <span>界面缩放</span>
                <span class="settings-row-description">调整文字与控件大小，点击应用后生效。</span>
              </span>
            </template>
            <div class="desktop-scale-settings">
              <div class="desktop-scale-controls">
                <n-slider
                  v-model:value="new_scale"
                  :step="0.25"
                  :min="0.5"
                  :max="3.0"
                  :marks="scale_marks"
                  :format-tooltip="(x) => `${x * 100}%`"
                  aria-label="界面缩放"
                />
              </div>
              <div class="desktop-scale-toolbar" role="group" aria-label="应用界面缩放">
                <output
                  class="desktop-scale-value"
                  :aria-label="new_scale === webview.scale ? '当前界面缩放' : '待应用的界面缩放'"
                  aria-live="polite"
                  >{{ new_scale === webview.scale ? '当前' : '待应用' }}
                  {{ Math.round(new_scale * 100) }}%</output
                >
                <n-button
                  class="scale-apply"
                  :disabled="new_scale == webview.scale"
                  @click="webview.scale = new_scale"
                >
                  应用
                </n-button>
              </div>
            </div>
          </n-form-item>
          <n-form-item
            label="显示主题"
            class="settings-appearance-row"
            v-if="runtime_platform !== 'android'"
          >
            <SettingsSegmented
              :value="theme"
              :options="themeOptions"
              @update:value="setTheme"
              class="settings-theme-choices"
              label="显示主题"
            />
          </n-form-item>
          <SoftwareVersionPreference />
          <VersionWatermarkPreference />
          <LogBackgroundPreference />
        </n-form>
      </n-card>
      <n-card v-if="runtime_platform !== 'android'" id="window-settings" title="窗口">
        <n-form
          class="settings-row-form"
          :label-placement="mobile ? 'top' : 'left'"
          :show-feedback="false"
          label-width="140"
          label-align="left"
        >
          <n-form-item>
            <template #label>
              <span class="settings-row-copy">
                <span>{{ runtime_platform === 'darwin' ? '隐藏菜单栏图标' : '使用托盘图标' }}</span>
                <span id="tray-description" class="settings-row-description">
                  <template v-if="runtime_platform === 'darwin'">
                    重启生效。独立启动时不创建托盘进程，关闭窗口后仍在后台运行。多开管理器统一提供托盘，静默重启后也保留托盘入口。
                  </template>
                  <template v-else>重启生效。多开管理器启动的实例统一使用管理器托盘。</template>
                </span>
              </span>
            </template>
            <n-switch
              v-if="runtime_platform === 'darwin'"
              v-model:value="hide_macos_menu_bar"
              aria-label="隐藏菜单栏图标"
              aria-describedby="tray-description"
            />
            <n-switch
              v-else
              v-model:value="webview.tray"
              aria-label="使用托盘图标"
              aria-describedby="tray-description"
            />
          </n-form-item>
          <n-form-item v-if="desktopPreferencesReady">
            <template #label>
              <span class="settings-row-copy"
                ><span>关闭窗口</span
                ><span class="settings-row-description">点击窗口关闭按钮时执行的操作。</span></span
              >
            </template>
            <n-select
              :consistent-menu-width="false"
              :value="desktopCloseMode"
              :options="closeOptions"
              :disabled="desktopPreferenceBusy"
              :input-props="{ 'aria-label': '关闭窗口' }"
              @update:value="changeCloseMode"
            />
          </n-form-item>
          <n-form-item v-if="desktopPreferencesReady">
            <template #label>
              <span class="settings-row-copy">
                <span>启动时窗口状态</span>
                <span id="window-launch-description" class="settings-row-description">
                  下次打开 Mower 桌面窗口时生效。“恢复上次状态”会沿用上次的普通窗口或最大化状态。
                </span>
              </span>
            </template>
            <n-select
              :consistent-menu-width="false"
              :value="desktopLaunchMode"
              :options="launchOptions"
              :disabled="desktopPreferenceBusy"
              :input-props="{
                'aria-label': '启动时窗口状态',
                'aria-describedby': 'window-launch-description'
              }"
              @update:value="changeLaunchMode"
            />
          </n-form-item>
          <n-alert v-if="desktopPreferenceError" type="error" :show-icon="false">{{
            desktopPreferenceError
          }}</n-alert>
        </n-form>
      </n-card>
    </SettingsSection>
    <SettingsSection v-bind="section['mower-notifications']" data-task-editor="mower-notifications">
      <email />
      <ChatBotSetting />
    </SettingsSection>
    <SettingsSection v-bind="section['mower-profiles']" data-task-editor="mower-profiles">
      <ConfigProfilesSettings />
      <ProcessControl
        v-if="runtime_platform !== 'android'"
        :running="running"
        :resume-only="!showExtraSettings"
      />
    </SettingsSection>
    <SettingsSection
      v-if="showExtraSettings"
      v-bind="section['mower-updates']"
      data-task-editor="mower-updates"
    >
      <SoftwareUpdate v-if="updates_enabled === true" />
      <ResourceUpdate v-if="updates_enabled === true" />
      <div v-if="updates_enabled === true" class="settings-card-wide"><MaaUpdates /></div>
      <div class="settings-card-wide"><NetworkSettings /></div>
    </SettingsSection>
    <SettingsSection
      v-if="showExtraSettings"
      v-bind="section['mower-data']"
      data-task-editor="mower-data"
    >
      <DepotHistorySettings />
      <n-card id="archive-settings" title="截图与报错归档">
        <n-form
          class="settings-row-form"
          :label-placement="mobile ? 'top' : 'left'"
          :show-feedback="false"
          label-width="140"
          label-align="left"
        >
          <n-form-item v-if="runtime_platform !== 'android'">
            <template #label>
              <span class="settings-row-copy">
                <span>截图保存时间</span>
                <span id="screenshot-retention-description" class="settings-row-description">
                  普通截图保留多久。设为 0 时只为报错归档保留画面。
                  <template v-if="inheritsFromManager('screenshot')">
                    当前使用通用设置，请在多开管理器中修改或选择使用本实例值。
                  </template>
                </span>
              </span>
            </template>
            <mower-input-number
              v-model:value="screenshot"
              :disabled="inheritsFromManager('screenshot')"
              :min="0"
              :input-props="{
                'aria-label': '截图保存时间',
                'aria-describedby': 'screenshot-retention-description'
              }"
            >
              <template #suffix>小时</template>
            </mower-input-number>
          </n-form-item>
          <n-form-item>
            <template #label>
              <span class="settings-row-copy">
                <span>报错归档空间上限</span>
                <span id="screenshot-archive-limit-description" class="settings-row-description">
                  达到上限后清理较早的报错归档，0 表示不限容量。
                  <template v-if="inheritsFromManager('screenshot_archive_limit_mb')">
                    当前使用通用设置，请在多开管理器中修改或选择使用本实例值。
                  </template>
                </span>
              </span>
            </template>
            <mower-input-number
              v-model:value="archive_limit_gib"
              :disabled="inheritsFromManager('screenshot_archive_limit_mb')"
              :min="0"
              :precision="2"
              :input-props="{
                'aria-label': '报错归档空间上限',
                'aria-describedby': 'screenshot-archive-limit-description'
              }"
            >
              <template #suffix>GiB</template>
            </mower-input-number>
          </n-form-item>
        </n-form>
        <p
          v-if="runtime_platform !== 'android' && screenshot === 0"
          class="archive-status"
          role="status"
        >
          日常截图不写盘。发生需归档的异常时，保存此前 5 分钟内缓存的全部画面及后续 5
          分钟截图；内存缓存最多 16 张、32 MiB。
        </p>
        <p
          v-else-if="runtime_platform !== 'android' && screenshot > 0 && screenshot < 5 / 60"
          class="archive-status"
          role="status"
        >
          截图会正常写盘，实际保存时间按 5 分钟处理。
        </p>
        <n-collapse class="archive-details">
          <n-collapse-item title="截图保存说明" name="retention" data-settings-label="截图保存说明">
            <p v-if="runtime_platform !== 'android'">
              普通截图默认保留 1 小时，可填小数；大于 0 且不足 5 分钟时按 5 分钟保留。
            </p>
            <p>报错归档默认上限 5 GiB。普通截图仍按保存时间清理，不受此容量上限影响。</p>
          </n-collapse-item>
        </n-collapse>
      </n-card>
      <ConfigBackup />
    </SettingsSection>
  </div>
</template>

<style scoped lang="scss">
.mower-settings-panels {
  display: grid;
  gap: 28px;
  min-width: 0;
  max-width: none;
  margin: 0;
  padding: 0;
}

.mower-settings-panels :deep(.settings-section) {
  margin: 0;
}

#appearance-settings {
  container: appearance-settings / inline-size;
}

.desktop-scale-settings {
  width: 100%;
  min-width: 0;
}

#appearance-settings :deep(.appearance-scale-row > .n-form-item-blank) {
  width: 340px;
  max-width: 100%;
}

.desktop-scale-controls {
  box-sizing: border-box;
  width: 100%;
  padding: 4px 16px 0;

  .n-slider {
    width: 100%;
  }
}

.desktop-scale-toolbar {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  flex-wrap: nowrap;
  gap: 12px;
  margin-top: 8px;
}

.desktop-scale-value {
  min-width: 0;
  color: var(--mower-text-muted);
  font-size: 13px;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

.scale-apply {
  flex: none;
}

#appearance-settings
  :deep(:is(.settings-appearance-row, .software-version-preference) > .n-form-item-blank) {
  width: 340px;
  max-width: 100%;
}

#appearance-settings :deep(.version-preview-row) {
  grid-template-areas: 'blank' 'feedback';
  row-gap: 0;
  padding-top: 0;
  border-top: 0;
}

.archive-status,
.archive-details {
  margin-top: 16px;
  color: var(--mower-text-muted);
  font-size: 12px;
  line-height: 1.65;
  overflow-wrap: anywhere;
}

#archive-settings :deep(.n-form > .n-form-item:has(> .n-form-item-label)) {
  grid-template-columns: minmax(0, 1fr) auto;
  grid-template-areas: 'label blank' 'feedback feedback';
  column-gap: 20px;
}

#archive-settings :deep(.n-form > .n-form-item > .n-form-item-blank) {
  width: auto;
  max-width: 128px;
}

.archive-details :deep(.n-collapse-item) {
  padding: 0;
  background: transparent;
}

.archive-details p {
  margin: 0 0 8px;
}

@container appearance-settings (max-width: 400px) {
  .desktop-scale-controls :deep(.n-slider-mark) {
    font-size: 12px;
  }
}

@container appearance-settings (max-width: 280px) {
  .desktop-scale-controls {
    padding-inline: 14px;
  }

  .desktop-scale-controls :deep(.n-slider-mark) {
    font-size: 11px;
  }
}
</style>
