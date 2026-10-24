<template>
  <header
    v-show="active"
    class="window-titlebar"
    :class="[
      `window-titlebar--controls-${controlSide}`,
      {
        'window-titlebar--dark': theme === 'dark',
        'window-titlebar--maximized': maximized,
        'window-titlebar--native-controls': nativeControls
      }
    ]"
    data-window-shell
    :aria-label="title"
  >
    <div
      v-if="nativeControls"
      class="window-titlebar__native-controls"
      data-window-controls
      aria-hidden="true"
    ></div>
    <div
      class="window-titlebar__brand"
      data-window-drag-region
      aria-hidden="true"
      @mousedown.left="onDragStart"
      @dblclick.stop="onTitlebarDoubleClick"
    >
      <img class="window-titlebar__brand-mark" :src="'/favicon.ico'" alt="" draggable="false" />
    </div>
    <button
      v-if="showSidebarToggle"
      type="button"
      class="window-titlebar__control window-titlebar__sidebar-toggle"
      :aria-label="sidebarCollapsed ? '展开侧边栏' : '收起侧边栏'"
      :title="sidebarCollapsed ? '展开侧边栏' : '收起侧边栏'"
      :aria-expanded="!sidebarCollapsed"
      aria-controls="sidebar-navigation"
      @mousedown.stop
      @dblclick.stop
      @click="$emit('toggle-sidebar')"
    >
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <rect x="3" y="4" width="18" height="16" rx="3.5" />
        <path :d="sidebarCollapsed ? 'M7.5 8v8' : 'M9 4v16'" />
      </svg>
    </button>
    <AppMenuBar
      :active="active"
      :instance-name="instanceName"
      :theme="theme"
      :mower-port="mowerPort"
      :emulator-name="emulatorName"
      :adb-port="adbPort"
      :manager-owned-device="managerOwnedDevice"
      :connection-test-disabled="connectionTestDisabled"
      :profile-state="profileState"
      :profile-write-disabled="profileWriteDisabled"
      :profile-read-disabled="profileReadDisabled"
      :sidebar-visible="sidebarVisible"
      @connection-action="$emit('connection-action', $event)"
      @profile-action="(action, profileId) => $emit('profile-action', action, profileId)"
      @help-action="$emit('help-action', $event)"
      @view-action="$emit('view-action', $event)"
    />
    <div
      class="window-titlebar__drag-region"
      data-window-drag-region
      @mousedown.left="onDragStart"
      @dblclick.stop="onTitlebarDoubleClick"
    >
      <span class="window-titlebar__identity" :title="title">
        <span class="window-titlebar__instance"
          >{{ instanceName }}{{ mowerPort ? `@${mowerPort}` : '' }}</span
        >
        <span v-if="emulatorName" class="window-titlebar__separator" aria-hidden="true">·</span>
        <span v-if="emulatorName" class="window-titlebar__instance"
          >{{ emulatorName }}{{ adbPort ? `@${adbPort}` : '' }}</span
        >
      </span>
    </div>

    <div v-if="!nativeControls" class="window-titlebar__controls" data-window-controls>
      <button
        v-for="control in controls"
        :key="control.id"
        class="window-titlebar__control"
        :class="{ 'window-titlebar__control--close': control.id === 'close' }"
        type="button"
        :aria-label="control.label"
        :title="control.label"
        :data-window-control="control.id"
        :disabled="busy[control.action || control.id] || control.disabled"
        @mousedown.stop
        @click="onControl(control.action || control.id)"
      >
        <svg v-if="control.icon === 'minimize'" aria-hidden="true" viewBox="0 0 16 16">
          <path d="M3 8.5h10" />
        </svg>
        <svg v-else-if="control.icon === 'restore'" aria-hidden="true" viewBox="0 0 16 16">
          <path d="M5.5 5.5h7v7h-7z" />
          <path d="M3.5 10.5h-1v-7h7v1" />
        </svg>
        <svg v-else-if="control.icon === 'maximize'" aria-hidden="true" viewBox="0 0 16 16">
          <rect x="3" y="3" width="10" height="10" rx="0.5" />
        </svg>
        <svg v-else aria-hidden="true" viewBox="0 0 16 16">
          <path d="m4 4 8 8M12 4l-8 8" />
        </svg>
      </button>
    </div>

    <template v-if="resizable">
      <div
        v-for="edge in resizeEdges"
        :key="edge"
        class="window-titlebar__resize-grip"
        :data-window-resize-edge="edge"
        aria-hidden="true"
        @mousedown.left.prevent.stop="onResizeStart(edge)"
      ></div>
    </template>
  </header>
