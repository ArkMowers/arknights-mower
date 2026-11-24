<script setup>
import { publicAsset } from '@/utils/publicAsset'
defineOptions({ name: 'MowerDocPage' })

import { computed, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { useThemeVars } from 'naive-ui'
import { useConfigStore } from '@/stores/config'
import { useResolvedTheme } from '@/composables/theme'
import PageLayout from '@/components/PageLayout.vue'
import PageHeader from '@/components/PageHeader.vue'
import LoadingSkeleton from '@/components/LoadingSkeleton.vue'

const { theme: themePreference } = storeToRefs(useConfigStore())
const theme = useResolvedTheme(themePreference)
const themeVars = useThemeVars()
const guideFrame = ref(null)
// 说明页在框内读完之前，按说明页的版面（目录和正文卡片）画出占位，读完后淡出。
const guideLoaded = ref(false)
const GUIDE_SKELETON_NAV = [72, 58, 84, 66, 76, 70, 88, 62, 74, 68, 56, 64]
const GUIDE_SKELETON_LINES = [96, 88, 92, 74, 90, 82, 94, 60]
const docSrc = `${publicAsset('/docs/Mower入门指北.html')}?theme=${theme.value === 'dark' ? 'dark' : 'light'}`
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

function onGuideLoad() {
  guideLoaded.value = true
  syncTheme()
}

function syncTheme() {
  guideFrame.value?.contentWindow?.postMessage(
    {
      type: 'mower-doc-theme',
      theme: theme.value === 'dark' ? 'dark' : 'light',
      colors: guideColors.value
    },
    new URL(docSrc, window.location.href).origin
  )
}

watch([theme, guideColors], syncTheme, { flush: 'post' })
</script>

<template>
  <PageLayout max-width="100%">
    <template #header>
      <PageHeader>
        帮助文档
        <template #actions>
          <n-button
            tag="a"
            href="https://arkmowers.github.io/arknights-mower/"
            target="_blank"
            rel="noopener noreferrer"
            secondary
          >
            在线文档 ↗
          </n-button>
        </template>
      </PageHeader>
    </template>
    <div class="doc-stage">
      <iframe
        ref="guideFrame"
        title="Mower 一条龙入门说明"
        :src="docSrc"
        :inert="!guideLoaded"
        :tabindex="guideLoaded ? undefined : -1"
        @load="onGuideLoad"
        sandbox="allow-popups allow-popups-to-escape-sandbox allow-scripts allow-same-origin allow-forms"
        class="doc-frame"
      />
      <Transition name="doc-skeleton">
        <LoadingSkeleton v-if="!guideLoaded" class="doc-skeleton" label="正在打开帮助文档">
          <span class="doc-skeleton__nav">
            <span class="doc-skeleton__nav-title">
              <span class="skeleton-bone skeleton-text" style="--skeleton-w: 7em" />
            </span>
            <span
              v-for="(width, index) in GUIDE_SKELETON_NAV"
              :key="index"
              class="doc-skeleton__link"
            >
              <span class="skeleton-bone skeleton-text" :style="{ '--skeleton-w': `${width}%` }" />
            </span>
          </span>
          <span class="doc-skeleton__main">
            <span class="doc-skeleton__card">
              <span class="doc-skeleton__title">
                <span class="skeleton-bone skeleton-text" style="--skeleton-w: 11em" />
              </span>
              <span
                v-for="(width, index) in GUIDE_SKELETON_LINES"
                :key="index"
                class="doc-skeleton__line"
              >
                <span
                  class="skeleton-bone skeleton-text"
                  :style="{ '--skeleton-w': `${width}%` }"
                />
              </span>
            </span>
          </span>
        </LoadingSkeleton>
      </Transition>
    </div>
  </PageLayout>
</template>

<style scoped>
.doc-stage {
  position: relative;
  container-type: inline-size;
}

.doc-frame {
  display: block;
  width: 100%;
  height: calc(100vh - 120px);
  border: none;
  border-radius: calc(8px * var(--mower-corner-scale));
  corner-shape: var(--mower-corner-shape);
  background: var(--mower-surface);
  box-shadow: var(--mower-shadow-surface);
}

@media (max-width: 640px) {
  .doc-frame {
    height: calc(100vh - 100px);
  }
}

/* 占位与说明页版面一致：宽于 992px 时左侧 210px 目录、右侧正文卡片，更窄时目录在上方，
   最高 300px。说明页读完后占位淡出，期间不挡操作。 */
.doc-skeleton {
  position: absolute;
  inset: 0;
  display: flex;
  overflow: hidden;
  border-radius: calc(8px * var(--mower-corner-scale));
  corner-shape: var(--mower-corner-shape);
  background: var(--mower-surface);
  font-size: 14px;
  line-height: 1.8;
}

.doc-skeleton-leave-active {
  transition: opacity 180ms ease-out;
  pointer-events: none;
}

.doc-skeleton-leave-to {
  opacity: 0;
}

.doc-skeleton__nav {
  display: flex;
  flex: 0 0 210px;
  flex-direction: column;
  border-right: 1px solid var(--mower-divider);
}

.doc-skeleton__nav-title {
  padding: 15px 20px;
  border-bottom: 1px solid var(--mower-divider);
  font-size: 16px;
}

.doc-skeleton__nav-title + .doc-skeleton__link {
  margin-top: 10px;
}

.doc-skeleton__link {
  padding: 12px 20px;
  font-size: 13px;
}

.doc-skeleton__main {
  flex: 1;
  min-width: 0;
  padding: 24px 28px;
}

.doc-skeleton__card {
  display: flex;
  flex-direction: column;
  padding: 24px;
  border: 1px solid var(--mower-divider);
  border-radius: 12px;
}

.doc-skeleton__title {
  margin-bottom: 20px;
  padding-bottom: 15px;
  border-bottom: 2px solid color-mix(in srgb, var(--mower-primary) 40%, transparent);
  font-size: 22px;
}

.doc-skeleton__line {
  display: block;
}

@container (max-width: 992px) {
  .doc-skeleton {
    flex-direction: column;
  }

  .doc-skeleton__nav {
    flex: 0 0 auto;
    max-height: 300px;
    overflow: hidden;
    border-right: 0;
    border-bottom: 1px solid var(--mower-divider);
  }

  .doc-skeleton__main {
    padding: 20px;
  }
}
</style>
