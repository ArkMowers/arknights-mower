<script setup>
import { computed, onBeforeUnmount, ref, useId, watch } from 'vue'
import { NPopover } from 'naive-ui'
import { itemIconUrl } from '@/utils/depot_inventory'
import '@/styles/logGlassSurface.css'

const props = defineProps({
  code: { type: String, required: true },
  drops: { type: Array, required: true }
})
const open = ref(false)
const pinned = ref(false)
const failedIcons = ref(new Set())
const panelId = useId()
const label = computed(() => `${props.code}主要掉落物`)
let closeTimer = null
function cancelClose() {
  if (closeTimer !== null) clearTimeout(closeTimer)
  closeTimer = null
}
function show() {
  cancelClose()
  open.value = true
}
function close() {
  cancelClose()
  open.value = false
  pinned.value = false
}
function scheduleClose() {
  cancelClose()
  if (!pinned.value) closeTimer = setTimeout(close, 120)
}
function toggle() {
  if (pinned.value) close()
  else {
    show()
    pinned.value = true
  }
}
function hideIcon(name) {
  failedIcons.value = new Set([...failedIcons.value, name])
}
watch(() => [props.code, props.drops], close)
onBeforeUnmount(cancelClose)
</script>

<template>
  <NPopover
    :show="open"
    trigger="manual"
    placement="top-start"
    :show-arrow="false"
    :space="4"
    class="mower-log-glass-surface"
    :theme-overrides="{ color: 'transparent', borderRadius: '12px', boxShadow: 'none' }"
    @clickoutside="close"
    @mouseenter="cancelClose"
    @mouseleave="scheduleClose"
    @focusin="cancelClose"
    @focusout="scheduleClose"
  >
    <template #trigger
      ><button
        type="button"
        class="log-stage__trigger"
        aria-haspopup="dialog"
        :aria-expanded="open"
        :aria-controls="panelId"
        :aria-label="label"
        @mouseenter="show"
        @mouseleave="scheduleClose"
        @focus="show"
        @blur="scheduleClose"
        @click="toggle"
        @keydown.esc.stop="close"
      >
        {{ code }}
      </button></template
    >
    <div
      :id="panelId"
      class="log-stage__panel"
      role="dialog"
      :aria-label="label"
      @keydown.esc.stop="close"
    >
      <div class="log-stage__title">{{ code }} · 主要掉落物</div>
      <div v-if="drops.length" class="log-stage__drops">
        <span v-for="name in drops" :key="name" class="log-stage__drop"
          ><img
            v-if="!failedIcons.has(name)"
            :src="itemIconUrl(name)"
            width="22"
            height="22"
            alt=""
            aria-hidden="true"
            @error="hideIcon(name)"
          />{{ name }}</span
        >
      </div>
      <span v-else>暂无主要掉落信息</span>
    </div>
  </NPopover>
</template>

<style scoped>
.log-stage__trigger {
  padding: 0;
  border: 0;
  border-radius: 3px;
  background: transparent;
  color: var(--log-room-ink, #13834a);
  font: inherit;
  font-weight: 600;
  cursor: pointer;
  user-select: text;
}
.log-stage__trigger:hover {
  text-decoration: underline;
  text-underline-offset: 3px;
}
.log-stage__trigger:focus-visible {
  outline: 2px solid currentColor;
  outline-offset: 3px;
}
.log-stage__panel {
  box-sizing: border-box;
  max-width: min(320px, calc(100vw - 48px));
  max-height: min(360px, calc(100vh - 48px));
  overflow-y: auto;
  font-size: 13px;
}
.log-stage__title {
  margin-bottom: 9px;
  font-weight: 600;
}
.log-stage__drops {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 14px;
}
.log-stage__drop {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  max-width: 100%;
  overflow-wrap: anywhere;
}
.log-stage__drop img {
  flex: none;
  object-fit: contain;
}
</style>
