<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { useThemeVars } from 'naive-ui'
import draggable from 'vuedraggable'
import Draggable from '@vicons/carbon/es/Draggable'
import { useGuiStore } from '@/stores/gui'
import { normalizeSortablePreview } from '@/utils/sortablePreview'
import {
  DEFAULT_RUNNING_LOG_LAYOUT,
  LOG_LAYOUT_MODULES,
  parseRunningLogLayout,
  serializeRunningLogLayout
} from '@/utils/logLayoutConfig'
import '@/styles/drag.css'

const gui = useGuiStore()
const theme = useThemeVars()
const dialogStyle = computed(() => ({
  width: 'min(700px, calc(100vw - 32px))',
  '--mower-text': theme.value.textColor1,
  '--mower-text-muted': theme.value.textColor2,
  '--mower-surface': theme.value.cardColor,
  '--mower-border': theme.value.borderColor,
  '--mower-primary': theme.value.primaryColor,
  '--layout-canvas': theme.value.bodyColor
}))
const cancelTheme = computed(() => ({
  textColorHover: theme.value.textColor1,
  textColorFocus: theme.value.textColor1,
  textColorPressed: theme.value.textColor1
}))
const saveTheme = {
  colorPrimary: '#087b44',
  colorHoverPrimary: '#076d3c',
  colorPressedPrimary: '#065e35',
  colorFocusPrimary: '#076d3c',
  borderPrimary: '1px solid #087b44',
  borderHoverPrimary: '1px solid #076d3c',
  borderPressedPrimary: '1px solid #065e35',
  borderFocusPrimary: '1px solid #076d3c',
  textColorPrimary: '#fff',
  textColorHoverPrimary: '#fff',
  textColorPressedPrimary: '#fff',
  textColorFocusPrimary: '#fff'
}
const {
  loaded,
  loading,
  runningLogLayout,
  runningLogLayoutDialogOpen: open,
  runningLogLayoutDisabled: disabled,
  runningLogLayoutSaving: saving,
  runningLogLayoutError: error
} = storeToRefs(gui)

const draft = ref(parseRunningLogLayout(DEFAULT_RUNNING_LOG_LAYOUT))
const board = ref(null)
const dragging = ref(false)
const attemptedSave = ref(false)
const moveStatus = ref('')
let layoutBeforeDrag
const splitColumns = [
  { key: 'left', title: '左栏' },
  { key: 'right', title: '右栏' }
]
const columns = computed(() =>
  draft.value.mode === 'split' ? splitColumns : [{ key: 'single', title: '上下排列' }]
)
const serialized = computed(() => serializeRunningLogLayout(draft.value))
const savedLayout = computed(() =>
  serializeRunningLogLayout(parseRunningLogLayout(runningLogLayout.value))
)
const hasChanges = computed(() => serialized.value !== savedLayout.value)
const screenshotSide = computed(() => (draft.value.left.includes('screenshot') ? 'left' : 'right'))
const moduleKey = (id) => id

watch([open, loaded], ([show, ready]) => {
  if (!show) return
  if (ready) {
    draft.value = parseRunningLogLayout(runningLogLayout.value)
    attemptedSave.value = false
    dragging.value = false
    moveStatus.value = ''
  } else {
    void gui.load()
  }
})

function splitAt(side, id, order) {
  const otherItems = order.filter((item) => item !== id)
  draft.value = {
    mode: 'split',
    left: side === 'left' ? [id] : otherItems,
    right: side === 'right' ? [id] : otherItems,
    single: []
  }
}

function startDrag(event) {
  dragging.value = true
  layoutBeforeDrag = {
    mode: draft.value.mode,
    left: [...draft.value.left],
    right: [...draft.value.right],
    single: [...draft.value.single]
  }
  normalizeSortablePreview(event)
}

function mergeEmptyColumn() {
  const { mode, left, right } = draft.value
  if (mode === 'split' && (!left.length || !right.length)) {
    draft.value = { mode: 'single', single: [...left, ...right], left: [], right: [] }
  }
}

