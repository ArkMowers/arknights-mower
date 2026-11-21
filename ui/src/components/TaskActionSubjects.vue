<script setup>
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { NPopover } from 'naive-ui'
import LogOperator from './LogOperator.vue'
import { actionSubjectRuns } from '@/utils/taskPresentation'
import '@/styles/logGlassSurface.css'

const props = defineProps({
  actions: { type: Array, default: () => [] },
  facilityPlan: { type: Object, default: () => ({}) },
  size: { type: Number, default: 24 },
  showNames: Boolean,
  inlineSingleOperator: Boolean
})

const runs = computed(() => actionSubjectRuns(props.actions, props.facilityPlan))
const sourceText = computed(() => runs.value.map((run) => run.text).join('；'))
const active = ref(null)
const rosterPanel = ref(null)
let closeTimer = null
let anchor = null

function cancelClose() {
  if (closeTimer !== null) clearTimeout(closeTimer)
  closeTimer = null
}

function close() {
  cancelClose()
  active.value = null
  anchor = null
  globalThis.removeEventListener?.('resize', fitRosterToViewport)
}

function fitRosterToViewport() {
  if (!active.value || !anchor || !Number.isFinite(globalThis.innerHeight)) return
  const surface = rosterPanel.value?.closest?.('.n-popover')
  if (!surface) return
  const bounds = anchor.getBoundingClientRect()
  const panelBounds = surface.getBoundingClientRect()
  const height = surface.offsetHeight || panelBounds.height
  const width = surface.offsetWidth || panelBounds.width
  const margin = 12
  const space = 4
  const fitsAbove = bounds.top >= height + margin + space
  const fitsBelow = bounds.top + height + space <= globalThis.innerHeight - margin
  active.value = {
    ...active.value,
    x: Math.max(margin, Math.min(bounds.left, globalThis.innerWidth - width - margin)),
    y:
      fitsAbove || fitsBelow
        ? bounds.top
        : Math.max(margin, Math.min(bounds.top, globalThis.innerHeight - height - margin - space)),
    placement: fitsAbove ? 'top-start' : 'bottom-start'
  }
}

function show(key, label, members, event, pinned = false) {
  cancelClose()
  if (active.value?.key === key && active.value.pinned && !pinned) return
  const target = event.currentTarget
  const bounds = target.getBoundingClientRect()
  const viewportWidth = globalThis.innerWidth
  const panelWidth = Math.min(410, viewportWidth - 24)
  anchor = target
  active.value = {
    key,
    label,
    members,
    pinned,
    placement: 'top-start',
    x: Number.isFinite(viewportWidth)
      ? Math.max(12, Math.min(bounds.left, viewportWidth - panelWidth - 12))
      : bounds.left,
    y: bounds.top
  }
  globalThis.addEventListener?.('resize', fitRosterToViewport)
  nextTick(fitRosterToViewport)
}

function toggle(key, label, members, event) {
  if (active.value?.key === key && active.value.pinned) close()
  else show(key, label, members, event, true)
}

function scheduleClose() {
  cancelClose()
  if (!active.value?.pinned) closeTimer = setTimeout(close, 120)
}

function outside(event) {
  if (!anchor?.contains?.(event.target)) close()
}

function rosterLabel(label, members) {
  return members.length
    ? `${label}：${members.join('、')}，共${members.length}人`
    : `${label}，暂无成员信息`
}

function rosterIdentity(value, key) {
  const [runIndex, partIndex] = key.split(':').map(Number)
  const run = value[runIndex]
  const part = run?.parts[partIndex]
  if (!part) return null
  return JSON.stringify([
    run.action,
    part.kind,
    part.subject,
    part.kind === 'group' ? part.members : run.operators
  ])
}

watch(runs, (next, previous) => {
  if (
    active.value &&
    rosterIdentity(next, active.value.key) !== rosterIdentity(previous, active.value.key)
  )
    close()
})
onBeforeUnmount(close)
</script>

