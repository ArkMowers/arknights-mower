<template>
  <nav
    class="mobile-tab-bar"
    :style="{ ...palette, '--tab-count': mobileTabs.length + 1 }"
    :aria-label="t('navigation.quickNavigation')"
  >
    <template v-for="item in mobileTabs" :key="item.key">
      <n-popover
        v-if="item.items"
        trigger="click"
        placement="top"
        :show="openTab === item.key"
        :show-arrow="false"
        :internal-trap-focus="true"
        :content-style="{ padding: '6px' }"
        @update:show="(show) => setTabOpen(item.key, show)"
      >
        <template #trigger>
          <button
            type="button"
            class="mobile-tab-bar__item"
            :class="{ 'is-active': activeTab === item.key }"
            aria-haspopup="dialog"
            :aria-label="t('navigation.choosePage', { label: navigationLabel(item) })"
            :title="navigationLabel(item)"
            :aria-expanded="openTab === item.key"
            :aria-controls="`${menuId}-${item.key}`"
            @keydown.esc="openTab = null"
          >
            <span class="mobile-tab-bar__icon">
              <n-icon :component="item.icon" aria-hidden="true" />
            </span>
            <span class="mobile-tab-bar__label">
              {{ navigationLabel(item, true) }}
              <n-icon class="mobile-tab-bar__caret" :component="ChevronUp" aria-hidden="true" />
            </span>
          </button>
        </template>
        <div
          :id="`${menuId}-${item.key}`"
          class="mobile-tab-bar__pages"
          :style="palette"
          role="dialog"
          :aria-label="t('navigation.pagePicker', { label: navigationLabel(item) })"
        >
          <SessionLink
            v-for="page in mobileTabItems(item)"
            :key="page.key"
            :to="page.to"
            class="mobile-tab-bar__page"
            exact-active-class="is-active"
            @click="openTab = null"
          >
            <n-icon :component="page.icon" aria-hidden="true" />
            <span>{{ navigationLabel(page) }}</span>
          </SessionLink>
        </div>
      </n-popover>
      <SessionLink
        v-else
        :to="item.to"
        class="mobile-tab-bar__item"
        :class="{
          'mobile-tab-bar__item--primary': item.key === 'log',
          'is-active': activeTab === item.key
        }"
        exact-active-class="is-active"
        :aria-label="navigationLabel(item)"
        :title="navigationLabel(item)"
      >
        <span class="mobile-tab-bar__icon">
          <n-icon :component="item.icon" aria-hidden="true" />
        </span>
        <span class="mobile-tab-bar__label">{{ navigationLabel(item, true) }}</span>
      </SessionLink>
    </template>
    <button
      type="button"
      class="mobile-tab-bar__item mobile-tab-bar__more"
      :class="{ 'is-active': moreActive }"
      aria-haspopup="dialog"
      :aria-expanded="moreOpen"
      @click="openMore"
    >
      <span class="mobile-tab-bar__icon">
        <n-icon :component="AppsOutline" aria-hidden="true" />
      </span>
      <span class="mobile-tab-bar__label">{{ t('navigation.more') }}</span>
    </button>
  </nav>
</template>

