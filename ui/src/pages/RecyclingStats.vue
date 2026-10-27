<script setup>
import { i18n } from '@/i18n'
import { itemDisplayName, operatorDisplayName } from '@/i18n/gameNames'
import { reportErrorMessage } from '@/i18n/reports'
const { t } = i18n.global
import { computed, inject, onMounted, onUnmounted, reactive, ref } from 'vue'
import { storeToRefs } from 'pinia'
import { useConfigStore } from '@/stores/config'
import { useResolvedTheme } from '@/composables/theme'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { PieChart } from 'echarts/charts'
import { TooltipComponent } from 'echarts/components'
import VChart from 'vue-echarts'
import CubeOutline from '@vicons/ionicons5/es/CubeOutline'
import RefreshOutline from '@vicons/ionicons5/es/RefreshOutline'
import DownloadOutline from '@vicons/ionicons5/es/DownloadOutline'
import TimeOutline from '@vicons/ionicons5/es/TimeOutline'
import PersonOutline from '@vicons/ionicons5/es/PersonOutline'
import LeafOutline from '@vicons/ionicons5/es/LeafOutline'

use([CanvasRenderer, PieChart, TooltipComponent])
const axios = inject('axios')
const { theme: themePreference } = storeToRefs(useConfigStore())
const theme = useResolvedTheme(themePreference)
const today = new Date()
const since = new Date(today)
since.setDate(today.getDate() - 29)
const range = ref([since.getTime(), today.getTime()])
const page = ref(1)
const loading = ref(false)
const error = ref('')
const exporting = ref(false)
const exportError = ref('')
const retrying = ref('')
const retryError = ref('')
const emptyData = () => ({ total: 0, materials: [], qualities: [], records: [], comparison: null })
const data = ref(emptyData())
const failedIcons = reactive(new Set())
let requestVersion = 0
let refreshTimer
let refreshesRemaining = 0
let disposed = false
const uploadLabels = computed(() => ({
  submitted: t('reports.uploaded'),
  failed: t('reports.uploadFailed'),
  pending: t('reports.pendingUpload'),
  waiting: t('reports.pendingUpload'),
  skipped: t('reports.uploadSkipped')
}))
const quantity = computed(() => data.value.materials.reduce((sum, item) => sum + item.count, 0))
const comparison = computed(() => data.value.comparison)
const qualityLabels = computed(() => ({
  0: t('reports.unknownRarity'),
  2: t('reports.greenMaterials'),
  3: t('reports.blueMaterials'),
  4: t('reports.purpleMaterials'),
  5: t('reports.goldMaterials')
}))
const qualityColors = {
  0: '#8b98a6',
  2: '#79ae59',
  3: '#549bd4',
  4: '#a078d0',
  5: '#dcb153'
}
const materialRarities = computed(() =>
  Object.fromEntries(data.value.materials.map((item) => [item.name, item.rarity]))
)
const qualityRows = computed(() => {
  const expected = comparison.value?.qualities || []
  const rarities = new Set([
    ...data.value.qualities.map((row) => row.rarity),
    ...expected.map((row) => row.rarity)
  ])
  return [...rarities]
    .sort((a, b) => (a || 0) - (b || 0))
    .map((rarity) => ({
      rarity,
      count: data.value.qualities.find((row) => row.rarity === rarity)?.count || 0,
      probability: expected.find((row) => row.rarity === rarity)?.probability ?? null
    }))
})
const chart = computed(() => ({
  backgroundColor: 'transparent',
  animationDuration: 350,
  tooltip: {
    trigger: 'item',
    formatter: ({ name, value, percent }) => t('reports.qualityTooltip', { name, value, percent })
  },
  series: [
    {
      type: 'pie',
      radius: ['66%', '83%'],
      center: ['50%', '50%'],
      label: { show: false },
      itemStyle: {
        borderRadius: 6,
        borderWidth: 3,
        borderColor: theme.value === 'dark' ? '#252a2f' : '#ffffff'
      },
      emphasis: { scaleSize: 5 },
      data: data.value.qualities.map((row) => ({
        name: qualityLabels.value[row.rarity] || qualityLabels.value[0],
        value: row.count,
        itemStyle: { color: qualityColors[row.rarity] || qualityColors[0] }
      }))
    }
  ]
}))
function localDate(at) {
  const date = new Date(at)
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
}
function formatTime(at) {
  return new Date(at * 1000).toLocaleString(i18n.global.locale.value, { hour12: false })
}
function number(value, digits = 1) {
  return value == null
    ? '—'
    : value.toLocaleString(i18n.global.locale.value, {
        maximumFractionDigits: digits,
        minimumFractionDigits: digits
      })
}
function percent(value) {
  return value == null ? '—' : `${(value * 100).toFixed(2)}%`
}
function materialColor(name) {
  return qualityColors[materialRarities.value[name]] || qualityColors[0]
}
const differenceText = computed(() => {
  const value = comparison.value?.difference
  if (value == null || !comparison.value?.expected_sanity) return t('reports.waitingSamples')
  return t(value >= 0 ? 'reports.aboveExpected' : 'reports.belowExpected', {
    percent: percent(Math.abs(value) / comparison.value.expected_sanity)
  })
})
async function load(resetRefresh = true) {
  if (disposed) return
  clearTimeout(refreshTimer)
  if (resetRefresh) refreshesRemaining = 60
  const version = ++requestVersion
  loading.value = Boolean(resetRefresh)
  error.value = ''
  try {
    const response = await axios.get(`${import.meta.env.VITE_HTTP_URL}/report/recycling_history`, {
      params: {
        startDate: localDate(range.value[0]),
        endDate: localDate(range.value[1]),
        page: page.value
      }
    })
    if (version === requestVersion) {
      data.value = response.data
      if (
        refreshesRemaining > 0 &&
        data.value.records.some((row) => ['pending', 'waiting'].includes(row.upload_status))
      ) {
        refreshTimer = setTimeout(() => {
          refreshesRemaining--
          load(false)
        }, 2000)
      }
    }
  } catch {
    if (version === requestVersion) {
      if (resetRefresh) data.value = emptyData()
      error.value = t('reports.recyclingReadFailed')
    }
  } finally {
    if (version === requestVersion) loading.value = false
  }
}
async function retryUpload(row) {
  if (disposed || retrying.value || row.upload_status !== 'failed') return
  retrying.value = row.id
  retryError.value = ''
  try {
    await axios.post(
      `${import.meta.env.VITE_HTTP_URL}/report/recycling_history/${encodeURIComponent(row.id)}/retry`
    )
  } catch (error) {
    retryError.value = error.response?.data?.error || t('reports.retryUploadFailed')
  } finally {
    retrying.value = ''
    await load()
  }
}
function changeRange() {
  page.value = 1
  load()
}
async function exportExcel() {
  if (exporting.value) return
  exporting.value = true
  exportError.value = ''
  const startDate = localDate(range.value[0])
  const endDate = localDate(range.value[1])
  try {
    const response = await axios.get(
      `${import.meta.env.VITE_HTTP_URL}/report/recycling_history/export`,
      {
        params: { startDate, endDate },
        responseType: 'blob'
      }
    )
    const url = URL.createObjectURL(response.data)
    const link = document.createElement('a')
    try {
      link.href = url
      link.download = `${t('reports.recyclingTitle')}-${startDate}-${endDate}.xlsx`
      document.body.appendChild(link)
      link.click()
    } finally {
      link.remove()
      setTimeout(() => URL.revokeObjectURL(url), 1000)
    }
  } catch {
    exportError.value = t('reports.excelExportFailed')
  } finally {
    exporting.value = false
  }
}
onMounted(() => {
  load()
})
onUnmounted(() => {
  disposed = true
  requestVersion++
  clearTimeout(refreshTimer)
})
</script>

