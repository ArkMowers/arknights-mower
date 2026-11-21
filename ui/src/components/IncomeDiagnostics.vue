<script setup>
import { computed } from 'vue'
import { incomeDiagnosticGroups } from '@/riic/incomeDiagnostics'

const props = defineProps({ diagnostics: { type: Array, default: () => [] } })
const groups = computed(() => incomeDiagnosticGroups(props.diagnostics))
</script>

<template>
  <div class="income-diagnostics">
    <template v-if="groups.failures.length">
      <p><strong>未完成的原因</strong></p>
      <ul>
        <li v-for="(item, i) in groups.failures" :key="i">{{ item.message }}</li>
      </ul>
    </template>
    <n-collapse v-if="groups.records.length" :default-expanded-names="['records']">
      <n-collapse-item
        v-if="groups.records.length"
        :title="`调度与校验记录（${groups.records.length} 条）`"
        name="records"
      >
        <p>这些是演算期间的记录，不表示结束时仍有问题。</p>
        <ul>
          <li v-for="(item, i) in groups.records" :key="i">{{ item.message }}</li>
        </ul>
      </n-collapse-item>
    </n-collapse>
  </div>
</template>

<style scoped>
.income-diagnostics {
  overflow-wrap: anywhere;
}
ul {
  padding-left: 20px;
}
li {
  margin: 8px 0;
}
</style>
