<script setup>
import { computed, inject, onMounted, reactive, ref } from 'vue'
import { storeToRefs } from 'pinia'
import { useConfigStore } from '@/stores/config'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { PieChart } from 'echarts/charts'
import { TooltipComponent } from 'echarts/components'
import VChart from 'vue-echarts'
import {
  CubeOutline,
  RefreshOutline,
  DownloadOutline,
  TimeOutline,
  PersonOutline,
  LeafOutline
} from '@vicons/ionicons5'

use([CanvasRenderer, PieChart, TooltipComponent])
const axios = inject('axios')
const { theme } = storeToRefs(useConfigStore())
const today = new Date()
const since = new Date(today)
since.setDate(today.getDate() - 29)
const range = ref([since.getTime(), today.getTime()])
const page = ref(1)
const loading = ref(false)
const error = ref('')
const exporting = ref(false)
const exportError = ref('')
const emptyData = () => ({ total: 0, materials: [], qualities: [], records: [], comparison: null })
const data = ref(emptyData())
const failedIcons = reactive(new Set())
let requestVersion = 0
const quantity = computed(() => data.value.materials.reduce((sum, item) => sum + item.count, 0))
const comparison = computed(() => data.value.comparison)
const qualityLabels = ['未知品质', '白色材料', '绿色材料', '蓝色材料', '紫色材料', '金色材料']
const qualityColors = ['#8b98a6', '#bfc7cf', '#79ae59', '#549bd4', '#a078d0', '#dcb153']
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
  tooltip: { trigger: 'item', formatter: '{b}：{c} 个（{d}%）' },
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
        name: qualityLabels[row.rarity] || qualityLabels[0],
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
  return new Date(at * 1000).toLocaleString('zh-CN', { hour12: false })
}
function number(value, digits = 1) {
  return value == null
    ? '—'
    : value.toLocaleString('zh-CN', {
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
  if (value == null || !comparison.value?.expected_sanity) return '等待有效样本'
  return `${value >= 0 ? '高于' : '低于'}预期 ${percent(Math.abs(value) / comparison.value.expected_sanity)}`
})
async function load() {
  const version = ++requestVersion
  loading.value = true
  error.value = ''
  try {
    const response = await axios.get(`${import.meta.env.VITE_HTTP_URL}/report/recycling_history`, {
      params: {
        startDate: localDate(range.value[0]),
        endDate: localDate(range.value[1]),
        page: page.value
      }
    })
    if (version === requestVersion) data.value = response.data
  } catch {
    if (version === requestVersion) {
      data.value = emptyData()
      error.value = '回收站统计读取失败，请重试'
    }
  } finally {
    if (version === requestVersion) loading.value = false
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
      link.download = `回收站材料统计-${startDate}-${endDate}.xlsx`
      document.body.appendChild(link)
      link.click()
    } finally {
      link.remove()
      setTimeout(() => URL.revokeObjectURL(url), 1000)
    }
  } catch {
    exportError.value = 'Excel 导出失败，请重试或缩小日期范围'
  } finally {
    exporting.value = false
  }
}
onMounted(() => {
  load()
})
</script>