<template>
  <div class="recycling-page" :class="{ dark: theme === 'dark' }">
    <header class="page-heading">
      <div class="heading-copy">
        <div class="title-line">
          <span class="heading-icon"><n-icon :component="CubeOutline" /></span>
          <h1>{{ t('reports.recyclingTitle') }}</h1>
        </div>
        <p>{{ t('reports.recyclingSubtitle') }}</p>
      </div>
      <div class="filters">
        <n-date-picker
          v-model:value="range"
          type="daterange"
          :clearable="false"
          @update:value="changeRange"
        />
        <n-button secondary :loading="loading" class="refresh-button" @click="load"
          ><template #icon><n-icon :component="RefreshOutline" /></template
          >{{ t('reports.refresh') }}</n-button
        >
        <n-button
          secondary
          :loading="exporting"
          :disabled="loading"
          class="refresh-button"
          :title="t('reports.exportRecyclingHelp')"
          @click="exportExcel"
          ><template #icon><n-icon :component="DownloadOutline" /></template
          >{{ t('reports.exportExcel') }}</n-button
        >
      </div>
    </header>
    <n-alert v-if="error" type="error" class="notice">{{ reportErrorMessage(error) }}</n-alert>
    <n-alert v-if="exportError" type="error" class="notice">{{
      reportErrorMessage(exportError)
    }}</n-alert>
    <section class="valuation-panel valuation-source">
      <span>{{ comparison?.valuation?.source || t('reports.materialValuesUnread') }}</span>
      <SessionLink to="/settings#task-accounts">{{
        t('reports.manageMaterialValues')
      }}</SessionLink>
    </section>
    <n-alert
      v-if="comparison?.unknown_collections || comparison?.unknown_materials.length"
      type="warning"
      class="notice"
      >{{ t('reports.incompleteRecordsPrefix') }}{{ comparison.unknown_collections
      }}{{ t('reports.incompleteRecordsSuffix')
      }}<span v-if="comparison.unknown_materials.length"
        >{{ t('reports.unpricedMaterialsPrefix')
        }}{{ comparison.unknown_materials.map((name) => itemDisplayName(name)).join('、') }}</span
      >{{ t('reports.incompleteMaterialsHelp') }}</n-alert
    >
    <n-alert v-if="comparison?.unmodeled_materials?.length" type="warning" class="notice"
      >{{ t('reports.missingProbabilityPrefix')
      }}{{ comparison.unmodeled_materials.map((name) => itemDisplayName(name)).join('、')
      }}{{ t('reports.missingProbabilityHelp') }}</n-alert
    >
    <n-spin :show="loading">
      <div class="metrics">
        <section class="metric">
          <span class="metric-label">{{ t('reports.materialsObtained') }}</span>
          <div class="metric-value">
            {{ number(quantity, 0) }}<small>{{ t('reports.piecesUnit') }}</small>
          </div>
          <span class="metric-note">{{ data.total }}{{ t('reports.collectionsDateSuffix') }}</span>
        </section>
        <section class="metric">
          <span class="metric-label">{{ t('reports.totalSanityValue') }}</span>
          <div class="metric-value accent">
            {{ number(comparison?.actual_sanity) }}<small>{{ t('reports.sanityUnit') }}</small>
          </div>
          <span class="metric-note">{{ t('reports.actualValueHelp') }}</span>
        </section>
        <section class="metric">
          <span class="metric-label">{{ t('reports.expectedIncome') }}</span>
          <div class="metric-value">
            {{ number(comparison?.expected_sanity) }}<small>{{ t('reports.sanityUnit') }}</small>
          </div>
          <span class="metric-note">{{ t('reports.expectedIncomeHelp') }}</span>
        </section>
        <section class="metric">
          <span class="metric-label">{{ t('reports.expectationDifference') }}</span>
          <div class="metric-value" :class="{ accent: comparison?.difference > 0 }">
            {{ comparison?.difference > 0 ? '+' : '' }}{{ number(comparison?.difference)
            }}<small>{{ t('reports.sanityUnit') }}</small>
          </div>
          <span class="metric-note">{{ differenceText }}</span>
        </section>
      </div>
      <div class="statistics">
        <section class="surface history-panel">
          <div class="section-heading">
            <div>
              <h2>{{ t('reports.collectionDetails') }}</h2>
              <p>{{ t('reports.collectionDetailsHelp') }}</p>
            </div>
            <span class="count-badge">{{ data.total }}{{ t('reports.recordsUnit') }}</span>
          </div>
          <n-alert v-if="retryError" type="error" class="notice">{{
            reportErrorMessage(retryError)
          }}</n-alert>
          <n-scrollbar style="max-height: 600px" class="history">
            <n-empty
              v-if="!data.records.length"
              :description="t('reports.noCollections')"
              class="empty-state"
              ><template #icon><n-icon :component="CubeOutline" /></template
            ></n-empty>
            <article v-for="row in data.records" :key="row.id" class="collection">
              <div class="timeline-dot"></div>
              <div class="collection-body">
                <time><n-icon :component="TimeOutline" />{{ formatTime(row.collected_at) }}</time>
                <div class="operators">
                  <n-icon :component="PersonOutline" /><span class="operator-label">{{
                    t('reports.occupants')
                  }}</span
                  ><span v-if="row.operators === null" class="muted">{{
                    t('reports.unrecognized')
                  }}</span
                  ><span v-else-if="!row.operators.length" class="muted">{{
                    t('reports.noOccupants')
                  }}</span
                  ><span v-for="name in row.operators || []" :key="name" class="operator-name">{{
                    operatorDisplayName(name)
                  }}</span>
                </div>
                <div v-if="row.materials" class="materials">
                  <div
                    v-for="(count, name) in row.materials"
                    :key="name"
                    class="material-chip"
                    :style="{ '--quality': materialColor(name) }"
                  >
                    <div class="material-icon">
                      <img
                        v-if="!failedIcons.has(name)"
                        :src="`/depot/${encodeURIComponent(name)}.webp`"
                        :alt="itemDisplayName(name)"
                        loading="lazy"
                        @error="failedIcons.add(name)"
                      /><span v-else>◇</span>
                    </div>
                    <span>{{ itemDisplayName(name) }}</span
                    ><strong>× {{ count }}</strong>
                  </div>
                </div>
                <span v-else class="muted">{{ t('reports.materialsUnrecognized') }}</span>
                <div class="upload-state" aria-live="polite">
                  <span
                    :class="['upload-label', row.upload_status]"
                    :title="
                      row.upload_status === 'submitted'
                        ? t('reports.uploadSubmittedHelp')
                        : undefined
                    "
                    >{{ uploadLabels[row.upload_status] || t('reports.pendingUpload') }}</span
                  >
                  <n-button
                    v-if="row.upload_status === 'failed'"
                    size="tiny"
                    secondary
                    :loading="retrying === row.id"
                    :disabled="Boolean(retrying)"
                    @click="retryUpload(row)"
                    >{{ t('reports.retryUpload') }}</n-button
                  >
                </div>
              </div>
            </article>
          </n-scrollbar>
          <div v-if="data.total > 50" class="pagination">
            <n-pagination
              v-model:page="page"
              :item-count="data.total"
              :page-size="50"
              :page-slot="5"
              @update:page="load"
            />
          </div>
        </section>
        <div class="right-column">
          <section class="surface">
            <div class="section-heading">
              <div>
                <h2>{{ t('reports.materialRarityDistribution') }}</h2>
                <p>{{ t('reports.byMaterialCount') }}</p>
              </div>
              <n-icon :component="LeafOutline" class="section-icon" />
            </div>
            <div v-if="quantity" class="donut-wrap">
              <v-chart
                :option="chart"
                :theme="theme === 'dark' ? 'dark' : undefined"
                autoresize
                class="quality-chart"
              />
              <div class="donut-center">
                <strong>{{ number(quantity, 0) }}</strong
                ><span>{{ t('reports.materialTotal') }}</span>
              </div>
            </div>
            <n-empty
              v-else
              :description="t('reports.waitingFirstCollection')"
              class="empty-chart"
            />
            <div class="quality-table">
              <div class="quality-table-head">
                <span>{{ t('reports.materialRarity') }}</span
                ><span>{{ t('reports.actualCountShare') }}</span
                ><span>{{ t('reports.expectedShare') }}</span>
              </div>
              <div v-for="row in qualityRows" :key="row.rarity ?? 'unknown'" class="quality-row">
                <span
                  ><i :style="{ background: qualityColors[row.rarity] || qualityColors[0] }"></i
                  >{{ qualityLabels[row.rarity] || qualityLabels[0] }}</span
                ><span
                  ><strong>{{ row.count }}</strong
                  ><small>{{ quantity ? percent(row.count / quantity) : '—' }}</small></span
                ><span class="muted">{{ percent(row.probability) }}</span>
              </div>
            </div>
          </section>
          <section class="surface totals-panel">
            <div class="section-heading">
              <div>
                <h2>{{ t('reports.materialSummary') }}</h2>
                <p>{{ data.materials.length }}{{ t('reports.materialTypesUnit') }}</p>
              </div>
            </div>
            <div class="material-totals">
              <div v-for="item in data.materials" :key="item.name" class="total-row">
                <span
                  ><i :style="{ background: materialColor(item.name) }"></i
                  >{{ itemDisplayName(item.name) }}</span
                ><strong>× {{ item.count }}</strong>
              </div>
              <n-empty v-if="!data.materials.length" :description="t('reports.noMaterials')" />
            </div>
          </section>
        </div>
      </div>
      <section v-if="comparison" class="model-note">
        <h3>{{ t('reports.dualPoolAssumption') }}</h3>
        <div v-if="comparison.calculator" class="calculator-results">
          <div>
            <span>{{ t('reports.dailyAt100') }}</span
            ><strong
              >{{ number(comparison.calculator.daily_sanity, 3)
              }}<small>{{ t('reports.sanityPerDay') }}</small></strong
            >
          </div>
          <div>
            <span>{{ t('reports.dailyAtEfficiency') }}</span
            ><strong
              >{{ number(comparison.calculator.configured_daily_sanity, 3)
              }}<small>{{ t('reports.sanityPerDay') }}</small></strong
            >
          </div>
          <div>
            <span>{{ t('reports.equivalentFactoryEfficiency') }}</span
            ><strong>{{ percent(comparison.calculator.manufacturing_equivalent) }}</strong>
          </div>
          <div>
            <span>{{ t('reports.figurinoEquivalent') }}</span
            ><strong
              >{{ percent(comparison.calculator.elite0_equivalent) }} /
              {{ percent(comparison.calculator.elite2_equivalent) }}</strong
            >
          </div>
        </div>
        <template v-if="comparison.calculator?.replacement">
          <h3>{{ t('reports.replacementPoolAssumption') }}</h3>
          <div class="calculator-results">
            <div>
              <span>{{ t('reports.dailyAt100') }}</span>
              <strong
                >{{ number(comparison.calculator.replacement.daily_sanity, 3)
                }}<small>{{ t('reports.sanityPerDay') }}</small></strong
              >
            </div>
            <div>
              <span>{{ t('reports.dailyAtEfficiency') }}</span>
              <strong
                >{{ number(comparison.calculator.replacement.configured_daily_sanity, 3)
                }}<small>{{ t('reports.sanityPerDay') }}</small></strong
              >
            </div>
            <div>
              <span>{{ t('reports.equivalentFactoryEfficiency') }}</span>
              <strong>{{
                percent(comparison.calculator.replacement.manufacturing_equivalent)
              }}</strong>
            </div>
            <div>
              <span>{{ t('reports.figurinoEquivalent') }}</span>
              <strong
                >{{ percent(comparison.calculator.replacement.elite0_equivalent) }} /
                {{ percent(comparison.calculator.replacement.elite2_equivalent) }}</strong
              >
            </div>
          </div>
        </template>
        <p>{{ t('reports.recyclingAssumptionsHelp') }}</p>
        <n-collapse
          ><n-collapse-item :title="t('reports.probabilitySources')" name="model"
            ><p>
              {{ t('reports.actualValueFormulaPrefix') }}{{ number(comparison.per_material, 4)
              }}{{ t('reports.sanityPerItemSuffix') }}
            </p>
            <p>
              {{ t('reports.extraDrawRatePrefix') }}{{ number(comparison.extra_rate, 6)
              }}{{ t('reports.poolAssumptionsHelp') }}
            </p>
            <p>
              {{ t('reports.sourcePrefix') }}{{ comparison.source.source }} ·
              {{ comparison.source.sheet }} {{ comparison.source.ranges.join('、')
              }}{{ t('reports.materialValuesPrefix')
              }}{{ comparison.valuation?.source || t('reports.materialValuesUnread')
              }}{{ t('reports.savedSnapshotHelp') }}
            </p></n-collapse-item
          ></n-collapse
        >
      </section>
    </n-spin>
  </div>
