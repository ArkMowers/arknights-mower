<template>
  <nav
    class="app-sidebar"
    :class="{
      'app-sidebar--collapsed': collapsed,
      'app-sidebar--mobile': mobile,
      'app-sidebar--dragging': dragKey || dragGroupKey
    }"
    :style="palette"
    aria-label="主导航"
  >
    <div v-if="persistenceError" class="app-sidebar__persistence" role="alert">
      <span v-if="!collapsed">{{ initialized ? '布局尚未保存' : '布局加载失败' }}</span>
      <button
        type="button"
        class="app-sidebar__retry"
        :disabled="retrying"
        :aria-label="initialized ? '重试保存侧边栏布局' : '重新加载侧边栏布局'"
        :title="initialized ? '重试保存侧边栏布局' : '重新加载侧边栏布局'"
        @click="retryPreferences"
      >
        <n-icon :component="ReloadOutline" aria-hidden="true" />
        <span v-if="!collapsed">重试</span>
      </button>
    </div>
    <component
      :is="zone.scroll ? SidebarScroll : 'div'"
      v-for="zone in sidebarZones"
      :key="zone.key"
      :class="zone.scroll ? 'app-sidebar__scroll sidebar-scroll-fade' : 'app-sidebar__pinned'"
    >
      <draggable
        :id="zone.scroll ? listId : `${listId}-pinned`"
        :class="zone.scroll ? 'app-sidebar__sections' : 'app-sidebar__pinned-sections'"
        :model-value="zone.sections"
        item-key="key"
        draggable=".app-sidebar__section--movable"
        handle=".app-sidebar__heading"
        :disabled="!initialized || collapsed || !!dragKey || !zone.scroll"
        :move="canMoveGroup"
        v-bind="dragOptions"
        @start="startGroupSort"
        @change="onGroupSort"
        @end="endDrag"
      >
        <template #item="{ element: section, index }">
          <div
            class="app-sidebar__section"
            :class="{
              'app-sidebar__section--movable': !section.pinned && !section.standalone,
              'app-sidebar__section--standalone': section.standalone,
              'app-sidebar__section--first': index === 0 && (!zone.scroll || !pinnedItems.length)
            }"
            :style="palette"
            :data-sidebar-group="section.key"
            :role="section.title ? 'group' : undefined"
            :aria-labelledby="section.title ? `${listId}-${section.key}` : undefined"
          >
            <div
              v-if="section.title"
              class="app-sidebar__heading-row"
              :class="{ 'is-menu-open': openMenu === `group-${section.key}` }"
            >
              <component
                :is="section.pinned ? 'div' : 'button'"
                :id="`${listId}-${section.key}`"
                class="app-sidebar__heading"
                v-bind="
                  section.pinned
                    ? {}
                    : {
                        type: 'button',
                        disabled: collapsed || !initialized,
                        'aria-expanded': sectionOpen(section),
                        'aria-controls': `${listId}-${section.key}-items`
                      }
                "
                draggable="false"
                @pointerdown="prepareActivation"
                @keydown="prepareActivation"
                @click.capture="guardDragClick"
                @click="!section.pinned && toggleGroup(section.key)"
              >
                <span class="app-sidebar__heading-text">{{ section.title || '常用' }}</span>
                <n-icon
                  v-if="!section.pinned"
                  class="app-sidebar__chevron"
                  :class="{ 'is-collapsed': section.collapsed }"
                  :component="ChevronDownOutline"
                  aria-hidden="true"
                />
              </component>
              <n-dropdown
                v-if="!collapsed"
                :disabled="!initialized"
                trigger="click"
                size="small"
                :theme-overrides="dropdownTheme"
                placement="bottom-end"
                :options="groupOptions(section.key)"
                :node-props="menuNodeProps"
                @update:show="(show) => setMenuOpen(`group-${section.key}`, show)"
                @select="(key) => selectGroupAction(key, section.key)"
              >
                <button
                  type="button"
                  class="app-sidebar__menu app-sidebar__group-menu"
                  :aria-label="`管理${section.title || '常用'}分组`"
                  aria-haspopup="menu"
                  :disabled="!initialized"
                >
                  <n-icon :component="EllipsisHorizontal" aria-hidden="true" />
                </button>
              </n-dropdown>
            </div>
            <Transition name="sidebar-group" :css="!collapsed && !dragKey">
              <div
                v-show="sectionOpen(section)"
                class="app-sidebar__collapse"
                :inert="!sectionOpen(section) || undefined"
                :aria-hidden="!sectionOpen(section) || undefined"
              >
                <div class="app-sidebar__collapse-clip">
                  <draggable
                    :id="`${listId}-${section.key}-items`"
                    class="app-sidebar__items"
                    :model-value="section.items"
                    item-key="id"
                    :data-sidebar-items-group="section.key"
                    :group="pageDragGroup"
                    :disabled="!initialized || collapsed || !!dragGroupKey"
                    :move="canMovePage"
                    v-bind="dragOptions"
                    @start="startPageSort"
                    @change="(change) => onPageSort(change, section.key)"
                    @end="endDrag"
                  >
                    <template #item="{ element: item }">
                      <div
                        class="app-sidebar__row"
                        :class="{ 'is-menu-open': openMenu === item.id }"
                        :style="palette"
                        :data-sidebar-item="item.key"
                        :data-sidebar-placement="item.id"
                      >
                        <component
                          :is="item.to ? SessionLink : item.action ? 'button' : 'a'"
                          v-bind="linkAttrs(item)"
                          class="app-sidebar__link"
                          :title="item.label"
                          :aria-describedby="collapsed ? undefined : `${listId}-drag-help`"
                          @pointerdown="prepareActivation"
                          @keydown="prepareActivation"
                          @click.capture="guardDragClick"
                          @click="activate(item, $event)"
                          @focus="focusTip(item.id, $event.target)"
                          @blur="blurTip(item.id)"
                        >
                          <n-tooltip
                            placement="right"
                            :disabled="!collapsed"
                            :show="tipKey === item.id"
                            @update:show="(show) => setTip(item.id, show)"
                          >
                            <template #trigger>
                              <span class="app-sidebar__icon">
                                <n-icon :component="item.icon" aria-hidden="true" />
                              </span>
                            </template>
                            {{ item.label }}
                          </n-tooltip>
                          <span class="app-sidebar__label">{{ item.label }}</span>
                          <template v-if="item.href">
                            <span class="visually-hidden">（在新标签页打开）</span>
                            <n-icon
                              class="app-sidebar__external"
                              :component="OpenOutline"
                              aria-hidden="true"
                            />
                          </template>
                        </component>
                        <n-dropdown
                          v-if="!collapsed"
                          :disabled="!initialized"
                          trigger="click"
                          size="small"
                          :theme-overrides="dropdownTheme"
                          placement="bottom-end"
                          :options="itemOptions(item)"
                          :node-props="menuNodeProps"
                          @update:show="(show) => setMenuOpen(item.id, show)"
                          @select="(key) => selectItemAction(key, item)"
                        >
                          <button
                            type="button"
                            class="app-sidebar__menu"
                            :aria-label="`管理${item.label}`"
                            aria-haspopup="menu"
                            :disabled="!initialized"
                            @click.stop
                          >
                            <n-icon :component="EllipsisHorizontal" aria-hidden="true" />
                          </button>
                        </n-dropdown>
                      </div>
                    </template>
                  </draggable>
                </div>
              </div>
            </Transition>
          </div>
        </template>
      </draggable>
    </component>
    <div class="app-sidebar__footer">
      <div class="app-sidebar__items app-sidebar__footer-items">
        <component
          :is="item.to ? SessionLink : 'button'"
          v-for="item in footerItems"
          :key="item.key"
          v-bind="linkAttrs(item)"
          class="app-sidebar__link"
          :data-sidebar-item="item.key"
          :title="item.label"
          @pointerdown="prepareActivation"
          @keydown="prepareActivation"
          @click.capture="guardDragClick"
          @click="activate(item, $event)"
          @focus="focusTip(item.key, $event.target)"
          @blur="blurTip(item.key)"
        >
          <n-tooltip
            placement="right"
            :disabled="!collapsed"
            :show="tipKey === item.key"
            @update:show="(show) => setTip(item.key, show)"
          >
            <template #trigger
              ><span class="app-sidebar__icon"
                ><n-icon :component="item.icon" aria-hidden="true" /></span
            ></template>
            {{ item.label }}
          </n-tooltip>
          <span class="app-sidebar__label">{{ item.label }}</span>
        </component>
      </div>
    </div>
    <SidebarCustomize :group-key="addingGroup" @close="addingGroup = null" />
    <span :id="`${listId}-drag-help`" class="visually-hidden">
      拖动页面可排序、移到分组或独立显示，菜单可置顶或移除当前页面。
    </span>
  </nav>