</template>

<script setup>
import { onBeforeUnmount } from 'vue'
import AppMenuBar from './AppMenuBar.vue'
import { WINDOW_RESIZE_EDGES } from '@/window-shell/adapter.js'

const resizeEdges = WINDOW_RESIZE_EDGES
const props = defineProps({
  active: { type: Boolean, required: true },
  title: { type: String, required: true },
  instanceName: { type: String, required: true },
  theme: { type: String, required: true },
  controlSide: { type: String, required: true },
  maximized: { type: Boolean, required: true },
  controls: { type: Array, required: true },
  busy: { type: Object, required: true },
  sidebarCollapsed: { type: Boolean, default: false },
  showSidebarToggle: { type: Boolean, default: false },
  mowerPort: { type: String, default: '' },
  emulatorName: { type: String, default: '' },
  adbPort: { type: String, default: '' },
  managerOwnedDevice: { type: Boolean, default: false },
  connectionTestDisabled: { type: Boolean, default: false },
  profileState: { type: Object, default: null },
  profileWriteDisabled: { type: Boolean, default: true },
  profileReadDisabled: { type: Boolean, default: true },
  sidebarVisible: { type: Boolean, default: true },
  onControl: { type: Function, required: true },
  onToggleMaximize: { type: Function, required: true },
  resizable: { type: Boolean, required: true },
  onResize: { type: Function, required: true },
  onMove: { type: Function, required: true },
  nativeInteractions: { type: Boolean, default: false },
  nativeControls: { type: Boolean, default: false }
})
defineEmits(['toggle-sidebar', 'connection-action', 'profile-action', 'view-action', 'help-action'])

// A press on the title bar is handed to the shell only once the pointer actually
// moves. The shell's move loop then owns the mouse until the button comes up, so
// starting it on the press itself would swallow the second click of a double
// click and take maximise-on-double-click away with it.
const DRAG_THRESHOLD = 4
let dragOriginX = 0
let dragOriginY = 0
let dragArmed = false

function stopWatchingDrag() {
  dragArmed = false
  window.removeEventListener('mousemove', watchDrag)
  window.removeEventListener('mouseup', stopWatchingDrag)
  window.removeEventListener('blur', stopWatchingDrag)
}

function watchDrag(event) {
  if (!dragArmed) return
  if (!(event.buttons & 1)) {
    // The button is already up: the press this move belongs to is over, so drop
    // the arming instead of handing a hover over to the shell as a caption drag.
    stopWatchingDrag()
    return
  }
  const moved =
    Math.abs(event.screenX - dragOriginX) >= DRAG_THRESHOLD ||
    Math.abs(event.screenY - dragOriginY) >= DRAG_THRESHOLD
  if (!moved) return
  stopWatchingDrag()
  props.onMove()
}

function onDragStart(event) {
  if (props.nativeInteractions) return
  dragOriginX = event.screenX
  dragOriginY = event.screenY
  dragArmed = true
  window.addEventListener('mousemove', watchDrag)
  window.addEventListener('mouseup', stopWatchingDrag)
  window.addEventListener('blur', stopWatchingDrag)
}

function onTitlebarDoubleClick() {
  if (!props.nativeInteractions) props.onToggleMaximize()
}

function onResizeStart(edge) {
  if (!props.nativeInteractions) props.onResize(edge)
}