<script setup>
import AppsOutline from '@vicons/ionicons5/es/AppsOutline'
import ChevronUp from '@vicons/ionicons5/es/ChevronUp'
import { useThemeVars } from 'naive-ui'
import { computed, ref, useId, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import SessionLink from './SessionLink.vue'
import { mobileTabItems, mobileTabs, navigationItems } from '@/navigation'
import { i18n } from '@/i18n'
import { navigationLabel } from '@/i18n/navigation'

const props = defineProps({
  moreOpen: { type: Boolean, default: false }
})
const emit = defineEmits(['more'])
const { t } = i18n.global

const route = useRoute()
const router = useRouter()
const menuId = useId()
const openTab = ref(null)
const themeVars = useThemeVars()
const palette = computed(() => ({
  '--tab-text': themeVars.value.textColor2,
  '--tab-active-text': themeVars.value.primaryColorPressed,
  '--tab-focus': themeVars.value.primaryColor,
  '--tab-primary-icon': themeVars.value.bodyColor
}))

const tabRecords = new Map(
  mobileTabs.map((tab) => [
    tab.key,
    new Set(mobileTabItems(tab).map((page) => router.resolve(page.to).matched.at(-1)))
  ])
)
const activeTab = computed(
  () => mobileTabs.find((tab) => tabRecords.get(tab.key).has(route.matched.at(-1)))?.key
)
const tabPages = new Set(mobileTabs.flatMap(mobileTabItems))
const moreRecords = new Set(
  navigationItems
    .filter((item) => item.to && !tabPages.has(item))
    .map((item) => router.resolve(item.to).matched.at(-1))
)
const moreActive = computed(() => moreRecords.has(route.matched.at(-1)))

function setTabOpen(key, show) {
  if (show) openTab.value = key
  else if (openTab.value === key) openTab.value = null
}

function openMore() {
  openTab.value = null
  emit('more')
}

watch(
  () => route.fullPath,
  () => (openTab.value = null)
)
watch(
  () => props.moreOpen,
  () => (openTab.value = null)
)
</script>

<style scoped>
.mobile-tab-bar {
  display: grid;
  grid-template-columns: repeat(var(--tab-count), minmax(0, 1fr));
  align-items: stretch;
  padding: 2px 0 calc(2px + env(safe-area-inset-bottom));
  border-top: 1px solid var(--mower-divider, color-mix(in srgb, var(--tab-text) 10%, transparent));
}

.mobile-tab-bar__item {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 2px;
  min-width: 0;
  box-sizing: border-box;
  min-height: 54px;
  padding: 3px 0;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: var(--tab-text);
  font: inherit;
  font-size: 11px;
  line-height: 16px;
  text-decoration: none;
  cursor: pointer;
  -webkit-tap-highlight-color: transparent;
  transition: color 0.15s ease;
}

.mobile-tab-bar__item:focus-visible,
.mobile-tab-bar__page:focus-visible {
  outline: 2px solid var(--tab-focus);
  outline-offset: -2px;
}

.mobile-tab-bar__icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 44px;
  height: 26px;
  border-radius: 13px;
  font-size: 21px;
  transition: background-color 0.15s ease;
}

.mobile-tab-bar__item:active .mobile-tab-bar__icon {
  background: color-mix(in srgb, var(--tab-text) 8%, transparent);
}

.mobile-tab-bar__item.is-active {
  color: var(--tab-active-text);
  font-weight: 600;
}

.mobile-tab-bar__item.is-active .mobile-tab-bar__icon {
  background: var(--mower-primary-block, color-mix(in srgb, var(--tab-focus) 14%, transparent));
}

.mobile-tab-bar__item--primary {
  padding: 0;
  color: var(--tab-active-text);
  font-weight: 600;
}

.mobile-tab-bar__item--primary .mobile-tab-bar__icon {
  width: 38px;
  height: 32px;
  border-radius: 11px;
  background: var(--tab-focus);
  color: var(--tab-primary-icon);
  font-size: 23px;
}

.mobile-tab-bar__item--primary.is-active .mobile-tab-bar__icon {
  background: var(--tab-active-text);
}

.mobile-tab-bar__item--primary:active .mobile-tab-bar__icon {
  background: var(--tab-active-text);
}

.mobile-tab-bar__label {
  display: flex;
  align-items: center;
  gap: 2px;
  white-space: nowrap;
}

.mobile-tab-bar__caret {
  font-size: 10px;
}

.mobile-tab-bar__pages {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 168px;
  max-width: calc(100vw - 32px);
  max-height: min(420px, 65dvh);
  overflow-y: auto;
}

.mobile-tab-bar__page {
  display: flex;
  align-items: center;
  gap: 10px;
  min-height: 44px;
  padding: 0 12px;
  border-radius: 6px;
  color: var(--tab-text);
  font-size: 14px;
  text-decoration: none;
}

.mobile-tab-bar__page .n-icon {
  flex-shrink: 0;
  font-size: 20px;
}

.mobile-tab-bar__page:hover {
  background: color-mix(in srgb, var(--tab-text) 7%, transparent);
}

.mobile-tab-bar__page.is-active {
  background: var(--mower-primary-block, color-mix(in srgb, var(--tab-focus) 14%, transparent));
  color: var(--tab-active-text);
  font-weight: 600;
}

@media (prefers-reduced-motion: reduce) {
  .mobile-tab-bar__item,
  .mobile-tab-bar__icon {
    transition: none;
  }
}
</style>