</template>

<script setup>
import ChevronDownOutline from '@vicons/ionicons5/es/ChevronDownOutline'
import EllipsisHorizontal from '@vicons/ionicons5/es/EllipsisHorizontal'
import OpenOutline from '@vicons/ionicons5/es/OpenOutline'
import ReloadOutline from '@vicons/ionicons5/es/ReloadOutline'
import { useThemeVars } from 'naive-ui'
import draggable from 'vuedraggable'
import { computed, ref, useId, watch } from 'vue'
import SessionLink from './SessionLink.vue'
import SidebarCustomize from './SidebarCustomize.vue'
import SidebarScroll from './SidebarScroll.vue'
import { useSidebarPreferences } from '@/composables/sidebarPreferences'
import { useCollapsedTips } from '@/composables/useCollapsedTips'
import { normalizeSortablePreview } from '@/utils/sortablePreview'
import '@/styles/sidebar.css'
import '@/styles/drag.css'

const props = defineProps({
  collapsed: { type: Boolean, default: false },
  mobile: { type: Boolean, default: false }
})
const emit = defineEmits(['navigate', 'open-chat', 'customize'])

const preferences = useSidebarPreferences()
const {
  state,
  initialized,
  persistenceError,
  visibleSections,
  standaloneItems,
  pinnedItems,
  footerItems,
  toggleGroup,
  moveItem
} = preferences
const addingGroup = ref(null)
const openMenu = ref(null)
const dropdownTheme = {
  borderRadius: '8px',
  fontSizeSmall: '12px',
  optionHeightSmall: '28px',
  padding: '4px 0',
  optionPrefixWidthSmall: '10px',
  optionSuffixWidthSmall: '8px'
}
const menuNodeProps = (option) => ({ title: option.description || undefined })
function setMenuOpen(key, show) {
  if (show) openMenu.value = key
  else if (openMenu.value === key) openMenu.value = null
}
const retrying = ref(false)
watch(
  () => state.value.groups.map((group) => group.key),
  (groupKeys) => {
    if (
      addingGroup.value &&
      !['pinned', 'ungrouped'].includes(addingGroup.value) &&
      !groupKeys.includes(addingGroup.value)
    )
      addingGroup.value = null
  }
)
const dragKey = ref(null)
const dragGroupKey = ref(null)
const draggedItem = ref(null)
const sidebarSections = computed(() => [
  ...(standaloneItems.value.length || dragKey.value || !visibleSections.value.length
    ? [{ key: 'ungrouped', standalone: true, items: standaloneItems.value }]
    : []),
  ...visibleSections.value
])
const pinnedSection = computed(() => ({
  key: 'pinned',
  title: '置顶',
  pinned: true,
  items: pinnedItems.value
}))
const sidebarZones = computed(() => [
  ...(pinnedItems.value.length
    ? [{ key: 'pinned', scroll: false, sections: [pinnedSection.value] }]
    : []),
  { key: 'main', scroll: true, sections: sidebarSections.value }
])
const listId = useId()
const pageDragGroup = `mower-sidebar-pages-${listId}`
const dragOptions = {
  animation:
    typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
      ? 0
      : 180,
  easing: 'cubic-bezier(0.2, 0, 0, 1)',
  forceFallback: true,
  fallbackOnBody: true,
  fallbackTolerance: 8,
  delay: 180,
  delayOnTouchOnly: true,
  touchStartThreshold: 8,
  emptyInsertThreshold: 18,
  ghostClass: 'mower-drag-ghost',
  chosenClass: 'sidebar-drag-chosen',
  fallbackClass: 'mower-drag-fallback',
  filter: '.app-sidebar__menu, input, textarea',
  preventOnFilter: false
}
const themeVars = useThemeVars()
const palette = computed(() => ({
  '--sidebar-text': themeVars.value.textColor2,
  '--sidebar-active-text': themeVars.value.primaryColorPressed,
  '--sidebar-focus': themeVars.value.primaryColor,
  '--sidebar-surface': themeVars.value.popoverColor,
  '--sidebar-hover': `color-mix(in srgb, ${themeVars.value.textColor2} 7%, transparent)`,
  '--sidebar-pressed': `color-mix(in srgb, ${themeVars.value.textColor2} 12%, transparent)`,
  '--sidebar-muted': `color-mix(in srgb, ${themeVars.value.textColor2} 72%, transparent)`,
  '--sidebar-rule': `color-mix(in srgb, ${themeVars.value.textColor2} 10%, transparent)`,
  '--mower-drag-surface': themeVars.value.popoverColor,
  '--mower-drag-text': themeVars.value.textColor2,
  '--mower-drag-accent': themeVars.value.primaryColor
}))

