<script setup>
import { computed } from 'vue'
import { formatDateShort, formatWeekday, number } from './statistics'

const props = defineProps({
  log: { type: Object, required: true },
  today: { type: String, required: true },
  selectable: { type: Boolean, default: true }
})
const emit = defineEmits(['select'])

const days = computed(() => {
  const groups = []
  for (const entry of props.log.entries) {
    const last = groups.at(-1)
    if (last?.date === entry.date) last.entries.push(entry)
    else groups.push({ date: entry.date, entries: [entry] })
  }
  return groups
})

const pendingToday = computed(() => props.log.entries.filter((entry) => entry.pending))

function channel(entry) {
  return entry.channel === 'bilibili服' ? 'B服' : entry.channel
}

function message(entry) {
  const text = entry.messages.join('、') || '未返回失败信息'
  return entry.attempts > 1 ? `失败 ${number(entry.attempts)} 次 · ${text}` : text
}
</script>

<template>
  <section aria-label="失败记录" class="failure-log">
    <template v-if="log.entries.length">
      <p class="failure-log__summary">
        <strong>{{ number(days.length) }}</strong> 天出现签到失败，共失败
        <strong>{{ number(log.attempts) }}</strong> 次<template v-if="log.recovered"
          >，<strong>{{ number(log.recovered) }}</strong> 项当天已签到</template
        >
      </p>
      <div v-if="pendingToday.length" class="failure-log__today">
        <span>今天有 {{ number(pendingToday.length) }} 项签到失败</span>
        <slot name="retry" />
      </div>
      <ul v-if="log.reasons.length" class="failure-log__reasons" aria-label="常见失败原因">
        <li v-for="reason in log.reasons" :key="reason.message" :title="reason.message">
          <span>{{ reason.message }}</span>
          <strong>{{ number(reason.count) }}</strong>
        </li>
      </ul>
      <section
        v-for="day in days"
        :key="day.date"
        class="failure-day"
        :aria-label="formatDateShort(day.date, today)"
      >
        <h3>
          {{ formatDateShort(day.date, today) }}
          <small>周{{ formatWeekday(day.date) }}</small>
        </h3>
        <ul>
          <li v-for="entry in day.entries" :key="entry.key">
            <component
              :is="selectable ? 'button' : 'div'"
              :type="selectable ? 'button' : undefined"
              class="failure-entry"
              :class="{ 'is-recovered': entry.recovered }"
              @click="selectable && emit('select', entry)"
            >
              <span class="failure-entry__head">
                <span class="failure-entry__identity">
                  <strong>{{ entry.account }}</strong>
                  {{ entry.game_group || entry.game }}
                  <template v-if="entry.channel"> · {{ channel(entry) }}</template>
                  <template v-if="entry.roleName"> · {{ entry.roleName }}</template>
                </span>
                <span v-if="entry.recovered" class="failure-entry__result">
                  {{ entry.accountFailure ? '当天已读到签到角色' : '当天已签到' }}
                </span>
              </span>
              <span class="failure-entry__message">{{ message(entry) }}</span>
            </component>
          </li>
        </ul>
      </section>
    </template>
    <p v-else class="failure-empty">本月没有失败记录</p>
  </section>
</template>

<style scoped>
.failure-log__summary {
  margin: 0 0 8px;
  color: var(--mower-text-muted);
  font-size: 12px;
}
.failure-log__summary strong {
  color: var(--mower-text);
  font-size: 14px;
  font-weight: 650;
  font-variant-numeric: tabular-nums;
}
.failure-log__today {
  margin: 0 0 8px;
  padding: 8px 10px;
  border-radius: calc(6px * var(--mower-corner-scale));
  corner-shape: var(--mower-corner-shape);
  background: color-mix(in srgb, var(--mower-error) 9%, var(--mower-surface));
  color: var(--mower-error-text, var(--mower-error));
  font-size: 12px;
}
.failure-log__today :deep(.skland-retry) {
  margin-top: 6px;
}
.failure-log__reasons {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin: 0 0 6px;
  padding: 0;
  list-style: none;
}
.failure-log__reasons li {
  display: inline-flex;
  align-items: baseline;
  gap: 5px;
  max-width: 100%;
  padding: 2px 8px;
  border-radius: calc(10px * var(--mower-corner-scale));
  corner-shape: var(--mower-corner-shape);
  background: color-mix(in srgb, var(--mower-error) 10%, var(--mower-surface));
  color: var(--mower-error-text, var(--mower-error));
  font-size: 12px;
}
.failure-log__reasons span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.failure-log__reasons strong {
  font-weight: 650;
  font-variant-numeric: tabular-nums;
}
.failure-day h3 {
  display: flex;
  align-items: baseline;
  gap: 6px;
  margin: 10px 0 2px;
  font-size: 13px;
  font-weight: 700;
}
.failure-day h3 small {
  color: var(--mower-text-muted);
  font-size: 12px;
  font-weight: 500;
}
.failure-day ul {
  margin: 0;
  padding: 0;
  list-style: none;
}
.failure-day li + li {
  border-top: 1px solid var(--mower-divider);
}
.failure-entry {
  display: grid;
  gap: 2px;
  width: 100%;
  padding: 7px 6px 7px 9px;
  border: 0;
  border-left: 3px solid var(--mower-error);
  border-radius: 0 calc(4px * var(--mower-corner-scale)) calc(4px * var(--mower-corner-scale)) 0;
  corner-shape: var(--mower-corner-shape);
  background: transparent;
  color: var(--mower-text);
  text-align: left;
  font: inherit;
  font-size: 12px;
  overflow-wrap: anywhere;
}
button.failure-entry {
  cursor: pointer;
}
.failure-entry.is-recovered {
  border-left-color: var(--mower-success);
}
button.failure-entry:hover {
  background: var(--mower-surface);
}
.failure-entry:focus-visible {
  outline: 2px solid var(--mower-primary);
  outline-offset: 1px;
}
.failure-entry__head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 2px 8px;
}
.failure-entry__identity {
  color: var(--mower-text-muted);
}
.failure-entry__identity strong {
  margin-right: 4px;
  color: var(--mower-text);
  font-weight: 600;
}
.failure-entry__result {
  color: var(--mower-error-text, var(--mower-error));
  font-weight: 600;
}
.is-recovered .failure-entry__result {
  color: var(--mower-success-text, var(--mower-success));
}
.failure-entry__message {
  color: var(--mower-error-text, var(--mower-error));
}
.failure-empty {
  margin: 7px 0;
  color: var(--mower-text-muted);
  font-size: 13px;
}
</style>