<template>
  <div class="recycling-page" :class="{ dark: theme === 'dark' }">
    <header class="page-heading">
      <div class="heading-copy">
        <div class="title-line">
          <span class="heading-icon"><n-icon :component="CubeOutline" /></span>
          <h1>回收站材料统计</h1>
        </div>
        <p>收取记录、材料品质与理智收益</p>
      </div>
      <div class="filters">
        <n-date-picker
          v-model:value="range"
          type="daterange"
          :clearable="false"
          @update:value="changeRange"
        />
        <n-button secondary :loading="loading" class="refresh-button" @click="load"
          ><template #icon><n-icon :component="RefreshOutline" /></template>刷新</n-button
        >
        <n-button
          secondary
          :loading="exporting"
          :disabled="loading"
          class="refresh-button"
          title="导出所选日期范围的全部记录与收益统计"
          @click="exportExcel"
          ><template #icon><n-icon :component="DownloadOutline" /></template>导出 Excel</n-button
        >
      </div>
    </header>
    <n-alert v-if="error" type="error" class="notice">{{ error }}</n-alert>
    <n-alert v-if="exportError" type="error" class="notice">{{ exportError }}</n-alert>
    <section class="valuation-panel valuation-source">
      <span>{{ comparison?.valuation?.source || '材料价值未读取' }}</span>
      <router-link to="/mowersettings">管理材料价值与基报算法</router-link>
    </section>
    <n-alert
      v-if="comparison?.unknown_collections || comparison?.unknown_materials.length"
      type="warning"
      class="notice"
    >
      存在 {{ comparison.unknown_collections }} 条未完整识别的记录<span
        v-if="comparison.unknown_materials.length"
        >，未定价材料：{{ comparison.unknown_materials.join('、') }}</span
      >。材料汇总仅含已识别数量，总理智收益和预期对比暂不计算。
    </n-alert>
    <n-alert v-if="comparison?.unmodeled_materials?.length" type="warning" class="notice">
      以下材料尚未加入概率表：{{
        comparison.unmodeled_materials.join('、')
      }}。已导入价格可用于实际收益；期望收益对比暂不计算，等待概率表更新。
    </n-alert>
    <n-spin :show="loading">
      <div class="metrics">
        <section class="metric">
          <span class="metric-label">累计获得材料</span>
          <div class="metric-value">{{ number(quantity, 0) }}<small>个</small></div>
          <span class="metric-note">{{ data.total }} 次收取 · 所选日期</span>
        </section>
        <section class="metric">
          <span class="metric-label">总理智收益</span>
          <div class="metric-value accent">
            {{ number(comparison?.actual_sanity) }}<small>理智</small>
          </div>
          <span class="metric-note">按实际材料及当前保存价值折算</span>
        </section>
        <section class="metric">
          <span class="metric-label">理论期望收益</span>
          <div class="metric-value">
            {{ number(comparison?.expected_sanity) }}<small>理智</small>
          </div>
          <span class="metric-note">与实际相同材料总数的长期期望</span>
        </section>
        <section class="metric">
          <span class="metric-label">与期望的差额</span>
          <div class="metric-value" :class="{ accent: comparison?.difference > 0 }">
            {{ comparison?.difference > 0 ? '+' : '' }}{{ number(comparison?.difference)
            }}<small>理智</small>
          </div>
          <span class="metric-note">{{ differenceText }}</span>
        </section>
      </div>
      <div class="statistics">
        <section class="surface history-panel">
          <div class="section-heading">
            <div>
              <h2>收取明细</h2>
              <p>收取时刻、进驻干员与实际获得材料</p>
            </div>
            <span class="count-badge">{{ data.total }} 条记录</span>
          </div>
          <n-scrollbar style="max-height: 600px" class="history">
            <n-empty
              v-if="!data.records.length"
              description="所选日期暂无收取记录"
              class="empty-state"
              ><template #icon><n-icon :component="CubeOutline" /></template
            ></n-empty>
            <article v-for="row in data.records" :key="row.id" class="collection">
              <div class="timeline-dot"></div>
              <div class="collection-body">
                <time><n-icon :component="TimeOutline" />{{ formatTime(row.collected_at) }}</time>
                <div class="operators">
                  <n-icon :component="PersonOutline" /><span class="operator-label">进驻干员</span
                  ><span v-if="row.operators === null" class="muted">未识别</span
                  ><span v-else-if="!row.operators.length" class="muted">无人进驻</span
                  ><span v-for="name in row.operators || []" :key="name" class="operator-name">{{
                    name
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
                        :alt="name"
                        loading="lazy"
                        @error="failedIcons.add(name)"
                      /><span v-else>◇</span>
                    </div>
                    <span>{{ name }}</span
                    ><strong>× {{ count }}</strong>
                  </div>
                </div>
                <span v-else class="muted">材料未完整识别，请查看收取截图</span>
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
                <h2>材料品质分布</h2>
                <p>按获得数量统计</p>
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
                ><span>材料总数</span>
              </div>
            </div>
            <n-empty v-else description="等待首次收取" class="empty-chart" />
            <div class="quality-table">
              <div class="quality-table-head">
                <span>材料品质</span><span>实际数量 / 占比</span><span>理论占比</span>
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
                <h2>材料汇总</h2>
                <p>{{ data.materials.length }} 种材料</p>
              </div>
            </div>
            <div class="material-totals">
              <div v-for="item in data.materials" :key="item.name" class="total-row">
                <span><i :style="{ background: materialColor(item.name) }"></i>{{ item.name }}</span
                ><strong>× {{ item.count }}</strong>
              </div>
              <n-empty v-if="!data.materials.length" description="暂无材料" />
            </div>
          </section>
        </div>
      </div>
      <section v-if="comparison" class="model-note">
        <h3>普通池和额外池各产一次（默认假设）</h3>
        <div v-if="comparison.calculator" class="calculator-results">
          <div>
            <span>100%效率理论日产</span
            ><strong
              >{{ number(comparison.calculator.daily_sanity, 3) }}<small> 理智/天</small></strong
            >
          </div>
          <div>
            <span>设定效率理论日产</span
            ><strong
              >{{ number(comparison.calculator.configured_daily_sanity, 3)
              }}<small> 理智/天</small></strong
            >
          </div>
          <div>
            <span>等效制造站效率</span
            ><strong>{{ percent(comparison.calculator.manufacturing_equivalent) }}</strong>
          </div>
          <div>
            <span>旅骨精零 / 精二等效制造站</span
            ><strong
              >{{ percent(comparison.calculator.elite0_equivalent) }} /
              {{ percent(comparison.calculator.elite2_equivalent) }}</strong
            >
          </div>
        </div>
        <template v-if="comparison.calculator?.replacement">
          <h3>额外池顶替普通池（对照假设）</h3>
          <div class="calculator-results">
            <div>
              <span>100%效率理论日产</span>
              <strong
                >{{ number(comparison.calculator.replacement.daily_sanity, 3)
                }}<small> 理智/天</small></strong
              >
            </div>
            <div>
              <span>设定效率理论日产</span>
              <strong
                >{{ number(comparison.calculator.replacement.configured_daily_sanity, 3)
                }}<small> 理智/天</small></strong
              >
            </div>
            <div>
              <span>等效制造站效率</span>
              <strong>{{
                percent(comparison.calculator.replacement.manufacturing_equivalent)
              }}</strong>
            </div>
            <div>
              <span>旅骨精零 / 精二等效制造站</span>
              <strong
                >{{ percent(comparison.calculator.replacement.elite0_equivalent) }} /
                {{ percent(comparison.calculator.replacement.elite2_equivalent) }}</strong
              >
            </div>
          </div>
        </template>
        <p>
          回收站实际机制尚未确认，以上展示两种假设。100%回收站效率每两天完成一次生产周期，100%制造站每日产出8000经验。旅骨精零/精二分别按20%/30%回收站效率换算。
        </p>
        <n-collapse
          ><n-collapse-item title="计算口径与概率来源" name="model"
            ><p>
              实际理智收益 = 各材料数量 × 当前材料理智价值。理论期望 = 材料总数 ×
              {{ number(comparison.per_material, 4) }} 理智/件。
            </p>
            <p>
              普通池与额外池分别按权重计算，长期平均每次普通抽取产生
              {{ number(comparison.extra_rate, 6) }}
              次额外抽取；双池收益除以双池材料总数，得到同材料量的理论基准。顶替假设下，额外池占生产周期的比例为
              r / (1 + r)，r
              为上述额外抽取率。两种假设的单件期望与品质比例相同，理论日产量不同。进驻干员供回溯分析；此比较不推算干员生产效率、收取次数对应的抽数或每日产能，也不保证短期结果。
            </p>
            <p>
              来源：{{ comparison.source.source }} · {{ comparison.source.sheet }}
              {{ comparison.source.ranges.join('、') }}。材料价值：{{
                comparison.valuation?.source || '材料价值未读取'
              }}，使用本地保存的快照，不自动更新。
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
