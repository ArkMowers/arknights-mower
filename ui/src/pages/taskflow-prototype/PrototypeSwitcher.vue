<script setup>
// PROTOTYPE：任务编排原型的变体切换条，仅开发构建显示，选定方案后删除。
import { computed, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'

const props = defineProps({
  // [{ key, name }]
  variants: { type: Array, required: true }
})

const route = useRoute()
const router = useRouter()
const dev = import.meta.env.DEV
const index = computed(() =>
  Math.max(
    0,
    props.variants.findIndex((variant) => variant.key === route.query.variant)
  )
)
const current = computed(() => props.variants[index.value])

function go(step) {
  const next = props.variants[(index.value + step + props.variants.length) % props.variants.length]
  router.replace({ query: { ...route.query, variant: next.key } })
}

function onKey(event) {
  if (event.defaultPrevented) return
  const target = event.target
  if (
    target.closest?.('input, textarea, select, [contenteditable], [role="slider"], [role="radio"]')
  )
    return
  if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return
  event.preventDefault()
  go(event.key === 'ArrowLeft' ? -1 : 1)
}

onMounted(() => window.addEventListener('keydown', onKey))
onUnmounted(() => window.removeEventListener('keydown', onKey))
</script>

<template>
  <div v-if="dev" class="proto-switcher" role="toolbar" aria-label="原型变体切换">
    <button type="button" aria-label="上一个变体" @click="go(-1)">‹</button>
    <span>
      <b>{{ current.key }}</b> {{ current.name }}
    </span>
    <button type="button" aria-label="下一个变体" @click="go(1)">›</button>
  </div>
</template>

<style scoped>
.proto-switcher {
  position: fixed;
  z-index: 3000;
  left: 50%;
  bottom: 18px;
  transform: translateX(-50%);
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 6px 8px;
  border-radius: 999px;
  font:
    13px/1 ui-monospace,
    SFMono-Regular,
    Consolas,
    monospace;
  color: #fff;
  background: #111;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.35);
}
.proto-switcher span {
  padding: 0 6px;
  white-space: nowrap;
}
.proto-switcher button {
  width: 28px;
  height: 28px;
  border: 0;
  border-radius: 50%;
  font-size: 18px;
  color: #fff;
  background: #333;
  cursor: pointer;
}
.proto-switcher button:hover,
.proto-switcher button:focus-visible {
  outline: none;
  background: #555;
}
</style>
