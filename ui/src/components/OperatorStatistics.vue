<template>
  <section v-if="statistics" class="operator-statistics">
    <div class="stat-toolbar">
      <div class="stat-toolbar__title">
        <h3>{{ t('reports.localRoster') }}</h3>
        <p>
          {{ t('reports.syncedPrefix') }}{{ format(totals.owned)
          }}{{ t('reports.operatorsRaritySuffix') }}
        </p>
      </div>
      <n-checkbox-group v-model:value="rarities">
        <n-space :size="12">
          <n-checkbox
            v-for="rarity in [6, 5, 4, 3, 2, 1]"
            :key="rarity"
            :value="rarity"
            :label="t('reports.rarityStars', { count: rarity })"
          />
        </n-space>
      </n-checkbox-group>
    </div>

    <n-tabs type="line" animated class="stat-tabs">
      <n-tab-pane name="roster" :tab="t('reports.operatorStatistics')">
        <div class="stat-kpis">
          <div class="stat-kpi">
            <span>{{ t('reports.recruited') }}</span>
            <strong class="gp-num"
              >{{ format(totals.owned) }}<small>/ {{ format(totals.available) }}</small></strong
            >
            <em
              >{{ t('reports.raritiesIncludedPrefix') }}{{ rarities.length
              }}{{ t('reports.raritiesIncludedSuffix') }}</em
            >
          </div>
          <div class="stat-kpi">
            <span>{{ t('reports.elite2Operators') }}</span>
            <strong class="gp-num"
              >{{ format(totals.elite2)
              }}<small>{{ percent(totals.elite2, totals.owned) }}</small></strong
            >
            <em>{{ t('reports.ofRecruited') }}</em>
          </div>
          <div class="stat-kpi">
            <span>{{ t('reports.mastery3Skills') }}</span>
            <strong class="gp-num">{{ format(totals.skills[3]) }}</strong>
            <em>{{ t('reports.mastery3Only') }}</em>
          </div>
          <div class="stat-kpi">
            <span>{{ t('reports.unlockedModules') }}</span>
            <strong class="gp-num">{{ format(openedModules) }}</strong>
            <em>{{ t('reports.byUnlockedCount') }}</em>
          </div>
        </div>

        <div class="stat-table">
          <n-data-table
            :columns="rosterColumns"
            :data="rosterRows"
            :bordered="false"
            :single-line="false"
            :scroll-x="1240"
            :row-key="(row) => row.key"
            size="small"
          />
        </div>

        <details class="stat-notes">
          <summary>{{ t('reports.statisticsScope') }}</summary>
          <p>{{ t('reports.recruitmentScopeHelp') }}</p>
          <p>{{ t('reports.developmentScopeHelp') }}</p>
        </details>

        <div v-if="historyChart.series.length" class="stat-history">
          <div class="stat-history__head">
            <h4>{{ t('reports.cachedGrowthTrends') }}</h4>
            <p>{{ t('reports.historicalGrowthHelp') }}</p>
          </div>
          <v-chart :option="historyChart" autoresize style="height: 260px" />
        </div>
        <p v-else-if="history.length > 1" class="stat-empty">{{ t('reports.noGrowthHistory') }}</p>
      </n-tab-pane>

      <n-tab-pane name="materials" :tab="t('reports.materialConsumption')">
        <div class="stat-resource">
          <div class="stat-resource__hero">
            <span>{{ t('reports.totalSanitySpent') }}</span>
            <strong class="gp-num">≈ {{ format(totals.sanity) }}</strong>
            <em
              >{{ t('reports.naturalRecoveryPrefix') }}{{ format(totals.sanity / 240, 1)
              }}{{ t('reports.days') }}</em
            >
          </div>
          <dl class="stat-resource__grid">
            <div>
              <dt>{{ t('reports.lmd') }}</dt>
              <dd class="gp-mono">{{ format(totals.consumed_lmd) }}</dd>
            </div>
            <div>
              <dt>{{ t('reports.battleRecordExp') }}</dt>
              <dd class="gp-mono">{{ format(totals.consumed_exp) }}</dd>
            </div>
            <div>
              <dt>{{ t('reports.moduleDataBlocks') }}</dt>
              <dd class="gp-mono">{{ format(totals.module_blocks) }}</dd>
            </div>
            <div>
              <dt>{{ t('reports.skillSummary3Equivalent') }}</dt>
              <dd class="gp-mono">{{ format(totals.skill_book_equivalent, 2) }}</dd>
            </div>
          </dl>
        </div>

        <details class="stat-notes">
          <summary>{{ t('reports.valuationSources') }}</summary>
          <p>{{ t('reports.consumptionScopeHelp') }}</p>
          <p>
            {{ t('reports.valuationSettingsPrefix') }}{{ statistics.source?.source
            }}{{ t('reports.valuationSettingsSuffix') }}
          </p>
          <p>
            <a :href="statistics.source?.algorithm_url" target="_blank" rel="noopener noreferrer">{{
              t('reports.itemValuationAlgorithm')
            }}</a>
            ·
            <a :href="statistics.source?.values_url" target="_blank" rel="noopener noreferrer">{{
              t('reports.yituliuValues')
            }}</a>
          </p>
        </details>

        <n-alert
          v-if="unpricedNames.length || totals.incomplete.length"
          type="info"
          :show-icon="false"
          class="stat-coverage"
        >
          <div v-if="unpricedNames.length">
            {{ t('reports.unpricedPrefix') }}{{ unpricedNames.join('、')
            }}{{ t('reports.knownPricesOnlySuffix') }}
          </div>
          <div v-if="totals.incomplete.length">
            {{ t('reports.incompleteGrowthDataPrefix') }}{{ totals.incomplete.join('、') }}。
          </div>
        </n-alert>

        <div class="stat-table-toolbar">
          <span class="gp-muted"
            >{{ filteredMaterials.length }}{{ t('reports.consumedResourcesUnit') }}</span
          >
          <n-input
            v-model:value="materialQuery"
            clearable
            :placeholder="t('reports.searchMaterials')"
            size="small"
            class="stat-search"
          />
        </div>
        <div class="stat-table">
          <n-data-table
            :columns="materialColumns"
            :data="filteredMaterials"
            :pagination="{ pageSize: 12 }"
            :bordered="false"
            :row-key="(row) => row.id"
            :scroll-x="620"
            size="small"
          />
        </div>
      </n-tab-pane>

      <n-tab-pane name="ranking" :tab="t('reports.sanityRanking')">
        <p class="stat-lead">{{ t('reports.rankingHelp') }}</p>
        <div class="stat-podium">
          <div
            v-for="(row, index) in totals.ranking.slice(0, 3)"
            :key="row.char_id"
            class="stat-podium__item"
          >
            <span class="stat-podium__rank gp-num">{{ String(index + 1).padStart(2, '0') }}</span>
            <img
              class="stat-podium__avatar"
              :src="'/avatar/' + encodeURIComponent(row.name) + '.webp'"
              :alt="operatorDisplayName(row.name)"
              loading="lazy"
              @error="(event) => (event.target.style.display = 'none')"
            />
            <div>
              <strong>{{ operatorDisplayName(row.name) }}</strong>
              <span
                >{{ row.rarity }}{{ t('reports.starsSanitySeparator') }}{{ format(row.sanity)
                }}{{ t('reports.sanityUnit') }}</span
              >
            </div>
          </div>
          <n-empty v-if="!totals.ranking.length" :description="t('reports.noSelectedRarities')" />
        </div>
        <details class="stat-ranking">
          <summary>
            {{ t('reports.viewFullRankingPrefix') }}{{ totals.ranking.length
            }}{{ t('reports.operatorsClosingSuffix') }}
          </summary>
          <div class="stat-table-toolbar">
            <span class="gp-muted">{{ t('reports.syncedDevelopmentBasis') }}</span>
            <n-input
              v-model:value="operatorQuery"
              clearable
              :placeholder="t('reports.searchOperators')"
              size="small"
              class="stat-search"
            />
          </div>
          <div class="stat-table">
            <n-data-table
              :columns="rankingColumns"
              :data="filteredRanking"
              :pagination="{ pageSize: 10 }"
              :bordered="false"
              :row-key="(row) => row.char_id"
              :scroll-x="600"
              size="small"
            />
          </div>
        </details>
      </n-tab-pane>
    </n-tabs>
  </section>