onBeforeUnmount(stopWatchingDrag)
</script>

<style scoped>
.window-titlebar {
  --window-titlebar-text: #302e2c;
  --window-titlebar-muted: #817d78;
  --window-titlebar-control: #242220;
  --window-titlebar-hover: rgba(40, 37, 35, 0.07);
  --window-titlebar-pressed: rgba(40, 37, 35, 0.12);
  --window-titlebar-divider: rgba(40, 37, 35, 0.1);
  --window-titlebar-focus: #18a058;
  display: flex;
  flex: 0 0 36px;
  align-items: flex-start;
  width: 100%;
  height: 36px;
  min-width: 0;
  color: var(--window-titlebar-text);
  font-size: 12px;
  font-weight: 400;
  line-height: 22px;
  background: transparent;
  border: 0;
  box-sizing: border-box;
  user-select: none;
}

.window-titlebar--native-controls {
  /* Native buttons keep their system size when page content is zoomed. */
  zoom: var(--mower-zoom-inverse, 1);
}

.window-titlebar--dark {
  --window-titlebar-text: rgba(255, 255, 255, 0.88);
  --window-titlebar-muted: rgba(255, 255, 255, 0.52);
  --window-titlebar-control: rgba(255, 255, 255, 0.9);
  --window-titlebar-hover: rgba(255, 255, 255, 0.08);
  --window-titlebar-pressed: rgba(255, 255, 255, 0.13);
  --window-titlebar-divider: rgba(255, 255, 255, 0.12);
  --window-titlebar-focus: #63c38a;
}

.window-titlebar__drag-region {
  position: relative;
  display: flex;
  flex: 1 1 auto;
  align-items: flex-start;
  min-width: 0;
  height: 100%;
  padding: 7px 18px 0 11px;
  box-sizing: border-box;
}

.window-titlebar__identity {
  display: flex;
  align-items: center;
  min-width: 0;
  height: 22px;
}

.window-titlebar__separator {
  flex: 0 0 24px;
  color: var(--window-titlebar-muted);
  text-align: center;
}

