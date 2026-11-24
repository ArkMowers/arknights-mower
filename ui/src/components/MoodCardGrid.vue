<script setup>
import { onBeforeUnmount, ref, watch } from 'vue'
import { createDragPreview } from '@/utils/dragPreview'
import LoadingSkeleton from '@/components/LoadingSkeleton.vue'
import { createSkeletonShape, skeletonCount, skeletonList } from '@/utils/skeletonShape'

const props = defineProps({
  groups: { type: Array, required: true },
  // 第一次读取还没有卡片时画出骨架屏，loadingLabel 是读屏软件读到的说明。卡片框和拖动把手
  // 由这里画，卡片里的内容由页面的 placeholder 插槽按真实卡片画出。
  loading: { type: Boolean, default: false },
  loadingLabel: { type: String, default: '正在读取' },
  // 给出时骨架按这个页面上次读到的卡片数和每张卡片里干员名的字数占位，上次没有卡片时骨架
  // 保持空白。
  shapeKey: { type: String, default: '' },
  // 读取失败时不改记下的形状，下次读取仍按上次读到的卡片占位。
  loadFailed: { type: Boolean, default: false }
})
const MAX_SKELETON_CARDS = 12
const DEFAULT_OPERATORS = [3, 3, 3]
const MAX_OPERATORS_PER_CARD = 16
const shapeCache = createSkeletonShape(props.shapeKey, {
  cards: skeletonCount(MAX_SKELETON_CARDS, 6),
  operators: skeletonList(
    MAX_SKELETON_CARDS,
    skeletonList(MAX_OPERATORS_PER_CARD, skeletonCount(16, 3), DEFAULT_OPERATORS)
  )
})
const skeletonShape = props.shapeKey ? shapeCache.read() : { cards: 6, operators: [] }
const skeletonCards = Array.from(
  { length: skeletonShape.cards },
  (_, index) => skeletonShape.operators[index] ?? DEFAULT_OPERATORS
)
watch(
  () => !props.loading && props.groups.length,
  (cards) => {
    if (!props.shapeKey || cards === false || props.loadFailed) return
    shapeCache.save({
      cards,
      operators: props.groups
        .slice(0, MAX_SKELETON_CARDS)
        .map((group) =>
          (group.moodData?.datasets ?? [])
            .slice(0, MAX_OPERATORS_PER_CARD)
            .map((dataset) => [...String(dataset.label ?? '')].length)
        )
    })
  }
)
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
    <LoadingSkeleton v-if="loading && !groups.length" class="mood-card-grid" :label="loadingLabel">
      <div
        v-for="(operators, index) in skeletonCards"
        :key="index"
        class="mood-grid-card mood-card-skeleton"
      >
        <button class="mood-drag-handle" type="button" tabindex="-1">
          <span aria-hidden="true">⠿</span>
        </button>
        <slot name="placeholder" :operators="operators" />
      </div>
    </LoadingSkeleton>
    <transition-group v-else name="mood-move" tag="div" class="mood-card-grid">
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
          :aria-label="'拖动或使用方向键调整 ' + group.groupName + ' 的卡片顺序'"
          title="拖动排序，手机可长按拖动，也可用方向键"
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
  border-radius: calc(10px * var(--mower-corner-scale));
  corner-shape: var(--mower-corner-shape);
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
.mood-card-skeleton .mood-drag-handle {
  cursor: default;
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
  border-radius: calc(7px * var(--mower-corner-scale));
  corner-shape: var(--mower-corner-shape);
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
