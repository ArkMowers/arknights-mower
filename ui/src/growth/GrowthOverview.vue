<script setup>
import { materialDisplayName as itemDisplayName } from '@/growth/growthFormatters'
import { operatorDisplayName } from '@/i18n/gameNames'
import { i18n } from '@/i18n'
import { computed } from 'vue'
import { NButton, NIcon, NSelect } from 'naive-ui'
import ArrowForwardOutline from '@vicons/ionicons5/es/ArrowForwardOutline'
import RefreshOutline from '@vicons/ionicons5/es/RefreshOutline'
import WorkshopStatus from '@/components/WorkshopStatus.vue'
import GrowthOperatorCard from './GrowthOperatorCard.vue'
import { materialIcon, planStatusLabel } from './growthFormatters'
import { recommendationSortOptions } from './growthDisplay'
import { formatMaterialAmount } from '@/utils/masteryMaterials'

const props = defineProps({
  goalCount: { type: Number, default: 0 },
  planCount: { type: Number, default: 0 },
  training: { type: Object, default: null },
  nextUp: { type: Object, default: null },
  queue: { type: Array, default: () => [] },
  queueError: { type: String, default: '' },
  materials: { type: Object, default: null },
  materialsLoading: Boolean,
  materialsError: { type: String, default: '' },
  materialStats: {
    type: Object,
    default: () => ({ ready: 0, total: 0, missing: 0, craftable: 0, percent: 0 })
  },
  recommended: { type: Array, default: () => [] },
  pickSort: { type: String, default: 'mastery' },
  rosterStats: {
    type: Object,
    default: () => ({ owned: 0, elite2: 0, masteries: 0, modules: 0 })
  },
  workshopStatusRevision: { type: Number, default: 0 },
  workshopLoading: Boolean,
  hasChipShortage: Boolean,
  chipFarmingLoading: Boolean
})
const emit = defineEmits([
  'open-plan',
  'open-materials',
  'open-insights',
  'open-operators',
  'open-operator',
  'add-target',
  'generate-crafting',
  'configure-chips',
  'refresh-materials',
  'update:pick-sort'
])

const RESOURCE_IDS = new Set(['4001', 'growth_exp', '4006', '32001'])
const pickSortOptions = computed(recommendationSortOptions)
const queueRows = computed(() => props.queue.slice(0, 5))
const overflowCount = computed(() => Math.max(0, props.queue.length - queueRows.value.length))
const missingItems = computed(() =>
  (props.materials?.missing || [])
    .filter((row) => !RESOURCE_IDS.has(row.id))
    .sort((left, right) => (right.rarity || 0) - (left.rarity || 0) || right.count - left.count)
    .slice(0, 4)
)
const resourceMissing = computed(() =>
  (props.materials?.missing || []).filter((row) => RESOURCE_IDS.has(row.id))
)
const percent = computed(() => Math.round(props.materialStats.percent || 0))
const elitePercent = computed(() =>
  props.rosterStats.owned
    ? Math.round((props.rosterStats.elite2 / props.rosterStats.owned) * 100)
    : 0
)

function statusTone(status) {
  if (status === 'training' || status === 'arranging' || status === 'waiting_collect') return 'warn'
  if (status === 'failed') return 'signal'
  if (status === 'waiting') return 'info'
  return 'idle'
}

function statusText(status) {
  return planStatusLabel(status)
}

function formatCount(value) {
  return formatMaterialAmount(value)
}
</script>

