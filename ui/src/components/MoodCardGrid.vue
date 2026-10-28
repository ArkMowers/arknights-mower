<script setup>
import { i18n } from '@/i18n'
const { t } = i18n.global
import { onBeforeUnmount, ref } from 'vue'
import { createDragPreview } from '@/utils/dragPreview'

defineProps({
  groups: { type: Array, required: true }
})
const emit = defineEmits(['reorder'])
const root = ref(null)
const dragged = ref('')
const hovered = ref('')
let touchId = null
const dragPreview = createDragPreview()

const keyOf = (group) => group.boardKey || group.groupName

function drop(source, target) {
  if (source && target && source !== target) emit('reorder', source, target)
  dragged.value = ''
  hovered.value = ''
  dragPreview.clear()
}

function dragStart(group, event) {
  dragPreview.start(event)
  dragged.value = keyOf(group)
  event.dataTransfer.effectAllowed = 'move'
  event.dataTransfer.setData('text/plain', dragged.value)
}

function dragOver(group, event) {
  if (!dragged.value || dragged.value === keyOf(group)) return
  event.preventDefault()
  event.dataTransfer.dropEffect = 'move'
  hovered.value = keyOf(group)
}

function onDrop(group, event) {
  event.preventDefault()
  drop(dragged.value || event.dataTransfer.getData('text/plain'), keyOf(group))
}

function dragLeave(group, event) {
  if (event.currentTarget.contains(event.relatedTarget)) return
  if (hovered.value === keyOf(group)) hovered.value = ''
}

function removePointerListeners() {
  window.removeEventListener('pointermove', pointerMove)
  window.removeEventListener('pointerup', pointerEnd)
  window.removeEventListener('pointercancel', pointerCancel)
}

function pointerStart(group, event) {
  if (event.pointerType === 'mouse') return // Desktop uses the native drag and drop.
  if (!event.isPrimary) return
  event.preventDefault()
  touchId = event.pointerId
  dragged.value = keyOf(group)
  hovered.value = ''
  window.addEventListener('pointermove', pointerMove, { passive: false })
  window.addEventListener('pointerup', pointerEnd)
  window.addEventListener('pointercancel', pointerCancel)
}

function targetAt(event) {
  const node = document
    .elementFromPoint(event.clientX, event.clientY)
    ?.closest('[data-mood-card-key]')
  return root.value?.contains(node) ? node?.dataset.moodCardKey : ''
}

function pointerMove(event) {
  if (event.pointerId !== touchId) return
  event.preventDefault()
  hovered.value = targetAt(event)
}

function pointerEnd(event) {
  if (event.pointerId !== touchId) return
  const destination = targetAt(event) || hovered.value
  drop(dragged.value, destination)
  touchId = null
  removePointerListeners()
}

function pointerCancel() {
  dragged.value = ''
  hovered.value = ''
  touchId = null
  dragPreview.clear()
  removePointerListeners()
}

function keyboardMove(group, index, event) {
  const forward = event.key === 'ArrowRight' || event.key === 'ArrowDown'
  const backward = event.key === 'ArrowLeft' || event.key === 'ArrowUp'
  if (!forward && !backward) return
  const items = root.value?.querySelectorAll('[data-mood-card-key]')
  const neighbor = items?.[index + (forward ? 1 : -1)]
  if (!neighbor) return
  event.preventDefault()
  emit('reorder', keyOf(group), neighbor.dataset.moodCardKey)
}

onBeforeUnmount(pointerCancel)
</script>

<template>
  <div ref="root">
    <transition-group name="mood-move" tag="div" class="mood-card-grid">
      <section
        v-for="(group, index) in groups"
        :key="keyOf(group)"
        :data-mood-card-key="keyOf(group)"
        class="mood-grid-card"
        :class="{
          'mood-card-dragging': dragged === keyOf(group),
          'mood-card-target': hovered === keyOf(group)
        }"
        draggable="true"
        @dragstart="dragStart(group, $event)"
        @dragover.prevent="dragOver(group, $event)"
        @dragenter.prevent="dragOver(group, $event)"
        @dragleave="dragLeave(group, $event)"
        @drop.prevent="onDrop(group, $event)"
        @dragend="pointerCancel"
      >
        <button
          class="mood-drag-handle"
          type="button"
          :aria-label="t('reports.reorderGroup', { name: group.groupName })"
          :title="t('reports.dragCardsHelp')"
          @pointerdown="pointerStart(group, $event)"
          @keydown="keyboardMove(group, index, $event)"
        >
          <span aria-hidden="true">⠿</span>
        </button>
        <slot :group="group" />
      </section>
    </transition-group>
  </div>
</template>

<style scoped>
.mood-card-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  align-items: stretch;
}
@media (max-width: 850px) {
  .mood-card-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
@media (max-width: 540px) {
  .mood-card-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}
.mood-grid-card {
  position: relative;
  min-width: 0;
  height: 365px;
  border: 1px solid var(--n-border-color);
  border-radius: 10px;
  padding: 10px 12px 12px;
  background: var(--n-color, #fff);
  display: flex;
  flex-direction: column;
  box-sizing: border-box;
  overflow: hidden;
  user-select: none;
  transition:
    border-color 0.16s,
    box-shadow 0.16s,
    opacity 0.16s;
}
.mood-card-dragging {
  opacity: 0.32;
}
.mood-card-target {
  border-color: var(--mower-primary, #18a058);
  outline: 2px solid var(--mower-primary, #18a058);
  outline-offset: 2px;
  box-shadow: 0 0 0 5px color-mix(in srgb, var(--mower-primary, #18a058) 12%, transparent);
}
.mood-grid-card:active {
  cursor: grabbing;
}
.mood-grid-card :deep(img),
.mood-grid-card :deep(a) {
  -webkit-user-drag: none;
}
.mood-move-move {
  transition: transform 0.23s cubic-bezier(0.2, 0.8, 0.2, 1);
}
.mood-drag-handle {
  position: absolute;
  z-index: 2;
  left: 9px;
  top: 8px;
  border: 1px solid var(--n-border-color, #ddd);
  border-radius: 7px;
  background: var(--n-color, white);
  color: var(--n-text-color, #26343b);
  width: 35px;
  height: 32px;
  font-size: 21px;
  cursor: grab;
  touch-action: none;
  user-select: none;
}
.mood-drag-handle:active {
  cursor: grabbing;
}
.mood-drag-handle:focus-visible {
  outline: 2px solid #358f78;
  outline-offset: 2px;
}
@media (prefers-reduced-motion: reduce) {
  .mood-grid-card,
  .mood-move-move {
    transition: none;
  }
}
</style>
