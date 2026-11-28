<script setup>
import { computed, ref, useTemplateRef, watch } from 'vue'
import LoadingSkeleton from '@/components/LoadingSkeleton.vue'
import SklandRewardArt from './SklandRewardArt.vue'
import SklandRewardDistribution from './SklandRewardDistribution.vue'
import { groupRewardTotals, number, percent } from './statistics'

const props = defineProps({
  report: { type: Object, default: null },
  coverage: { type: Object, default: null },
  distribution: { type: Object, default: null },
  selectedItem: { type: String, default: '' },
  loading: { type: Boolean, default: false },
  error: { type: String, default: '' },
  // 读取中还没有统计时，按这些分组的奖励数画出同样排布的占位卡片。
  placeholderGroups: { type: Array, default: () => [6] },
  // 上次读到的出现情况表的月份行数；为 0 时不画这张表的占位。
  placeholderMonths: { type: Number, default: 0 }
})
const emit = defineEmits(['select-item', 'retry'])
const groups = computed(() => groupRewardTotals(props.report?.items))
const results = useTemplateRef('results')
const minResultsHeight = ref(0)

watch([() => props.report, () => props.loading, () => props.error], () => {
  const body = results.value
  const scroller = body?.closest('.page')
  if (!scroller?.scrollTop || !body.offsetHeight) {
    minResultsHeight.value = 0
    return
  }
  const viewport = scroller.getBoundingClientRect()
  const bounds = body.getBoundingClientRect()
  const visibleHeight = viewport.bottom - Math.max(viewport.top, bounds.top)
  const retainedHeight = Math.max(0, Math.min(bounds.height, visibleHeight))
  // 保留视口内的结果区高度，避免空结果缩短页面后滚动位置被拉回。
  minResultsHeight.value = Math.ceil((retainedHeight / bounds.height) * body.offsetHeight)
})

const coverageTitle = computed(() => {
  const { signedPairDays, expectedPairDays } = props.coverage
  const days = `${number(signedPairDays)}/${number(expectedPairDays)}`
  return `本机有签到记录 ${days} 天`
})

function tileLabel(item) {
  return `${item.name} ×${number(item.count)}，${number(item.days)} 天获得`
}

function itemKey(item) {
  return `${item.game_group}::${item.name}`
}
</script>

<template>
  <section class="skland-panel reward-report" aria-label="签到奖励统计">
    <header class="reward-report__header">
      <h2>签到奖励统计</h2>
      <slot name="controls" />
    </header>
    <div
      ref="results"
      class="reward-report__results"
      :style="{ minBlockSize: minResultsHeight ? `${minResultsHeight}px` : undefined }"
    >
      <LoadingSkeleton v-if="loading && !report" label="正在读取奖励记录">
        <p class="reward-report__summary">
          <span
            >本机签到记录率
            <strong><span class="skeleton-bone skeleton-text" style="--skeleton-w: 2.6em" /></strong
          ></span>
          <span
            >本机记录到
            <strong
              ><span class="skeleton-bone skeleton-text" style="--skeleton-w: 1.2em"
            /></strong>
            天签到</span
          >
        </p>
        <div class="reward-groups">
          <section v-for="(count, index) in placeholderGroups" :key="index" class="reward-group">
            <h3><span class="skeleton-bone skeleton-text" style="--skeleton-w: 4em" /></h3>
            <ul class="reward-tiles">
              <li v-for="tile in count" :key="tile" class="reward-tile">
                <span class="reward-tile__button">
                  <span class="skeleton-bone reward-tile__placeholder" />
                  <span class="reward-tile__name"
                    ><span class="skeleton-bone skeleton-text" style="--skeleton-w: 4em"
                  /></span>
                  <span class="reward-tile__days"
                    ><span class="skeleton-bone skeleton-text" style="--skeleton-w: 3.5em"
                  /></span>
                </span>
              </li>
            </ul>
          </section>
        </div>
        <SklandRewardDistribution v-if="placeholderMonths" :placeholder="placeholderMonths" />
      </LoadingSkeleton>
      <p v-else-if="loading" class="reward-note" role="status">正在读取奖励记录…</p>
      <div v-if="error" class="reward-note" role="alert">
        {{ error }}
        <n-button v-if="!report" text @click="emit('retry')">重试</n-button>
      </div>
      <p v-if="coverage?.expectedPairDays || report?.signedDays" class="reward-report__summary">
        <span v-if="coverage?.expectedPairDays" :title="coverageTitle">
          本机签到记录率 <strong>{{ percent(coverage.coverage) }}</strong>
        </span>
        <span v-if="report?.signedDays">
          本机记录到 <strong>{{ number(report.signedDays) }}</strong> 天签到，获得
          <strong>{{ number(report.items.length) }}</strong> 种奖励
        </span>
        <span v-if="coverage?.failedPairDays" class="reward-report__failed">
          失败 {{ number(coverage.failedPairDays) }}
        </span>
      </p>

      <div v-if="groups.length" class="reward-groups">
        <section v-for="group in groups" :key="group.group" class="reward-group">
          <h3>{{ group.group }}</h3>
          <ul class="reward-tiles">
            <li
              v-for="item in group.items"
              :key="item.name"
              class="reward-tile"
              :title="tileLabel(item)"
            >
              <button
                type="button"
                class="reward-tile__button"
                :aria-pressed="itemKey(item) === selectedItem"
                @click="emit('select-item', itemKey(item))"
              >
                <SklandRewardArt
                  class="reward-tile__art"
                  :game="item.game_group"
                  :item="item.name"
                  :count="item.count"
                />
                <span class="reward-tile__name">{{ item.name }}</span>
                <span class="reward-tile__days">{{ number(item.days) }} 天获得</span>
              </button>
            </li>
          </ul>
        </section>
      </div>
      <SklandRewardDistribution v-if="distribution" :distribution="distribution" />
      <p v-else-if="report" class="reward-note" role="status">所选范围没有奖励记录</p>
      <p v-if="report?.unparsed" class="reward-note">
        {{ number(report.unparsed) }} 条签到记录缺少奖励明细。
      </p>
    </div>
  </section>