// Internal entries retain the session; external entries open a new tab without opener access.
function linkAttrs(item) {
  if (item.to) return { to: item.to, exactActiveClass: 'is-active', draggable: false }
  if (item.action) return { type: 'button', draggable: false }
  return { href: item.href, target: '_blank', rel: 'noopener noreferrer', draggable: false }
}

function prepareActivation() {
  draggedItem.value = null
}

function guardDragClick(event) {
  if (!draggedItem.value) return false
  event?.preventDefault()
  event?.stopPropagation()
  draggedItem.value = null
  return true
}

function activate(item, event) {
  if (event?.defaultPrevented || guardDragClick(event)) return
  emit(item.action === 'chat' ? 'open-chat' : 'navigate')
}

function startEditing() {
  emit('customize')
}

async function retryPreferences() {
  if (retrying.value) return
  retrying.value = true
  try {
    return await preferences.retrySave()
  } finally {
    retrying.value = false
  }
}

function finishEditing() {
  addingGroup.value = null
  endDrag()
  return true
}

defineExpose({ startEditing, finishEditing })

function sectionOpen(section) {
  return (
    props.collapsed || section.pinned || section.standalone || !!dragKey.value || !section.collapsed
  )
}

function targetHasPage(item, groupKey) {
  return state.value.placements.some(
    (entry) =>
      entry.id !== item.id &&
      entry.key === item.key &&
      (groupKey === 'pinned' ? entry.pinned : entry.group === groupKey && !entry.pinned)
  )
}

