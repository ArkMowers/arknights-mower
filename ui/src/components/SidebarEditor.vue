<script setup>
import { i18n } from '@/i18n'
const { t } = i18n.global

import { computed, nextTick, ref, watch } from 'vue'
import draggable from 'vuedraggable'
import ReorderThreeOutline from '@vicons/ionicons5/es/ReorderThreeOutline'
import CloseOutline from '@vicons/ionicons5/es/CloseOutline'
import { useThemeVars } from 'naive-ui'
import { useSidebarPreferences } from '@/composables/sidebarPreferences'
import SidebarCustomize from './SidebarCustomize.vue'
import { normalizeSortablePreview } from '@/utils/sortablePreview'
import { navigationGroupTitle, navigationLabel } from '@/i18n/navigation'
import '@/styles/drag.css'

const props = defineProps({
  show: Boolean,
  request: { type: Object, default: () => ({}) }
})
const emit = defineEmits(['update:show'])
const preferences = useSidebarPreferences()
const themeVars = useThemeVars()
const dialogStyle = computed(() => ({
  width: 'min(560px, calc(100vw - 32px))',
  '--mower-text-muted': themeVars.value.textColor3,
  '--mower-border': themeVars.value.borderColor,
  '--mower-surface': themeVars.value.cardColor,
  '--mower-error': themeVars.value.errorColor
}))
const { state, visibleSections, standaloneItems, pinnedItems, initialized, persistenceError } =
  preferences
const groupDraft = ref('')
const groupInput = ref(null)
const namingGroup = ref(null)
const nameErrorKey = ref('')
const nameError = computed(() => (nameErrorKey.value ? t(`runtime.${nameErrorKey.value}`) : ''))
const pickerGroup = ref(null)
const dragArea = { name: 'sidebar-editor-pages', pull: true, put: true }
const dragOptions = {
  animation:
    typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
      ? 0
      : 150,
  forceFallback: true,
  fallbackOnBody: true,
  fallbackTolerance: 8,
  delay: 180,
  delayOnTouchOnly: true,
  touchStartThreshold: 6,
  ghostClass: 'mower-drag-ghost',
  chosenClass: 'mower-drag-chosen',
  fallbackClass: 'mower-drag-fallback',
  filter: 'input, textarea, select, button, a',
  preventOnFilter: false
}
function displayItems(items) {
  return items.map((item) => ({ ...item, label: navigationLabel(item) }))
}
const groups = computed(() =>
  visibleSections.value.map((group) => ({
    ...group,
    title: navigationGroupTitle(group),
    items: displayItems(group.items)
  }))
)
const outerSections = computed(() => [
  {
    key: 'pinned',
    get title() {
      return t('runtime.pinned')
    },
    items: displayItems(pinnedItems.value)
  },
  {
    key: 'ungrouped',
    get title() {
      return t('runtime.standalonePages')
    },
    items: displayItems(standaloneItems.value)
  }
])

function close() {
  pickerGroup.value = null
  emit('update:show', false)
}

function startNaming(request = {}) {
  const group = state.value.groups.find((entry) => entry.key === request.groupKey)
  namingGroup.value = request.action === 'rename-group' && group ? group.key : 'new'
  groupDraft.value = group?.title || ''
  nameErrorKey.value = ''
  void nextTick(() => groupInput.value?.focus())
}

watch(
  () => [props.show, props.request],
  () => {
    namingGroup.value = null
    nameErrorKey.value = ''
    pickerGroup.value = null
    if (props.show && ['new-group', 'rename-group'].includes(props.request.action)) {
      startNaming(props.request)
    }
  },
  { immediate: true }
)