</template>

<style scoped>
.reward-report__header {
  display: grid;
  gap: 12px;
}
.reward-report h2 {
  margin: 0;
  font-size: 17px;
  font-weight: 650;
}
.reward-report__summary {
  display: flex;
  align-items: baseline;
  flex-wrap: wrap;
  gap: 2px 14px;
  margin: 0 0 12px;
  color: var(--mower-text-muted);
  font-size: 13px;
  font-variant-numeric: tabular-nums;
}
.reward-report__results {
  display: flow-root;
  overflow-anchor: none;
  margin-top: 12px;
}
.reward-report__summary strong {
  color: var(--mower-text);
  font-weight: 650;
}
.reward-report__summary span:first-child strong {
  font-size: 15px;
}
.reward-report__failed {
  color: var(--mower-error-text, var(--mower-error));
}
.reward-groups {
  display: grid;
  gap: 18px;
  padding-top: 12px;
  border-top: 1px solid var(--mower-divider);
}
.reward-group {
  min-width: 0;
}
.reward-group h3 {
  margin: 0 0 10px;
  font-size: 14px;
  font-weight: 650;
}
.reward-tiles {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(104px, 1fr));
  gap: 14px 12px;
  margin: 0;
  padding: 0;
  list-style: none;
}
.reward-tile {
  min-width: 0;
}
/* 点选一种奖励，在下方查看它在所选时间内每天的出现情况。 */
.reward-tile__button {
  display: grid;
  gap: 2px;
  width: 100%;
  min-width: 0;
  padding: 0;
  border: 0;
  background: none;
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
}
.reward-tile__button:focus-visible {
  outline: 2px solid var(--mower-primary);
  outline-offset: 3px;
  border-radius: calc(8px * var(--mower-corner-scale));
  corner-shape: var(--mower-corner-shape);
}
.reward-tile__button:hover .reward-tile__art {
  box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--mower-text) 28%, transparent);
}
.reward-tile__button[aria-pressed='true'] .reward-tile__art {
  box-shadow: inset 0 0 0 2px var(--mower-primary);
}
.reward-tile__art {
  --reward-art-radius: calc(8px * var(--mower-corner-scale));
  --reward-art-icon: 70%;
  --reward-art-count: 13px;
  --reward-art-ratio: 5 / 4;
  margin-bottom: 4px;
}
.reward-tile__placeholder {
  aspect-ratio: 5 / 4;
  margin-bottom: 4px;
  border-radius: calc(8px * var(--mower-corner-scale));
}
.reward-tile__name {
  overflow: hidden;
  color: var(--mower-text);
  font-size: 13px;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.reward-tile__days {
  color: var(--skland-muted, var(--mower-text-muted));
  font-size: 12px;
}
.reward-note {
  margin: 0;
  color: var(--skland-muted, var(--mower-text-muted));
  font-size: 13px;
}
.reward-note + .reward-note,
.reward-note + .reward-report__summary,
.reward-distribution + .reward-note {
  margin-top: 12px;
}
@container main-content (max-width: 480px) {
  .reward-tiles {
    grid-template-columns: repeat(auto-fill, minmax(88px, 1fr));
    gap: 12px 8px;
  }
  .reward-tile__art {
    --reward-art-count: 12px;
  }
}
</style>