function itemOptions(item) {
  const placement = state.value.placements.find((entry) => entry.id === item.id)
  const targetOccupied = targetHasPage(item, placement?.pinned ? placement.group : 'pinned')
  return [
    {
      key: 'pin',
      label: placement?.pinned ? '取消置顶' : '置顶',
      disabled: targetOccupied,
      ...(targetOccupied && placement?.pinned
        ? { description: '原位置已有此页面，可移除此处的入口。' }
        : {})
    },
    { type: 'divider', key: 'page-remove-divider' },
    {
      key: 'remove',
      label: placement?.pinned
        ? '移除此入口'
        : placement?.group === 'ungrouped'
          ? '从侧边栏移除'
          : '从此分组移除'
    }
  ]
}

function selectItemAction(action, item) {
  if (!initialized.value) return
  if (action === 'pin') {
    const placement = state.value.placements.find((entry) => entry.id === item.id)
    preferences.setPinned(item.id, !placement?.pinned)
  } else if (action === 'remove') {
    preferences.removeEntry(item.id)
  }
}

function groupOptions(groupKey) {
  if (groupKey === 'pinned')
    return [
      { key: 'add', label: '添加页面' },
      { type: 'divider', key: 'pinned-actions-divider' },
      { key: 'unpin-all', label: '取消全部置顶' }
    ]
  return [
    { key: 'add', label: '添加页面' },
    { key: 'new', label: '新建分组' },
    { type: 'divider', key: 'group-edit-divider' },
    { key: 'rename', label: '重命名分组' },
    { type: 'divider', key: 'group-dissolve-divider' },
    {
      key: 'dissolve-options',
      label: '取消分组',
      children: [{ key: 'dissolve', label: '确认取消分组，页面独立显示' }]
    }
  ]
}