<template>
  <span
    class="task-action-subjects"
    :data-source-text="sourceText"
    :style="{ '--subject-size': `${size}px` }"
  >
    <template v-for="(run, runIndex) in runs" :key="run.action">
      <template v-if="runIndex">；</template>
      <span class="task-action-subjects__run">
        <template v-for="(part, partIndex) in run.parts" :key="partIndex">
          <template v-if="partIndex && (part.kind === 'group' || part.preview?.length)"
            >、</template
          >
          <button
            v-if="part.kind === 'group'"
            type="button"
            class="task-action-subjects__trigger task-action-subjects__group"
            :data-action-trigger="`${runIndex}:${partIndex}`"
            aria-haspopup="dialog"
            :aria-expanded="active?.key === `${runIndex}:${partIndex}`"
            :aria-label="rosterLabel(part.subject, part.members)"
            @mouseenter="show(`${runIndex}:${partIndex}`, part.subject, part.members, $event)"
            @mouseleave="scheduleClose"
            @focus="show(`${runIndex}:${partIndex}`, part.subject, part.members, $event)"
            @blur="scheduleClose"
            @click="toggle(`${runIndex}:${partIndex}`, part.subject, part.members, $event)"
            @keydown.esc.stop="close"
          >
            {{ part.subject }}
          </button>
          <LogOperator
            v-else-if="inlineSingleOperator && run.operators.length === 1"
            :name="part.preview[0]"
            :size="size"
            show-name
            hide-hint
            class="task-action-subjects__single"
          />
          <button
            v-else-if="part.preview.length || part.overflow"
            type="button"
            class="task-action-subjects__trigger task-action-subjects__people"
            :class="{ 'task-action-subjects__people--named': showNames }"
            :data-action-trigger="`${runIndex}:${partIndex}`"
            aria-haspopup="dialog"
            :aria-expanded="active?.key === `${runIndex}:${partIndex}`"
            :aria-label="rosterLabel(run.action, run.operators)"
            @mouseenter="show(`${runIndex}:${partIndex}`, run.action, run.operators, $event)"
            @mouseleave="scheduleClose"
            @focus="show(`${runIndex}:${partIndex}`, run.action, run.operators, $event)"
            @blur="scheduleClose"
            @click="toggle(`${runIndex}:${partIndex}`, run.action, run.operators, $event)"
            @keydown.esc.stop="close"
          >
            <span
              v-for="(name, previewIndex) in part.preview"
              :key="name"
              class="task-action-subjects__portrait"
              :class="{
                'task-action-subjects__stack':
                  part.overflow && previewIndex === part.preview.length - 1
              }"
              :style="{ '--tail-count': part.tail.length }"
            >
              <LogOperator
                :name="name"
                :size="size"
                :tabindex="-1"
                class="task-action-subjects__front"
                :class="{ 'task-action-subjects__front--named': showNames }"
              />
              <span
                v-if="part.overflow && previewIndex === part.preview.length - 1"
                class="task-action-subjects__tail"
                aria-hidden="true"
              >
                <LogOperator
                  v-for="(tailName, index) in part.tail"
                  :key="tailName"
                  :name="tailName"
                  :size="size"
                  :tabindex="-1"
                  class="task-action-subjects__ghost"
                  :style="{ '--ghost-index': index }"
                />
              </span>
            </span>
            <span v-if="showNames" class="task-action-subjects__name">{{ part.preview[0] }}</span>
            <span v-if="part.overflow" class="task-action-subjects__count" aria-hidden="true"
              >+{{ part.overflow }}</span
            >
          </button> </template
        >{{ run.action }}
      </span>
    </template>
    <NPopover
      v-if="active"
      class="mower-log-glass-surface task-action-roster-surface"
      :show="true"
      trigger="manual"
      :placement="active.placement"
      :space="4"
      :x="active.x"
      :y="active.y"
      :show-arrow="false"
      :theme-overrides="{ color: 'transparent', borderRadius: '12px', boxShadow: 'none' }"
      @clickoutside="outside"
      @mouseenter="cancelClose"
      @mouseleave="scheduleClose"
      @focusin="cancelClose"
      @focusout="scheduleClose"
    >
      <div
        ref="rosterPanel"
        class="task-action-roster"
        role="dialog"
        :aria-label="`${active.label}完整名单`"
        @keydown.esc.stop="close"
      >
        <div class="task-action-roster__title">
          {{ active.label
          }}<span v-if="active.members.length"> · {{ active.members.length }} 人</span>
        </div>
        <div v-if="active.members.length" class="task-action-roster__members">
          <LogOperator
            v-for="name in active.members"
            :key="name"
            :name="name"
            :size="28"
            show-name
          />
        </div>
        <span v-else>暂无成员信息</span>
      </div>
    </NPopover>
  </span>
</template>

