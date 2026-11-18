<script setup>
import { computed, ref, useId, watch } from 'vue'
import SearchIcon from '@vicons/fluent/es/Search20Regular'
import CollapseNavigationIcon from '@vicons/fluent/es/PanelLeftContract20Regular'
import ExpandNavigationIcon from '@vicons/fluent/es/PanelLeftExpand20Regular'
import { matchesSettingsSearch, settingsElementKeywords } from '@/utils/settingsSearch'
import { defaultSettingsFavorites } from './model'

const props = defineProps({
  tasks: { type: Array, required: true },
  editors: { type: Array, default: () => [] },
  favoriteIds: { type: Array, default: () => defaultSettingsFavorites },
  saveFavorites: { type: Function, default: undefined },
  loadFavorites: { type: Function, default: undefined },
  groups: { type: Array, required: true },
  selectedId: { type: String, required: true },
  selectedTitle: { type: String, default: '选择配置' },
  statuses: { type: Object, required: true },
  connectionEnabled: { type: Boolean, default: true },
  connectionId: { type: String, default: 'device' },
  selectionRequest: { type: Number, default: 0 },
  collapsed: { type: Boolean, default: false }
})
const emit = defineEmits(['select', 'toggle', 'update:collapsed'])
const query = ref('')
const directory = ref(null)
const directoryScroll = ref(null)
const renderedKeywords = ref({})
const directoryId = useId()
const mobileOpen = ref(false)
const mobileToggle = ref(null)
const editingFavorites = ref(false)
const favoritesBusy = ref(false)
const favoriteDraft = ref([])
const favoriteQuery = ref('')
const favoriteError = ref('')

const directorySelectedId = computed(() =>
  props.selectedId === 'idle' ? props.connectionId : props.selectedId
)

function matchesEditor(words, editor, groupLabel) {
  return matchesSettingsSearch(
    words,
    editor.title,
    editor.description,
    editor.searchKeywords,
    renderedKeywords.value[editor.id],
    groupLabel
  )
}

const visibleFavorites = computed(() =>
  props.favoriteIds
    .map((id) => props.editors.find((editor) => editor.id === id))
    .filter((editor) => editor && matchesEditor(query.value, editor, '常用设置'))
)
const favoriteOptions = computed(() =>
  props.editors.filter((editor) => matchesEditor(favoriteQuery.value, editor))
)

async function editFavorites() {
  if (favoritesBusy.value) return
  favoritesBusy.value = true
  favoriteError.value = ''
  const loaded = props.loadFavorites ? await props.loadFavorites() : true
  favoritesBusy.value = false
  if (!loaded) {
    favoriteError.value = '常用设置读取失败，请重试。'
    return
  }
  favoriteDraft.value = [...props.favoriteIds]
  favoriteQuery.value = ''
  editingFavorites.value = true
}

function closeFavorites() {
  if (!favoritesBusy.value) {
    editingFavorites.value = false
    favoriteError.value = ''
  }
}

async function confirmFavorites() {
  if (favoritesBusy.value) return
  favoritesBusy.value = true
  favoriteError.value = ''
  const saved = await props.saveFavorites([...favoriteDraft.value])
  favoritesBusy.value = false
  if (saved) closeFavorites()
  else favoriteError.value = '常用设置保存失败，请重试。'
}