function selectGroupAction(action, groupKey) {
  if (!initialized.value) return
  if (action === 'add') {
    addingGroup.value = groupKey
    return
  }
  if (action === 'new') {
    emit('customize', { action: 'new-group', afterKey: groupKey })
    return
  }
  if (action === 'unpin-all') {
    pinnedItems.value.forEach((item) => {
      if (!preferences.setPinned(item.id, false)) preferences.removeEntry(item.id)
    })
    return
  }
  if (!state.value.groups.some((entry) => entry.key === groupKey)) return
  if (action === 'rename') {
    emit('customize', { action: 'rename-group', groupKey })
  } else if (action === 'dissolve') {
    preferences.removeGroup(groupKey)
  }
}

function startPageSort(event) {
  const key = event.item?.dataset.sidebarPlacement
  const placement = state.value.placements.find((item) => item.id === key)
  if (
    !initialized.value ||
    props.collapsed ||
    !placement ||
    !preferences.catalog.value.some((item) => item.key === placement.key)
  )
    return
  normalizeSortablePreview(event)
  dragKey.value = key
  draggedItem.value = key
}

function startGroupSort(event) {
  const key = event.item?.dataset.sidebarGroup
  if (
    !initialized.value ||
    props.collapsed ||
    !state.value.groups.some((group) => group.key === key)
  )
    return
  normalizeSortablePreview(event)
  dragGroupKey.value = key
  draggedItem.value = `group:${key}`
}

function endDrag() {
  dragGroupKey.value = null
  dragKey.value = null
}

function canMovePage(event) {
  if (!initialized.value || props.collapsed) return false
  const item = event.draggedContext?.element
  const group = event.to?.dataset.sidebarItemsGroup
  return Boolean(
    item &&
    (['pinned', 'ungrouped'].includes(group) ||
      state.value.groups.some((entry) => entry.key === group)) &&
    !targetHasPage(item, group)
  )
}

function onPageSort(change, group) {
  if (!initialized.value || props.collapsed) return
  const mutation = change.added || change.moved
  if (!mutation) return
  const section =
    group === 'pinned'
      ? pinnedSection.value
      : sidebarSections.value.find((entry) => entry.key === group)
  if (!section) return
  const remaining = section.items.filter((item) => item.id !== mutation.element.id)
  moveItem(mutation.element.id, group, remaining[mutation.newIndex]?.id || null)
}

function canMoveGroup(event) {
  return (
    initialized.value &&
    !props.collapsed &&
    state.value.groups.some((group) => group.key === event.draggedContext?.element?.key) &&
    !event.relatedContext?.element?.standalone &&
    !event.relatedContext?.element?.pinned
  )
}

function onGroupSort(change) {
  if (!initialized.value || props.collapsed || !change.moved) return
  const { element, newIndex } = change.moved
  if (!state.value.groups.some((group) => group.key === element.key)) return
  const remaining = state.value.groups.filter((group) => group.key !== element.key)
  const index = Math.max(0, newIndex - Number(Boolean(sidebarSections.value[0]?.standalone)))
  preferences.moveGroup(element.key, remaining[index]?.key || null)
}

// Tooltips anchor on the icon column in the collapsed rail.
const { tipKey, setTip, focusTip, blurTip } = useCollapsedTips(() => props.collapsed)
</script>

