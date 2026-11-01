<script setup>
import { getRoomDisplayName } from '@/riic/vendor/workbench/operatorHelpers'
import { incomeDiagnosticMessage } from '@/riic/incomeDiagnostics'

defineProps({ activity: { type: Object, required: true }, historical: Boolean })
const format = (value) => Number(value).toLocaleString('zh-CN', { maximumFractionDigits: 3 })
</script>

<template>
  <div class="income-activity">
    <p v-if="!historical">{{ activity.message }}</p>
    <ul v-if="activity.findings?.length">
      <li v-for="(finding, i) in activity.findings" :key="i">
        {{ incomeDiagnosticMessage(finding) }}
      </li>
    </ul>
    <p v-if="activity.task">
      {{ activity.task.source === 'active' ? '当前任务' : '最近待执行任务' }}：{{
        activity.task.label
      }}
      {{ activity.task.metadata }} · 计划时刻 T+{{ format(activity.task.dueHours) }} 小时
      <span v-if="activity.task.rooms.length">
        · {{ activity.task.rooms.map(getRoomDisplayName).join('、') }}</span
      >
    </p>
    <ul v-if="activity.operators.length">
      <li v-for="op in activity.operators" :key="op.id">
        {{ op.name }} · 心情 {{ format(op.morale) }} / {{ format(op.upperLimit) }} ·
        {{ op.room ? getRoomDisplayName(op.room) : '未驻员' }} ·
        {{ op.groups.join('、') || '未绑组' }}
      </li>
    </ul>
    <p v-if="activity.recentEvents.length">
      近期活动：{{
        activity.recentEvents.map((event) => `${event.label} ${event.count} 次`).join('；')
      }}
    </p>
    <p v-if="!activity.findings?.length && !activity.task && !activity.operators.length">
      当前观测没有具体干员或任务信息。
    </p>
    <p>以上为已观测记录，不能仅凭活动频次认定原因；历史校验记录不表示当前仍未解决。</p>
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