function saveName() {
  const title = groupDraft.value.trim()
  if (!title) {
    nameErrorKey.value = 'groupNameRequired'
    return
  }
  if (namingGroup.value === 'new') {
    const key = preferences.addGroup(title)
    if (!key) {
      nameErrorKey.value = 'groupCreateFailed'
      return
    }
    const after = state.value.groups.findIndex((group) => group.key === props.request.afterKey)
    if (after >= 0) preferences.moveGroup(key, state.value.groups[after + 1]?.key || null)
  } else if (!preferences.renameGroup(namingGroup.value, title)) {
    nameErrorKey.value = 'groupRenameFailed'
    return
  }
  namingGroup.value = null
}

function onPageSort(change, groupKey) {
  const item = change.added || change.moved
  if (!item) return
  const section = [...outerSections.value, ...groups.value].find((entry) => entry.key === groupKey)
  const others = section.items.filter((entry) => entry.id !== item.element.id)
  preferences.moveItem(item.element.id, groupKey, others[item.newIndex]?.id || null)
}

function canMovePage(event) {
  const groupKey = event.to?.dataset.editorGroup
  const item = event.draggedContext?.element
  if (!item || !groupKey) return false
  return canPlace(item, groupKey)
}

function canPlace(item, groupKey) {
  return !state.value.placements.some(
    (entry) =>
      entry.id !== item.id &&
      entry.key === item.key &&
      (groupKey === 'pinned' ? entry.pinned : !entry.pinned && entry.group === groupKey)
  )
}

function onGroupSort({ moved }) {
  if (!moved) return
  const others = state.value.groups.filter((group) => group.key !== moved.element.key)
  preferences.moveGroup(moved.element.key, others[moved.newIndex]?.key || null)
}

function retry() {
  if (!initialized.value) void preferences.initialize()
  else void preferences.retrySave()
}
</script>

