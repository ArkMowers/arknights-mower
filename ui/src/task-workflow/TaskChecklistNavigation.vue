<script setup>
import { computed, ref, useId, watch } from 'vue'
import ConnectionIcon from '@vicons/fluent/es/PlugConnected20Regular'
import SearchIcon from '@vicons/fluent/es/Search20Regular'
import CollapseNavigationIcon from '@vicons/fluent/es/PanelLeftContract20Regular'
import ExpandNavigationIcon from '@vicons/fluent/es/PanelLeftExpand20Regular'
import { matchesSettingsSearch, settingsElementKeywords } from '@/utils/settingsSearch'

const props = defineProps({
  tasks: { type: Array, required: true },
  groups: { type: Array, required: true },
  selectedId: { type: String, required: true },
  selectedTitle: { type: String, default: '选择配置' },
  statuses: { type: Object, required: true },
  connectionEnabled: { type: Boolean, default: true },
  connectionId: { type: String, default: 'device' },
  connectionKeywords: { type: String, default: '设备 模拟器 ADB 截图 触控 游戏 启动' },
  selectionRequest: { type: Number, default: 0 },
  waterfall: { type: Boolean, default: false },
  collapsed: { type: Boolean, default: false }
})
const emit = defineEmits(['select', 'toggle', 'set-all', 'update:collapsed'])
const query = ref('')
const directory = ref(null)
const renderedKeywords = ref({})
const directoryId = useId()
const mobileOpen = ref(false)
const mobileToggle = ref(null)
const section = ref('tasks')
const lastTask = ref('base')
const lastSupport = ref('intervals')
const supportIds = computed(() =>
  props.tasks.filter((task) => task.group === 'support').map((task) => task.id)
)
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
const connectionVisible = computed(() => {
  if (!props.connectionEnabled) return false
  return query.value.trim()
    ? matchesSettingsSearch(
        query.value,
        '连接与启动',
        props.connectionKeywords,
        renderedKeywords.value[props.connectionId]
      )
    : section.value === 'tasks'
})
function selectSection(value) {
  section.value = value
  query.value = ''
  emit('select', value === 'support' ? lastSupport.value : lastTask.value)
}
function closeDirectory() {
  if (mobileOpen.value) mobileToggle.value?.focus({ preventScroll: true })
  mobileOpen.value = false
}
function selectEntry(id) {
  closeDirectory()
  emit('select', id)
}
const visibleGroups = computed(() => {
  const words = query.value.trim()
  return props.groups
    .filter((group) => words || (group.id === 'support') === (section.value === 'support'))
    .map((group) => ({
      ...group,
      tasks: props.tasks.filter(
        (task) =>
          task.group === group.id &&
          (!words ||
            matchesSettingsSearch(
              words,
              task.title,
              task.description,
              task.searchKeywords,
              renderedKeywords.value[task.id],
              group.label
            ))
      )
    }))
    .filter((group) => group.tasks.length)
})
watch(
  () => [props.selectedId, props.selectionRequest],
  (_current, previous) => {
    if (previous && props.selectionRequest !== previous[1]) closeDirectory()
    const support = supportIds.value.includes(props.selectedId)
    section.value = support ? 'support' : 'tasks'
    if (support) lastSupport.value = props.selectedId
    else lastTask.value = props.selectedId
    if (
      !(props.selectedId === props.connectionId && connectionVisible.value) &&
      !visibleGroups.value.some((group) => group.tasks.some((task) => task.id === props.selectedId))
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
      'is-collapsed': collapsed,
      'task-checklist--waterfall': waterfall
    }"
    aria-label="全部设置导航"
  >
    <div v-if="waterfall" class="checklist-desktop-heading">
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
          :input-props="{ 'aria-label': '查找托管功能' }"
        >
          <template #prefix><n-icon :component="SearchIcon" :size="16" /></template>
        </n-input>
      </div>

      <div class="checklist-sections" role="group" aria-label="配置分类">
        <button type="button" :aria-pressed="section === 'tasks'" @click="selectSection('tasks')">
          任务
        </button>
        <button
          type="button"
          :aria-pressed="section === 'support'"
          @click="selectSection('support')"
        >
          运行配置
        </button>
      </div>

      <div
        v-if="connectionEnabled"
        v-show="connectionVisible"
        class="connection-row"
        :class="{ selected: selectedId === connectionId }"
      >
        <button
          class="connection-select"
          type="button"
          aria-label="配置连接与启动"
          :aria-pressed="selectedId === connectionId"
          @click="selectEntry(connectionId)"
        >
          <n-icon :component="ConnectionIcon" :size="20" />
          <span>连接与启动</span>
        </button>
      </div>

      <div class="checklist-scroll">
        <section v-for="group in visibleGroups" :key="group.id" class="checklist-group">
          <h3 class="checklist-group-heading">{{ group.label }}</h3>

          <div
            v-for="task in group.tasks"
            :key="task.id"
            class="checklist-task"
            :class="{
              selected: selectedId === task.id,
              enabled: statuses[task.id],
              'checklist-task--support': group.id === 'support'
            }"
            :data-task-id="task.id"
            :data-enabled="Boolean(statuses[task.id])"
          >
            <span
              v-if="task.mode === 'automatic' && group.id !== 'support'"
              class="checklist-control-spacer"
              aria-hidden="true"
            />
            <input
              v-else-if="task.mode !== 'automatic'"
              class="checklist-checkbox"
              type="checkbox"
              :checked="Boolean(statuses[task.id])"
              :aria-label="`启用${task.title}`"
              @change="emit('toggle', task.id, $event.target.checked)"
            />
            <button
              class="checklist-task-select"
              type="button"
              :title="task.title"
              :aria-label="`${task.title}设置`"
              :aria-pressed="selectedId === task.id"
              @click="selectEntry(task.id)"
            >
              {{ task.title }}
            </button>
          </div>
        </section>
        <p
          v-if="query.trim() && !visibleGroups.length && !connectionVisible"
          class="checklist-empty"
        >
          没有找到匹配的功能
        </p>
      </div>

      <footer
        v-show="section === 'tasks' && !query.trim()"
        class="checklist-footer"
        aria-label="批量启用任务"
      >
        <button type="button" @click="emit('set-all', true)">全选</button>
        <button type="button" @click="emit('set-all', false)">清空</button>
      </footer>
    </div>
  </nav>
</template>

<style scoped>
.task-checklist {
  display: flex;
  flex-direction: column;
  width: 100%;
  min-width: 0;
  box-sizing: border-box;
  min-height: 0;
  border-right: 1px solid var(--mower-border);
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
.task-checklist--waterfall {
  position: sticky;
  top: 16px;
  max-height: calc(100dvh / var(--mower-zoom, 1) - 148px);
  border: 1px solid var(--mower-border);
  border-radius: 12px;
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
.task-checklist--waterfall.is-collapsed .checklist-desktop-heading {
  justify-content: center;
  padding-inline: 3px;
  border-bottom: 0;
}
.task-checklist--waterfall.is-collapsed .checklist-content,
.task-checklist--waterfall.is-collapsed .checklist-desktop-title {
  display: none;
}
.task-checklist--waterfall .checklist-search {
  padding-top: 12px;
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
  padding: 20px 16px 12px;
}
.checklist-sections {
  display: flex;
  gap: 4px;
  margin: 0 16px 16px;
  padding: 3px;
  border-radius: 8px;
  background: var(--mower-control-surface);
}
.checklist-sections button {
  flex: 1;
  min-height: 32px;
  padding: 5px 8px;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: var(--mower-text-muted);
  font: inherit;
  font-size: 13px;
  cursor: pointer;
}
.checklist-sections button[aria-pressed='true'] {
  background: var(--mower-surface);
  color: var(--mower-text);
  font-weight: 600;
}
.connection-row,
.checklist-group-heading,
.checklist-task {
  display: flex;
  align-items: center;
  min-width: 0;
  border-radius: 5px;
}
.connection-row {
  margin: 0 10px 10px;
  padding: 3px 6px;
}
.connection-select,
.checklist-task-select,
.checklist-footer button {
  border: 0;
  background: transparent;
  color: inherit;
  font: inherit;
  cursor: pointer;
}
.connection-select {
  display: flex;
  flex: 1;
  align-items: center;
  gap: 10px;
  min-width: 0;
  padding: 8px 4px;
  font-size: 14px;
  text-align: left;
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
.checklist-task-select:hover,
.connection-select:hover {
  color: var(--mower-primary);
}
.checklist-footer {
  flex: none;
  display: flex;
  border-top: 1px solid var(--mower-border);
  padding: 6px 12px;
}
.checklist-footer button {
  flex: 1;
  padding: 7px 0;
  color: var(--mower-text-muted);
  font-size: 13px;
}
.checklist-footer button + button {
  border-left: 1px solid var(--mower-border);
}
.checklist-footer button:hover {
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
@container task-configuration (min-width: 1500px) {
  .task-checklist--waterfall .checklist-group {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    column-gap: 4px;
  }
  .task-checklist--waterfall .checklist-group-heading {
    grid-column: 1 / -1;
  }
}
@container main-content (max-width: 760px) {
  .checklist-desktop-heading {
    display: none;
  }
  .task-checklist--waterfall.is-collapsed .checklist-content {
    display: flex;
  }
  .task-checklist {
    position: sticky;
    top: 0;
    z-index: 5;
    align-self: start;
    max-height: min(440px, calc(100dvh / var(--mower-zoom, 1) - 112px));
    border-right: 0;
    border-bottom: 1px solid var(--mower-border);
    border-radius: 16px 16px 0 0;
    box-shadow: 0 3px 8px rgb(0 0 0 / 4%);
  }
  .task-checklist--waterfall {
    border: 1px solid var(--mower-border);
    border-radius: 12px;
  }
  .checklist-content {
    overflow-y: auto;
    overscroll-behavior: contain;
  }
  .checklist-scroll {
    min-height: 88px;
    overscroll-behavior: contain;
  }
  .checklist-search,
  .task-checklist--waterfall .checklist-search {
    flex: none;
    padding-top: 8px;
  }
  .checklist-sections,
  .connection-row {
    flex: none;
  }
  .checklist-sections {
    margin-bottom: 8px;
  }
  .checklist-sections button,
  .connection-select,
  .checklist-task-select,
  .checklist-footer button {
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
