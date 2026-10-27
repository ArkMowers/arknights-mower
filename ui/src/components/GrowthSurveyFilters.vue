<template>
  <section class="survey">
    <header class="survey__head">
      <div>
        <h4 class="survey__title">{{ i18n.global.t('growth.survey.surveyFilters') }}</h4>
        <p class="survey__coverage">
          {{ coverageText }}
        </p>
      </div>
      <n-button size="tiny" quaternary :loading="loading" @click="$emit('refresh')">
        {{ i18n.global.t('growth.survey.loadStatistics') }}
      </n-button>
    </header>

    <n-alert v-if="survey.error" type="warning" :bordered="false" class="survey__alert">
      {{ survey.error }}
      <template v-if="survey.retry_after">
        {{ i18n.global.t('growth.survey.nextRetryAt')
        }}{{ new Date(survey.retry_after * 1000).toLocaleTimeString() }}。
      </template>
    </n-alert>

    <div class="survey__rows">
      <div v-for="dimension in surveyDimensions" :key="dimension.key" class="survey__row">
        <n-tooltip>
          <template #trigger
            ><span class="survey__label">{{ dimension.label }}</span></template
          >
          {{ dimension.detail
          }}{{ i18n.global.t('growth.survey.theDenominatorIsSampleParticipantsWhoOwn') }}
        </n-tooltip>
        <div
          class="survey__rail"
          role="group"
          :aria-label="dimension.label + i18n.global.t('growth.survey.threshold')"
        >
          <button
            v-for="rate in surveyThresholds"
            :key="rate"
            type="button"
            class="survey__node"
            :class="{ 'is-active': modelValue[dimension.key] === rate }"
            :disabled="!hasSamples"
            :aria-pressed="modelValue[dimension.key] === rate"
            :aria-label="dimension.label + i18n.global.t('growth.survey.atLeast') + rate + '%'"
            @click="updateRate(dimension.key, rate)"
          >
            {{ rate }}
          </button>
        </div>
        <button
          type="button"
          class="survey__clear"
          :class="{ 'is-active': modelValue[dimension.key] === null }"
          :disabled="!hasSamples"
          @click="update(dimension.key, null)"
        >
          {{ i18n.global.t('growth.survey.any') }}
        </button>
      </div>
    </div>

    <div class="survey__foot">
      <n-checkbox
        :checked="modelValue.hideCompleted"
        :disabled="!hasSamples"
        @update:checked="update('hideCompleted', $event)"
      >
        {{ i18n.global.t('growth.survey.hideOperatorsAlreadyMeetingGoals') }}
      </n-checkbox>
      <n-select
        :value="modelValue.sort"
        :options="sortOptions"
        size="small"
        class="survey__sort"
        :aria-label="i18n.global.t('growth.survey.sortOrder')"
        @update:value="update('sort', $event)"
      />
    </div>
    <slot />
    <p class="survey__source">
      {{ i18n.global.t('growth.survey.ratesUseTheDistributionAmongOwnersTo') }}
      <template v-if="survey.fetched_at">
        {{ i18n.global.t('growth.survey.fetchedAt') }}
        {{ new Date(survey.fetched_at * 1000).toLocaleString() }}。
      </template>
    </p>
  </section>
</template>

<script setup>
import { i18n } from '@/i18n'
import { computed } from 'vue'
import { NAlert, NButton, NCheckbox, NSelect, NTooltip } from 'naive-ui'
import { surveyDimensions, surveyThresholds } from '@/utils/growthSurvey'

const props = defineProps({
  modelValue: { type: Object, required: true },
  survey: { type: Object, required: true },
  loading: Boolean
})
const emit = defineEmits(['update:modelValue', 'refresh'])
const hasSamples = computed(() => props.survey.operators?.some((row) => row.own > 0))
const coverageText = computed(() => {
  const rows = props.survey.operators || []
  const known = rows.filter((row) => row.own > 0).length
  if (!known) return i18n.global.t('growth.survey.noPublicSamplesAvailable')
  return i18n.global.t('growth.format.surveyCoverage', { count: known })
})
function updateRate(key, rate) {
  update(key, props.modelValue[key] === rate ? null : rate)
}
const sortOptions = computed(() => [
  { label: i18n.global.t('growth.survey.defaultOrder'), value: 'default' },
  { label: i18n.global.t('growthUpdates.remainingMasteryFirst'), value: 'recommendation' },
  { label: i18n.global.t('growthUpdates.remainingModuleFirst'), value: 'module' },
  { label: i18n.global.t('growth.survey.highestLevelFirst'), value: 'level' }
])
function update(key, value) {
  emit('update:modelValue', { ...props.modelValue, [key]: value })
}
</script>

<style scoped>
.survey {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 16px;
  border-radius: 18px;
  background: var(--gp-surface);
}

.survey__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.survey__title {
  margin: 0;
  color: var(--gp-ink);
  font-size: 15px;
  font-weight: 700;
}

.survey__coverage {
  margin: 3px 0 0;
  color: var(--gp-muted);
  font-size: 11px;
}

.survey__alert {
  font-size: 11.5px;
}

.survey__rows {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.survey__row {
  display: grid;
  grid-template-columns: 82px minmax(0, 1fr) auto;
  align-items: center;
  gap: 10px;
}

.survey__label {
  color: var(--gp-ink-2);
  font-size: 11.5px;
  font-weight: 650;
  border-bottom: 1px dashed var(--gp-hair);
  cursor: help;
}

.survey__rail {
  display: grid;
  grid-template-columns: repeat(10, 1fr);
  gap: 2px;
  padding: 3px;
  border-radius: 8px;
  background: var(--gp-surface-2);
}

.survey__node {
  height: 26px;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: var(--gp-muted);
  font: inherit;
  font-family: var(--gp-mono);
  font-size: 10.5px;
  font-weight: 600;
  cursor: pointer;
  font-variant-numeric: tabular-nums;
  transition:
    background 140ms var(--gp-ease),
    color 140ms var(--gp-ease);
}

.survey__node:hover:not(:disabled) {
  background: var(--gp-surface-3);
  color: var(--gp-ink);
}

.survey__node.is-active {
  background: var(--gp-ink);
  color: var(--gp-page);
}

.survey__node:focus-visible {
  outline: 2px solid var(--gp-accent);
  outline-offset: 1px;
}

.survey__node:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.survey__clear {
  height: 26px;
  padding: 0 8px;
  border: 1px solid transparent;
  border-radius: 6px;
  background: transparent;
  color: var(--gp-muted);
  font: inherit;
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
}

.survey__clear.is-active {
  border-color: var(--gp-hair);
  color: var(--gp-ink);
}

.survey__foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  padding-top: 8px;
  border-top: 1px solid var(--gp-hair-soft);
}

.survey__sort {
  width: 150px;
}

.survey__source {
  margin: 0;
  color: var(--gp-faint);
  font-size: 10.5px;
  line-height: 1.6;
}

@media (max-width: 600px) {
  .survey__row {
    grid-template-columns: 1fr auto;
  }
  .survey__rail {
    grid-column: 1 / -1;
    grid-row: 2;
    overflow-x: auto;
  }
  .survey__node {
    min-width: 30px;
  }
}
</style>