.window-titlebar__instance {
  min-width: 0;
  overflow: hidden;
  color: var(--window-titlebar-muted);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.window-titlebar__controls {
  display: flex;
  flex: 0 0 auto;
  height: 36px;
}

.window-titlebar__native-controls {
  flex: 0 0 80px;
  height: 100%;
}

.window-titlebar--controls-start .window-titlebar__controls {
  order: -1;
}

.window-titlebar__control {
  position: relative;
  display: inline-grid;
  place-items: center;
  width: 46px;
  height: 100%;
  padding: 0;
  color: var(--window-titlebar-control);
  background: transparent;
  border: 0;
  border-radius: 0;
  appearance: none;
}

.window-titlebar__brand {
  position: relative;
  display: inline-grid;
  place-items: center;
  flex: 0 0 52px;
  width: 52px;
  height: 24px;
  margin-top: 6px;
  padding: 0 16px 0 12px;
  box-sizing: border-box;
}

.window-titlebar__brand::after,
.window-titlebar__drag-region::before {
  content: '';
  position: absolute;
  width: 1px;
  height: 14px;
  background: var(--window-titlebar-divider);
  pointer-events: none;
}

.window-titlebar__brand::after {
  top: 5px;
  right: 4px;
}

.window-titlebar__drag-region::before {
  top: 11px;
  left: 1px;
}

.window-titlebar__brand-mark {
  width: 20px;
  height: 20px;
  object-fit: contain;
  pointer-events: none;
}

.window-titlebar__control:hover:not(:disabled) {
  background: var(--window-titlebar-hover);
}

.window-titlebar__control:active:not(:disabled) {
  background: var(--window-titlebar-pressed);
}

.window-titlebar__control:focus-visible {
  outline: 2px solid var(--window-titlebar-focus);
  outline-offset: -3px;
}

.window-titlebar__control:disabled {
  cursor: default;
  opacity: 0.42;
}

.window-titlebar__control--close:hover:not(:disabled),
.window-titlebar__control--close:focus-visible {
  color: #fff;
  background: #c94b52;
}

.window-titlebar__control--close:active:not(:disabled) {
  color: #fff;
  background: #b33e45;
}

.window-titlebar__control svg {
  width: 13px;
  height: 13px;
  overflow: visible;
  fill: none;
  stroke: currentcolor;
  stroke-linecap: square;
  stroke-linejoin: miter;
  stroke-width: 1.25;
  vector-effect: non-scaling-stroke;
}

.window-titlebar__sidebar-toggle {
  flex: 0 0 28px;
  width: 28px;
  height: 24px;
  margin: 6px 0 0;
  color: var(--window-titlebar-muted);
}

.window-titlebar__sidebar-toggle::before {
  content: '';
  position: absolute;
  z-index: 0;
  top: 50%;
  left: 50%;
  width: 24px;
  height: 24px;
  border-radius: 9px;
  transform: translate(-50%, -50%);
  pointer-events: none;
}

.window-titlebar__sidebar-toggle:hover:not(:disabled),
.window-titlebar__sidebar-toggle:active:not(:disabled) {
  background: transparent;
}

.window-titlebar__sidebar-toggle:hover:not(:disabled)::before {
  background: var(--window-titlebar-hover);
}

.window-titlebar__sidebar-toggle:active:not(:disabled)::before {
  background: var(--window-titlebar-pressed);
}

.window-titlebar__sidebar-toggle:focus-visible {
  outline: none;
}

.window-titlebar__sidebar-toggle:focus-visible::before {
  outline: 2px solid var(--window-titlebar-focus);
  outline-offset: -2px;
}

.window-titlebar__sidebar-toggle svg {
  position: relative;
  z-index: 1;
  width: 14px;
  height: 14px;
  stroke-linecap: round;
  stroke-linejoin: round;
  stroke-width: 1.5;
}

.window-titlebar__resize-grip {
  position: fixed;
  z-index: 10000;
}

.window-titlebar__resize-grip[data-window-resize-edge='top'],
.window-titlebar__resize-grip[data-window-resize-edge='bottom'] {
  right: 10px;
  left: 10px;
  height: 6px;
  cursor: ns-resize;
}

.window-titlebar__resize-grip[data-window-resize-edge='top'] {
  top: 0;
}

.window-titlebar__resize-grip[data-window-resize-edge='bottom'] {
  bottom: 0;
}

.window-titlebar__resize-grip[data-window-resize-edge='left'],
.window-titlebar__resize-grip[data-window-resize-edge='right'] {
  top: 10px;
  bottom: 10px;
  width: 6px;
  cursor: ew-resize;
}

.window-titlebar__resize-grip[data-window-resize-edge='left'] {
  left: 0;
}

.window-titlebar__resize-grip[data-window-resize-edge='right'] {
  right: 0;
}

.window-titlebar__resize-grip[data-window-resize-edge^='top-'],
.window-titlebar__resize-grip[data-window-resize-edge^='bottom-'] {
  width: 10px;
  height: 10px;
}

.window-titlebar__resize-grip[data-window-resize-edge^='top-'] {
  top: 0;
}

.window-titlebar__resize-grip[data-window-resize-edge^='bottom-'] {
  bottom: 0;
}

.window-titlebar__resize-grip[data-window-resize-edge$='-left'] {
  left: 0;
}

.window-titlebar__resize-grip[data-window-resize-edge$='-right'] {
  right: 0;
}

.window-titlebar__resize-grip[data-window-resize-edge='top-left'],
.window-titlebar__resize-grip[data-window-resize-edge='bottom-right'] {
  cursor: nwse-resize;
}

.window-titlebar__resize-grip[data-window-resize-edge='top-right'],
.window-titlebar__resize-grip[data-window-resize-edge='bottom-left'] {
  cursor: nesw-resize;
}
</style>