<style scoped>
.app-sidebar {
  --sidebar-hover: color-mix(in srgb, var(--sidebar-text) 7%, transparent);
  --sidebar-pressed: color-mix(in srgb, var(--sidebar-text) 12%, transparent);
  --sidebar-muted: color-mix(in srgb, var(--sidebar-text) 72%, transparent);
  --sidebar-rule: color-mix(in srgb, var(--sidebar-text) 10%, transparent);
  position: relative;
  isolation: isolate;
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
  color: var(--sidebar-text);
}

.app-sidebar :deep(.app-sidebar__scroll) {
  position: relative;
  z-index: 0;
  flex: 1 1 0;
  min-height: 0;
}

.app-sidebar__sections {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 8px 16px 10px;
}

.app-sidebar__section,
.app-sidebar__footer,
.app-sidebar__items {
  display: flex;
  flex-direction: column;
  min-width: 0;
  gap: 2px;
}

.app-sidebar__section {
  min-height: 4px;
  border-radius: 8px;
}

.app-sidebar__section .app-sidebar__items:empty {
  min-height: 18px;
}

.app-sidebar__sections > .app-sidebar__section--standalone:not(:has(.app-sidebar__row)) {
  position: absolute;
  top: 8px;
  right: 16px;
  left: 16px;
}

.app-sidebar__collapse {
  display: grid;
  grid-template-rows: 1fr;
}

.app-sidebar__collapse-clip {
  min-height: 0;
  min-width: 0;
  overflow: hidden;
}

.sidebar-group-enter-active,
.sidebar-group-leave-active {
  transition:
    grid-template-rows 180ms cubic-bezier(0.2, 0, 0, 1),
    opacity 140ms ease-out;
}

.sidebar-group-enter-from,
.sidebar-group-leave-to {
  grid-template-rows: 0fr;
  opacity: 0;
}

.app-sidebar__footer {
  position: relative;
  z-index: 1;
  flex: none;
  box-sizing: border-box;
  min-height: 0;
  padding: 12px 16px 8px;
}

.app-sidebar__pinned {
  flex: 0 1 auto;
  min-height: 0;
  max-height: 45%;
  box-sizing: border-box;
  padding: 4px 16px;
  overflow-x: hidden;
  overflow-y: auto;
  scrollbar-width: thin;
}

.app-sidebar__persistence {
  display: flex;
  flex: none;
  align-items: center;
  justify-content: space-between;
  gap: 4px;
  padding: 6px 16px 6px 14px;
  font-size: 12px;
  color: var(--sidebar-muted);
}

.app-sidebar__retry {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px;
  border: 0;
  border-radius: 4px;
  background: transparent;
  color: inherit;
  font: inherit;
  cursor: pointer;
}

.app-sidebar__retry:hover {
  background: var(--sidebar-hover);
}

.app-sidebar__retry:focus-visible {
  outline: 2px solid var(--sidebar-focus);
}

.app-sidebar__retry:disabled {
  opacity: 0.45;
}

.app-sidebar__retry:disabled,
.app-sidebar__menu:disabled {
  cursor: default;
}

.app-sidebar--collapsed .app-sidebar__persistence {
  justify-content: center;
  padding-inline: 8px;
}

.app-sidebar__footer-items .app-sidebar__link {
  padding-right: 6px;
}

/* Collapsed group headings become compact dividers between the icon rows. */
.app-sidebar__heading-row {
  position: relative;
  display: flex;
  align-items: center;
  min-height: 28px;
  margin-inline: -8px;
  border-radius: 6px;
}

.app-sidebar__heading {
  position: relative;
  box-sizing: border-box;
  min-width: 0;
  display: flex;
  align-items: center;
  height: 28px;
  flex-shrink: 0;
  width: 100%;
  padding: 0 40px 0 8px;
  overflow: hidden;
  border: 0;
  border-radius: 6px;
  background: transparent;
  font: inherit;
  font-size: 12px;
  font-weight: 600;
  color: var(--sidebar-muted);
  text-align: left;
  white-space: nowrap;
}

