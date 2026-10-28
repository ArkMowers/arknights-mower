<script setup>
import { i18n } from '@/i18n'
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
import { themeSelectionKey } from '@/composables/themeSelection'
import SettingsSection from '@/components/SettingsSection.vue'
import SoftwareVersionPreference from '@/components/SoftwareVersionPreference.vue'
import InterfaceLanguagePreference from '@/components/InterfaceLanguagePreference.vue'
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

const sections = computed(() => [
  {
    id: 'mower-interface',
    title: i18n.global.t('settings.general.appearanceWindow'),
    icon: InterfaceIcon
  },
  {
    id: 'mower-notifications',
    title: i18n.global.t('settings.general.notificationsAssistant'),
    icon: NotifyIcon
  },
  {
    id: 'mower-profiles',
    title: i18n.global.t('settings.general.profilesRuntime'),
    icon: DataIcon
  },
  {
    id: 'mower-updates',
    title: i18n.global.t('settings.general.networkUpdates'),
    icon: UpdateIcon
  },
  {
    id: 'mower-data',
    title: i18n.global.t('settings.general.dataMaintenance'),
    icon: DataIcon
  }
])
const section = computed(() => Object.fromEntries(sections.value.map((item) => [item.id, item])))

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
const setTheme = inject(themeSelectionKey, (value) => (theme.value = value))
const themeOptions = computed(() => [
  { value: 'light', label: i18n.global.t('settings.general.light'), icon: SunIcon },
  { value: 'dark', label: i18n.global.t('settings.general.dark'), icon: MoonIcon },
  { value: 'system', label: i18n.global.t('settings.general.followSystem'), icon: SystemIcon }
])

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
  { label: i18n.global.t('settings.general.askEveryTime'), value: 'ask' },
  ...(desktopTrayEnabled.value
    ? [{ label: i18n.global.t('settings.general.minimizeToTray'), value: 'tray' }]
    : []),
  { label: i18n.global.t('settings.general.exitCompletely'), value: 'exit' }
])
const launchOptions = computed(() => [
  { label: i18n.global.t('settings.general.restoreLastState'), value: 'last' },
  { label: i18n.global.t('settings.general.normalWindow'), value: 'normal' },
  { label: i18n.global.t('settings.general.maximizedWindow'), value: 'maximized' }
])

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
    desktopPreferenceError.value =
      error.message || i18n.global.t('settings.general.couldNotLoadWindowPreferences')
  }
}