<style scoped>
.task-action-subjects {
  display: inline;
}
.task-action-subjects__run {
  display: inline;
}
.task-action-subjects__trigger {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 0;
  border: 0;
  border-radius: 3px;
  background: transparent;
  color: inherit;
  font: inherit;
  line-height: inherit;
  vertical-align: middle;
  cursor: pointer;
  user-select: text;
  transition:
    color 90ms ease-out,
    background-color 90ms ease-out;
}
.task-action-subjects__trigger:focus-visible {
  outline: 2px solid var(--lg-primary, #13834a);
  outline-offset: 3px;
}
.task-action-subjects__group {
  color: var(--log-room-ink, var(--lg-primary, #13834a));
  font-weight: 600;
  vertical-align: baseline;
}
.task-action-subjects__group:hover {
  text-decoration: underline;
  text-underline-offset: 3px;
}
.task-action-subjects__single,
.task-action-subjects__people {
  color: var(--log-operator-ink, inherit);
}
.task-action-subjects__people {
  max-width: 100%;
  flex-wrap: wrap;
}
.task-action-subjects__people--named {
  align-items: baseline;
  vertical-align: baseline;
}
.task-action-subjects__people--named .task-action-subjects__portrait,
.task-action-subjects__people--named .task-action-subjects__count {
  align-self: center;
}
.task-action-subjects__people--named .task-action-subjects__name {
  line-height: var(--subject-size);
}
.task-action-subjects__tail {
  position: absolute;
  inset: 0;
  pointer-events: none;
}
.task-action-subjects__portrait {
  display: inline-flex;
  align-items: center;
  flex: none;
  width: var(--subject-size);
  height: var(--subject-size);
  transition: transform 100ms ease-out;
}
.task-action-subjects__stack {
  position: relative;
  isolation: isolate;
  width: calc(var(--subject-size) + var(--tail-count) * 12px);
}
.task-action-subjects__front {
  display: inline-flex;
  align-items: center;
  height: var(--subject-size);
  border-radius: 50%;
  background-color: var(--mower-surface, #fff);
  position: relative;
  z-index: 3;
}
.task-action-subjects__front--named :deep(.log-operator__name),
.task-action-subjects__ghost :deep(.log-operator__name) {
  display: none;
}
.task-action-subjects__ghost {
  --ghost-opacity: calc(0.78 - var(--ghost-index) * 0.2);
  display: inline-flex;
  align-items: center;
  height: var(--subject-size);
  border-radius: 50%;
  background-color: var(--mower-surface, #fff);
  position: absolute;
  top: 0;
  left: calc((var(--ghost-index) + 1) * 11px);
  z-index: calc(2 - var(--ghost-index));
  transition: left 100ms ease-out;
}
.task-action-subjects__ghost :deep(.log-operator__avatar) {
  opacity: var(--ghost-opacity);
  box-shadow: none;
  transition: opacity 100ms ease-out;
}
.task-action-subjects__people:is(:hover, :focus-visible, [aria-expanded='true'])
  .task-action-subjects__ghost {
  left: calc((var(--ghost-index) + 1) * 12px);
  --ghost-opacity: calc(0.94 - var(--ghost-index) * 0.18);
}
.task-action-subjects__people:is(:hover, :focus-visible, [aria-expanded='true'])
  .task-action-subjects__portrait {
  transform: scale(1.035);
}
.task-action-subjects__name {
  white-space: nowrap;
}
.task-action-subjects__count {
  color: var(--mower-text-muted, #8a9099);
  margin-inline-start: 2px;
  padding: 0 3px;
  font-size: 12px;
  font-variant-numeric: tabular-nums;
  transition: color 90ms ease-out;
}
.task-action-subjects__people:is(:hover, :focus-visible, [aria-expanded='true'])
  .task-action-subjects__count {
  color: var(--mower-text, #333639);
}
:global(
  html:is([data-mower-theme='dark'], [data-window-shell-theme='dark'])
    .n-popover.mower-log-glass-surface.task-action-roster-surface
) {
  --mower-surface: rgb(24 24 28);
  --mower-text: #fff;
  --mower-text-muted: rgb(255 255 255 / 52%);
  background: var(--mower-surface);
  backdrop-filter: none;
}
.task-action-roster {
  display: flex;
  flex-direction: column;
  min-width: 0;
  max-width: min(380px, calc(100vw - 56px));
  max-height: calc(100dvh - 48px);
}
.task-action-roster__title {
  flex: 0 0 auto;
  max-height: 40dvh;
  margin-bottom: 8px;
  overflow: auto;
  overflow-wrap: anywhere;
  font-weight: 600;
}
.task-action-roster__title span {
  color: var(--mower-text-muted, #8a9099);
  font-size: 12px;
  font-weight: 400;
}
.task-action-roster__members {
  display: flex;
  flex: 0 1 auto;
  flex-wrap: wrap;
  gap: 10px 14px;
  min-height: 0;
  max-height: 300px;
  overflow: auto;
}
.task-action-roster__members :deep(.log-operator) {
  max-width: 100%;
  overflow-wrap: anywhere;
  white-space: normal;
}
@media (prefers-reduced-motion: reduce) {
  .task-action-subjects__trigger,
  .task-action-subjects__portrait,
  .task-action-subjects__ghost,
  .task-action-subjects__ghost :deep(.log-operator__avatar),
  .task-action-subjects__count {
    transition: none;
  }
}
</style>
