<script setup>
import { computed } from 'vue'
import { NButton, NIcon } from 'naive-ui'
import RefreshOutline from '@vicons/ionicons5/es/RefreshOutline'
import MasteryMaterials from '@/components/MasteryMaterials.vue'
import {
  formatMaterialAmount as formatAmount,
  materialStatus,
  materialStatusType
} from '@/utils/masteryMaterials'
import { materialIcon } from './growthFormatters'

const props = defineProps({
  summary: { type: Object, default: null },
  loading: Boolean,
  error: { type: String, default: '' },
  missingSkills: { type: Array, default: () => [] },
  totalGoals: { type: Number, default: 0 },
  planCount: { type: Number, default: 0 },
  hasChipShortage: Boolean,
  chipLoading: Boolean,
  workshopLoading: Boolean
})
const emit = defineEmits([
  'refresh',
  'generate-crafting',
  'configure-chips',
  'add-target',
  'open-plan'
])

const directRows = computed(() => props.summary?.materials || [])
const highlighted = computed(() => {
  const ids = ['4001', 'growth_exp', '3303', '32001', '4006']
  const rows = directRows.value
  return ids
    .map((id) => rows.find((row) => row.id === id))
    .filter(Boolean)
    .map((row) => ({
      ...row,
      percent: row.required ? Math.min(100, Math.round((row.owned / row.required) * 100)) : 100
    }))
})
const RESOURCE_IDS = new Set(['4001', 'growth_exp', '4006', '32001'])
const materialRows = computed(() => directRows.value.filter((row) => !RESOURCE_IDS.has(row.id)))
const missing = computed(() => props.summary?.missing || [])
const depotMissing = computed(() => missing.value.filter((row) => !RESOURCE_IDS.has(row.id)))
const resourceMissing = computed(() => missing.value.filter((row) => RESOURCE_IDS.has(row.id)))
const onlyResourcesMissing = computed(
  () =>
    resourceMissing.value.length > 0 &&
    !directRows.value.some((row) => !RESOURCE_IDS.has(row.id) && row.owned < row.required)
)
const readyCount = computed(
  () => materialRows.value.filter((row) => row.owned >= row.required).length
)
const status = computed(() => {
  if (onlyResourcesMissing.value && !props.summary?.available) return '资源待备'
  return materialStatus(props.summary)
})
const statusType = computed(() => {
  if (onlyResourcesMissing.value && !props.summary?.available) return 'warning'
  return materialStatusType(props.summary)
})
const readableLine = computed(() => {
  if (props.summary?.available) return '库存可以覆盖当前计划'
  if (props.summary?.craftable) {
    return '成品尚未备齐，可逐级合成；资源缺口请在下方明细中核对。'
  }
  if (depotMissing.value.length) {
    return (
      '材料缺口 ' +
      depotMissing.value.length +
      ' 种' +
      (props.summary?.craftable ? ' · 可逐级合成' : '')
    )
  }
  if (resourceMissing.value.length) {
    return '材料已齐，资源缺口 ' + resourceMissing.value.length + ' 项'
  }
  return '仍有材料未备齐，请查看下方材料明细。'
})
const missingList = computed(() =>
  [...depotMissing.value]
    .filter((row) => !row.id.startsWith('330'))
    .sort((left, right) => (right.rarity || 0) - (left.rarity || 0) || right.count - left.count)
    .slice(0, 12)
)
</script>

