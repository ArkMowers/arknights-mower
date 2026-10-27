<script setup>
import { i18n } from '@/i18n'
import { computed } from 'vue'
import { NButton, NIcon } from 'naive-ui'
import RefreshOutline from '@vicons/ionicons5/es/RefreshOutline'
import OpenOutline from '@vicons/ionicons5/es/OpenOutline'
import OperatorStatistics from '@/components/OperatorStatistics.vue'
import { formatCompactNumber } from './growthFormatters'

const props = defineProps({
  statistics: { type: Object, default: null },
  history: { type: Array, default: () => [] },
  survey: { type: Object, default: () => ({ operators: [] }) },
  operatorCount: { type: Number, default: 0 },
  surveyLoading: Boolean
})
const emit = defineEmits(['refresh-survey'])

const surveyCoverage = computed(
  () => (props.survey?.operators || []).filter((row) => row.own > 0).length
)
const fetchedAt = computed(() => {
  const stamp = props.survey?.fetched_at
  if (!stamp) return i18n.global.t('growth.insights.notFetched')
  return new Date(stamp * 1000).toLocaleString(i18n.global.locale.value, {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  })
})
const surveyNote = computed(() => {
  if (props.survey?.error)
    return (
      i18n.global.t('growth.insights.publicSamplesAreTemporarilyUnavailable') + props.survey.error
    )
  if (!surveyCoverage.value)
    return i18n.global.t('growth.insights.noPublicSamplesAreAvailableYetOperator')
  return i18n.global.t('growth.format.surveyNote', {
    count: formatCompactNumber(surveyCoverage.value),
    time: fetchedAt.value
  })
})
</script>

<template>
  <div class="growth-insights">
    <section class="gp-panel growth-insights__stats">
      <header class="gp-section-head">
        <div>
          <span class="gp-kicker">{{ i18n.global.t('growth.format.localArchive') }}</span>
          <h2 class="gp-section-head__title">
            {{ i18n.global.t('growth.insights.growthStatistics') }}
          </h2>
        </div>
        <span class="gp-muted growth-insights__hint">{{
          i18n.global.t('growth.insights.statisticsUseLocallySynchronizedProgression')
        }}</span>
      </header>
      <OperatorStatistics v-if="statistics" :statistics="statistics" :history="history" />
      <div v-else class="gp-empty">
        <p class="gp-empty__title">
          {{ i18n.global.t('growth.insights.noProgressionDataToAnalyzeYet') }}
        </p>
        <p class="gp-muted">
          {{ i18n.global.t('growth.insights.syncOperatorDataFromSklandToView') }}
        </p>
      </div>
    </section>

    <section class="gp-panel growth-insights__survey">
      <header class="gp-section-head">
        <div>
          <span class="gp-kicker">{{ i18n.global.t('growth.format.publicSample') }}</span>
          <h2 class="gp-section-head__title">
            {{ i18n.global.t('growth.insights.publicSurveySamples') }}
          </h2>
        </div>
        <n-button size="small" quaternary :loading="surveyLoading" @click="emit('refresh-survey')">
          <template #icon><n-icon :component="RefreshOutline" /></template>
          {{ i18n.global.t('growth.insights.reload') }}
        </n-button>
      </header>
      <div class="growth-insights__survey-body">
        <div class="growth-insights__survey-metric">
          <strong class="gp-num">{{ surveyCoverage }}</strong>
          <span>{{ i18n.global.t('growth.insights.operatorsWithPublicSamples') }}</span>
        </div>
        <p class="growth-insights__survey-note">{{ surveyNote }}</p>
        <p class="growth-insights__survey-legal">
          {{ i18n.global.t('growth.insights.useRatesToFindGrowthGoalsNot') }}
          <a
            href="https://ark.yituliu.cn/survey/operators"
            target="_blank"
            rel="noopener noreferrer"
            >{{ i18n.global.t('growth.insights.arknightsYituliu') }}<sup>↗</sup></a
          >{{ i18n.global.t('growth.insights.licensedUnder') }}
          <a
            href="https://creativecommons.org/licenses/by-nc/4.0/deed.zh"
            target="_blank"
            rel="noopener noreferrer"
            >CC BY-NC 4.0<sup>↗</sup></a
          >{{ i18n.global.t('growth.insights.withAttributionForNoncommercialUseMowerImplements') }}
        </p>
        <a
          class="gp-link growth-insights__survey-link"
          href="https://ark.yituliu.cn/survey/operators"
          target="_blank"
          rel="noopener noreferrer"
        >
          {{ i18n.global.t('growth.insights.viewDataSource') }}
          <n-icon :component="OpenOutline" :size="13" />
        </a>
      </div>
    </section>
  </div>
</template>

<style scoped>
.growth-insights {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.growth-insights__stats {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.growth-insights__hint {
  font-size: 11.5px;
}

.growth-insights__survey-body {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.growth-insights__survey-metric {
  display: flex;
  align-items: baseline;
  gap: 10px;
}

.growth-insights__survey-metric strong {
  font-size: 44px;
  line-height: 0.9;
}

.growth-insights__survey-metric span {
  color: var(--gp-muted);
  font-size: 12px;
}

.growth-insights__survey-note {
  margin: 0;
  color: var(--gp-ink-2);
  font-size: 13px;
}

.growth-insights__survey-legal {
  margin: 0;
  max-width: 70ch;
  color: var(--gp-faint);
  font-size: 11.5px;
  line-height: 1.75;
}

.growth-insights__survey-legal a {
  color: var(--gp-muted);
  text-decoration: underline;
  text-underline-offset: 3px;
}

.growth-insights__survey-link {
  align-self: flex-start;
  font-size: 12px;
}
</style>
