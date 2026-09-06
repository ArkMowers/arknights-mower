<template>
  <header
    v-show="active"
    class="window-titlebar"
    :class="[
      `window-titlebar--controls-${controlSide}`,
      {
        'window-titlebar--dark': theme === 'dark',
        'window-titlebar--maximized': maximized
      }
    ]"
    data-window-shell
  >
    <div
      class="window-titlebar__brand pywebview-drag-region"
      data-window-drag-region
      aria-hidden="true"
      @dblclick.stop="onToggleMaximize"
    >
      <img class="window-titlebar__brand-mark" :src="'/favicon.ico'" alt="" />
    </div>

    <div
      class="window-titlebar__drag-region pywebview-drag-region"
      data-window-drag-region
      @dblclick.stop="onToggleMaximize"
    >
      <span class="window-titlebar__identity" :title="title">
        <span class="window-titlebar__product">Mower</span>
        <span v-if="version" class="window-titlebar__version">{{ version }}</span>
        <span class="window-titlebar__separator" aria-hidden="true">·</span>
        <span class="window-titlebar__instance"
          >{{ instanceName }}{{ mowerPort ? `@${mowerPort}` : '' }}</span
        >
        <span v-if="emulatorName" class="window-titlebar__separator" aria-hidden="true">·</span>
        <span v-if="emulatorName" class="window-titlebar__instance"
          >{{ emulatorName }}{{ adbPort ? `@${adbPort}` : '' }}</span
        >
      </span>
    </div>

    <div class="window-titlebar__controls" data-window-controls>
      <button
        v-for="control in controls"
        :key="control.id"
        class="window-titlebar__control"
        :class="{ 'window-titlebar__control--close': control.id === 'close' }"
        type="button"
        :aria-label="control.label"
        :title="control.label"
        :data-window-control="control.id"
        :disabled="busy[control.action || control.id]"
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
        @mousedown.left.prevent.stop="onResize(edge)"
      ></div>
    </template>
  </header>
</template>

<script setup>
import { WINDOW_RESIZE_EDGES } from '@/window-shell/adapter.js'

const resizeEdges = WINDOW_RESIZE_EDGES

defineProps({
  active: { type: Boolean, required: true },
  title: { type: String, required: true },
  version: { type: String, required: true },
  instanceName: { type: String, required: true },
  theme: { type: String, required: true },
  controlSide: { type: String, required: true },
  maximized: { type: Boolean, required: true },
  controls: { type: Array, required: true },
  busy: { type: Object, required: true },
  mowerPort: { type: String, default: '' },
  emulatorName: { type: String, default: '' },
  adbPort: { type: String, default: '' },
  onControl: { type: Function, required: true },
  onToggleMaximize: { type: Function, required: true },
  resizable: { type: Boolean, required: true },
  onResize: { type: Function, required: true }
})
</script>

<style scoped>
.window-titlebar {
  --window-titlebar-text: #302e2c;
  --window-titlebar-muted: #817d78;
  --window-titlebar-control: #242220;
  --window-titlebar-hover: rgba(40, 37, 35, 0.07);
  --window-titlebar-pressed: rgba(40, 37, 35, 0.12);
  --window-titlebar-focus: #18a058;
  display: flex;
  flex: 0 0 36px;
  align-items: stretch;
  width: 100%;
  height: 36px;
  min-width: 0;
  color: var(--window-titlebar-text);
  background: transparent;
  border: 0;
  box-sizing: border-box;
  user-select: none;
}

.window-titlebar--dark {
  --window-titlebar-text: rgba(255, 255, 255, 0.88);
  --window-titlebar-muted: rgba(255, 255, 255, 0.52);
  --window-titlebar-control: rgba(255, 255, 255, 0.9);
  --window-titlebar-hover: rgba(255, 255, 255, 0.08);
  --window-titlebar-pressed: rgba(255, 255, 255, 0.13);
  --window-titlebar-focus: #63c38a;
}

.window-titlebar__drag-region {
  display: flex;
  flex: 1 1 auto;
  align-items: center;
  min-width: 0;
  height: 100%;
  padding: 0 18px 0 4px;
  box-sizing: border-box;
}

.window-titlebar__identity {
  display: flex;
  align-items: baseline;
  min-width: 0;
  gap: 7px;
  line-height: 1;
}

.window-titlebar__product {
  flex: 0 0 auto;
  font-size: 13px;
  font-weight: 600;
  color: var(--window-titlebar-text);
}

.window-titlebar__version {
  flex: 0 0 auto;
  font-size: 11px;
  font-variant-numeric: tabular-nums;
  color: var(--window-titlebar-muted);
}

.window-titlebar__separator {
  flex: 0 0 auto;
  color: var(--window-titlebar-muted);
}

.window-titlebar__instance {
  min-width: 0;
  overflow: hidden;
  font-size: 12px;
  font-weight: 400;
  color: var(--window-titlebar-muted);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.window-titlebar__controls {
  display: flex;
  flex: 0 0 auto;
  height: 100%;
}

.window-titlebar--controls-start .window-titlebar__controls {
  order: -1;
}

.window-titlebar__brand,
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
  flex: 0 0 44px;
  width: 44px;
  display: inline-grid;
  place-items: center;
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

.window-titlebar__brand-mark {
  width: 20px;
  height: 20px;
  object-fit: contain;
  pointer-events: none;
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
