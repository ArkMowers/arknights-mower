<script setup>
import { formatMonthDayCN, number } from './statistics'

defineProps({
  distribution: { type: Object, required: true }
})

const DAYS = Array.from({ length: 31 }, (_, index) => index + 1)
const LABELED_DAYS = new Set([1, 5, 10, 15, 20, 25, 30])
const OUTCOME_TEXT = {
  signed: '领到其他奖励',
  repeated: '已签到，奖励未知',
  unknown: '已签到，奖励未知',
  failed: '签到失败',
  none: '无记录'
}

function result(state, count) {
  if (state === 'got') return `获得 ×${number(count)}`
  return OUTCOME_TEXT[state]
}

function cellLabel(cell) {
  const text = `${formatMonthDayCN(cell.date)}：${result(cell.state, cell.count)}`
  if (!cell.channels.length) return text
  const channels = cell.channels.map(
    (channel) =>
      `${channel.channel} ${result(channel.count ? 'got' : channel.outcome, channel.count)}`
  )
  return `${text}（${channels.join('；')}）`
}

function visible(cell) {
  return cell && cell.state !== 'outside'
}
</script>

<template>
  <section class="reward-distribution" :aria-label="`${distribution.item}的出现情况`">
    <header class="reward-distribution__header">
      <h3>{{ distribution.item }}的出现情况</h3>
      <p v-if="distribution.days">
        共获得 <strong>{{ number(distribution.total) }}</strong>，出现在
        <strong>{{ number(distribution.days) }}</strong> 天
      </p>
      <p v-else>所选时间内没有获得</p>
    </header>
    <ul class="reward-distribution__legend" aria-label="图例">
      <li><span class="day-cell is-got" aria-hidden="true" />获得{{ distribution.item }}</li>
      <li><span class="day-cell is-signed" aria-hidden="true" />领到其他奖励</li>
      <li><span class="day-cell is-unknown" aria-hidden="true" />已签到，奖励未知</li>
      <li><span class="day-cell is-failed" aria-hidden="true" />签到失败</li>
      <li><span class="day-cell is-none" aria-hidden="true" />无记录</li>
    </ul>
    <div class="reward-distribution__scroll">
      <table class="reward-distribution__table">
        <thead>
          <tr>
            <th scope="col"><span class="sr-only">月份</span></th>
            <th
              v-for="day in DAYS"
              :key="day"
              scope="col"
              :class="{ 'is-quiet': !LABELED_DAYS.has(day) }"
            >
              {{ day }}
            </th>
            <th scope="col" class="reward-distribution__total">合计</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="month in distribution.months" :key="month.month">
            <th scope="row">{{ month.label }}</th>
            <td v-for="(cell, index) in month.cells" :key="index">
              <span
                v-if="visible(cell)"
                class="day-cell"
                :class="`is-${cell.state}`"
                role="img"
                :aria-label="cellLabel(cell)"
                :title="cellLabel(cell)"
              />
            </td>
            <td class="reward-distribution__total">
              {{ month.total ? number(month.total) : '—' }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>

<style scoped>
.reward-distribution {
  margin-top: 18px;
  padding-top: 14px;
  border-top: 1px solid var(--mower-divider);
}
.reward-distribution__header {
  display: flex;
  align-items: baseline;
  flex-wrap: wrap;
  gap: 2px 12px;
}
.reward-distribution h3 {
  margin: 0;
  font-size: 14px;
  font-weight: 650;
}
.reward-distribution__header p {
  margin: 0;
  color: var(--mower-text-muted);
  font-size: 13px;
  font-variant-numeric: tabular-nums;
}
.reward-distribution__header strong {
  color: var(--mower-text);
  font-weight: 650;
}
.reward-distribution__legend {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 14px;
  margin: 8px 0 6px;
  padding: 0;
  color: var(--mower-text-muted);
  font-size: 12px;
  list-style: none;
}
.reward-distribution__legend li {
  display: inline-flex;
  align-items: center;
  gap: 5px;
}
.reward-distribution__legend .day-cell {
  width: 11px;
}
.reward-distribution__scroll {
  overflow-x: auto;
  scrollbar-width: thin;
}
/* 每行一个月、每列是当月第几天，签到按月重置，同一种奖励在各月的位置可以直接对照。 */
.reward-distribution__table {
  width: 100%;
  min-width: 430px;
  border-collapse: separate;
  border-spacing: 2px;
  table-layout: fixed;
  font-variant-numeric: tabular-nums;
}
.reward-distribution__table th {
  color: var(--mower-text-muted);
  font-size: 10px;
  font-weight: 500;
  text-align: center;
}
.reward-distribution__table thead th:first-child,
.reward-distribution__table tbody th {
  width: 54px;
  padding-right: 4px;
  font-size: 12px;
  text-align: right;
  white-space: nowrap;
}
.reward-distribution__table th.is-quiet {
  color: transparent;
}
.reward-distribution__table td {
  padding: 0;
}
.reward-distribution__table .reward-distribution__total {
  width: 58px;
  padding-left: 6px;
  color: var(--mower-text);
  font-size: 12px;
  text-align: right;
  white-space: nowrap;
}
.reward-distribution__table thead .reward-distribution__total {
  color: var(--mower-text-muted);
}
.day-cell {
  display: block;
  box-sizing: border-box;
  aspect-ratio: 1;
  border-radius: 3px;
}
.day-cell.is-got {
  background: var(--mower-primary);
}
.day-cell.is-signed {
  background: color-mix(in srgb, var(--mower-text) 13%, transparent);
}
/* 失败用斜纹加描边，不只靠颜色和获得区分。 */
.day-cell.is-failed {
  border: 1px solid var(--mower-error);
  background: repeating-linear-gradient(
    135deg,
    color-mix(in srgb, var(--mower-error) 55%, transparent) 0 2px,
    transparent 2px 4px
  );
}
.day-cell.is-none {
  border: 1px dashed color-mix(in srgb, var(--mower-text) 34%, transparent);
}
.day-cell.is-unknown {
  border: 1px solid color-mix(in srgb, var(--mower-text) 34%, transparent);
  background: color-mix(in srgb, var(--mower-text) 8%, transparent);
}
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
  white-space: nowrap;
}
</style>