<template>
  <n-modal
    :show="show"
    preset="card"
    :title="t('runtime.editSidebar')"
    :aria-label="t('runtime.editSidebar')"
    class="sidebar-editor"
    :style="dialogStyle"
    content-style="display: flex; flex-direction: column; overflow: hidden"
    @update:show="!$event && close()"
  >
    <p class="sidebar-editor__hint">{{ t('runtime.sidebarEditingHelp') }}</p>
    <p v-if="persistenceError" class="sidebar-editor__error" role="alert">
      {{ initialized ? t('runtime.sidebarSaveFailed') : t('runtime.sidebarLoadFailed') }}
      <n-button text type="primary" @click="retry">{{ t('runtime.retry') }}</n-button>
    </p>
    <p v-else-if="!initialized" role="status">{{ t('runtime.sidebarLoading') }}</p>
    <fieldset :disabled="!initialized" class="sidebar-editor__fields">
      <div class="sidebar-editor__toolbar">
        <n-button :disabled="!initialized" @click="pickerGroup = 'ungrouped'">{{
          t('runtime.addPage')
        }}</n-button>
        <n-button :disabled="!initialized" @click="startNaming()">{{
          t('runtime.newGroup')
        }}</n-button>
      </div>
      <form v-if="namingGroup" class="sidebar-editor__naming" @submit.prevent="saveName">
        <input
          ref="groupInput"
          v-model="groupDraft"
          :aria-label="t('runtime.groupName')"
          :placeholder="t('runtime.groupName')"
          maxlength="80"
          :aria-invalid="Boolean(nameError) || undefined"
          @keydown.esc.stop.prevent="namingGroup = null"
        />
        <n-button attr-type="submit" :disabled="!initialized">{{ t('runtime.saveName') }}</n-button>
        <n-button @click="namingGroup = null">{{ t('runtime.cancel') }}</n-button>
        <span v-if="nameError" class="sidebar-editor__error" role="alert">{{ nameError }}</span>
      </form>
      <div class="sidebar-editor__layout">
        <template v-for="section in outerSections" :key="section.key">
          <section class="sidebar-editor__section" :data-editor-section="section.key">
            <div class="sidebar-editor__heading">
              <strong>{{ section.title }}</strong>
              <n-button text :disabled="!initialized" @click="pickerGroup = section.key">{{
                t('runtime.addPage')
              }}</n-button>
            </div>
            <draggable
              :model-value="section.items"
              item-key="id"
              class="sidebar-editor__pages"
              :data-editor-group="section.key"
              :group="dragArea"
              :disabled="!initialized"
              :move="canMovePage"
              v-bind="dragOptions"
              @start="normalizeSortablePreview"
              @change="onPageSort($event, section.key)"
            >
              <template #item="{ element: item }">
                <div class="sidebar-editor__page" :data-editor-placement="item.id">
                  <n-icon :component="item.icon" aria-hidden="true" />
                  <span>{{ item.label }}</span>
                  <button
                    type="button"
                    class="sidebar-editor__remove"
                    :disabled="!initialized"
                    :aria-label="t('runtime.removeNamedPage', { label: item.label })"
                    :title="t('runtime.removeNamedPage', { label: item.label })"
                    @click="preferences.removeEntry(item.id)"
                  >
                    <n-icon :component="CloseOutline" aria-hidden="true" />
                  </button>
                </div>
              </template>
              <template #footer>
                <p v-if="!section.items.length" class="sidebar-editor__empty">
                  {{
                    section.key === 'pinned' ? t('runtime.dropToPin') : t('runtime.dropStandalone')
                  }}
                </p>
              </template>
            </draggable>
          </section>
        </template>
        <draggable
          :model-value="groups"
          item-key="key"
          handle=".sidebar-editor__group-handle"
          :disabled="!initialized"
          v-bind="dragOptions"
          @start="normalizeSortablePreview"
          @change="onGroupSort"
        >
          <template #item="{ element: section }">
            <section class="sidebar-editor__section" :data-editor-section="section.key">
              <div class="sidebar-editor__heading">
                <n-icon
                  class="sidebar-editor__group-handle"
                  :component="ReorderThreeOutline"
                  aria-hidden="true"
                />
                <strong>{{ section.title }}</strong>
                <n-button text :disabled="!initialized" @click="pickerGroup = section.key">{{
                  t('runtime.addPage')
                }}</n-button>
                <n-button
                  text
                  :disabled="!initialized"
                  @click="startNaming({ action: 'rename-group', groupKey: section.key })"
                  >{{ t('runtime.rename') }}</n-button
                >
                <n-popconfirm @positive-click="preferences.removeGroup(section.key)">
                  <template #trigger
                    ><n-button text :disabled="!initialized">{{
                      t('runtime.dissolveGroup')
                    }}</n-button></template
                  >{{ t('runtime.dissolveGroupHelp') }}</n-popconfirm
                >
              </div>
              <draggable
                :model-value="section.items"
                item-key="id"
                class="sidebar-editor__pages"
                :data-editor-group="section.key"
                :group="dragArea"
                :disabled="!initialized"
                :move="canMovePage"
                v-bind="dragOptions"
                @start="normalizeSortablePreview"
                @change="onPageSort($event, section.key)"
              >
                <template #item="{ element: item }">
                  <div class="sidebar-editor__page" :data-editor-placement="item.id">
                    <n-icon :component="item.icon" aria-hidden="true" />
                    <span>{{ item.label }}</span>
                    <button
                      type="button"
                      class="sidebar-editor__remove"
                      :disabled="!initialized"
                      :aria-label="t('runtime.removeNamedPage', { label: item.label })"
                      :title="t('runtime.removeNamedPage', { label: item.label })"
                      @click="preferences.removeEntry(item.id)"
                    >
                      <n-icon :component="CloseOutline" aria-hidden="true" />
                    </button>
                  </div>
                </template>
              </draggable>
              <p v-if="!section.items.length" class="sidebar-editor__empty">
                {{ t('runtime.emptyGroup') }}
              </p>
            </section>
          </template>
        </draggable>
      </div>
    </fieldset>
    <template #footer>
      <div class="sidebar-editor__footer">
        <n-popconfirm @positive-click="preferences.reset()">
          <template #trigger
            ><n-button :disabled="!initialized">{{
              t('runtime.restoreDefaults')
            }}</n-button></template
          >{{ t('runtime.restoreSidebarConfirm') }}</n-popconfirm
        >
        <n-button type="primary" @click="close">{{ t('runtime.done') }}</n-button>
      </div>
    </template>
  </n-modal>
  <SidebarCustomize :group-key="pickerGroup" @close="pickerGroup = null" />
