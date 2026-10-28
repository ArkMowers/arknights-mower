<script setup>
defineOptions({ name: 'MowerDocPage' })

import { computed, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { useThemeVars } from 'naive-ui'
import { useConfigStore } from '@/stores/config'
import { useResolvedTheme } from '@/composables/theme'
import PageLayout from '@/components/PageLayout.vue'
import PageHeader from '@/components/PageHeader.vue'
import { i18n } from '@/i18n'

const { t } = i18n.global

const { theme: themePreference } = storeToRefs(useConfigStore())
const theme = useResolvedTheme(themePreference)
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
  <PageLayout max-width="100%">
    <template #header>
      <PageHeader>
        {{ t('runtime.helpDocs') }}
        <template #actions>
          <n-button
            tag="a"
            href="https://arkmowers.github.io/arknights-mower/"
            target="_blank"
            rel="noopener noreferrer"
            secondary
          >
            {{ t('runtime.onlineDocs') }} ↗
          </n-button>
        </template>
      </PageHeader>
    </template>
    <iframe
      ref="guideFrame"
      :title="t('runtime.gettingStarted')"
      :src="docSrc"
      @load="syncTheme"
      sandbox="allow-popups allow-popups-to-escape-sandbox allow-scripts allow-same-origin allow-forms"
      class="doc-frame"
    />
  </PageLayout>
</template>

<style scoped>
.doc-frame {
  width: 100%;
  height: calc(100vh - 120px);
  border: none;
  border-radius: 8px;
  background: var(--mower-surface);
  box-shadow: var(--mower-shadow-surface);
}

@media (max-width: 640px) {
  .doc-frame {
    height: calc(100vh - 100px);
  }
}
</style>