<template>
  <div class="growth-materials">
    <section class="gp-panel growth-materials__summary">
      <header class="gp-section-head">
        <div>
          <span class="gp-kicker">Requisition sheet</span>
          <h2 class="gp-section-head__title">材料总览</h2>
        </div>
        <div class="growth-materials__actions">
          <n-button size="small" quaternary :loading="loading" @click="emit('refresh')">
            <template #icon><n-icon :component="RefreshOutline" /></template>
            重新计算
          </n-button>
          <n-button
            size="small"
            secondary
            type="primary"
            :loading="workshopLoading"
            :disabled="!totalGoals"
            @click="emit('generate-crafting')"
          >
            生成缺失材料合成任务
          </n-button>
          <n-button
            v-if="hasChipShortage"
            size="small"
            secondary
            :loading="chipLoading"
            @click="emit('configure-chips')"
          >
            设置芯片刷取
          </n-button>
        </div>
      </header>

      <div v-if="loading && !summary" class="growth-materials__loading">
        <div class="gp-skeleton" style="height: 150px" />
      </div>

      <div v-else-if="error" class="gp-empty">
        <p class="gp-empty__title">材料计算失败</p>
        <p class="gp-muted">{{ error }}</p>
        <div class="gp-empty__actions">
          <n-button size="small" @click="emit('refresh')">重试</n-button>
        </div>
      </div>

      <div v-else-if="!totalGoals" class="gp-empty">
        <p class="gp-empty__title">材料清单还是空的</p>
        <p class="gp-muted">
          选好养成目标后，这里按库存与合成配方算出缺口、可合成项和手动准备清单。
        </p>
        <div class="gp-empty__actions">
          <n-button size="small" type="primary" @click="emit('add-target')">选择养成目标</n-button>
          <n-button size="small" ghost @click="emit('open-plan')">查看养成计划</n-button>
        </div>
      </div>

      <template v-else-if="summary">
        <div class="growth-materials__headline">
          <div class="growth-materials__readiness">
            <span class="gp-kicker">Readiness</span>
            <strong class="gp-num"
              >{{ readyCount }}<small>/{{ materialRows.length }}</small></strong
            >
            <span class="gp-muted">种材料已备齐</span>
          </div>
          <div class="growth-materials__status" :class="'is-' + statusType">
            <span
              class="gp-stamp"
              :class="
                statusType === 'error'
                  ? 'gp-stamp--signal'
                  : statusType === 'warning'
                    ? 'gp-stamp--warn'
                    : ''
              "
              >{{ status }}</span
            >
            <p>{{ readableLine }}</p>
          </div>
        </div>

        <div class="growth-materials__tiles">
          <div v-for="row in highlighted" :key="row.id" class="growth-materials__tile">
            <img :src="materialIcon(row)" :alt="row.name" loading="lazy" />
            <div class="growth-materials__tile-body">
              <span class="growth-materials__tile-name">{{ row.name }}</span>
              <span
                class="growth-materials__tile-value gp-mono"
                :title="
                  row.name +
                  '：库存 ' +
                  row.owned.toLocaleString('zh-CN') +
                  ' / 需要 ' +
                  row.required.toLocaleString('zh-CN')
                "
              >
                {{ formatAmount(row.owned) }}
                <em>/ {{ formatAmount(row.required) }}</em>
              </span>
              <span class="gp-meter growth-materials__tile-meter" aria-hidden="true">
                <span :style="{ width: row.percent + '%' }" />
              </span>
            </div>
          </div>
        </div>

        <div v-if="missingList.length" class="growth-materials__missing">
          <div class="growth-materials__missing-head">
            <span class="gp-kicker">Still needed</span>
            <span class="gp-muted">按缺口数量排序</span>
          </div>
          <div class="growth-materials__missing-list">
            <div v-for="row in missingList" :key="row.id" class="growth-materials__missing-row">
              <img :src="materialIcon(row)" :alt="row.name" loading="lazy" />
              <span class="growth-materials__missing-name">{{ row.name }}</span>
              <span
                class="gp-mono growth-materials__missing-count"
                :title="row.name + ' ×' + row.count.toLocaleString('zh-CN')"
                >×{{ formatAmount(row.count) }}</span
              >
            </div>
          </div>
        </div>

        <div v-if="resourceMissing.length" class="growth-materials__resources">
          <span class="gp-kicker">Resources</span>
          <div class="growth-materials__resource-list">
            <span
              v-for="resource in resourceMissing"
              :key="resource.id"
              class="gp-chip gp-chip--signal"
              :title="resource.name + ' ×' + resource.count.toLocaleString('zh-CN')"
            >
              <img
                :src="materialIcon(resource)"
                :alt="resource.name"
                class="growth-materials__resource-icon"
              />
              {{ resource.name }} ×{{ formatAmount(resource.count) }}
            </span>
          </div>
        </div>

        <div v-if="missingSkills.length" class="growth-materials__skills">
          <span class="gp-kicker">Blocked skills</span>
          <div class="growth-materials__skill-list">
            <span v-for="skill in missingSkills" :key="skill.key" class="gp-chip gp-chip--signal">
              {{ skill.name }} · {{ skill.skill_name }}
            </span>
          </div>
        </div>

        <section class="growth-materials__detail">
          <header class="gp-section-head growth-materials__detail-head">
            <div>
              <h3 class="growth-materials__detail-title">材料明细</h3>
              <p class="gp-muted">成品按当前库存列出；展开可看逐级合成链与技巧概要。</p>
            </div>
            <span class="gp-muted gp-mono">{{ planCount }} 项计划</span>
          </header>
          <MasteryMaterials
            :summary="summary"
            :missing-skills="missingSkills"
            :show-header="false"
            :show-shortage="false"
            expand-crafting
          />
        </section>

        <p class="growth-materials__note">
          芯片、龙门币、经验与模组任务需在游戏内或对应任务中准备；材料预算只计算可直接合成的部分。
        </p>
      </template>
    </section>
  </div>
