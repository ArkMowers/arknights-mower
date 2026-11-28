<script setup>
import { computed } from 'vue'

const props = defineProps({
  script: { type: Object, required: true },
  settings: { type: Object, required: true }
})
const report = computed(() => props.script.roster_check)
const borrowing = computed(() => props.settings.formation && props.settings.support_unit_usage > 0)
</script>

<template>
  <div class="script-result">
    <n-text strong>{{ script.stage_name }} · {{ script.title }}</n-text>
    <p v-if="report.message">{{ report.message }}</p>
    <p v-else-if="report.status === 'unknown'">
      练度数据不足，请在「养成规划」中刷新森空岛干员练度。
    </p>
    <ul v-if="report.gaps?.length">
      <li v-for="(gap, index) in report.gaps" :key="index">
        <span v-if="gap.candidates.length > 1 || gap.slot !== gap.candidates[0]?.name"
          >{{ gap.slot }}：</span
        >
        {{
          gap.candidates.map(({ name, reasons }) => `${name}（${reasons.join('，')}）`).join(' 或 ')
        }}
      </li>
    </ul>
    <p v-if="report.gaps?.length > 1">
      还差 {{ report.gaps.length }} 个编队位置，每场最多借用一名助战。
    </p>
    <p v-if="report.can_borrow" class="support-hint">
      <template v-if="borrowing">普通队列已允许借用助战补一个缺位。</template>
      <template v-else-if="settings.support_unit_usage">
        普通队列已设置助战方式，可在「队列统一设置」中开启自动编队以借用助战。
      </template>
      <template v-else>
        可在普通队列的「队列统一设置」中{{
          settings.formation ? '' : '开启自动编队，并'
        }}将「助战方式」设为「只补一名缺失干员」。
      </template>
    </p>
  </div>
</template>

<style scoped>
.script-result {
  overflow-wrap: anywhere;
  max-height: 60vh;
  overflow-y: auto;
}
.support-hint {
  margin: 10px 0 0;
}
.script-result p,
.script-result ul {
  margin: 4px 0 0;
}
.script-result ul {
  padding-left: 1.4em;
}
</style>
