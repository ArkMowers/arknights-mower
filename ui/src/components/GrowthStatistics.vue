<template>
  <section
    v-if="statistics"
    class="growth-statistics"
    :style="{ '--panel': theme.cardColor, '--muted': theme.textColor3, color: theme.textColor1 }"
  >
    <div class="stats-heading">
      <div>
        <n-text strong>养成概览</n-text
        ><n-text depth="3" class="stats-caption">按已同步的干员数据统计</n-text>
      </div>
      <n-checkbox-group v-model:value="rarities">
        <n-space :size="18"
          ><n-checkbox v-for="star in [6, 5, 4]" :key="star" :value="star" :label="`${star} 星`"
        /></n-space>
      </n-checkbox-group>
    </div>
    <div class="stats-grid">
      <div v-for="metric in growthMetrics" :key="metric.key" class="stat-card">
        <n-popover v-if="metric.key === 'sanity_value'" trigger="hover" style="max-width: 400px">
          <template #trigger
            ><span class="stat-label value-help" tabindex="0">{{ metric.label }} ⓘ</span></template
          >
          <div class="value-explanation">
            <p>
              按已同步的等级、精英化、基础技能、专精和模组各级材料，乘以一图流物品价值求和；不扣仓库，不计未完成计划。等效理智是统一估值，不代表实际刷取或使用理智。
            </p>
            <p>按常规养成材料重建，无法识别直升券等历史优惠；集成战略专属养成不计普通仓库材料。</p>
            <p>
              龙门币与经验是已完成养成的直接消耗；无法确认历史材料获取方式，因此不推算历史加工费。自然恢复按每
              6 分钟 1 理智、每天 240 理智折算。
            </p>
            <p v-if="coverage.source">
              采用一图流发布的固定价值快照（{{
                coverage.source.retrieved_at
              }}），包含材料副产物估值。经验按中级作战记录每 1000 EXP 折算。
            </p>
            <p v-if="coverage.unpriced.length">
              未计价：{{
                coverage.unpriced.map((item) => `${item.name} ×${item.count}`).join('、')
              }}。
            </p>
            <p v-if="coverage.incomplete.length">
              以下干员部分养成数据缺失，数值仅含可确认部分：{{ coverage.incomplete.join('、') }}。
            </p>
            <p v-if="coverage.source">
              <a :href="coverage.source.algorithm_url" target="_blank" rel="noopener noreferrer"
                >算法说明</a
              >
              ·
              <a :href="coverage.source.values_url" target="_blank" rel="noopener noreferrer"
                >价值快照来源</a
              >
            </p>
          </div>
        </n-popover>
        <span v-else class="stat-label">{{ metric.label }}</span>
        <div class="stat-value-row">
          <strong class="stat-value">{{
            metric.key === 'sanity_value'
              ? formatValue(totals[metric.key], true)
              : totals[metric.key]
          }}</strong>
          <span v-if="metric.key === 'modules'" class="stat-detail"
            >累计消耗 {{ formatValue(coverage.moduleBlocks) }} 个模组数据块</span
          >
          <n-popover v-if="metric.key === 'masteries'" trigger="hover">
            <template #trigger
              ><span class="stat-detail value-help" tabindex="0"
                >技巧概要·卷3等效<br />{{ formatValue(coverage.skillBookEquivalent) }} ⓘ</span
              ></template
            >
            按基础技能升级与已完成专精消耗累计；卷1 ÷ 9 + 卷2 ÷ 3 + 卷3，不计合成副产品。
          </n-popover>
        </div>
        <div v-if="metric.key === 'sanity_value'" class="sanity-breakdown">
          <span>龙门币 {{ formatValue(coverage.consumedLmd) }}</span>
          <span>经验值 {{ formatValue(coverage.consumedExp) }}</span>
          <span
            >相当于自然恢复约
            {{
              totals.sanity_value === null ? '—' : formatValue(totals.sanity_value / 240)
            }}
            天</span
          >
        </div>
        <span class="stat-detail">{{
          metric.key === 'sanity_value' && (coverage.unpriced.length || coverage.incomplete.length)
            ? '已计价部分 · 查看估值说明'
            : metric.detail
        }}</span>
      </div>
    </div>
    <n-collapse v-if="history.length > 1" class="trend-collapse">
      <n-collapse-item title="养成趋势" name="history">
        <v-chart :option="chart" autoresize style="height: 240px" />
      </n-collapse-item>
    </n-collapse>
  </section>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useThemeVars } from 'naive-ui'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { LineChart } from 'echarts/charts'
import { CanvasRenderer } from 'echarts/renderers'
import { GridComponent, TooltipComponent, LegendComponent } from 'echarts/components'
import {
  growthMetrics,
  sumGrowthStatistics,
  growthValueCoverage,
  growthHistoryPoints
} from '@/utils/growthPlanning'
use([LineChart, CanvasRenderer, GridComponent, TooltipComponent, LegendComponent])
const props = defineProps({ statistics: Object, history: { type: Array, default: () => [] } })
const theme = useThemeVars()
const rarities = ref([6, 5, 4])
const totals = computed(() => sumGrowthStatistics(props.statistics, rarities.value))
const coverage = computed(() => growthValueCoverage(props.statistics, rarities.value))
function formatValue(value, approximate = false) {
  if (value === null) return '—'
  return `${approximate ? '≈ ' : ''}${value.toLocaleString('zh-CN', { maximumFractionDigits: approximate ? 0 : 2 })}`
}
const chart = computed(() => ({
  tooltip: { trigger: 'axis' },
  legend: { textStyle: { color: theme.value.textColor2 } },
  grid: { left: 40, right: 76, bottom: 32, top: 64 },
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
      name: '等效理智',
      position: 'right',
      axisLabel: { color: theme.value.textColor3 },
      splitLine: { show: false }
    }
  ],
  series: growthMetrics
    .filter(
      ({ key }) =>
        key !== 'sanity_value' || growthHistoryPoints(props.history, rarities.value, key).length > 1
    )
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
.growth-statistics {
  margin: 22px 0;
}
.stats-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 14px;
}
.stats-caption {
  margin-left: 12px;
  font-size: 12px;
}
.stats-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}
.stat-card {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 18px 20px;
  border-radius: 14px;
  background: var(--panel);
  box-shadow: 0 2px 12px #00000009;
}
.stat-label {
  font-size: 13px;
}
.stat-value-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.stat-value-row .stat-detail {
  max-width: 170px;
  text-align: right;
  line-height: 1.6;
}
.stat-value {
  font-size: clamp(22px, 2.4vw, 30px);
  line-height: 1.15;
  font-variant-numeric: tabular-nums;
  font-weight: 650;
}
.stat-detail {
  font-size: 11px;
  color: var(--muted);
}
.sanity-breakdown {
  display: flex;
  flex-direction: column;
  gap: 3px;
  font-size: 11px;
  font-variant-numeric: tabular-nums;
}
.trend-collapse {
  margin-top: 18px;
}
.value-help {
  cursor: help;
}
.value-explanation p {
  margin: 8px 0;
}
.value-explanation a {
  color: inherit;
  text-decoration: underline;
}
@media (max-width: 1000px) {
  .stats-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}
@media (max-width: 600px) {
  .stats-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 8px;
  }
  .stat-card {
    padding: 14px;
  }
  .stats-caption {
    display: block;
    margin: 4px 0 0;
  }
}
</style>