function endDrag({ originalEvent, item }) {
  if (originalEvent?.type.endsWith('cancel')) {
    draft.value = layoutBeforeDrag
  } else if (draft.value.mode === 'single' && originalEvent) {
    const pointer = originalEvent.changedTouches?.[0] ?? originalEvent
    const edges = board.value?.querySelectorAll('[data-layout-edge]') ?? []
    for (const edge of edges) {
      const { left, right, top, bottom } = edge.getBoundingClientRect()
      if (
        pointer.clientX >= left &&
        pointer.clientX <= right &&
        pointer.clientY >= top &&
        pointer.clientY <= bottom
      ) {
        splitAt(edge.dataset.layoutEdge, item.dataset.moduleId, layoutBeforeDrag.single)
        // Sortable can swallow the next click if the fallback never entered another item.
        // Let its click guard consume an event on the original card, which has no click action.
        item.click()
        break
      }
    }
  } else {
    mergeEmptyColumn()
  }
  layoutBeforeDrag = undefined
  dragging.value = false
}

async function moveWithKeyboard(event, column, index) {
  if (saving.value || dragging.value || event.altKey || event.ctrlKey || event.metaKey) return
  const { key } = event
  const source = draft.value[column]
  const id = source[index]
  if (key === 'ArrowUp' || key === 'ArrowDown') {
    event.preventDefault()
    const position = index + (key === 'ArrowUp' ? -1 : 1)
    if (position < 0 || position >= source.length) return
    source.splice(index, 1)
    source.splice(position, 0, id)
  } else if (key === 'ArrowLeft' || key === 'ArrowRight') {
    event.preventDefault()
    const side = key === 'ArrowLeft' ? 'left' : 'right'
    if (column === side) return
    if (column === 'single') {
      splitAt(side, id, source)
    } else {
      const target = draft.value[side]
      source.splice(index, 1)
      target.splice(Math.min(index, target.length), 0, id)
      mergeEmptyColumn()
    }
  } else {
    return
  }
  await nextTick()
  const card = board.value?.querySelector(`[data-module-id="${id}"]`)
  card?.focus()
  moveStatus.value = card?.getAttribute('aria-label') ?? ''
}

async function save() {
  if (disabled.value || dragging.value || !hasChanges.value) return
  attemptedSave.value = true
  if (await gui.setRunningLogLayout(serialized.value)) gui.closeRunningLogLayoutDialog()
}
</script>

