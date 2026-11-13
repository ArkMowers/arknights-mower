<script setup>
import DailyDoneIcon from '@vicons/ionicons5/es/CheckmarkCircle'
import DailyAttemptedIcon from '@vicons/ionicons5/es/AlertCircleOutline'
import DailyPendingIcon from '@vicons/ionicons5/es/EllipseOutline'

defineProps({
  items: { type: Array, required: true },
  gameDay: { type: String, default: null },
  logDate: { type: String, default: null },
  alternate: Boolean,
  standalone: Boolean,
  loading: Boolean
})

const daily_states = {
  done: { icon: DailyDoneIcon, label: '今日已处理（按调度记录）', summary: '已处理' },
  attempted: { icon: DailyAttemptedIcon, label: '今日已尝试，尚未完成', summary: '已尝试' },
  pending: { icon: DailyPendingIcon, label: '今日尚未完成', summary: '未处理' }
}
const dailyState = (state) =>
  Object.hasOwn(daily_states, state)
    ? daily_states[state]
    : { icon: DailyPendingIcon, label: '处理结果未确认', summary: '未确认' }
</script>

<template>
  <div
    class="daily-status"
    :class="{ 'daily-status--view': alternate, 'daily-status--standalone': standalone }"
    :role="alternate || standalone ? 'region' : 'group'"
    :aria-label="alternate || standalone ? '今日任务' : '任务状态'"
    :tabindex="alternate ? 0 : undefined"
    :title="items.length ? `游戏日 ${gameDay}，北京时间每日凌晨 4 点开始新的游戏日` : undefined"
  >
    <h2 v-if="standalone" class="daily-status__heading">今日任务</h2>
    <p v-if="!alternate && logDate" class="daily-status__date">
      {{ logDate }}
    </p>
    <ul v-if="items.length" class="daily-status__items" aria-label="任务概览">
      <li
        v-for="item in items"
        :key="item.id"
        class="daily-status__item"
        :class="`daily-status__item--${item.state}`"
        :title="`${item.title}：${dailyState(item.state).label}`"
      >
        <n-icon
          class="daily-status__icon"
          :component="dailyState(item.state).icon"
          aria-hidden="true"
        />
        <span class="daily-status__title">{{ item.title }}</span>
        <span class="daily-status__state">，{{ dailyState(item.state).label }}</span>
        <span v-if="alternate" class="daily-status__summary" aria-hidden="true">
          {{ dailyState(item.state).summary }}
        </span>
      </li>
    </ul>
    <p v-else class="daily-status__empty" role="status">
      {{ loading ? '正在读取今日任务…' : '暂无今日任务状态' }}
    </p>
  </div>
</template>

<style scoped lang="scss">
/* 日志上方的日期与今日任务：整体居中，透明波点底在四周浅出。 */
.daily-status {
  position: relative;
  display: flex;
  width: 100%;
  max-width: 100%;
  box-sizing: border-box;
  flex-direction: column;
  flex-shrink: 0;
  align-items: center;
  gap: 4px;
  margin-inline: auto;
  padding: 6px 24px 8px;
  border-radius: 10px;
  font-size: 12px;
  line-height: 18px;
}

.daily-status::before {
  content: '';
  position: absolute;
  inset: -8px -40px;
  background-image: radial-gradient(
    circle,
    color-mix(in srgb, currentColor 9%, transparent) 1px,
    transparent 1.2px
  );
  background-size: 12px 12px;
  -webkit-mask-image: radial-gradient(ellipse 55% 110% at 50% 50%, #000 25%, transparent 100%);
  mask-image: radial-gradient(ellipse 55% 110% at 50% 50%, #000 25%, transparent 100%);
  pointer-events: none;
}

.daily-status > * {
  position: relative;
  z-index: 1;
}

.daily-status--standalone {
  align-items: flex-start;
  padding: 8px 4px;
}

.daily-status--standalone::before {
  content: none;
}

.daily-status__heading {
  margin: 0;
  color: var(--mower-text-muted);
  font: inherit;
  font-weight: 600;
}

.daily-status--standalone .daily-status__items {
  justify-content: flex-start;
  max-height: none;
}

.daily-status__date {
  margin: 0;
  color: var(--mower-text-muted, #8a9099);
  font-size: 11px;
  font-weight: var(--log-label-weight);
  letter-spacing: 0.12em;
  font-variant-numeric: tabular-nums;
}

.daily-status__items {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 6px;
  max-height: 58px;
  width: 100%;
  overflow: hidden;
  margin: 0;
  padding: 0;
  list-style: none;
}

.daily-status--view {
  align-items: stretch;
  height: 100%;
  padding: 0 var(--log-scroll-padding) 8px var(--log-inset);
  overflow: auto;
  overscroll-behavior: contain;
}

.daily-status--view::before {
  content: none;
}

.daily-status--view .daily-status__items {
  display: block;
  max-height: none;
  overflow: visible;
}

.daily-status--view .daily-status__item {
  display: flex;
  gap: 8px;
  height: auto;
  min-height: 36px;
  padding: 6px 0;
  border: 0;
  border-bottom: var(--log-hairline) solid var(--log-rule);
  border-radius: 0;
  background: none;
  box-shadow: none;
  backdrop-filter: none;
  -webkit-backdrop-filter: none;
}

.daily-status__summary {
  margin-inline-start: auto;
  font-size: 11px;
}

.daily-status__empty {
  margin: 8px 0;
  color: var(--mower-text-muted);
}

.daily-status__item {
  --lg-btn-label: var(--lg-btn-neutral-label);
  --lg-btn-line: var(--lg-btn-neutral-line);
  --lg-btn-bg: var(--lg-btn-neutral-bg);
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  box-sizing: border-box;
  height: 26px;
  max-width: 100%;
  flex-shrink: 0;
  padding: 2px 9px 2px 6px;
  border: var(--log-hairline) solid var(--lg-btn-line);
  border-radius: 999px;
  color: var(--lg-btn-label);
  background-image: var(--lg-btn-sheen), var(--lg-btn-bg);
  backdrop-filter: blur(20px) saturate(1.1);
  -webkit-backdrop-filter: blur(20px) saturate(1.1);
  box-shadow: var(--lg-btn-shadow);
  white-space: nowrap;
}

.daily-status__item--done {
  --lg-btn-label: var(--lg-btn-primary-label);
  --lg-btn-line: var(--lg-btn-primary-line);
  --lg-btn-bg: var(--lg-btn-primary-bg);
}

.daily-status__item--attempted {
  --lg-btn-label: var(--lg-btn-warning-label);
  --lg-btn-line: var(--lg-btn-warning-line);
  --lg-btn-bg: var(--lg-btn-warning-bg);
}

.daily-status__item--pending,
.daily-status__item--unknown {
  .daily-status__icon {
    color: var(--mower-text-muted, #8a9099);
  }
}

.daily-status__title {
  overflow: hidden;
  text-overflow: ellipsis;
}

.daily-status__icon {
  font-size: 14px;
}

/* 状态文字只给读屏软件，视觉上由图标和颜色区分。 */
.daily-status__state {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
}
</style>