async function changeCloseMode(value) {
  const api = window.pywebview?.api
  if (!api?.set_close_preference || desktopPreferenceBusy.value) return
  desktopPreferenceBusy.value = true
  try {
    const choice = value === 'ask' ? (desktopTrayEnabled.value ? 'tray' : 'exit') : value
    const ok = await api.set_close_preference(choice, value !== 'ask')
    if (ok !== true) throw new Error(i18n.global.t('settings.general.couldNotSaveTheCloseAction'))
    desktopCloseMode.value = value
    desktopPreferenceError.value = ''
  } catch (error) {
    desktopPreferenceError.value =
      error.message || i18n.global.t('settings.general.failedToSaveTheCloseAction')
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
    if (ok !== true)
      throw new Error(i18n.global.t('settings.general.couldNotSaveTheStartupWindowState'))
    desktopLaunchMode.value = value
    desktopPreferenceError.value = ''
  } catch (error) {
    desktopPreferenceError.value =
      error.message || i18n.global.t('settings.general.failedToSaveTheStartupWindowState')
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
      <n-card id="appearance-settings" :title="i18n.global.t('settings.general.general')">
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
                <span>{{ i18n.global.t('settings.general.interfaceScale') }}</span>
                <span class="settings-row-description">{{
                  i18n.global.t('settings.general.adjustTextAndControlSizesThenClick')
                }}</span>
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
                  :aria-label="i18n.global.t('settings.general.interfaceScale')"
                />
              </div>
              <div
                class="desktop-scale-toolbar"
                role="group"
                :aria-label="i18n.global.t('settings.general.applyInterfaceScale')"
              >
                <output
                  class="desktop-scale-value"
                  :aria-label="
                    new_scale === webview.scale
                      ? i18n.global.t('settings.general.currentInterfaceScale')
                      : i18n.global.t('settings.general.pendingInterfaceScale')
                  "
                  aria-live="polite"
                  >{{
                    new_scale === webview.scale
                      ? i18n.global.t('settings.general.current')
                      : i18n.global.t('settings.general.pending')
                  }}
                  {{ Math.round(new_scale * 100) }}%</output
                >
                <n-button
                  class="scale-apply"
                  :disabled="new_scale == webview.scale"
                  @click="webview.scale = new_scale"
                >
                  {{ i18n.global.t('settings.general.apply') }}
                </n-button>
              </div>
            </div>
          </n-form-item>
          <n-form-item
            :label="i18n.global.t('settings.general.theme')"
            class="settings-appearance-row"
            v-if="runtime_platform !== 'android'"
          >
            <SettingsSegmented
              :value="theme"
              @update:value="setTheme"
              emit-reselect
              :options="themeOptions"
              class="settings-theme-choices"
              :label="i18n.global.t('settings.general.theme')"
            />
          </n-form-item>
          <InterfaceLanguagePreference />
          <SoftwareVersionPreference />
          <VersionWatermarkPreference />
          <LogBackgroundPreference />
        </n-form>
      </n-card>
      <n-card
        v-if="runtime_platform !== 'android'"
        id="window-settings"
        :title="i18n.global.t('settings.general.window')"
      >
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
                <span>{{
                  runtime_platform === 'darwin'
                    ? i18n.global.t('settings.general.hideMenuBarIcon')
                    : i18n.global.t('settings.general.useTrayIcon')
                }}</span>
                <span id="tray-description" class="settings-row-description">
                  <template v-if="runtime_platform === 'darwin'">
                    {{
                      i18n.global.t('settings.general.takesEffectAfterRestartingAStandaloneLaunch')
                    }}
                  </template>
                  <template v-else>{{
                    i18n.global.t('settings.general.takesEffectAfterRestartingInstancesLaunchedBy')
                  }}</template>
                </span>
              </span>
            </template>
            <n-switch
              v-if="runtime_platform === 'darwin'"
              v-model:value="hide_macos_menu_bar"
              :aria-label="i18n.global.t('settings.general.hideMenuBarIcon')"
              aria-describedby="tray-description"
            />
            <n-switch
              v-else
              v-model:value="webview.tray"
              :aria-label="i18n.global.t('settings.general.useTrayIcon')"
              aria-describedby="tray-description"
            />
          </n-form-item>
          <n-form-item v-if="desktopPreferencesReady">
            <template #label>
              <span class="settings-row-copy"
                ><span>{{ i18n.global.t('settings.general.closeWindow') }}</span
                ><span class="settings-row-description">{{
                  i18n.global.t('settings.general.chooseWhatHappensWhenYouClickThe')
                }}</span></span
              >
            </template>
            <n-select
              :consistent-menu-width="false"
              :value="desktopCloseMode"
              :options="closeOptions"
              :disabled="desktopPreferenceBusy"
              :input-props="{ 'aria-label': i18n.global.t('settings.general.closeWindow') }"
              @update:value="changeCloseMode"
            />
          </n-form-item>
          <n-form-item v-if="desktopPreferencesReady">
            <template #label>
              <span class="settings-row-copy">
                <span>{{ i18n.global.t('settings.general.startupWindowState') }}</span>
                <span id="window-launch-description" class="settings-row-description">
                  {{ i18n.global.t('settings.general.appliesTheNextTimeTheMowerDesktop') }}
                </span>
              </span>
            </template>
            <n-select
              :consistent-menu-width="false"
              :value="desktopLaunchMode"
              :options="launchOptions"
              :disabled="desktopPreferenceBusy"
              :input-props="{
                'aria-label': i18n.global.t('settings.general.startupWindowState'),
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
      <n-card
        id="archive-settings"
        :title="i18n.global.t('settings.general.screenshotsErrorArchives')"
      >
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
                <span>{{ i18n.global.t('settings.general.screenshotRetention') }}</span>
                <span id="screenshot-retention-description" class="settings-row-description">
                  {{ i18n.global.t('settings.general.howLongOrdinaryScreenshotsAreKeptSet') }}
                  <template v-if="inheritsFromManager('screenshot')">
                    {{ i18n.global.t('settings.general.usingSharedSettingsChangeThemInThe') }}
                  </template>
                </span>
              </span>
            </template>
            <mower-input-number
              v-model:value="screenshot"
              :disabled="inheritsFromManager('screenshot')"
              :min="0"
              :input-props="{
                'aria-label': i18n.global.t('settings.general.screenshotRetention'),
                'aria-describedby': 'screenshot-retention-description'
              }"
            >
              <template #suffix>{{ i18n.global.t('settings.general.hours') }}</template>
            </mower-input-number>
          </n-form-item>
          <n-form-item>
            <template #label>
              <span class="settings-row-copy">
                <span>{{ i18n.global.t('settings.general.errorArchiveSizeLimit') }}</span>
                <span id="screenshot-archive-limit-description" class="settings-row-description">
                  {{ i18n.global.t('settings.general.olderErrorArchivesAreRemovedWhenThe') }}
                  <template v-if="inheritsFromManager('screenshot_archive_limit_mb')">
                    {{ i18n.global.t('settings.general.usingSharedSettingsChangeThemInThe') }}
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
                'aria-label': i18n.global.t('settings.general.errorArchiveSizeLimit'),
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
          {{ i18n.global.t('settings.general.ordinaryScreenshotsAreNotWrittenToDisk') }}
        </p>
        <p
          v-else-if="runtime_platform !== 'android' && screenshot > 0 && screenshot < 5 / 60"
          class="archive-status"
          role="status"
        >
          {{ i18n.global.t('settings.general.screenshotsAreWrittenToDiskAndRetained') }}
        </p>
        <n-collapse class="archive-details">
          <n-collapse-item
            :title="i18n.global.t('settings.general.screenshotRetentionDetails')"
            name="retention"
            :data-settings-label="i18n.global.t('settings.general.screenshotRetentionDetails')"
          >
            <p v-if="runtime_platform !== 'android'">
              {{ i18n.global.t('settings.general.ordinaryScreenshotsAreKeptFor1Hour') }}
            </p>
            <p>{{ i18n.global.t('settings.general.errorArchivesAreLimitedTo5Gib') }}</p>
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
