<template>
  <n-collapse :default-expanded-names="['trainers']">
    <n-collapse-item title="各职业最优协助者" name="trainers">
      <n-text depth="3">
        供培养参考，不受拥有情况或排班限制。
        速度为技能解锁后的加成，不计分支专属额外加成、资源转换/挂件加成及中枢加成。
      </n-text>
      <n-scrollbar x-scrollable style="margin-top: 10px">
        <n-table size="small" :single-line="false" style="min-width: 560px">
          <thead>
            <tr>
              <th>职业</th>
              <th v-for="level in [1, 2, 3]" :key="level">专{{ level }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="profession in professions" :key="profession">
              <th>{{ profession }}</th>
              <td v-for="level in [1, 2, 3]" :key="level">
                <template v-if="trainers[profession]?.[level]">
                  {{ trainers[profession][level].name }}
                  <n-text depth="3" class="speed"
                    >+{{ trainers[profession][level].efficiency }}%</n-text
                  >
                  <n-tag
                    v-if="trainers[profession][level].owned === false"
                    size="small"
                    :bordered="false"
                    class="availability"
                    >未拥有</n-tag
                  >
                  <n-tag
                    v-else-if="trainers[profession][level].unlocked === false"
                    size="small"
                    type="warning"
                    :bordered="false"
                    class="availability"
                    >未解锁</n-tag
                  >
                  <n-text
                    v-else-if="trainers[profession][level].unlocked === null"
                    depth="3"
                    class="availability"
                    >练度未知</n-text
                  >
                </template>
                <n-text v-else depth="3">暂无推荐</n-text>
              </td>
            </tr>
          </tbody>
        </n-table>
      </n-scrollbar>
    </n-collapse-item>
  </n-collapse>
</template>

<script setup>
import { NCollapse, NCollapseItem, NScrollbar, NTable, NTag, NText } from 'naive-ui'
defineProps({
  trainers: { type: Object, default: () => ({}) },
  professions: { type: Array, default: () => [] }
})
</script>

<style scoped>
.availability {
  margin-left: 6px;
  font-size: 12px;
  vertical-align: middle;
}
.speed {
  display: inline-block;
  margin-left: 4px;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
</style>