button.app-sidebar__heading:not(:disabled) {
  cursor: pointer;
}

.app-sidebar__heading-row:has(button:not(:disabled)):hover,
.app-sidebar__heading-row:has(:focus-visible),
.app-sidebar__heading-row.is-menu-open {
  background: var(--sidebar-hover);
}

.app-sidebar__heading:focus-visible {
  outline: 2px solid var(--sidebar-focus);
  outline-offset: -2px;
}

.app-sidebar__heading::after {
  content: '';
  position: absolute;
  top: 50%;
  left: calc((var(--shell-rail-size, 64px) - 16px) / 2);
  width: 24px;
  border-top: 1px solid var(--sidebar-rule);
  transform: translateX(-50%);
  opacity: 0;
  transition: opacity 0.2s;
}

.app-sidebar__heading-text {
  flex: 1 1 auto;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  transition: opacity 0.2s;
}

.app-sidebar__chevron {
  flex-shrink: 0;
  font-size: 12px;
  opacity: 0;
  transition:
    transform 0.2s,
    opacity 0.15s;
}

.app-sidebar__chevron.is-collapsed {
  transform: rotate(-90deg);
  opacity: 1;
}

.app-sidebar__heading-row:has(:focus-visible) .app-sidebar__chevron,
.app-sidebar__heading-row.is-menu-open .app-sidebar__chevron {
  opacity: 1;
}

@media (hover: hover) {
  .app-sidebar__heading-row:hover .app-sidebar__chevron {
    opacity: 1;
  }
}

.app-sidebar__row {
  position: relative;
  min-width: 0;
}

.app-sidebar__row.mower-drag-fallback,
.app-sidebar__section.mower-drag-fallback {
  overflow: hidden;
  border-radius: 10px;
  background: var(--sidebar-surface);
  color: var(--sidebar-text);
}

.app-sidebar__section.mower-drag-fallback {
  max-height: min(420px, 60dvh);
  border: 0 !important;
}

.mower-drag-fallback .app-sidebar__menu {
  visibility: hidden;
}

.app-sidebar__link {
  position: relative;
  display: flex;
  align-items: center;
  gap: 2px;
  box-sizing: border-box;
  width: 100%;
  height: 36px;
  padding: 0 24px 0 10px;
  overflow: hidden;
  border: 0;
  border-radius: 10px;
  background: transparent;
  color: inherit;
  font: inherit;
  font-size: 14px;
  text-align: left;
  text-decoration: none;
  white-space: nowrap;
  cursor: pointer;
}

.app-sidebar__menu {
  position: absolute;
  top: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 28px;
  padding: 0;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: var(--sidebar-muted);
  font-size: 16px;
  opacity: 0;
  pointer-events: none;
  cursor: pointer;
}

.app-sidebar__menu {
  right: 4px;
}

.app-sidebar__group-menu {
  top: 2px;
  right: 12px;
  height: 24px;
  border-radius: 4px;
}

.app-sidebar--mobile .app-sidebar__menu {
  opacity: 1;
  pointer-events: auto;
}

.app-sidebar--mobile .app-sidebar__external {
  opacity: 0;
}

.app-sidebar--mobile .app-sidebar__link {
  height: 44px;
  padding-right: 48px;
}

.app-sidebar--mobile .app-sidebar__footer-items .app-sidebar__link {
  padding-right: 6px;
}

.app-sidebar--mobile .app-sidebar__menu {
  top: 0;
  width: 44px;
  height: 44px;
}

.app-sidebar--mobile .app-sidebar__heading-row,
.app-sidebar--mobile .app-sidebar__heading {
  height: 44px;
}

.app-sidebar--mobile .app-sidebar__heading {
  padding-right: 60px;
}

.app-sidebar__row:hover .app-sidebar__menu,
.app-sidebar__row:has(:focus-visible) .app-sidebar__menu,
.app-sidebar__heading-row:hover .app-sidebar__menu,
.app-sidebar__heading-row:has(:focus-visible) .app-sidebar__menu,
.app-sidebar__row.is-menu-open .app-sidebar__menu,
.app-sidebar__heading-row.is-menu-open .app-sidebar__menu {
  opacity: 1;
  pointer-events: auto;
}