function revealSelectedEntry() {
  const viewport = directoryScroll.value
  if (!viewport?.clientHeight) return
  const bounds = viewport.getBoundingClientRect()
  if (bounds.height <= 0) return
  const rows = Array.from(viewport.querySelectorAll('.checklist-task.selected'), (element) =>
    element.getBoundingClientRect()
  )
  if (!rows.length) return
  if (rows.length > 1 && rows.some((row) => row.top >= bounds.top && row.bottom <= bounds.bottom))
    return
  const [row] = rows
  const offset = (row.top + row.bottom - bounds.top - bounds.bottom) / 2
  const target = viewport.scrollTop + offset / (bounds.height / viewport.clientHeight)
  const maximum = Math.max(0, viewport.scrollHeight - viewport.clientHeight)
  const scrollTop = Math.max(0, Math.min(maximum, target))
  if (scrollTop !== viewport.scrollTop) viewport.scrollTop = scrollTop
}
watch([() => props.selectedId, directoryScroll], revealSelectedEntry, { flush: 'post' })
watch(
  query,
  () => {
    if (!query.value.trim()) return
    const workspace = directory.value?.closest?.('.task-workspace')
    const keywords = {}
    for (const panel of workspace?.querySelectorAll('[data-task-editor]') ?? []) {
      const editorId = panel.getAttribute('data-task-editor')
      const id = editorId === 'idle' ? props.connectionId : editorId
      keywords[id] = `${keywords[id] || ''} ${settingsElementKeywords(panel)}`
    }
    renderedKeywords.value = keywords
  },
  { flush: 'post' }
)
function closeDirectory() {
  if (mobileOpen.value) mobileToggle.value?.focus({ preventScroll: true })
  mobileOpen.value = false
}
function selectEntry(id) {
  closeDirectory()
  emit('select', id)
}
const visibleGroups = computed(() => {
  const connection = props.editors.find((editor) => editor.id === props.connectionId)
  return props.groups
    .map((group) => {
      const tasks = props.tasks.filter((task) => task.group === group.id)
      if (group.id === 'support' && props.connectionEnabled && connection)
        tasks.unshift({ ...connection, mode: 'automatic' })
      return {
        ...group,
        tasks: tasks.filter((task) => matchesEditor(query.value, task, group.label))
      }
    })
    .filter((group) => group.tasks.length)
})
watch(
  () => [props.selectedId, props.selectionRequest],
  (_current, previous) => {
    if (previous && props.selectionRequest !== previous[1]) closeDirectory()
    if (
      !visibleFavorites.value.some((editor) => editor.id === props.selectedId) &&
      !visibleGroups.value.some((group) =>
        group.tasks.some((task) => task.id === directorySelectedId.value)
      )
    )
      query.value = ''
  },
  { immediate: true }
)
</script>

<template>
  <nav
    ref="directory"
    class="task-checklist"
    :class="{
      'is-open': mobileOpen,
      'is-collapsed': collapsed
    }"
    aria-label="全部设置导航"
  >
    <div class="checklist-desktop-heading">
      <span class="checklist-desktop-title">配置导航</span>
      <button
        class="checklist-desktop-toggle"
        type="button"
        :aria-expanded="!collapsed"
        :aria-controls="directoryId"
        :aria-label="collapsed ? '展开配置导航' : '收起配置导航'"
        :title="collapsed ? '展开配置导航' : '收起配置导航'"
        @click="emit('update:collapsed', !collapsed)"
      >
        <n-icon :component="collapsed ? ExpandNavigationIcon : CollapseNavigationIcon" :size="20" />
      </button>
    </div>
    <button
      ref="mobileToggle"
      class="checklist-mobile-toggle"
      type="button"
      :aria-expanded="mobileOpen"
      :aria-controls="directoryId"
      :aria-label="`选择配置：${selectedTitle}`"
      @click="mobileOpen = !mobileOpen"
    >
      <span>{{ selectedTitle }}</span>
      <svg viewBox="0 0 20 20" width="18" height="18" aria-hidden="true">
        <path d="m5 7.5 5 5 5-5" fill="none" stroke="currentColor" stroke-width="1.5" />
      </svg>
    </button>
    <div :id="directoryId" class="checklist-content">
      <div class="checklist-search">
        <n-input
          v-model:value="query"
          clearable
          size="small"
          placeholder="查找功能"
          :input-props="{ 'aria-label': '查找设置' }"
        >
          <template #prefix><n-icon :component="SearchIcon" :size="16" /></template>
        </n-input>
      </div>

      <div ref="directoryScroll" class="checklist-scroll">
        <section class="checklist-group checklist-group--favorites">
          <div class="checklist-favorites-heading">
            <h3 class="checklist-group-heading">常用设置</h3>
            <button
              v-if="saveFavorites"
              type="button"
              class="checklist-favorites-edit"
              aria-label="编辑常用设置"
              :disabled="favoritesBusy"
              @click="editFavorites"
            >
              编辑
            </button>
          </div>
          <p
            v-if="favoriteError && !editingFavorites"
            class="checklist-favorites-error"
            role="alert"
          >
            {{ favoriteError }}
          </p>
          <div
            v-for="editor in visibleFavorites"
            :key="editor.id"
            class="checklist-task checklist-task--support enabled"
            :class="{ selected: selectedId === editor.id }"
            :data-favorite-id="editor.id"
          >
            <button
              class="checklist-task-select"
              type="button"
              :aria-pressed="selectedId === editor.id"
              :title="editor.title"
              @click="selectEntry(editor.id)"
            >
              {{ editor.title }}
            </button>
          </div>
          <p v-if="!query.trim() && !visibleFavorites.length" class="checklist-favorites-empty">
            暂无常用设置
          </p>
        </section>
        <section v-for="group in visibleGroups" :key="group.id" class="checklist-group">
          <h3 class="checklist-group-heading">{{ group.label }}</h3>

          <div
            v-for="task in group.tasks"
            :key="task.id"
            class="checklist-task"
            :class="{
              selected: directorySelectedId === task.id,
              enabled: task.id === connectionId || statuses[task.id],
              'checklist-task--support': ['support', 'mower'].includes(group.id)
            }"
            :data-task-id="task.id === connectionId ? undefined : task.id"
            :data-enabled="task.id === connectionId || Boolean(statuses[task.id])"
          >
            <span
              v-if="task.mode === 'automatic' && !['support', 'mower'].includes(group.id)"
              class="checklist-control-spacer"
              aria-hidden="true"
            />
            <input
              v-else-if="task.mode !== 'automatic'"
              class="checklist-checkbox"
              type="checkbox"
              :checked="Boolean(statuses[task.id])"
              :disabled="task.disabled"
              :indeterminate.prop="Boolean(task.indeterminate)"
              :aria-checked="task.indeterminate ? 'mixed' : Boolean(statuses[task.id])"
              :aria-label="`启用${task.title}`"
              @change="emit('toggle', task.id, $event.target.checked)"
            />
            <button
              class="checklist-task-select"
              type="button"
              :title="task.title"
              :aria-label="task.id === connectionId ? `配置${task.title}` : `${task.title}设置`"
              :aria-pressed="directorySelectedId === task.id"
              @click="selectEntry(task.id)"
            >
              {{ task.title }}
            </button>
          </div>
        </section>
        <p
          v-if="query.trim() && !visibleGroups.length && !visibleFavorites.length"
          class="checklist-empty"
        >
          没有找到匹配的功能
        </p>
      </div>
    </div>
    <n-modal
      v-if="editingFavorites"
      :show="editingFavorites"
      preset="card"
      title="编辑常用设置"
      aria-label="编辑常用设置"
      class="checklist-favorites-dialog"
      :closable="!favoritesBusy"
      :mask-closable="!favoritesBusy"
      :close-on-esc="!favoritesBusy"
      @update:show="(show) => !show && closeFavorites()"
    >
      <n-input
        v-model:value="favoriteQuery"
        placeholder="查找设置"
        :input-props="{ 'aria-label': '查找可收藏的设置' }"
        clearable
      />
      <p v-if="favoriteError" class="checklist-favorites-error" role="alert">{{ favoriteError }}</p>
      <div class="checklist-favorites-options">
        <label v-for="editor in favoriteOptions" :key="editor.id">
          <input
            v-model="favoriteDraft"
            type="checkbox"
            :value="editor.id"
            :disabled="favoritesBusy"
          />
          <span>{{ editor.title }}</span>
        </label>
        <p v-if="!favoriteOptions.length" class="checklist-favorites-empty">没有找到匹配的设置</p>
      </div>
      <template #footer>
        <n-flex justify="end">
          <n-button :disabled="favoritesBusy" @click="closeFavorites">取消</n-button>
          <n-button type="primary" :loading="favoritesBusy" @click="confirmFavorites"
            >保存</n-button
          >
        </n-flex>
      </template>
    </n-modal>
  </nav>
