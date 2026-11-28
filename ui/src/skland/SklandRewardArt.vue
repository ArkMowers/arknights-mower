<script setup>
// 参照游戏内签到页的奖励格：图标居中，数量以深色角标压在右下角。
import SklandRewardIcon from './SklandRewardIcon.vue'
import { number } from './statistics'

defineProps({
  game: { type: String, required: true },
  item: { type: String, required: true },
  count: { type: Number, default: null }
})
</script>

<template>
  <span class="reward-art">
    <SklandRewardIcon class="reward-art__icon" :game="game" :item="item">
      <span class="reward-art__fallback" aria-hidden="true">{{ item.slice(0, 1) }}</span>
    </SklandRewardIcon>
    <span v-if="count != null" class="reward-art__count">{{ number(count) }}</span>
  </span>
</template>

<style scoped>
.reward-art {
  position: relative;
  display: grid;
  place-items: center;
  aspect-ratio: var(--reward-art-ratio, 1);
  overflow: hidden;
  container-type: inline-size;
  border-radius: var(--reward-art-radius, calc(7px * var(--mower-corner-scale)));
  corner-shape: var(--mower-corner-shape);
  background: linear-gradient(
    150deg,
    color-mix(in srgb, var(--mower-text) 5%, var(--mower-surface)),
    color-mix(in srgb, var(--mower-text) 12%, var(--mower-surface))
  );
  box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--mower-text) 8%, transparent);
}
.reward-art__icon {
  width: var(--reward-art-icon, 72%);
  height: var(--reward-art-icon, 72%);
  object-fit: contain;
}
.reward-art__fallback {
  color: color-mix(in srgb, var(--mower-text) 46%, transparent);
  font-size: 38cqi;
  font-weight: 700;
  line-height: 1;
}
.reward-art__count {
  position: absolute;
  inset: auto 4px 4px auto;
  max-width: calc(100% - 8px);
  min-width: 18px;
  overflow: hidden;
  padding: 0 5px;
  border-radius: 9px;
  background: rgb(24 24 28 / 80%);
  color: #fff;
  font-size: var(--reward-art-count, 11px);
  font-variant-numeric: tabular-nums;
  font-weight: 650;
  line-height: 1.55;
  text-align: center;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
