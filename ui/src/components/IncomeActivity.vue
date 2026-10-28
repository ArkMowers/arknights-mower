<script setup>
import { incomeDisplayMessage, incomeRoomName } from '@/i18n/income'
import { operatorDisplayName } from '@/i18n/gameNames'
import { i18n } from '@/i18n'
const { t, locale } = i18n.global

defineProps({ activity: { type: Object, required: true } })
const format = (value) => Number(value).toLocaleString(locale.value, { maximumFractionDigits: 3 })
</script>

<template>
  <div class="income-activity">
    <p>{{ incomeDisplayMessage(activity.message) }}</p>
    <ul v-if="activity.findings?.length">
      <li v-for="(finding, i) in activity.findings" :key="i">
        {{ incomeDisplayMessage(finding.message) }}
      </li>
    </ul>
    <p v-if="activity.task">
      {{
        t('income.taskLabel', {
          kind: t(activity.task.source === 'active' ? 'income.currentTask' : 'income.pendingTask'),
          label: incomeDisplayMessage(activity.task.label)
        })
      }}
      {{ activity.task.metadata }} ·
      {{ t('income.due', { hours: format(activity.task.dueHours) }) }}
      <span v-if="activity.task.rooms.length">
        · {{ activity.task.rooms.map((room) => incomeRoomName(room)).join(', ') }}</span
      >
    </p>
    <ul v-if="activity.operators.length">
      <li v-for="op in activity.operators" :key="op.id">
        {{ operatorDisplayName(op.name) }} ·
        {{ t('income.morale', { value: format(op.morale), limit: format(op.upperLimit) }) }} ·
        {{ op.room ? incomeRoomName(op.room) : t('income.noStaff') }} ·
        {{ op.groups.join(', ') || t('income.noGroup') }}
      </li>
    </ul>
    <p v-if="activity.recentEvents.length">
      {{
        t('income.recent', {
          events: activity.recentEvents
            .map((event) =>
              t('income.occurrences', { ...event, label: incomeDisplayMessage(event.label) })
            )
            .join('; ')
        })
      }}
    </p>
    <p v-if="!activity.findings?.length && !activity.task && !activity.operators.length">
      {{ t('income.noDetails') }}
    </p>
    <p>{{ t('income.observedOnly') }}</p>
  </div>
</template>

<style scoped>
.income-activity {
  overflow-wrap: anywhere;
}
p {
  margin: 8px 0;
}
ul {
  margin: 8px 0;
  padding-left: 20px;
}
</style>
