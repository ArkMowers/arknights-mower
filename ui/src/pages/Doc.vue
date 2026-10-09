<script setup>
import { computed, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { useThemeVars } from 'naive-ui'
import { useConfigStore } from '@/stores/config'

const { theme } = storeToRefs(useConfigStore())
const themeVars = useThemeVars()
const guideFrame = ref(null)
const docSrc = `/docs/Mower入门指北.html?theme=${theme.value === 'dark' ? 'dark' : 'light'}`
const guideColors = computed(() => {
  const colors = themeVars.value
  return {
    '--page-bg': colors.bodyColor,
    '--card-bg': colors.cardColor,
    '--light-bg': colors.cardColor,
    '--text-color': colors.textColor2,
    '--heading-color': colors.textColor1,
    '--muted-color': colors.textColor3,
    '--primary-color': colors.primaryColor,
    '--secondary-color': colors.infoColor,
    '--link-color': theme.value === 'dark' ? colors.primaryColor : colors.primaryColorPressed,
    '--link-hover': colors.primaryColorPressed,
    '--reference-color': theme.value === 'dark' ? colors.primaryColor : colors.primaryColorPressed,
    '--reference-hover': colors.primaryColorPressed,
    '--border-color': colors.dividerColor,
    '--hover-bg': colors.hoverColor,
    '--active-color': colors.hoverColor,
    '--code-bg': colors.actionColor,
    '--note-border': colors.warningColor,
    '--warning-border': colors.errorColor,
    '--error-color': colors.errorColor
  }
})

function syncTheme() {
  guideFrame.value?.contentWindow?.postMessage(
    {
      type: 'mower-doc-theme',
      theme: theme.value === 'dark' ? 'dark' : 'light',
      colors: guideColors.value
    },
    window.location.origin
  )
}

watch([theme, guideColors], syncTheme, { flush: 'post' })
</script>

<template>
  <div class="link-container">
    <strong>本地一条龙入门说明</strong>
    <n-a
      href="https://docs.qq.com/sheet/DUEJ6UWN5VFVRU0dG?tab=BB08J2"
      target="_blank"
      rel="noopener noreferrer"
    >
      Mower 反馈表
    </n-a>
    在线文档地址：
    <n-a href="https://arkmowers.github.io/arknights-mower/" target="_blank">
      https://arkmowers.github.io/arknights-mower/
    </n-a>
  </div>
  <iframe
    ref="guideFrame"
    title="Mower 一条龙入门说明"
    :src="docSrc"
    @load="syncTheme"
    sandbox="allow-popups allow-popups-to-escape-sandbox allow-scripts allow-same-origin allow-forms"
    style="width: 100%; height: 100vh; border: none"
  />
</template>

<style scoped>
.link-container {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 16px;
  width: 100%;
  padding: 6px 12px 0;
  box-sizing: border-box;
}
</style>