</template>

<script setup>
import { i18n } from '@/i18n'
import { itemDisplayName, operatorDisplayName } from '@/i18n/gameNames'
const { t } = i18n.global
import { computed, h, ref } from 'vue'
import { useThemeVars } from 'naive-ui'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { LineChart } from 'echarts/charts'
import { CanvasRenderer } from 'echarts/renderers'
import { GridComponent, TooltipComponent, LegendComponent } from 'echarts/components'
import { personalStatisticsRows, sumPersonalStatistics } from '@/utils/operatorStatistics'
import { growthMetrics, growthHistoryPoints } from '@/utils/growthPlanning'
import { materialIcon } from '@/growth/growthFormatters'

use([LineChart, CanvasRenderer, GridComponent, TooltipComponent, LegendComponent])
const props = defineProps({ statistics: Object, history: { type: Array, default: () => [] } })
const theme = useThemeVars()
const rarities = ref([6, 5, 4, 3, 2, 1])
const materialQuery = ref('')
const operatorQuery = ref('')
const totals = computed(() => sumPersonalStatistics(props.statistics, rarities.value))
const rosterRows = computed(() => personalStatisticsRows(props.statistics, rarities.value))
const openedModules = computed(() =>
  [1, 2, 3].reduce((sum, level) => sum + totals.value.modules[level], 0)
)
const unpricedNames = computed(() =>
  totals.value.materials
    .filter((row) => row.sanity === null)
    .map((row) => itemDisplayName(row.id, row.name))
)
const filteredMaterials = computed(() =>
  totals.value.materials.filter(
    (row) =>
      row.name.includes(materialQuery.value.trim()) ||
      itemDisplayName(row.id, row.name)
        .toLowerCase()
        .includes(materialQuery.value.trim().toLowerCase()) ||
      row.id.includes(materialQuery.value.trim())
  )
)
const filteredRanking = computed(() =>
  totals.value.ranking
    .map((row, index) => ({ ...row, position: index + 1 }))
    .filter(
      (row) =>
        row.name.includes(operatorQuery.value.trim()) ||
        operatorDisplayName(row.name)
          .toLowerCase()
          .includes(operatorQuery.value.trim().toLowerCase())
    )
)
const format = (value, decimals = 0) =>
  Number(value || 0).toLocaleString(i18n.global.locale.value, { maximumFractionDigits: decimals })
