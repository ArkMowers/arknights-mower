<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import draggable from 'vuedraggable'
import ReorderThreeOutline from '@vicons/ionicons5/es/ReorderThreeOutline'
import CloseOutline from '@vicons/ionicons5/es/CloseOutline'
import { useThemeVars } from 'naive-ui'
import { useSidebarPreferences } from '@/composables/sidebarPreferences'
import SidebarCustomize from './SidebarCustomize.vue'
import { normalizeSortablePreview } from '@/utils/sortablePreview'
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
const nameError = ref('')
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
const groups = computed(() => visibleSections.value)
const outerSections = computed(() => [
  { key: 'pinned', title: '置顶', items: pinnedItems.value },
  { key: 'ungrouped', title: '独立页面', items: standaloneItems.value }
])

function close() {
  pickerGroup.value = null
  emit('update:show', false)
}

function startNaming(request = {}) {
  const group = state.value.groups.find((entry) => entry.key === request.groupKey)
  namingGroup.value = request.action === 'rename-group' && group ? group.key : 'new'
  groupDraft.value = group?.title || ''
  nameError.value = ''
  void nextTick(() => groupInput.value?.focus())
}

watch(
  () => [props.show, props.request],
  () => {
    namingGroup.value = null
    nameError.value = ''
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
    nameError.value = '请填写分组名称。'
    return
  }
  if (namingGroup.value === 'new') {
    const key = preferences.addGroup(title)
    if (!key) {
      nameError.value = '暂时无法新建分组，最多可保留 20 个分组。'
      return
    }
    const after = state.value.groups.findIndex((group) => group.key === props.request.afterKey)
    if (after >= 0) preferences.moveGroup(key, state.value.groups[after + 1]?.key || null)
  } else if (!preferences.renameGroup(namingGroup.value, title)) {
    nameError.value = '暂时无法修改分组名称。'
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
    title="编辑侧边栏"
    aria-label="编辑侧边栏"
    class="sidebar-editor"
    :style="dialogStyle"
    @update:show="!$event && close()"
  >
    <p class="sidebar-editor__hint">拖动页面排序、分组或置顶，修改后自动保存。</p>
    <p v-if="persistenceError" class="sidebar-editor__error" role="alert">
      {{ initialized ? '侧边栏尚未保存，当前修改仍保留在页面中。' : '暂时无法读取侧边栏布局。' }}
      <n-button text type="primary" @click="retry">重试</n-button>
    </p>
    <p v-else-if="!initialized" role="status">正在读取侧边栏布局…</p>
    <fieldset :disabled="!initialized" class="sidebar-editor__fields">
      <div class="sidebar-editor__toolbar">
        <n-button :disabled="!initialized" @click="pickerGroup = 'ungrouped'">添加页面</n-button>
        <n-button :disabled="!initialized" @click="startNaming()">新建分组</n-button>
      </div>
      <form v-if="namingGroup" class="sidebar-editor__naming" @submit.prevent="saveName">
        <input
          ref="groupInput"
          v-model="groupDraft"
          aria-label="分组名称"
          placeholder="分组名称"
          maxlength="80"
          :aria-invalid="Boolean(nameError) || undefined"
          @keydown.esc.stop.prevent="namingGroup = null"
        />
        <n-button attr-type="submit" :disabled="!initialized">保存名称</n-button>
        <n-button @click="namingGroup = null">取消</n-button>
        <span v-if="nameError" class="sidebar-editor__error" role="alert">{{ nameError }}</span>
      </form>
      <div class="sidebar-editor__layout">
        <template v-for="section in outerSections" :key="section.key">
          <section class="sidebar-editor__section" :data-editor-section="section.key">
            <div class="sidebar-editor__heading">
              <strong>{{ section.title }}</strong>
              <n-button text :disabled="!initialized" @click="pickerGroup = section.key"
                >添加页面</n-button
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
                    :aria-label="`移除${item.label}`"
                    :title="`移除${item.label}`"
                    @click="preferences.removeEntry(item.id)"
                  >
                    <n-icon :component="CloseOutline" aria-hidden="true" />
                  </button>
                </div>
              </template>
              <template #footer>
                <p v-if="!section.items.length" class="sidebar-editor__empty">
                  {{ section.key === 'pinned' ? '拖到这里即可置顶' : '拖到这里即可独立显示' }}
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
                <n-button text :disabled="!initialized" @click="pickerGroup = section.key"
                  >添加页面</n-button
                >
                <n-button
                  text
                  :disabled="!initialized"
                  @click="startNaming({ action: 'rename-group', groupKey: section.key })"
                  >重命名</n-button
                >
                <n-popconfirm @positive-click="preferences.removeGroup(section.key)">
                  <template #trigger
                    ><n-button text :disabled="!initialized">取消分组</n-button></template
                  >
                  取消分组后，组内页面会独立显示，其他分组中的副本保持原位。
                </n-popconfirm>
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
                      :aria-label="`移除${item.label}`"
                      :title="`移除${item.label}`"
                      @click="preferences.removeEntry(item.id)"
                    >
                      <n-icon :component="CloseOutline" aria-hidden="true" />
                    </button>
                  </div>
                </template>
              </draggable>
              <p v-if="!section.items.length" class="sidebar-editor__empty">分组暂无页面</p>
            </section>
          </template>
        </draggable>
      </div>
    </fieldset>
    <template #footer>
      <div class="sidebar-editor__footer">
        <n-popconfirm @positive-click="preferences.reset()">
          <template #trigger><n-button :disabled="!initialized">恢复默认</n-button></template>
          恢复默认分组、页面顺序和置顶设置？
        </n-popconfirm>
        <n-button type="primary" @click="close">完成</n-button>
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
  margin: 0 0 12px;
  font-size: 12px;
  line-height: 1.6;
}
.sidebar-editor__fields {
  min-width: 0;
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
.sidebar-editor__layout {
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
