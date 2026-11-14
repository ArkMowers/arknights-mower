<script setup>
import { computed, useId } from 'vue'
import { growthGameIcon, moduleBadge } from './growthGameIcons'

const props = defineProps({
  kind: { type: String, required: true },
  value: { type: [String, Number], default: null },
  moduleId: { type: String, default: '' }
})

const icon = computed(() => growthGameIcon(props.kind, props.value))
const originalImage = computed(() => props.kind === 'mastery' || props.kind === 'elite')
const badge = computed(() =>
  props.kind === 'module' ? moduleBadge(props.value, props.moduleId) : null
)
const textureId = 'growth-module-' + useId()
const iconStyle = computed(() => {
  if (badge.value) return { color: badge.value.color }
  if (icon.value.src && !originalImage.value)
    return { '--growth-game-icon': `url("${icon.value.src}")` }
  return undefined
})
</script>

<template>
  <span
    class="growth-game-icon"
    :class="{
      'growth-game-icon--fallback': !icon.src && !badge,
      'growth-game-icon--luminance': kind === 'profession',
      'growth-game-icon--image': originalImage,
      'growth-game-icon--module': !!badge
    }"
    :style="iconStyle"
    :data-icon-kind="kind"
    :data-icon-value="value"
    aria-hidden="true"
  >
    <template v-if="badge">
      <svg class="growth-game-icon__module-texture" aria-hidden="true" focusable="false">
        <defs>
          <pattern :id="textureId + '-dots'" width="3" height="3" patternUnits="userSpaceOnUse">
            <path fill="currentColor" d="M.5 .5h1v1h-1zM2 2h1v1H2z" />
          </pattern>
          <filter :id="textureId + '-spread'" x="-100%" y="-100%" width="300%" height="300%">
            <feMorphology operator="dilate" radius="1.5" />
            <feGaussianBlur stdDeviation="2.2" />
          </filter>
          <mask :id="textureId + '-shape'" maskUnits="userSpaceOnUse">
            <text
              class="growth-game-icon__module-shape"
              x="50%"
              y="50%"
              text-anchor="middle"
              dominant-baseline="central"
              fill="white"
              :filter="'url(#' + textureId + '-spread)'"
            >
              {{ badge.label }}
            </text>
          </mask>
        </defs>
        <rect
          width="100%"
          height="100%"
          :fill="'url(#' + textureId + '-dots)'"
          :mask="'url(#' + textureId + '-shape)'"
        />
      </svg>
      <span class="growth-game-icon__module-label">{{ badge.label }}</span>
    </template>
    <img v-else-if="originalImage && icon.src" :src="icon.src" alt="" draggable="false" />
    <template v-else-if="!icon.src">{{ icon.fallback }}</template>
  </span>
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

.growth-game-icon--image,
.growth-game-icon--module {
  background: none;
  mask: none;
}

.growth-game-icon--image img {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.growth-game-icon--module {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.growth-game-icon__module-texture {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  overflow: visible;
  opacity: var(--module-pattern-opacity, 0.45);
  pointer-events: none;
}

.growth-game-icon__module-label {
  position: relative;
}

.growth-game-icon__module-label,
.growth-game-icon__module-shape {
  font-family: var(--gp-display);
  font-size: 14px;
  font-weight: 700;
  line-height: 1;
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