const percent = (count, all) => `${all ? ((count / all) * 100).toFixed(1) : 0}%`
const numberColumn = (title, key, notApplicable = () => false) => ({
  title,
  key,
  align: 'right',
  render: (row) => (notApplicable(row) ? '—' : format(row[key]))
})
const rosterColumns = computed(() => [
  { title: t('reports.rarity'), key: 'label', fixed: 'left', width: 88 },
  {
    title: t('reports.ownedAvailable'),
    key: 'owned',
    width: 140,
    render: (row) => `${format(row.owned)} / ${format(row.available)}`
  },
  numberColumn(t('reports.elite2'), 'elite2', (row) => row.max_phase < 2),
  numberColumn(t('reports.maxDevelopment'), 'max_level'),
  {
    ...numberColumn(
      t('reports.moduleUnlockLevel'),
      'module_level',
      (row) => row.supports_modules === false
    ),
    width: 160
  },
  {
    title: t('reports.masterySkills'),
    key: 'skills',
    children: [1, 2, 3].map((level) => ({
      title: t('reports.masteryLevel', { level }),
      key: `skills.${level}`,
      align: 'right',
      render: (row) => (row.supports_mastery === false ? '—' : format(row.skills?.[level]))
    }))
  },
  {
    title: t('reports.moduleCounts'),
    key: 'modules',
    children: [1, 2, 3].map((level) => ({
      title: t('reports.levelNumber', { level }),
      key: `modules.${level}`,
      align: 'right',
      render: (row) => (row.supports_modules === false ? '—' : format(row.modules?.[level]))
    }))
  }
])
// 数据表列由 n-data-table 渲染，拿不到本组件的 scoped 属性，尺寸与布局用行内样式。
const assetIcon = (src, kind) =>
  h('img', {
    src,
    alt: '',
    loading: 'lazy',
    class: kind === 'avatar' ? 'stat-asset__avatar' : 'stat-asset__icon',
    style:
      kind === 'avatar'
        ? 'width:24px;height:24px;flex:none;border-radius:999px;object-fit:cover;object-position:50% 22%;background:var(--gp-surface-2)'
        : 'width:22px;height:22px;flex:none;border-radius:6px;object-fit:contain;background:var(--gp-surface-2)',
    onError: (event) => {
      event.target.style.display = 'none'
    }
  })
const assetRow = (icon, name) =>
  h('div', { class: 'stat-asset', style: 'display:flex;align-items:center;gap:8px;min-width:0' }, [
    icon,
    h('span', name)
  ])