</template>

<style scoped>
.sidebar-editor__hint,
.sidebar-editor__empty {
  color: var(--mower-text-muted);
}
.sidebar-editor__hint {
  flex: none;
  margin: 0 0 12px;
  font-size: 12px;
  line-height: 1.6;
}
.sidebar-editor__fields {
  display: flex;
  flex: 1 1 auto;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
  height: 52dvh;
  margin: 0;
  padding: 0;
  border: 0;
}
.sidebar-editor__toolbar,
.sidebar-editor__naming,
.sidebar-editor__heading,
.sidebar-editor__page,
.sidebar-editor__footer {
  display: flex;
  align-items: center;
  gap: 10px;
}
.sidebar-editor__naming {
  flex-wrap: wrap;
  margin-top: 12px;
}
.sidebar-editor__toolbar,
.sidebar-editor__naming {
  flex: none;
}
.sidebar-editor__layout {
  flex: 1 1 auto;
  min-height: 0;
  max-height: 52dvh;
  margin-top: 12px;
  padding-right: 6px;
  overflow-y: auto;
}
.sidebar-editor__section {
  padding: 8px 0;
  border-top: 1px solid var(--mower-border);
}
.sidebar-editor__heading {
  flex-wrap: wrap;
  margin-bottom: 4px;
  font-size: 13px;
}
.sidebar-editor__heading :deep(.n-button) {
  font-size: 12px;
  height: 24px;
}
.sidebar-editor__heading strong {
  margin-right: auto;
  font-weight: 600;
}
.sidebar-editor__group-handle {
  cursor: grab;
}
.sidebar-editor__pages {
  min-height: 28px;
}
.sidebar-editor__page {
  min-height: 34px;
  padding: 0 4px;
  gap: 8px;
  font-size: 13px;
  cursor: grab;
}
.sidebar-editor__page > span {
  flex: 1;
  min-width: 0;
}
.sidebar-editor__naming input {
  min-width: 0;
  padding: 5px 7px;
  border: 1px solid var(--mower-border);
  border-radius: 4px;
  background: var(--mower-surface);
  color: inherit;
  font: inherit;
}
.sidebar-editor__remove {
  display: grid;
  flex: 0 0 26px;
  width: 26px;
  height: 26px;
  padding: 0;
  place-items: center;
  border: 0;
  border-radius: 4px;
  background: transparent;
  color: var(--mower-text-muted);
  cursor: pointer;
  opacity: 0;
}
.sidebar-editor__page:hover .sidebar-editor__remove,
.sidebar-editor__page:focus-within .sidebar-editor__remove {
  opacity: 1;
}
.sidebar-editor__remove:hover,
.sidebar-editor__remove:focus-visible {
  color: var(--mower-error);
  background: var(--mower-border);
}
.sidebar-editor__remove:focus-visible {
  outline: 2px solid currentColor;
  outline-offset: 1px;
}
.sidebar-editor__empty {
  margin: 4px;
  font-size: 12px;
}
.sidebar-editor__error {
  flex: none;
  color: var(--mower-error, #d03050);
}
.sidebar-editor__footer {
  justify-content: space-between;
}
@media (max-width: 440px) {
  .sidebar-editor__page {
    gap: 7px;
    font-size: 12px;
  }
}
@media (hover: none), (pointer: coarse) {
  .sidebar-editor__remove {
    opacity: 1;
  }
}
@media (prefers-reduced-motion: reduce) {
  .sidebar-editor__layout :deep(*) {
    transition: none !important;
  }
}
</style>
