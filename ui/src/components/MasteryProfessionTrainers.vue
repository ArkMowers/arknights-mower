<template>
  <n-collapse :default-expanded-names="['trainers']">
    <n-collapse-item
      :title="i18n.global.t('growth.trainers.bestAssistantsByProfession')"
      name="trainers"
    >
      <n-text depth="3">
        {{ i18n.global.t('growth.trainers.forGrowthReferenceRegardlessOfOwnershipOr') }}
      </n-text>
      <n-scrollbar x-scrollable style="margin-top: 10px">
        <n-table size="small" :single-line="false" style="min-width: 560px">
          <thead>
            <tr>
              <th>{{ i18n.global.t('growth.trainers.profession') }}</th>
              <th v-for="level in [1, 2, 3]" :key="level">
                {{ i18n.global.t('growth.trainers.m') }}{{ level }}
              </th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="profession in professions" :key="profession">
              <th>{{ professionName(profession) }}</th>
              <td v-for="level in [1, 2, 3]" :key="level">
                <template v-if="trainers[profession]?.[level]">
                  {{ operatorDisplayName(trainers[profession][level].name) }}
                  <n-text depth="3" class="speed"
                    >+{{ trainers[profession][level].efficiency }}%</n-text
                  >
                  <n-tag
                    v-if="trainers[profession][level].owned === false"
                    size="small"
                    :bordered="false"
                    class="availability"
                    >{{ i18n.global.t('growth.trainers.notOwned') }}</n-tag
                  >
                  <n-tag
                    v-else-if="trainers[profession][level].unlocked === false"
                    size="small"
                    type="warning"
                    :bordered="false"
                    class="availability"
                    >{{ i18n.global.t('growth.trainers.locked') }}</n-tag
                  >
                  <n-text
                    v-else-if="trainers[profession][level].unlocked === null"
                    depth="3"
                    class="availability"
                    >{{ i18n.global.t('growth.trainers.progressionUnknown') }}</n-text
                  >
                </template>
                <n-text v-else depth="3">{{
                  i18n.global.t('growth.trainers.noRecommendation')
                }}</n-text>
              </td>
            </tr>
          </tbody>
        </n-table>
      </n-scrollbar>
    </n-collapse-item>
  </n-collapse>
</template>

<script setup>
import { operatorDisplayName } from '@/i18n/gameNames'
import { i18n } from '@/i18n'
import { professionName } from '@/growth/growthFormatters'
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