const materialColumns = computed(() => [
  {
    title: t('reports.resourceLabel'),
    key: 'name',
    minWidth: 170,
    render: (row) =>
      assetRow(assetIcon(materialIcon(row), 'icon'), itemDisplayName(row.id, row.name))
  },
  numberColumn(t('reports.cumulativeConsumption'), 'count'),
  {
    title: t('reports.itemSanityValue'),
    key: 'value',
    align: 'right',
    render: (row) => (row.value === null ? t('reports.unpriced') : format(row.value, 4))
  },
  {
    title: t('reports.totalEquivalentSanity'),
    key: 'sanity',
    align: 'right',
    render: (row) => (row.sanity === null ? t('reports.unpriced') : format(row.sanity, 1))
  }
])
const rankingColumns = computed(() => [
  { title: t('reports.rank'), key: 'position', width: 65 },
  {
    title: t('reports.operator'),
    key: 'name',
    minWidth: 160,
    render: (row) =>
      assetRow(
        assetIcon('/avatar/' + encodeURIComponent(row.name) + '.webp', 'avatar'),
        operatorDisplayName(row.name)
      )
  },
  { title: t('reports.rarity'), key: 'rarity', width: 65 },
  {
    title: t('reports.equivalentSanity'),
    key: 'sanity',
    align: 'right',
    render: (row) => `≈ ${format(row.sanity)}`
  },
  {
    title: t('reports.coverage'),
    key: 'coverage',
    render: (row) =>
      row.incomplete
        ? t('reports.incompleteDevelopment')
        : row.unpriced.length
          ? t('reports.containsUnpriced')
          : t('reports.priced')
  }
])
const historyChart = computed(() => ({
  color: [
    theme.value.primaryColor,
    theme.value.errorColor,
    theme.value.infoColor,
    theme.value.warningColor,
    theme.value.textColor3,
    theme.value.textColor2
  ],
  tooltip: { trigger: 'axis' },
  legend: {
    top: 0,
    left: 0,
    itemWidth: 12,
    itemHeight: 6,
    itemGap: 14,
    textStyle: { color: theme.value.textColor2, fontSize: 10 }
  },
  grid: { left: 40, right: 76, bottom: 28, top: 52 },
  xAxis: { type: 'time', axisLabel: { color: theme.value.textColor3 } },
  yAxis: [
    {
      type: 'value',
      minInterval: 1,
      axisLabel: { color: theme.value.textColor3 },
      splitLine: { lineStyle: { color: theme.value.dividerColor } }
    },
    {
      type: 'value',
      name: t('reports.equivalentSanity'),
      position: 'right',
      axisLabel: { color: theme.value.textColor3 },
      splitLine: { show: false }
    }
  ],
  series: growthMetrics
    .filter(({ key }) => growthHistoryPoints(props.history, rarities.value, key).length > 1)
    .map(({ key, label }) => ({
      name: label,
      type: 'line',
      showSymbol: false,
      yAxisIndex: key === 'sanity_value' ? 1 : 0,
      data: growthHistoryPoints(props.history, rarities.value, key)
    }))
}))
</script>

<style scoped>
.operator-statistics {
  display: flex;
  flex-direction: column;
  gap: 14px;
  color: inherit;
  --stat-line: var(--gp-hair-soft);
  --stat-muted: var(--gp-muted);
}

.stat-toolbar {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
}

.stat-toolbar__title h3 {
  margin: 0;
  font-size: 15px;
  font-weight: 700;
}

.stat-toolbar__title p {
  margin: 3px 0 0;
  color: var(--stat-muted);
  font-size: 11.5px;
}

.stat-tabs :deep(.n-tabs-nav) {
  margin-bottom: 4px;
}

.stat-tabs :deep(.n-tabs-tab) {
  margin-right: 20px;
  padding: 6px 1px;
  color: var(--gp-muted);
  font-size: 13px;
  font-weight: 650;
}

.stat-tabs :deep(.n-tabs-tab--active) {
  color: var(--gp-ink);
}

.stat-tabs :deep(.n-tabs-bar) {
  height: 2px;
  background: var(--gp-ink);
}

.stat-kpis {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 10px;
  padding: 4px 0 14px;
}

.stat-kpi {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 12px 14px;
  border-radius: 12px;
  background: var(--gp-surface-2);
}

.stat-kpi span {
  color: var(--stat-muted);
  font-size: 10.5px;
}