.app-sidebar__menu:hover {
  background: var(--sidebar-pressed);
}

.app-sidebar__menu:focus-visible {
  opacity: 1;
  outline: 2px solid var(--sidebar-focus);
}

.app-sidebar__link:hover {
  background: var(--sidebar-hover);
}

.app-sidebar__link:active {
  background: var(--sidebar-pressed);
}

.app-sidebar:not(.app-sidebar--collapsed) .app-sidebar__section--movable .app-sidebar__heading,
.app-sidebar:not(.app-sidebar--collapsed) .app-sidebar__sections .app-sidebar__link {
  user-select: none;
}

.app-sidebar--dragging .app-sidebar__link,
.app-sidebar--dragging .app-sidebar__heading {
  cursor: grabbing !important;
}

.app-sidebar__link:focus-visible {
  outline: 2px solid var(--sidebar-focus);
  outline-offset: -2px;
}

.app-sidebar__link.is-active {
  background: var(--mower-primary-block, color-mix(in srgb, var(--sidebar-focus) 14%, transparent));
  color: var(--sidebar-active-text);
  font-weight: 600;
}

.app-sidebar__icon {
  display: flex;
  flex: 0 0 28px;
  align-self: stretch;
  align-items: center;
  justify-content: center;
  font-size: 20px;
}

.app-sidebar--collapsed .app-sidebar__icon {
  flex-basis: calc(var(--shell-rail-size, 64px) - 16px);
  font-size: 22px;
}

.app-sidebar__label {
  flex: 1 1 auto;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  transition: opacity 0.2s;
}

.app-sidebar__external {
  position: absolute;
  right: 6px;
  top: 11px;
  font-size: 14px;
  opacity: 0.6;
  transition: opacity 0.2s;
}

.app-sidebar__row:hover .app-sidebar__external,
.app-sidebar__row:has(:focus-visible) .app-sidebar__external,
.app-sidebar__row.is-menu-open .app-sidebar__external {
  opacity: 0;
}

.app-sidebar--collapsed .app-sidebar__label,
.app-sidebar--collapsed .app-sidebar__heading-text,
.app-sidebar--collapsed .app-sidebar__external,
.app-sidebar--collapsed .app-sidebar__chevron {
  opacity: 0;
}

.app-sidebar--collapsed .app-sidebar__link {
  padding-inline: 0;
  gap: 0;
}

.app-sidebar--collapsed .app-sidebar__sections {
  gap: 4px;
  padding: 4px 8px 6px;
}

.app-sidebar--collapsed .app-sidebar__pinned {
  padding: 4px 8px;
}

.app-sidebar--collapsed .app-sidebar__footer {
  padding: 10px 8px 6px;
}

.app-sidebar:not(.app-sidebar--mobile) .app-sidebar__footer {
  padding-bottom: 16px;
}

.app-sidebar--collapsed .app-sidebar__heading-row {
  min-height: 12px;
  margin-inline: 0;
}

.app-sidebar--collapsed .app-sidebar__heading {
  height: 12px;
}

.app-sidebar--collapsed .app-sidebar__heading::after {
  opacity: 1;
}

.app-sidebar--collapsed .app-sidebar__section--first .app-sidebar__heading::after {
  content: none;
}

.visually-hidden {
  position: absolute;
  width: 1px;
  height: 1px;
  margin: -1px;
  padding: 0;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
  border: 0;
}

@media (hover: none) {
  .app-sidebar__menu {
    opacity: 1;
    pointer-events: auto;
  }
  .app-sidebar__external {
    opacity: 0;
  }
}

@media (prefers-reduced-motion: reduce) {
  .sidebar-group-enter-active,
  .sidebar-group-leave-active,
  .app-sidebar__label,
  .app-sidebar__heading-text,
  .app-sidebar__heading::after,
  .app-sidebar__external,
  .app-sidebar__chevron {
    transition: none;
  }
}
</style>