<template>
  <div class="gp-overview">
    <div class="gp-overview__top">
      <section class="gp-sheet gp-overview__queue" aria-labelledby="growth-queue-title">
        <header class="gp-section-head">
          <div>
            <span class="gp-kicker">{{ i18n.global.t('growth.format.trainingQueueHeading') }}</span>
            <h2 id="growth-queue-title" class="gp-section-head__title">
              {{ i18n.global.t('growth.overview.trainingQueue') }}
            </h2>
          </div>
          <div class="gp-section-head__meta">
            <span class="gp-mono"
              >{{ goalCount }} {{ i18n.global.t('growth.overview.items') }}</span
            >
            <button type="button" class="gp-link" @click="emit('open-plan')">
              {{ i18n.global.t('growth.overview.reorder') }}
              <n-icon :component="ArrowForwardOutline" :size="14" />
            </button>
          </div>
        </header>

        <p v-if="queueError" class="gp-muted" role="status">{{ queueError }}</p>
        <ol v-if="queueRows.length" class="gp-queue">
          <li v-for="(item, index) in queueRows" :key="item.key" class="gp-queue__row">
            <span class="gp-queue__index gp-mono">{{ String(index + 1).padStart(2, '0') }}</span>
            <span class="gp-queue__avatar">
              <img
                :src="'/avatar/' + encodeURIComponent(item.name) + '.webp'"
                :alt="operatorDisplayName(item.name)"
                loading="lazy"
                @error="(event) => (event.target.src = '/avatar/阿米娅.webp')"
              />
            </span>
            <div class="gp-queue__text">
              <b>{{ operatorDisplayName(item.name) }}</b>
              <span class="gp-queue__label">{{ item.label }}</span>
            </div>
            <span
              v-if="statusTone(item.status) === 'warn' || statusTone(item.status) === 'signal'"
              class="gp-stamp gp-overview__stamp"
              :class="{
                'gp-stamp--warn': statusTone(item.status) === 'warn',
                'gp-stamp--signal': statusTone(item.status) === 'signal'
              }"
            >
              {{ statusText(item.status) }}
            </span>
            <span
              v-else
              class="gp-overview__status gp-mono"
              :class="'is-' + statusTone(item.status)"
            >
              {{ statusText(item.status) }}
            </span>
          </li>
        </ol>

        <div v-else class="gp-empty gp-overview__empty">
          <p class="gp-empty__title">{{ i18n.global.t('growth.overview.theQueueIsEmpty') }}</p>
          <p class="gp-muted">
            {{ i18n.global.t('growth.overview.chooseOperatorsAndGrowthGoalsAutomaticMastery') }}
          </p>
          <div class="gp-empty__actions">
            <n-button size="small" type="primary" @click="emit('add-target')">{{
              i18n.global.t('growth.overview.chooseGrowthGoals')
            }}</n-button>
          </div>
        </div>

        <footer v-if="queueRows.length" class="gp-overview__queue-foot">
          <span v-if="overflowCount" class="gp-muted"
            >{{ i18n.global.t('growth.overview.another') }} {{ overflowCount }}
            {{ i18n.global.t('growth.overview.itemsPlanned') }}</span
          >
          <span v-else class="gp-muted">{{
            i18n.global.t('growth.overview.ongoingTrainingStaysAtTheFrontOf')
          }}</span>
          <button type="button" class="gp-link" @click="emit('open-plan')">
            {{ i18n.global.t('growth.overview.openFullPlan') }}
          </button>
        </footer>
      </section>

      <section class="gp-panel gp-overview__materials" aria-labelledby="growth-materials-title">
        <header class="gp-section-head gp-overview__materials-head">
          <h2 id="growth-materials-title" class="gp-section-head__title">
            {{ i18n.global.t('growth.overview.materialPreparation') }}
          </h2>
          <button type="button" class="gp-link" @click="emit('open-materials')">
            {{ i18n.global.t('growth.overview.viewDetails') }}
          </button>
        </header>

        <div v-if="materialsLoading && !materials" class="gp-overview__loading">
          <div class="gp-skeleton" style="height: 64px" />
          <div class="gp-skeleton" style="height: 26px" />
        </div>

        <div v-else-if="materialsError" class="gp-overview__material-error">
          <p>{{ materialsError }}</p>
          <button type="button" class="gp-link" @click="emit('refresh-materials')">
            <n-icon :component="RefreshOutline" :size="13" />
            {{ i18n.global.t('growth.overview.recalculate') }}
          </button>
        </div>

        <div v-else-if="!goalCount" class="gp-overview__material-empty">
          <p class="gp-muted">
            {{ i18n.global.t('growth.overview.afterAddingGoalsInventoryIsUsedTo') }}
          </p>
        </div>

        <template v-else>
          <div class="gp-overview__readiness">
            <div class="gp-overview__readiness-value gp-num">{{ percent }}<small>%</small></div>
            <div class="gp-overview__readiness-meta">
              <span>{{ i18n.global.t('growth.overview.materialTypesReady') }}</span>
              <span class="gp-mono">{{ materialStats.ready }} / {{ materialStats.total }}</span>
            </div>
          </div>
          <div
            class="gp-meter gp-overview__meter"
            :class="{ 'gp-meter--signal': percent < 60 && materialStats.missing }"
          >
            <span :style="{ width: percent + '%' }" />
          </div>
          <dl class="gp-overview__material-stats">
            <div>
              <dt>{{ i18n.global.t('growth.overview.materialShortages') }}</dt>
              <dd class="gp-mono" :class="{ 'is-signal': missingItems.length }">
                {{ materialStats.missing }} {{ i18n.global.t('growth.overview.types') }}
              </dd>
            </div>
            <div>
              <dt>{{ i18n.global.t('growth.overview.craftable') }}</dt>
              <dd class="gp-mono">
                {{ materialStats.craftable }} {{ i18n.global.t('growth.overview.types') }}
              </dd>
            </div>
            <div>
              <dt>{{ i18n.global.t('growth.overview.ready') }}</dt>
              <dd class="gp-mono">
                {{ materialStats.ready }} {{ i18n.global.t('growth.overview.types') }}
              </dd>
            </div>
          </dl>
          <div v-if="missingItems.length" class="gp-overview__missing">
            <div
              v-for="material in missingItems"
              :key="material.id"
              class="gp-overview__missing-item"
              :title="
                itemDisplayName(material.id, material.name) +
                i18n.global.t('growth.overview.short') +
                material.count
              "
            >
              <img
                :src="materialIcon(material)"
                :alt="itemDisplayName(material.id, material.name)"
                loading="lazy"
              />
              <span class="gp-mono">×{{ formatCount(material.count) }}</span>
            </div>
          </div>
          <div v-if="resourceMissing.length" class="gp-overview__resources">
            <span class="gp-overview__resources-label">{{
              i18n.global.t('growth.overview.resourceShortages')
            }}</span>
            <span
              v-for="resource in resourceMissing"
              :key="resource.id"
              class="gp-overview__resource"
            >
              <img
                :src="materialIcon(resource)"
                :alt="itemDisplayName(resource.id, resource.name)"
                loading="lazy"
              />
              {{ itemDisplayName(resource.id, resource.name) }} ×{{ formatCount(resource.count) }}
            </span>
          </div>
          <div class="gp-overview__material-actions">
            <n-button
              size="small"
              secondary
              type="primary"
              :loading="workshopLoading"
              :disabled="!goalCount"
              @click="emit('generate-crafting')"
            >
              {{ i18n.global.t('growth.overview.generateCraftingTasks') }}
            </n-button>
            <button
              v-if="hasChipShortage"
              type="button"
              class="gp-link"
              :disabled="chipFarmingLoading"
              @click="emit('configure-chips')"
            >
              {{ i18n.global.t('growth.overview.farmChips') }}
            </button>
          </div>
          <div class="gp-overview__workshop">
            <WorkshopStatus :revision="workshopStatusRevision" />
          </div>
        </template>
      </section>
    </div>

    <div class="gp-overview__bottom">
      <section class="gp-panel gp-overview__roster" aria-labelledby="growth-roster-title">
        <header class="gp-section-head gp-overview__roster-head">
          <h2 id="growth-roster-title" class="gp-section-head__title">
            {{ i18n.global.t('growth.overview.rosterOverview') }}
          </h2>
          <button type="button" class="gp-link" @click="emit('open-insights')">
            {{ i18n.global.t('growth.overview.statistics') }}
          </button>
        </header>
        <dl class="gp-overview__roster-grid">
          <div>
            <dt>{{ i18n.global.t('growth.overview.owned') }}</dt>
            <dd class="gp-num">{{ rosterStats.owned }}</dd>
          </div>
          <div>
            <dt>{{ i18n.global.t('growth.overview.elite2') }}</dt>
            <dd class="gp-num">{{ rosterStats.elite2 }}</dd>
          </div>
          <div>
            <dt>{{ i18n.global.t('growth.overview.m3Skills') }}</dt>
            <dd class="gp-num">{{ rosterStats.masteries }}</dd>
          </div>
          <div>
            <dt>{{ i18n.global.t('growth.overview.unlockedModules') }}</dt>
            <dd class="gp-num">{{ rosterStats.modules }}</dd>
          </div>
        </dl>
        <div class="gp-overview__roster-meter">
          <div class="gp-overview__roster-meter-head">
            <span>{{ i18n.global.t('growth.overview.elite2Rate') }}</span>
            <span class="gp-mono">{{ elitePercent }}%</span>
          </div>
          <div class="gp-meter">
            <span :style="{ width: elitePercent + '%' }" />
          </div>
        </div>
        <p class="gp-overview__roster-note">
          {{
            i18n.global.t(
              'growth.overview.calculatedFromLocallySynchronizedProgressionUnsynchronizedOperators'
            )
          }}
        </p>
      </section>

      <section class="gp-panel gp-overview__pick" aria-labelledby="growth-pick-title">
        <header class="gp-section-head">
          <div class="gp-overview__pick-head">
            <span class="gp-kicker">{{ i18n.global.t('growth.format.suggestedNext') }}</span>
            <h2 id="growth-pick-title" class="gp-section-head__title">
              {{ i18n.global.t('growth.overview.worthRaising') }}
            </h2>
            <p class="gp-overview__pick-sub">
              {{ i18n.global.t('growthUpdates.remainingRecommendationsHelp') }}
            </p>
          </div>
          <div class="gp-overview__pick-actions">
            <n-select
              size="small"
              class="gp-overview__pick-sort"
              :value="pickSort"
              :options="pickSortOptions"
              :aria-label="i18n.global.t('growthUpdates.pickSort')"
              @update:value="emit('update:pick-sort', $event)"
            />
            <button type="button" class="gp-link" @click="emit('open-operators')">
              {{ i18n.global.t('growth.overview.allOperators') }}
              <n-icon :component="ArrowForwardOutline" :size="14" />
            </button>
          </div>
        </header>

        <div v-if="recommended.length" class="gp-overview__cards">
          <GrowthOperatorCard
            v-for="(card, index) in recommended"
            :key="card.operator.char_id"
            class="gp-rise"
            :style="{ '--gp-delay': index }"
            layout="compact"
            :operator="card.operator"
            :survey="card.survey"
            :planned="card.planned"
            :planned-count="card.plannedCount"
            :rank="index + 1"
            @open="(op) => emit('open-operator', op)"
          />
        </div>
        <div v-else class="gp-empty gp-overview__pick-empty">
          <p class="gp-empty__title">{{ i18n.global.t('growth.overview.noNewRecommendations') }}</p>
          <p class="gp-muted">
            {{ i18n.global.t('growth.overview.ownedOperatorsAreEitherAlreadyPlannedOr') }}
          </p>
          <div class="gp-empty__actions">
            <n-button size="small" @click="emit('open-operators')">{{
              i18n.global.t('growth.overview.viewAllOperators')
            }}</n-button>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.gp-overview {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.gp-overview__top {
  display: grid;
  grid-template-columns: minmax(0, 1.5fr) minmax(320px, 1fr);
  gap: 16px;
  align-items: stretch;
}

.gp-overview__bottom {
  display: grid;
  grid-template-columns: minmax(240px, 0.85fr) minmax(0, 2.15fr);
  gap: 16px;
  align-items: stretch;
}

.gp-overview__queue {
  display: flex;
  flex-direction: column;
  min-height: 420px;
}

.gp-queue {
  display: flex;
  flex-direction: column;
  gap: 2px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.gp-queue__row {
  display: flex;
  align-items: center;
  gap: 12px;
  min-height: 62px;
  padding: 8px 6px;
  border-radius: 10px;
  transition: background 160ms var(--gp-ease);
}

.gp-queue__row:hover {
  background: var(--gp-surface-2);
}

.gp-queue__index {
  flex: none;
  width: 22px;
  color: var(--gp-faint);
  font-size: 10.5px;
}

.gp-queue__avatar {
  display: block;
  width: 38px;
  height: 38px;
  flex: none;
  overflow: hidden;
  border-radius: 9px;
  background: var(--gp-surface-3);
  box-shadow: inset 0 0 0 1px var(--gp-hair-soft);
}

.gp-queue__avatar img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  object-position: 50% 22%;
}

.gp-queue__text {
  display: flex;
  flex: 1;
  min-width: 0;
  flex-direction: column;
  gap: 2px;
}

.gp-queue__text b {
  overflow: hidden;
  font-size: 13.5px;
  font-weight: 700;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.gp-queue__label {
  overflow: hidden;
  color: var(--gp-muted);
  font-size: 11.5px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.gp-overview__stamp {
  flex: none;
  font-size: 9.5px;
}

.gp-overview__status {
  flex: none;
  color: var(--gp-faint);
  font-size: 10.5px;
}

.gp-overview__status.is-signal {
  color: var(--gp-signal);
}

.gp-overview__status.is-warn {
  color: var(--gp-warn);
}

.gp-overview__empty {
  flex: 1;
  justify-content: center;
}

.gp-overview__queue-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-top: auto;
  padding-top: 14px;
  border-top: 1px solid var(--gp-hair-soft);
  font-size: 11.5px;
}

.gp-overview__materials {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.gp-overview__materials-head {
  margin-bottom: 10px;
}

.gp-overview__loading {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.gp-overview__material-error {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  color: var(--gp-signal);
  font-size: 12px;
}

.gp-overview__material-error p {
  margin: 0;
}

.gp-overview__material-empty {
  padding: 12px 0 4px;
  font-size: 12px;
}

.gp-overview__readiness {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 12px;
}

.gp-overview__readiness-value {
  font-size: 54px;
  line-height: 0.9;
  color: var(--gp-ink);
}

.gp-overview__readiness-value small {
  margin-left: 2px;
  color: var(--gp-muted);
  font-size: 20px;
  font-weight: 600;
}

.gp-overview__readiness-meta {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 2px;
  color: var(--gp-muted);
  font-size: 11px;
}

.gp-overview__meter {
  margin: 12px 0 14px;
  height: 7px;
}

.gp-overview__material-stats {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
  margin: 0;
}

.gp-overview__material-stats dt {
  color: var(--gp-faint);
  font-size: 10.5px;
}

.gp-overview__material-stats dd {
  margin: 2px 0 0;
  font-size: 14px;
  font-weight: 700;
}

.gp-overview__material-stats dd.is-signal {
  color: var(--gp-signal);
}

.gp-overview__missing {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 12px;
  padding: 9px 10px;
  border-radius: 10px;
  background: var(--gp-surface-2);
}

.gp-overview__missing-item {
  display: inline-flex;
  align-items: center;
  gap: 3px;
}

.gp-overview__missing-item img {
  width: 28px;
  height: 28px;
  object-fit: contain;
}

.gp-overview__missing-item span {
  color: var(--gp-muted);
  font-size: 10px;
}

.gp-overview__resources {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-top: 8px;
  padding: 7px 10px;
  border-radius: 10px;
  background: var(--gp-signal-block);
}

.gp-overview__resources-label {
  color: var(--gp-signal);
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.04em;
}

.gp-overview__resource {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: var(--gp-signal);
  font-size: 10.5px;
}

.gp-overview__resource img {
  width: 20px;
  height: 20px;
  object-fit: contain;
}

.gp-overview__material-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-top: auto;
  padding-top: 14px;
}

.gp-overview__material-actions .gp-link {
  font-size: 11.5px;
}

.gp-overview__workshop {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid var(--gp-hair-soft);
}

.gp-overview__workshop :deep(.n-space) {
  font-size: 11px;
  margin-top: 0 !important;
}

.gp-overview__workshop :deep(.n-text) {
  font-size: 11px;
}

.gp-overview__roster {
  display: flex;
  flex-direction: column;
}

.gp-overview__roster-head {
  margin-bottom: 12px;
}

.gp-overview__roster-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 14px 10px;
  margin: 0;
}

.gp-overview__roster-grid dt {
  color: var(--gp-faint);
  font-size: 10.5px;
}

.gp-overview__roster-grid dd {
  margin: 4px 0 0;
  font-size: 30px;
  color: var(--gp-ink);
}

.gp-overview__roster-meter {
  margin-top: 18px;
}

.gp-overview__roster-meter-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
  color: var(--gp-muted);
  font-size: 10.5px;
}

.gp-overview__roster-meter-head .gp-mono {
  color: var(--gp-ink-2);
  font-weight: 700;
}

.gp-overview__roster-meter .gp-meter {
  height: 6px;
}

.gp-overview__roster-note {
  margin: auto 0 0;
  padding-top: 12px;
  color: var(--gp-faint);
  font-size: 10.5px;
  line-height: 1.5;
}

.gp-overview__pick {
  display: flex;
  flex-direction: column;
}

.gp-overview__pick-head {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.gp-overview__pick-sub {
  margin: 0;
  color: var(--gp-muted);
  font-size: 11.5px;
}

.gp-overview__pick-actions {
  display: flex;
  flex: none;
  align-items: center;
  gap: 10px;
}

.gp-overview__pick-sort {
  width: 148px;
}

.gp-overview__cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 10px;
}

.gp-overview__pick-empty {
  margin-top: 4px;
}

@media (max-width: 1080px) {
  .gp-overview__top,
  .gp-overview__bottom {
    grid-template-columns: 1fr;
  }
  .gp-overview__queue {
    min-height: 0;
  }
}

@media (max-width: 720px) {
  .gp-overview__cards {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .gp-overview__readiness-value {
    font-size: 44px;
  }
  .gp-overview__roster-grid dd {
    font-size: 24px;
  }
}
</style>
