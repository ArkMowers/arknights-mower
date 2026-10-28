<script setup>
import { i18n } from '@/i18n'
const { t } = i18n.global

import { computed, ref, watch } from 'vue'
import { useThemeVars } from 'naive-ui'
import { useSidebarPreferences } from '@/composables/sidebarPreferences'
import { navigationLabel } from '@/i18n/navigation'

const props = defineProps({ groupKey: { type: String, default: null } })
const emit = defineEmits(['close'])
const preferences = useSidebarPreferences()
const themeVars = useThemeVars()
const dialogStyle = computed(() => ({
  width: 'min(520px, calc(100vw - 32px))',
  '--mower-text-muted': themeVars.value.textColor3,
  '--mower-border': themeVars.value.borderColor,
  '--mower-surface': themeVars.value.cardColor,
  '--mower-control-hover': themeVars.value.hoverColor,
  '--mower-primary': themeVars.value.primaryColor,
  '--mower-error': themeVars.value.errorColor
}))
const { state, catalog, persistenceError } = preferences
const search = ref('')
const selectedKeys = ref([])
const error = ref('')
const errorMessage = computed(() => (error.value ? t('runtime.addPageFailed') : ''))
const addedKeys = computed(
  () =>
    new Set(
      state.value.placements
        .filter(
          (item) =>
            item.visible &&
            (props.groupKey === 'pinned'
              ? item.pinned
              : item.group === props.groupKey && !item.pinned)
        )
        .map((item) => item.key)
    )
)
const availableEntries = computed(() => {
  const query = search.value.trim().toLocaleLowerCase()
  return catalog.value
    .filter((item) =>
      [item.label, navigationLabel(item)].some((label) => label.toLocaleLowerCase().includes(query))
    )
    .map((item) => ({ ...item, label: navigationLabel(item) }))
})

function clearDraft() {
  search.value = ''
  selectedKeys.value = []
  error.value = ''
}

watch(() => props.groupKey, clearDraft, { flush: 'sync' })

function close() {
  clearDraft()
  emit('close')
}

function updateShow(show) {
  if (!show) close()
}

function confirm() {
  if (!selectedKeys.value.length || props.groupKey === null) return
  const pending = selectedKeys.value.filter((key) => !addedKeys.value.has(key))
  for (const key of pending) {
    if (!preferences.addEntry(key, props.groupKey)) {
      error.value = t('runtime.addPageFailed')
      return
    }
  }
  close()
}
</script>

<template>
  <n-modal
    :show="groupKey !== null"
    preset="card"
    :title="t('runtime.addPage')"
    class="sidebar-page-dialog"
    :style="dialogStyle"
    content-style="display: flex; flex-direction: column; overflow: hidden"
    :aria-label="t('runtime.addPage')"
    @update:show="updateShow"
  >
    <input
      v-model="search"
      class="sidebar-customize__search"
      type="search"
      :placeholder="t('runtime.searchPages')"
      :aria-label="t('runtime.searchPages')"
    />
    <p v-if="persistenceError" class="sidebar-customize__error" role="alert">
      {{ t('runtime.sidebarTemporary') }}
    </p>
    <p v-if="error" class="sidebar-customize__error" role="alert">{{ errorMessage }}</p>
    <div class="sidebar-customize__entries">
      <label
        v-for="item in availableEntries"
        :key="item.key"
        class="sidebar-customize__entry"
        :class="{ 'sidebar-customize__entry--added': addedKeys.has(item.key) }"
        :data-sidebar-entry="item.key"
      >
        <input
          v-model="selectedKeys"
          type="checkbox"
          :value="item.key"
          :disabled="addedKeys.has(item.key)"
          :aria-label="t('runtime.addNamedPage', { label: item.label })"
          :data-page-key="item.key"
        />
        <n-icon :component="item.icon" aria-hidden="true" />
        <span>{{ item.label }}</span>
        <span v-if="addedKeys.has(item.key)" class="sidebar-customize__added">{{
          t('runtime.alreadyAdded')
        }}</span>
      </label>
      <p v-if="!availableEntries.length" class="sidebar-customize__empty">
        {{ t('runtime.noPagesFound') }}
      </p>
    </div>
    <template #footer>
      <div class="sidebar-customize__actions">
        <n-button :aria-label="t('runtime.cancelAddPages')" @click="close">{{
          t('runtime.cancel')
        }}</n-button>
        <n-button
          type="primary"
          :aria-label="t('runtime.confirmAddPages')"
          :disabled="!selectedKeys.length"
          @click="confirm"
        >
          {{ t('runtime.addPagesCount', { count: selectedKeys.length }) }}
        </n-button>
      </div>
    </template>
  </n-modal>
</template>

<style scoped>
.sidebar-customize__search {
  flex: none;
  box-sizing: border-box;
  width: 100%;
  min-width: 0;
  padding: 8px 10px;
  border: 1px solid var(--mower-border, #dedee3);
  border-radius: 5px;
  background: var(--mower-surface, #fff);
  color: inherit;
  font: inherit;
}

.sidebar-customize__entries {
  display: grid;
  flex: 1 1 auto;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 4px;
  min-height: 0;
  max-height: calc(70dvh - 210px);
  margin-top: 12px;
  overflow-y: auto;
}

.sidebar-customize__entry {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  padding: 8px;
  border-radius: 5px;
  background: transparent;
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
}

.sidebar-customize__entry:hover {
  background: var(--mower-control-hover, rgba(0, 0, 0, 0.06));
}

.sidebar-customize__entry:focus-within,
.sidebar-customize__search:focus-visible {
  outline: 2px solid var(--mower-primary, #18a058);
  outline-offset: -2px;
}

.sidebar-customize__entry--added {
  color: var(--mower-text-muted, #767c82);
  cursor: default;
}

.sidebar-customize__entry input {
  flex-shrink: 0;
  margin: 0;
  accent-color: var(--mower-primary, #18a058);
}

.sidebar-customize__entry .n-icon {
  flex-shrink: 0;
}

.sidebar-customize__added {
  margin-left: auto;
  white-space: nowrap;
  font-size: 12px;
}

.sidebar-customize__actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

.sidebar-customize__empty,
.sidebar-customize__error {
  margin: 6px 0;
  overflow-wrap: anywhere;
}

.sidebar-customize__empty {
  color: var(--mower-text-muted, #767c82);
}

.sidebar-customize__error {
  flex: none;
  color: var(--mower-error, #d03050);
}

@media (max-width: 440px) {
  .sidebar-customize__entries {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
