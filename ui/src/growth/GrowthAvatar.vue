<script setup>
import { operatorDisplayName } from '@/i18n/gameNames'
import { computed, ref, watch } from 'vue'

const props = defineProps({
  name: { type: String, default: '' },
  size: { type: [Number, String], default: 64 },
  rarity: { type: Number, default: 0 },
  round: { type: Boolean, default: false },
  muted: Boolean
})

const failed = ref(false)
watch(
  () => props.name,
  () => {
    failed.value = false
  }
)
const fallback = '/avatar/阿米娅.webp'
const src = computed(() =>
  failed.value || !props.name ? fallback : '/avatar/' + encodeURIComponent(props.name) + '.webp'
)
const px = computed(() => (typeof props.size === 'number' ? props.size + 'px' : props.size))
const rarityClass = computed(() => (props.rarity ? 'growth-avatar--rarity-' + props.rarity : ''))
</script>

<template>
  <span
    class="growth-avatar"
    :class="[rarityClass, { 'growth-avatar--round': round, 'growth-avatar--muted': muted }]"
    :style="{ width: px, height: px }"
  >
    <img
      :src="src"
      :alt="operatorDisplayName(name)"
      loading="lazy"
      decoding="async"
      @error="failed = true"
    />
  </span>
</template>

<style scoped>
.growth-avatar {
  position: relative;
  display: inline-flex;
  flex: none;
  overflow: hidden;
  border-radius: 10px;
  background: var(--gp-surface-3);
  box-shadow: inset 0 0 0 1px var(--gp-hair-soft);
}

.growth-avatar--round {
  border-radius: 999px;
}

.growth-avatar img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  object-position: 50% 22%;
  display: block;
}

.growth-avatar--muted img {
  filter: grayscale(0.85) contrast(1.05);
  opacity: 0.78;
}

.growth-avatar--rarity-6 {
  box-shadow:
    inset 0 0 0 1px rgba(214, 152, 44, 0.5),
    inset 0 -14px 24px -18px rgba(214, 152, 44, 0.5);
}

.growth-avatar--rarity-5 {
  box-shadow: inset 0 0 0 1px rgba(196, 155, 96, 0.42);
}
</style>