<template>
  <n-modal
    v-model:show="open"
    preset="card"
    title="运行日志布局"
    class="running-log-layout-dialog"
    :style="dialogStyle"
    aria-label="运行日志布局"
    :closable="!saving"
    :close-on-esc="!saving"
    :mask-closable="false"
  >
    <div v-if="loaded" class="layout-editor">
      <div
        ref="board"
        class="layout-board"
        :data-mode="draft.mode"
        :data-screenshot-side="screenshotSide"
        role="group"
        aria-label="运行日志布局预览"
      >
        <section
          v-for="column in columns"
          :key="column.key"
          :aria-label="column.title"
          class="layout-column"
        >
          <draggable
            v-model="draft[column.key]"
            :item-key="moduleKey"
            group="running-log-layout"
            class="layout-column__list"
            :data-column="column.key"
            :disabled="saving"
            :delay="160"
            :delay-on-touch-only="true"
            :touch-start-threshold="5"
            :animation="150"
            :force-fallback="true"
            :fallback-on-body="true"
            :fallback-tolerance="3"
            ghost-class="mower-drag-ghost"
            chosen-class="mower-drag-chosen"
            fallback-class="mower-drag-fallback"
            @start="startDrag"
            @end="endDrag"
          >
            <template #item="{ element: id, index }">
              <div
                class="layout-module"
                :data-module-id="id"
                :tabindex="saving ? -1 : 0"
                role="group"
                :aria-label="`${LOG_LAYOUT_MODULES[id]}，${column.title}第 ${index + 1} 项`"
                aria-describedby="running-log-layout-hint"
                @keydown="moveWithKeyboard($event, column.key, index)"
              >
                <div class="layout-module__title">
                  <n-icon :component="Draggable" size="16" aria-hidden="true" />
                  {{ LOG_LAYOUT_MODULES[id] }}
                </div>
                <div v-if="id === 'screenshot'" class="layout-module__scene" aria-hidden="true">
                  <span></span>
                  <div v-for="room in 6" :key="room"></div>
                </div>
                <div v-else-if="id === 'daily'" class="layout-module__pills" aria-hidden="true">
                  <span v-for="pill in 3" :key="pill"></span>
                </div>
                <div v-else class="layout-module__lines" aria-hidden="true">
                  <div v-for="line in id === 'log' ? 6 : 3" :key="line">
                    <span></span><span></span>
                  </div>
                </div>
              </div>
            </template>
          </draggable>
        </section>
        <template v-if="dragging && draft.mode === 'single'">
          <div class="layout-edge" data-layout-edge="left" aria-hidden="true">放到左侧</div>
          <div class="layout-edge" data-layout-edge="right" aria-hidden="true">放到右侧</div>
        </template>
      </div>
      <p id="running-log-layout-hint" class="layout-editor__hint">
        拖动卡片或用方向键移动<span v-if="draft.mode === 'single'">。拖到画布边缘可并排</span>。
      </p>
      <span class="layout-editor__announcement" role="status">{{ moveStatus }}</span>
      <n-alert v-if="attemptedSave && error" role="alert" type="error">
        {{ error }}
      </n-alert>
    </div>
    <div v-else-if="loading" class="layout-editor__loading" role="status">
      <n-spin size="small" />
      正在读取布局…
    </div>
    <n-alert v-else-if="error" role="alert" type="error">
      {{ error }}
      <template #action>
        <n-button size="small" @click="gui.load">重试</n-button>
      </template>
    </n-alert>

    <template #footer>
      <div class="layout-editor__footer">
        <n-button
          :disabled="saving"
          :theme-overrides="cancelTheme"
          @click="gui.closeRunningLogLayoutDialog"
        >
          取消
        </n-button>
        <n-button
          type="primary"
          :theme-overrides="saveTheme"
          :loading="saving"
          :disabled="disabled || dragging || !hasChanges"
          @click="save"
        >
          保存布局
        </n-button>
      </div>
    </template>
  </n-modal>
</template>

<style scoped>
.layout-editor {
  display: grid;
  gap: 10px;
}

.layout-editor__footer,
.layout-editor__loading {
  display: flex;
  align-items: center;
  gap: 8px;
}

.layout-editor__footer {
  justify-content: flex-end;
}

.layout-editor__hint {
  margin: 0;
  color: var(--mower-text-muted);
  font-size: 12px;
}

.layout-editor__announcement {
  position: absolute;
  width: 1px;
  height: 1px;
  clip-path: inset(50%);
  overflow: hidden;
}

.layout-board {
  position: relative;
  display: grid;
  gap: 10px;
  min-width: 0;
  padding: 12px;
  border: 1px solid var(--mower-border);
  border-radius: 12px;
  background: color-mix(in srgb, var(--mower-primary) 4%, var(--layout-canvas));
}

.layout-board[data-mode='split'] {
  grid-template-columns: minmax(0, 1.7fr) minmax(0, 1fr);
}

.layout-board[data-mode='split'][data-screenshot-side='left'] {
  grid-template-columns: minmax(0, 1fr) minmax(0, 1.7fr);
}

.layout-column {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.layout-column__list {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 8px;
}

.layout-board[data-mode='split'] .layout-column__list {
  min-height: 274px;
}

.layout-module {
  --module-accent: var(--mower-text-muted);
  --module-mark: color-mix(in srgb, var(--module-accent) 18%, transparent);
  --module-tint: color-mix(in srgb, var(--module-accent) 5%, var(--mower-surface));
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
  padding: 6px 10px 10px;
  border: 1px solid var(--mower-border);
  border-radius: 8px;
  background: var(--module-tint);
  color: var(--mower-text);
  cursor: grab;
  user-select: none;
}

.layout-module[data-module-id='log'],
.layout-module[data-module-id='tasks'] {
  flex: 1 0 auto;
}

.layout-module[data-module-id='daily'] {
  --module-accent: var(--mower-primary);
}

.layout-module[data-module-id='screenshot'] {
  --module-accent: #6591c7;
}

.layout-module[data-module-id='tasks'] {
  --module-accent: #a6794e;
}

.layout-module__title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 600;
  padding-block: 4px;
}

