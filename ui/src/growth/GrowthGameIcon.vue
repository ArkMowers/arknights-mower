<script setup>
import { computed } from 'vue'
import { growthGameIcon } from './growthGameIcons'

const props = defineProps({
  kind: { type: String, required: true },
  value: { type: [String, Number], default: null }
})

const icon = computed(() => growthGameIcon(props.kind, props.value))
const iconStyle = computed(() =>
  icon.value.src ? { '--growth-game-icon': `url("${icon.value.src}")` } : undefined
)
</script>

<template>
  <span
    class="growth-game-icon"
    :class="{
      'growth-game-icon--fallback': !icon.src,
      'growth-game-icon--luminance': kind === 'mastery' || kind === 'profession'
    }"
    :style="iconStyle"
    :data-icon-kind="kind"
    :data-icon-value="value"
    aria-hidden="true"
    >{{ !icon.src ? icon.fallback : '' }}</span
  >
</template>

<style scoped>
.growth-game-icon {
  display: inline-block;
  flex: none;
  width: 1em;
  height: 1em;
  vertical-align: middle;
  background: currentColor;
  mask: var(--growth-game-icon) center / contain no-repeat;
}

.growth-game-icon--luminance {
  mask-mode: luminance;
}

.growth-game-icon--fallback {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: auto;
  min-width: 1em;
  background: none;
  mask: none;
  font-size: 0.75em;
  font-weight: 700;
}
</style>
