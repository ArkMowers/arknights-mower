<script setup>
import { computed } from 'vue'
import SklandRewardArt from './SklandRewardArt.vue'
import { groupRewardTotals, number } from './statistics'

const props = defineProps({
  items: { type: Array, default: () => [] },
  upcoming: { type: Array, default: () => [] },
  missed: { type: Array, default: () => [] },
  unparsed: { type: Number, default: 0 },
  current: { type: Boolean, default: false }
})

const sections = computed(() =>
  [
    { key: 'received', title: '已领取', items: props.items, empty: '本月没有奖励记录' },
    props.current && { key: 'upcoming', title: '月底前可领取', items: props.upcoming },
    props.missed.length && {
      key: 'missed',
      title: props.current ? '本月领不到' : '月底未领取',
      items: props.missed
    }
  ]
    .filter(Boolean)
    .filter((section) => section.items.length || section.empty)
    .map((section) => ({ ...section, groups: groupRewardTotals(section.items) }))
)

function tileLabel(item, section) {
  const total = `${item.name} ×${number(item.count)}`
  return section.key === 'received' ? `${total}，签到 ${number(item.days)} 次获得` : total
}
</script>

<template>
  <section aria-label="月度奖励" class="monthly-rewards">
    <section
      v-for="section in sections"
      :key="section.key"
      class="monthly-rewards__section"
      :class="`is-${section.key}`"
      :aria-label="section.title"
    >
      <h3>{{ section.title }}</h3>
      <template v-for="group in section.groups" :key="group.group">
        <h4 v-if="section.groups.length > 1">{{ group.group }}</h4>
        <ul class="reward-grid">
          <li
            v-for="item in group.items"
            :key="item.name"
            class="reward-cell"
            :title="tileLabel(item, section)"
          >
            <SklandRewardArt
              class="reward-cell__art"
              :game="item.game_group"
              :item="item.name"
              :count="item.count"
            />
            <span class="reward-cell__name">{{ item.name }}</span>
          </li>
        </ul>
      </template>
      <p v-if="!section.items.length" class="reward-note">{{ section.empty }}</p>
    </section>
    <p v-if="unparsed" class="reward-note">{{ number(unparsed) }} 次签到缺少奖励明细。</p>
  </section>
</template>

<style scoped>
.monthly-rewards__section + .monthly-rewards__section {
  margin-top: 14px;
  padding-top: 12px;
  border-top: 1px solid var(--mower-divider);
}
.monthly-rewards h3 {
  margin: 0 0 8px;
  font-size: 13px;
  font-weight: 700;
}
.monthly-rewards h4 {
  margin: 8px 0 6px;
  color: var(--mower-text-muted);
  font-size: 12px;
  font-weight: 600;
}
.reward-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(56px, 1fr));
  gap: 8px 6px;
  margin: 0;
  padding: 0;
  list-style: none;
}
.reward-cell {
  display: grid;
  gap: 3px;
  min-width: 0;
}
.reward-cell__name {
  overflow: hidden;
  color: var(--mower-text);
  font-size: 11px;
  line-height: 1.3;
  text-align: center;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.is-upcoming .reward-cell__art {
  outline: 1px dashed color-mix(in srgb, var(--mower-text) 28%, transparent);
  outline-offset: -1px;
}
.is-missed .reward-cell__art {
  opacity: 0.55;
  filter: grayscale(0.6);
}
.is-missed .reward-cell__name {
  color: var(--skland-muted, var(--mower-text-muted));
}
.reward-note {
  margin: 7px 0;
  color: var(--skland-muted, var(--mower-text-muted));
  font-size: 12px;
}
</style>