.layout-module__title :deep(.n-icon) {
  flex: none;
  color: var(--mower-text-muted);
}

.layout-module:focus-visible {
  outline: 2px solid var(--mower-primary);
  outline-offset: -2px;
}

@media (hover: hover) {
  .layout-module:hover {
    border-color: color-mix(in srgb, var(--module-accent) 55%, var(--mower-border));
  }
}
.layout-module__pills,
.layout-module__lines,
.layout-module__scene {
  pointer-events: none;
}

.layout-module__pills {
  display: flex;
  gap: 5px;
}

.layout-module__pills span {
  width: 24%;
  max-width: 49px;
  height: 10px;
  border: 1px solid color-mix(in srgb, var(--module-accent) 28%, transparent);
  border-radius: 20px;
  background: var(--module-mark);
}

.layout-module__lines {
  display: grid;
  gap: 7px;
  padding-block: 3px;
}

.layout-module__lines div {
  display: grid;
  align-items: center;
  gap: 8px;
  grid-template-columns: minmax(12px, 16%) minmax(0, 1fr);
}

.layout-module__lines span {
  height: 4px;
  border-radius: 5px;
  background: var(--module-mark);
}

.layout-module__lines div:nth-child(3n + 2) span:last-child {
  width: 74%;
}

.layout-module__lines div:nth-child(3n) span:last-child {
  width: 88%;
}

[data-module-id='tasks'] .layout-module__lines div {
  padding-block-end: 6px;
  border-block-end: 1px solid var(--mower-border);
}

[data-module-id='tasks'] .layout-module__lines div:last-child {
  border: 0;
  padding-block-end: 0;
}

.layout-module__scene {
  display: grid;
  grid-template: auto repeat(2, 1fr) / repeat(3, minmax(0, 1fr));
  gap: 5px;
  width: min(100%, 205px);
  aspect-ratio: 16 / 9;
  box-sizing: border-box;
  padding: 8px;
  border-radius: 5px;
  background: linear-gradient(145deg, #1b2d3e, #14232c);
}

.layout-module__scene > span {
  grid-column: 1 / -1;
  width: 34%;
  height: 3px;
  border-radius: 5px;
  background: #8ba5bc;
}

.layout-module__scene > div {
  display: flex;
  align-items: end;
  min-height: 0;
  padding: 4px;
  border: 1px solid #536e80;
  border-radius: 3px;
  background: #263e4d;
}

.layout-module__scene > div::after {
  content: '';
  width: 70%;
  height: 2px;
  border-radius: 3px;
  background: #71aa9d;
}

.layout-edge {
  position: absolute;
  z-index: 1;
  inset-block: 7px;
  inset-inline-start: 13px;
  display: grid;
  place-items: center;
  width: clamp(28px, 9%, 46px);
  padding: 4px;
  border: 1px dashed var(--mower-primary);
  border-radius: 7px;
  background: color-mix(in srgb, var(--mower-primary) 17%, var(--mower-surface));
  color: var(--mower-text);
  font-size: 11px;
  text-align: center;
  pointer-events: none;
}

.layout-edge[data-layout-edge='right'] {
  inset-inline: auto 13px;
}

@media (max-width: 480px) {
  :global(.running-log-layout-dialog.n-card) {
    --n-padding-left: 16px !important;
    --n-padding-right: 16px !important;
  }

  .layout-board {
    padding: 7px;
    gap: 6px;
  }

  .layout-board[data-mode='split'] {
    grid-template-columns: minmax(0, 1.25fr) minmax(0, 1fr);
  }

  .layout-board[data-mode='split'][data-screenshot-side='left'] {
    grid-template-columns: minmax(0, 1fr) minmax(0, 1.25fr);
  }

  .layout-module {
    padding-inline: 6px;
  }
}
</style>
