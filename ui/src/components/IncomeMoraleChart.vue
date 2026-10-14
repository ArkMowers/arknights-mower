<script setup>
import { computed } from 'vue'
import RecordLine from '@/pages/RecordLine.vue'
import { incomeMoraleReport } from '@/riic/incomeMorale'
const props = defineProps({
  rows: { type: Array, default: () => [] },
  plan: Object,
  warmupHours: Number
})
const report = computed(() => incomeMoraleReport(props.rows, props.plan, props.warmupHours))
</script>
<template>
  <p>
    曲线来自本次离线演算，横轴包含预热；虚线标出采样起点。绑组来自本次主副表快照，多绑组干员显示在各自组内。
  </p>
  <n-alert v-if="rows.some((row) => row.truncated)" type="warning">
    部分干员超过 6000 个转折点，省略区间以断线表示，末点保留结束心情。
  </n-alert>
  <RecordLine :simulation="report" />
</template>
