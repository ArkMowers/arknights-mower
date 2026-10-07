<template>
  <div class="mastery-materials">
    <n-collapse>
      <n-collapse-item :title="title" name="details">
        <template #header-extra>
          <n-tag v-if="summary" :type="materialStatusType(summary)" size="small" :bordered="false">
            {{ materialStatus(summary) }}
          </n-tag>
        </template>
        <slot name="before" />
        <template v-if="summary">
          <n-text v-if="!summary.materials.length" depth="3">无需继续准备材料</n-text>
          <template v-else>
            <div v-if="missingSkills.length" class="missing-materials">
              <n-text type="error">缺料技能</n-text>
              <n-space :size="4" wrap>
                <n-tag v-for="skill in missingSkills" :key="skill.key" size="small" type="error">
                  {{ skill.name }} {{ skill.skill_name }}
                </n-tag>
              </n-space>
            </div>
            <n-text depth="3" class="inventory-hint">数量：库存 / 需要</n-text>
            <n-text v-if="summary.crafting_gold" depth="3" class="inventory-hint">
              其中加工费
              {{ summary.crafting_gold.toLocaleString() }} 龙门币，已计入下方龙门币总需求。
            </n-text>
            <n-alert v-if="summary.manual_chips" type="info" :bordered="false" class="chip-hint">
              双芯片需手动准备：每个消耗 2 个同职业芯片组和 1 个芯片助剂。每个缺少的芯片助剂折算为
              90 张采购凭证；下方同时展示成品与原料需求，不会生成芯片合成任务。
            </n-alert>
            <div class="material-grid">
              <div v-for="material in summary.materials" :key="material.id" class="material-row">
                <n-avatar
                  :src="
                    '/depot/' + (material.id === 'growth_exp' ? 'EXP' : material.name) + '.webp'
                  "
                  :size="28"
                  :bordered="false"
                />
                <div>
                  <div>{{ material.name }}</div>
                  <n-text :type="materialQuantityType(material)">
                    {{ material.owned }} / {{ material.required }}
                  </n-text>
                </div>
              </div>
            </div>
            <n-collapse v-if="expandCrafting && summary.crafting.length" class="crafting-details">
              <n-collapse-item title="逐级合成材料" name="materials">
                <section v-for="group in craftingGroups" :key="group.label" class="crafting-tier">
                  <n-text depth="3" class="inventory-hint">{{ group.label }}</n-text>
                  <div class="material-grid">
                    <div
                      v-for="material in group.materials"
                      :key="material.id"
                      class="material-row"
                    >
                      <n-avatar
                        :src="
                          '/depot/' +
                          (material.id === 'growth_exp' ? 'EXP' : material.name) +
                          '.webp'
                        "
                        :size="24"
                        :bordered="false"
                      />
                      <div>
                        <div>{{ material.name }}</div>
                        <n-text :type="materialQuantityType(material)">
                          {{ material.owned }} / {{ material.required }}
                        </n-text>
                      </div>
                    </div>
                  </div>
                </section>
              </n-collapse-item>
            </n-collapse>
            <div v-if="blueMissing.length" class="missing-materials">
              <n-text type="error">仍缺蓝材料（T3）</n-text>
              <n-space :size="4" wrap>
                <n-tag v-for="material in blueMissing" :key="material.id" size="small" type="error">
                  {{ material.name }} ×{{ material.count }}
                </n-tag>
              </n-space>
            </div>
            <div v-if="otherMissing.length" class="missing-materials">
              <n-text type="error">其他缺少材料</n-text>
              <n-space :size="4" wrap>
                <n-tag
                  v-for="material in otherMissing"
                  :key="material.id"
                  size="small"
                  type="error"
                >
                  {{ material.name }} ×{{ material.count }}
                </n-tag>
              </n-space>
            </div>
          </template>
        </template>
        <n-text v-else depth="3">尚未选择养成目标</n-text>
        <slot />
      </n-collapse-item>
    </n-collapse>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { materialStatus, materialStatusType, materialQuantityType } from '@/utils/masteryMaterials'

const props = defineProps({
  summary: Object,
  expandCrafting: Boolean,
  missingSkills: { type: Array, default: () => [] },
  title: { type: String, default: '材料消耗与库存' }
})
const craftingGroups = computed(() => {
  const groups = new Map()
  for (const material of props.summary?.crafting || []) {
    const label = material.id.startsWith('330') ? '技巧概要' : `T${material.rarity} 材料`
    if (!groups.has(label)) groups.set(label, { label, rarity: material.rarity, materials: [] })
    groups.get(label).materials.push(material)
  }
  return [...groups.values()].sort((a, b) => b.rarity - a.rarity)
})
const blueMissing = computed(() => props.summary?.missing.filter((item) => item.blue) || [])
const otherMissing = computed(() => props.summary?.missing.filter((item) => !item.blue) || [])
</script>

<style scoped>
.mastery-materials {
  font-variant-numeric: tabular-nums;
}
.inventory-hint {
  display: block;
  margin: 8px 0;
  font-size: 12px;
}
.chip-hint {
  margin: 12px 0;
  font-size: 12px;
}
.material-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 10px 16px;
}
.material-row {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
}
.crafting-details,
.missing-materials {
  margin-top: 12px;
}
.missing-materials > :first-child {
  display: block;
  margin-bottom: 6px;
}
</style>
