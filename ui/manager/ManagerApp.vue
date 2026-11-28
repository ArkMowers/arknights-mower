<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { darkTheme, zhCN, dateZhCN } from 'naive-ui'
import SunnyIcon from '@vicons/ionicons5/es/SunnyOutline'
import MoonIcon from '@vicons/ionicons5/es/MoonOutline'
import MowerManager from './MowerManager.vue'
import {
  mowerLightThemeOverrides,
  mowerDarkThemeOverrides,
  mowerLightCssVariables,
  mowerDarkCssVariables
} from '../src/theme/mower'
import '../src/theme/mower.css'

const media = window.matchMedia('(prefers-color-scheme: dark)')
const dark = ref(media.matches)
const variables = computed(() => (dark.value ? mowerDarkCssVariables : mowerLightCssVariables))
watch(
  variables,
  (values) => {
    for (const [key, value] of Object.entries(values))
      document.documentElement.style.setProperty(key, value)
  },
  { immediate: true }
)
function followSystem(event) {
  dark.value = event.matches
}
watch(
  dark,
  (value) => {
    document.documentElement.dataset.mowerTheme = value ? 'dark' : 'light'
  },
  { immediate: true }
)
onMounted(() => media.addEventListener('change', followSystem))
onUnmounted(() => media.removeEventListener('change', followSystem))
</script>

<template>
  <n-config-provider
    class="provider manager-provider"
    :locale="zhCN"
    :date-locale="dateZhCN"
    :theme="dark ? darkTheme : undefined"
    :theme-overrides="dark ? mowerDarkThemeOverrides : mowerLightThemeOverrides"
    :style="variables"
  >
    <n-global-style />
    <MowerManager>
      <template #appearance>
        <n-button
          quaternary
          circle
          :aria-label="dark ? '切换浅色主题' : '切换深色主题'"
          @click="dark = !dark"
        >
          <template #icon
            ><n-icon><SunnyIcon v-if="dark" /><MoonIcon v-else /></n-icon
          ></template>
        </n-button>
      </template>
    </MowerManager>
  </n-config-provider>
</template>

<style>
body {
  margin: 0;
}
.manager-provider {
  min-height: 100dvh;
  font-family:
    v-sans,
    system-ui,
    -apple-system,
    BlinkMacSystemFont,
    'Segoe UI',
    sans-serif;
}
</style>
