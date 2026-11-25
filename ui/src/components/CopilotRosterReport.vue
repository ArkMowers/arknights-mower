<script setup>
import { computed } from 'vue'

const props = defineProps({
  scripts: { type: Array, required: true },
  settings: { type: Object, required: true }
})
const issues = computed(() =>
  props.scripts.filter((script) => script.roster_check.status !== 'ready')
)
const canBorrow = computed(() =>
  issues.value.some(
    ({ roster_check }) => roster_check.status === 'shortfall' && roster_check.can_borrow === true
  )
)
const borrowing = computed(() => props.settings.formation && props.settings.support_unit_usage > 0)
</script>

<template>
  <n-text v-if="!issues.length" depth="3" role="status">本次导入的普通作业均满足编队要求。</n-text>
  <n-alert v-else title="导入作业的练度检查" type="warning" :show-icon="false">
    <section v-for="script in issues" :key="script.id" class="script-result">
      <n-text strong>{{ script.stage_name }} · {{ script.title }}</n-text>
      <p v-if="script.roster_check.status === 'unknown'">
        {{
          script.roster_check.message ||
          '练度数据不足，请在「养成规划」中刷新森空岛干员练度后重新导入。'
        }}
      </p>
      <ul v-if="script.roster_check.gaps?.length">
        <li v-for="(gap, index) in script.roster_check.gaps" :key="index">
          <span v-if="gap.candidates.length > 1 || gap.slot !== gap.candidates[0]?.name"
            >{{ gap.slot }}：</span
          >
          {{
            gap.candidates
              .map(({ name, reasons }) => `${name}（${reasons.join('，')}）`)
              .join(' 或 ')
          }}
        </li>
      </ul>
      <p v-if="script.roster_check.gaps?.length > 1">
        还差 {{ script.roster_check.gaps.length }} 个编队位置，每场最多借用一名助战。
      </p>
    </section>
    <p v-if="canBorrow" class="support-hint">
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
  </n-alert>
</template>

<style scoped>
.script-result {
  overflow-wrap: anywhere;
}
.script-result + .script-result,
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