.stat-kpi strong {
  color: var(--gp-ink);
  font-size: 32px;
}

.stat-kpi strong small {
  margin-left: 4px;
  color: var(--stat-muted);
  font-size: 12px;
  font-weight: 500;
}

.stat-kpi em {
  color: var(--gp-faint);
  font-size: 10px;
  font-style: normal;
}

.stat-table {
  border-radius: 12px;
  overflow: hidden;
}

.stat-table :deep(.n-data-table-th) {
  font-size: 11px;
  font-weight: 600;
}

.stat-table :deep(.n-data-table-td) {
  font-size: 11.5px;
}

.stat-asset {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.stat-asset__icon {
  width: 22px;
  height: 22px;
  flex: none;
  border-radius: 6px;
  object-fit: contain;
  background: var(--gp-surface-2);
}

.stat-asset__avatar {
  width: 24px;
  height: 24px;
  flex: none;
  border-radius: 999px;
  object-fit: cover;
  object-position: 50% 22%;
  background: var(--gp-surface-2);
}

.stat-notes {
  margin-top: 12px;
  padding-top: 10px;
  border-top: 1px solid var(--stat-line);
}

.stat-notes > summary {
  color: var(--stat-muted);
  font-size: 11.5px;
  font-weight: 600;
  cursor: pointer;
}

.stat-notes p {
  margin: 8px 0 0;
  color: var(--stat-muted);
  font-size: 11px;
  line-height: 1.7;
}

.stat-notes a {
  color: inherit;
  text-decoration: underline;
  text-underline-offset: 3px;
}

.stat-history {
  margin-top: 16px;
  padding-top: 12px;
  border-top: 1px solid var(--stat-line);
}

.stat-history__head h4 {
  margin: 0;
  font-size: 12.5px;
  font-weight: 700;
}

.stat-history__head p {
  margin: 3px 0 8px;
  color: var(--stat-muted);
  font-size: 10.5px;
}

.stat-empty {
  margin: 12px 0 0;
  color: var(--stat-muted);
  font-size: 11px;
}

.stat-resource {
  display: grid;
  grid-template-columns: 1fr 1.4fr;
  gap: 20px;
  padding: 16px;
  border-radius: 14px;
  background: var(--gp-surface-2);
}

.stat-resource__hero {
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.stat-resource__hero span {
  color: var(--stat-muted);
  font-size: 10.5px;
}

.stat-resource__hero strong {
  color: var(--gp-ink);
  font-size: 38px;
}

.stat-resource__hero em {
  color: var(--gp-faint);
  font-size: 10.5px;
  font-style: normal;
}

.stat-resource__grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px 20px;
  margin: 0;
  align-content: center;
}

.stat-resource__grid dt {
  color: var(--stat-muted);
  font-size: 10.5px;
}

.stat-resource__grid dd {
  margin: 3px 0 0;
  color: var(--gp-ink);
  font-size: 18px;
  font-weight: 700;
}

.stat-coverage {
  margin-top: 12px;
  font-size: 11px;
}

.stat-table-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  margin: 12px 0 8px;
  font-size: 11px;
}

.stat-search {
  width: 200px;
}

.stat-lead {
  margin: 4px 0 14px;
  color: var(--stat-muted);
  font-size: 11.5px;
  line-height: 1.6;
}

.stat-podium {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 10px;
}

.stat-podium__item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px;
  border-radius: 12px;
  background: var(--gp-surface-2);
}

.stat-podium__rank {
  color: var(--gp-surface-3);
  font-size: 30px;
  line-height: 1;
}

.stat-podium__avatar {
  width: 40px;
  height: 40px;
  flex: none;
  border-radius: 12px;
  object-fit: cover;
  object-position: 50% 22%;
  background: var(--gp-surface-3);
}

.stat-podium__item strong {
  display: block;
  font-size: 13px;
}

.stat-podium__item span:not(.stat-podium__rank) {
  display: block;
  margin-top: 3px;
  color: var(--stat-muted);
  font-size: 10.5px;
}

.stat-ranking {
  margin-top: 16px;
}

.stat-ranking > summary {
  color: var(--stat-muted);
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
}

@media (max-width: 860px) {
  .stat-kpis {
    grid-template-columns: repeat(2, 1fr);
  }
  .stat-resource {
    grid-template-columns: 1fr;
  }
  .stat-podium {
    grid-template-columns: 1fr;
  }
  .stat-search {
    width: 140px;
  }
}
</style>