</template>

<style scoped>
.growth-materials {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.growth-materials__summary {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.growth-materials__actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.growth-materials__loading {
  display: flex;
}

.growth-materials__headline {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
  flex-wrap: wrap;
  padding: 4px 0 2px;
}

.growth-materials__readiness {
  display: flex;
  align-items: baseline;
  gap: 12px;
}

.growth-materials__readiness strong {
  font-size: 56px;
  line-height: 0.9;
  color: var(--gp-ink);
}

.growth-materials__readiness strong small {
  margin-left: 3px;
  font-size: 22px;
  font-weight: 600;
  color: var(--gp-muted);
}

.growth-materials__readiness .gp-muted {
  font-size: 12px;
}

.growth-materials__status {
  display: flex;
  align-items: center;
  gap: 10px;
}

.growth-materials__status p {
  margin: 0;
  color: var(--gp-muted);
  font-size: 12px;
}

.growth-materials__tiles {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 10px;
}

.growth-materials__tile {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border-radius: 12px;
  background: var(--gp-surface-2);
}

.growth-materials__tile img {
  width: 38px;
  height: 38px;
  object-fit: contain;
  flex: none;
}

.growth-materials__tile-body {
  display: flex;
  flex: 1;
  min-width: 0;
  flex-direction: column;
  gap: 3px;
}

.growth-materials__tile-name {
  color: var(--gp-muted);
  font-size: 10.5px;
}

.growth-materials__tile-value {
  overflow: hidden;
  color: var(--gp-ink);
  font-size: 14px;
  font-weight: 700;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.growth-materials__tile-value em {
  color: var(--gp-faint);
  font-size: 10.5px;
  font-style: normal;
  font-weight: 500;
}

.growth-materials__tile-meter {
  height: 3px;
}

.growth-materials__missing {
  padding: 14px 16px;
  border-radius: 14px;
  background: var(--gp-surface-2);
}

.growth-materials__missing-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
}

.growth-materials__missing-head .gp-muted {
  font-size: 10.5px;
}

.growth-materials__missing-list {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  gap: 8px 16px;
}

.growth-materials__missing-row {
  display: flex;
  align-items: center;
  gap: 7px;
  min-width: 0;
}

.growth-materials__missing-row img {
  width: 28px;
  height: 28px;
  object-fit: contain;
  flex: none;
}

.growth-materials__missing-name {
  overflow: hidden;
  flex: 1;
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.growth-materials__missing-count {
  color: var(--gp-signal);
  font-size: 11px;
  font-weight: 700;
}

.growth-materials__skills {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.growth-materials__resources {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.growth-materials__resource-list {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.growth-materials__resource-icon {
  width: 18px;
  height: 18px;
  object-fit: contain;
}

.growth-materials__skill-list {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.growth-materials__detail {
  padding-top: 4px;
}

.growth-materials__detail-head {
  margin-bottom: 8px;
}

.growth-materials__detail-title {
  margin: 0;
  font-size: 17px;
  font-weight: 700;
}

.growth-materials__detail-head p {
  margin: 3px 0 0;
  font-size: 11.5px;
}

.growth-materials__note {
  margin: 0;
  padding-top: 12px;
  border-top: 1px solid var(--gp-hair-soft);
  color: var(--gp-faint);
  font-size: 11.5px;
}

@media (max-width: 720px) {
  .growth-materials__readiness strong {
    font-size: 42px;
  }
  .growth-materials__tiles {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .growth-materials__missing-list {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