</template>

<style scoped>
.valuation-panel {
  margin-bottom: 18px;
  padding: 18px 22px;
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 16px;
}
.valuation-source,
.calculator-results span {
  color: var(--muted);
  font-size: 13px;
  line-height: 1.8;
}
.valuation-source {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin: 12px 0;
}
.calculator-results {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 16px;
  margin: 18px 0;
}
.calculator-results > div {
  display: flex;
  flex-direction: column;
  gap: 5px;
  min-width: 0;
}
.calculator-results strong {
  font-size: 19px;
  overflow-wrap: anywhere;
}
.calculator-results small {
  font-size: 12px;
  font-weight: 400;
}
@media (max-width: 800px) {
  .calculator-results {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
@media (max-width: 480px) {
  .valuation-panel {
    padding: 16px;
  }
}
.recycling-page {
  --surface: #fff;
  --ink: #25333c;
  --muted: #7c8991;
  --soft: #f5f8f7;
  --line: rgba(27, 51, 42, 0.08);
  --accent: #238570;
  max-width: 1480px;
  color: var(--ink);
  font-variant-numeric: tabular-nums;
  -webkit-font-smoothing: antialiased;
  padding: 8px 0 28px;
}
.recycling-page.dark {
  --surface: #252a2f;
  --ink: #e1e8eb;
  --muted: #9aa6ad;
  --soft: #2c3237;
  --line: rgba(255, 255, 255, 0.08);
  --accent: #72cdb2;
}
.page-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
  margin-bottom: 26px;
}
.title-line {
  display: flex;
  align-items: center;
  gap: 12px;
}
.heading-icon {
  display: grid;
  place-items: center;
  width: 42px;
  height: 42px;
  border-radius: 13px;
  background: var(--soft);
  color: var(--accent);
  font-size: 25px;
}
h1 {
  font-size: 25px;
  line-height: 1.3;
  margin: 0;
  font-weight: 650;
  text-wrap: balance;
  letter-spacing: -0.6px;
}
.heading-copy p {
  margin: 9px 0 0 54px;
  color: var(--muted);
  font-size: 13px;
}
.filters {
  display: flex;
  gap: 10px;
  align-items: center;
}
.refresh-button {
  min-height: 40px;
  transition: transform 0.15s;
}
.refresh-button:active {
  transform: scale(0.96);
}
.notice {
  margin-bottom: 18px;
}
.metrics {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 16px;
  margin-bottom: 22px;
}
.metric,
.surface {
  background: var(--surface);
  border-radius: 16px;
  box-shadow:
    0 2px 8px rgba(0, 0, 0, 0.025),
    0 0 0 1px var(--line);
}
.metric {
  padding: 22px 24px;
}
.metric-label {
  font-size: 13px;
  color: var(--muted);
}
.metric-value {
  font-size: 32px;
  font-weight: 650;
  letter-spacing: -0.7px;
  margin: 9px 0 7px;
  line-height: 1.25;
  overflow-wrap: anywhere;
}
.metric-value small {
  display: inline-block;
  font-size: 12px;
  font-weight: 400;
  margin-left: 8px;
  color: var(--muted);
  letter-spacing: 0;
}
.metric-note {
  font-size: 12px;
  color: var(--muted);
}
.accent {
  color: var(--accent);
}
.statistics {
  display: grid;
  grid-template-columns: minmax(0, 1.35fr) minmax(0, 1fr);
  gap: 22px;
  align-items: start;
}
.surface {
  padding: 24px;
  min-width: 0;
}
.section-heading {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  margin-bottom: 18px;
}
h2 {
  font-size: 16px;
  margin: 0;
  font-weight: 600;
}
.section-heading p {
  font-size: 12px;
  color: var(--muted);
  margin: 5px 0 0;
}
.count-badge {
  background: var(--soft);
  color: var(--muted);
  font-size: 12px;
  padding: 5px 10px;
  border-radius: 8px;
  white-space: nowrap;
}
.section-icon {
  font-size: 22px;
  color: var(--accent);
}
.collection {
  position: relative;
  display: flex;
  gap: 18px;
  padding: 20px 10px 22px 3px;
}
.collection::before {
  content: '';
  position: absolute;
  left: 6px;
  top: 31px;
  bottom: -21px;
  width: 1px;
  background: var(--line);
}
.collection:last-child::before {
  display: none;
}
.timeline-dot {
  flex-shrink: 0;
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--accent);
  margin-top: 8px;
  box-shadow: 0 0 0 4px var(--soft);
}
.collection-body {
  min-width: 0;
  flex: 1;
}
time {
  display: flex;
  gap: 7px;
  align-items: center;
  font-size: 13px;
  font-weight: 600;
}
time .n-icon {
  color: var(--muted);
  font-size: 15px;
}
.operators {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 7px;
  margin: 12px 0;
  font-size: 12px;
}
.operators > .n-icon,
.operator-label,
.muted {
  color: var(--muted);
}
.operator-name {
  padding: 3px 8px;
  background: var(--soft);
  border-radius: 6px;
}
.materials {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.upload-state {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
  margin-top: 10px;
  font-size: 12px;
}
.upload-label {
  color: var(--muted);
}
.upload-label.submitted {
  color: var(--accent);
}
.upload-label.failed {
  color: #d35454;
}
.dark .upload-label.failed {
  color: #f28b82;
}
.material-chip {
  display: flex;
  align-items: center;
  gap: 7px;
  border-radius: 10px;
  background: var(--soft);
  padding: 5px 10px 5px 5px;
  font-size: 12px;
  border-left: 2px solid var(--quality);
}
.material-icon {
  display: grid;
  place-items: center;
  width: 34px;
  height: 34px;
  border-radius: 6px;
  background: var(--surface);
}
.material-icon img {
  width: 32px;
  height: 32px;
  object-fit: contain;
  outline: 1px solid rgba(0, 0, 0, 0.1);
  border-radius: 6px;
}
.dark .material-icon img {
  outline-color: rgba(255, 255, 255, 0.1);
}
.material-chip strong {
  font-weight: 600;
  margin-left: 4px;
}
.pagination {
  display: flex;
  justify-content: center;
  border-top: 1px solid var(--line);
  padding-top: 20px;
  margin-top: 12px;
}
.right-column {
  display: grid;
  gap: 22px;
}
.donut-wrap {
  height: 255px;
  position: relative;
}
.quality-chart {
  width: 100%;
  height: 100%;
}
.donut-center {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-direction: column;
  pointer-events: none;
}
.donut-center strong {
  font-size: 34px;
  font-weight: 600;
  line-height: 1.25;
}
.donut-center span {
  color: var(--muted);
  font-size: 12px;
  margin-top: 3px;
}
.quality-table-head,
.quality-row {
  display: grid;
  grid-template-columns: 1.2fr 1.1fr 0.8fr;
  align-items: center;
  gap: 8px;
}
.quality-table-head {
  font-size: 11px;
  color: var(--muted);
  padding: 11px 0;
  border-bottom: 1px solid var(--line);
}
.quality-table-head > :not(:first-child),
.quality-row > :not(:first-child) {
  text-align: right;
}
.quality-row {
  font-size: 12px;
  padding: 12px 0;
}
.quality-row i,
.total-row i {
  display: inline-block;
  width: 7px;
  height: 7px;
  border-radius: 50%;
  margin-right: 8px;
}
.quality-row small {
  display: inline-block;
  min-width: 57px;
  color: var(--muted);
  margin-left: 8px;
  font-size: 11px;
}
.material-totals {
  max-height: 220px;
  overflow-y: auto;
}
.total-row {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 0;
  font-size: 12px;
  border-bottom: 1px solid var(--line);
}
.total-row:last-child {
  border: none;
}
.total-row strong {
  font-weight: 600;
}
.model-note {
  margin: 24px 2px 0;
  color: var(--muted);
  font-size: 12px;
  overflow-wrap: anywhere;
}
.model-note p {
  line-height: 1.8;
  text-wrap: pretty;
}
.empty-state {
  padding: 110px 0;
}
.empty-chart {
  padding: 85px 0;
}
@media (max-width: 1100px) {
  .metrics {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .page-heading {
    align-items: flex-start;
    flex-direction: column;
    gap: 18px;
  }
}
@media (max-width: 850px) {
  .statistics {
    grid-template-columns: minmax(0, 1fr);
  }
}
@media (max-width: 540px) {
  h1 {
    font-size: 22px;
  }
  .filters {
    flex-wrap: wrap;
    width: 100%;
  }
  .filters :deep(.n-date-picker) {
    width: 100%;
  }
  .metric {
    padding: 17px;
  }
  .metric-value {
    font-size: 25px;
  }
  .metrics {
    gap: 12px;
  }
  .surface {
    padding: 18px;
  }
  .collection {
    gap: 12px;
  }
  .quality-row small {
    margin-left: 4px;
    min-width: 48px;
  }
}
@media (prefers-reduced-motion: reduce) {
  .refresh-button {
    transition: none;
  }
}
</style>