</template>

<style scoped>
.task-checklist {
  position: sticky;
  top: 16px;
  height: calc(var(--settings-viewport-height, 100dvh / var(--mower-zoom, 1)) - 40px);
  max-height: calc(var(--settings-viewport-height, 100dvh / var(--mower-zoom, 1)) - 40px);
  border: 1px solid var(--mower-border);
  border-radius: 12px;
  display: flex;
  flex-direction: column;
  width: 100%;
  min-width: 0;
  box-sizing: border-box;
  min-height: 0;
  background: var(--mower-surface);
  color: var(--mower-text);
  overflow: hidden;
}
.checklist-content {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-height: 0;
}
.checklist-desktop-heading {
  display: flex;
  flex: none;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  min-height: 52px;
  padding: 4px 8px 4px 16px;
  box-sizing: border-box;
  border-bottom: 1px solid var(--mower-border);
}
.checklist-desktop-title {
  min-width: 0;
  font-size: 13px;
  font-weight: 600;
}
.checklist-desktop-toggle {
  display: inline-flex;
  flex: none;
  align-items: center;
  justify-content: center;
  width: 44px;
  height: 44px;
  padding: 0;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: var(--mower-text-muted);
  cursor: pointer;
}
.checklist-desktop-toggle:hover {
  background: var(--mower-control-surface);
  color: var(--mower-primary);
}
.task-checklist.is-collapsed .checklist-desktop-heading {
  justify-content: center;
  padding-inline: 3px;
  border-bottom: 0;
}
.task-checklist.is-collapsed .checklist-content,
.task-checklist.is-collapsed .checklist-desktop-title {
  display: none;
}
.checklist-mobile-toggle {
  display: none;
  flex: none;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  width: 100%;
  min-height: 52px;
  padding: 14px 18px;
  border: 0;
  background: transparent;
  color: var(--mower-text);
  font: inherit;
  font-weight: 600;
  text-align: left;
  cursor: pointer;
}
.checklist-mobile-toggle svg {
  flex: none;
  color: var(--mower-text-muted);
  transition: transform 0.15s ease;
}
.is-open .checklist-mobile-toggle svg {
  transform: rotate(180deg);
}
.checklist-search {
  padding: 12px 16px;
}
.checklist-group-heading,
.checklist-task {
  display: flex;
  align-items: center;
  min-width: 0;
  border-radius: 5px;
}
.checklist-task-select {
  border: 0;
  background: transparent;
  color: inherit;
  font: inherit;
  cursor: pointer;
}
.checklist-scroll {
  flex: 1;
  min-height: 0;
  box-sizing: border-box;
  overflow-y: auto;
  padding: 0 10px 8px;
  scrollbar-width: thin;
}
.checklist-group {
  padding-top: 8px;
}
.checklist-group + .checklist-group {
  margin-top: 7px;
}
.checklist-favorites-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.checklist-favorites-edit {
  padding: 4px 10px;
  border: 0;
  background: transparent;
  color: var(--mower-primary);
  cursor: pointer;
  font: inherit;
  font-size: 12px;
}
.checklist-favorites-edit:disabled {
  cursor: wait;
  opacity: 0.6;
}
.checklist-favorites-dialog {
  width: min(480px, calc(100vw - 32px));
}
.checklist-favorites-options {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(175px, 100%), 1fr));
  gap: 4px 8px;
  max-height: min(48dvh, 420px);
  overflow: auto;
  margin-top: 12px;
}
.checklist-favorites-options label {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 34px;
  padding: 0 6px;
  cursor: pointer;
}
.checklist-favorites-options input {
  accent-color: var(--mower-primary);
}
.checklist-favorites-empty,
.checklist-favorites-error {
  margin: 6px 10px;
  font-size: 12px;
}
.checklist-favorites-empty {
  color: var(--mower-text-muted);
}
.checklist-favorites-error {
  color: var(--mower-error, #d03050);
}
.checklist-group-heading {
  min-height: 28px;
  margin: 0 0 3px;
  padding: 0 10px;
  color: var(--mower-text-muted);
  font-size: 12px;
  font-weight: 600;
  line-height: 1.5;
}
.checklist-task {
  min-height: 40px;
  padding: 0 6px;
  color: var(--mower-text-muted);
}
.checklist-task--support {
  padding-left: 14px;
}
.checklist-task.enabled {
  color: var(--mower-text);
}
.checklist-checkbox {
  flex: none;
  width: 17px;
  height: 17px;
  margin: 0 10px 0 4px;
  accent-color: var(--mower-primary);
  cursor: pointer;
}
.checklist-control-spacer {
  flex: none;
  width: 27px;
  margin-right: 4px;
}
.checklist-task-select {
  flex: 1;
  min-width: 0;
  padding: 8px 0;
  font-size: 14px;
  line-height: 20px;
  text-align: left;
  text-overflow: ellipsis;
  overflow: hidden;
  white-space: nowrap;
}
.selected {
  background: var(--mower-control-surface);
  color: var(--mower-text);
}
.checklist-task.selected .checklist-task-select,
.checklist-task-select:hover {
  color: var(--mower-primary);
}
.checklist-empty {
  margin: 0;
  padding: 24px 4px;
  color: var(--mower-text-muted);
  font-size: 13px;
  text-align: center;
}
button:focus-visible,
input:focus-visible {
  outline: 2px solid var(--mower-primary);
  outline-offset: 2px;
}
@container main-content (max-width: 760px) {
  .checklist-desktop-heading {
    display: none;
  }
  .task-checklist.is-collapsed .checklist-content {
    display: flex;
  }
  .task-checklist {
    position: sticky;
    top: 0;
    z-index: 5;
    align-self: start;
    height: auto;
    max-height: min(440px, calc(100dvh / var(--mower-zoom, 1) - 112px));
    box-shadow: 0 3px 8px rgb(0 0 0 / 4%);
  }
  .checklist-content {
    overflow-y: auto;
    overscroll-behavior: contain;
  }
  .checklist-scroll {
    min-height: 88px;
    overscroll-behavior: contain;
  }
  .checklist-search {
    flex: none;
    padding-top: 8px;
  }
  .checklist-task-select,
  .checklist-favorites-edit,
  .checklist-favorites-options label {
    min-height: 44px;
  }
  .checklist-mobile-toggle {
    display: flex;
  }
  .task-checklist:not(.is-open) .checklist-content {
    display: none;
  }
}
</style>
