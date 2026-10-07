<template>
  <section
    v-if="statistics"
    class="operator-statistics"
    :style="{
      color: theme.textColor1,
      '--line': theme.dividerColor,
      '--muted': theme.textColor3,
      '--panel': theme.cardColor
    }"
  >
    <div class="section-heading">
      <div>
        <h2>干员数据统计</h2>
        <n-text depth="3">使用本地已同步练度，支持全部星级干员</n-text>
      </div>
      <n-checkbox-group v-model:value="rarities"
        ><n-space :size="18"
          ><n-checkbox
            v-for="rarity in [6, 5, 4, 3, 2, 1]"
            :key="rarity"
            :value="rarity"
            :label="`${rarity} 星`" /></n-space
      ></n-checkbox-group>
    </div>
    <n-tabs type="line" animated>
      <n-tab-pane name="roster" tab="干员统计">
        <div class="roster-summary">
          <div>
            <span>已招募</span
            ><strong
              >{{ format(totals.owned) }} <small>/ {{ format(totals.available) }}</small></strong
            >
          </div>
          <div>
            <span>精二干员</span
            ><strong
              >{{ format(totals.elite2) }}
              <small>{{ percent(totals.elite2, totals.owned) }}</small></strong
            >
          </div>
          <div>
            <span>专三技能</span><strong>{{ format(totals.skills[3]) }}</strong>
          </div>
          <div>
            <span>已开启模组</span><strong>{{ format(openedModules) }}</strong>
          </div>
        </div>
        <n-data-table
          :columns="rosterColumns"
          :data="rosterRows"
          :bordered="false"
          :single-line="false"
          :scroll-x="1120"
          :row-key="(row) => row.key"
          size="small"
        />
        <p class="explanation">
          招募分母为当前资源收录的所选星级干员，包含尚未获得的干员，并非历史抽取次数。阿米娅各形态共用等级，仅计一位干员；各形态独立技能和模组分别统计。
        </p>
        <p class="explanation">
          技能和模组列按当前恰好达到的等级分别计数。满练按实际能力统计：6 / 5 / 4 星为精二 90 / 80 /
          70 级，3 星为精一 55 级，1 / 2 星为精零 30 级。模组等级为精二 ≥60 / 50 / 40 级（6 / 5 / 4
          星）；不支持的养成项显示“—”。
        </p>
        <n-collapse v-if="historyChart.series.length"
          ><n-collapse-item title="已缓存的养成趋势" name="history">
            <p class="explanation">
              沿用每次同步时保存的原始统计，历史干员形态独立计数。未记录的指标不会补零。
            </p>
            <v-chart :option="historyChart" autoresize style="height: 260px" /> </n-collapse-item
        ></n-collapse>
        <n-text v-else-if="history.length > 1" depth="3"
          >所选星级尚无足够历史记录；旧缓存缺失的星级不会补零，积累新快照后显示趋势。</n-text
        >
      </n-tab-pane>
      <n-tab-pane name="materials" tab="材料消耗情况">
        <div class="resource-summary">
          <div class="sanity-total">
            <span>总消耗等效理智</span><strong>≈ {{ format(totals.sanity) }}</strong
            ><span>相当于自然恢复约 {{ format(totals.sanity / 240, 1) }} 天</span>
          </div>
          <dl>
            <div>
              <dt>龙门币</dt>
              <dd>{{ format(totals.consumed_lmd) }}</dd>
            </div>
            <div>
              <dt>作战记录经验</dt>
              <dd>{{ format(totals.consumed_exp) }}</dd>
            </div>
            <div>
              <dt>模组数据块</dt>
              <dd>{{ format(totals.module_blocks) }}</dd>
            </div>
            <div>
              <dt>技巧概要·卷3等效</dt>
              <dd>{{ format(totals.skill_book_equivalent, 2) }}</dd>
            </div>
          </dl>
        </div>
        <n-collapse class="valuation-notes"
          ><n-collapse-item title="估值口径与数据来源" name="method">
            <p>
              由已完成的等级、精英化、基础技能、专精与模组升级重建材料消耗，不扣当前仓库，也不计未完成计划。龙门币仅含直接养成支出，不推测历史加工费；技巧概要等效
              = 卷1 ÷ 9 + 卷2 ÷ 3 + 卷3，不计加工副产品。
            </p>
            <p>
              物品使用一图流已发布价值快照（{{
                statistics.source?.retrieved_at
              }}），材料价格包含其副产物估值；EXP 以中级作战记录每 1000 经验折算。自然恢复按每 6
              分钟 1 理智、每天 240
              理智折算。无法识别直升券等历史优惠，集成战略专属养成不计普通仓库材料。
            </p>
            <p>
              <a :href="statistics.source?.algorithm_url" target="_blank" rel="noopener noreferrer"
                >物品价值算法</a
              >
              ·
              <a :href="statistics.source?.values_url" target="_blank" rel="noopener noreferrer"
                >固定价值快照</a
              >
            </p>
          </n-collapse-item></n-collapse
        >
        <n-alert
          v-if="unpricedNames.length || totals.incomplete.length"
          type="info"
          :show-icon="false"
          class="coverage-note"
        >
          <div v-if="unpricedNames.length">
            未计价：{{ unpricedNames.join('、') }}。等效理智仅包含已知价格部分。
          </div>
          <div v-if="totals.incomplete.length">
            部分养成材料数据缺失：{{ totals.incomplete.join('、') }}。
          </div>
        </n-alert>
        <div class="table-toolbar">
          <n-text depth="3">{{ filteredMaterials.length }} 种已消耗资源</n-text
          ><n-input
            v-model:value="materialQuery"
            clearable
            placeholder="查找材料"
            size="small"
            class="search-input"
          />
        </div>
        <n-data-table
          :columns="materialColumns"
          :data="filteredMaterials"
          :pagination="{ pageSize: 12 }"
          :bordered="false"
          :row-key="(row) => row.id"
          :scroll-x="620"
          size="small"
        />
      </n-tab-pane>
      <n-tab-pane name="ranking" tab="干员消耗理智排行">
        <p class="explanation">
          按已完成养成材料的等效理智排序，包含全部已升级技能与模组。阿米娅各形态合并；未计价材料不参与排名数值。
        </p>
        <div class="rank-preview">
          <div v-for="(row, index) in totals.ranking.slice(0, 3)" :key="row.char_id">
            <span class="rank-index">{{ index + 1 }}</span>
            <div>
              <strong>{{ row.name }}</strong
              ><n-text depth="3">{{ row.rarity }} 星 · ≈ {{ format(row.sanity) }} 理智</n-text>
            </div>
          </div>
          <n-empty v-if="!totals.ranking.length" description="没有所选星级的数据" />
        </div>
        <n-collapse
          ><n-collapse-item :title="`查看完整排行（${totals.ranking.length} 位）`" name="ranking">
            <div class="table-toolbar">
              <n-text depth="3">以已同步练度为准</n-text
              ><n-input
                v-model:value="operatorQuery"
                clearable
                placeholder="查找干员"
                size="small"
                class="search-input"
              />
            </div>
            <n-data-table
              :columns="rankingColumns"
              :data="filteredRanking"
              :pagination="{ pageSize: 10 }"
              :bordered="false"
              :row-key="(row) => row.char_id"
              :scroll-x="600"
              size="small"
            /> </n-collapse-item
        ></n-collapse>
      </n-tab-pane>
    </n-tabs>
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
import { personalStatisticsRows, sumPersonalStatistics } from '@/utils/operatorStatistics'
import { growthMetrics, growthHistoryPoints } from '@/utils/growthPlanning'

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
  totals.value.materials.filter((row) => row.sanity === null).map((row) => row.name)
)
const filteredMaterials = computed(() =>
  totals.value.materials.filter(
    (row) =>
      row.name.includes(materialQuery.value.trim()) || row.id.includes(materialQuery.value.trim())
  )
)
const filteredRanking = computed(() =>
  totals.value.ranking
    .map((row, index) => ({ ...row, position: index + 1 }))
    .filter((row) => row.name.includes(operatorQuery.value.trim()))
)
const format = (value, decimals = 0) =>
  Number(value || 0).toLocaleString('zh-CN', { maximumFractionDigits: decimals })
const percent = (count, all) => `${all ? ((count / all) * 100).toFixed(1) : 0}%`
const numberColumn = (title, key, notApplicable = () => false) => ({
  title,
  key,
  align: 'right',
  render: (row) => (notApplicable(row) ? '—' : format(row[key]))
})
const rosterColumns = [
  { title: '星级', key: 'label', fixed: 'left', width: 88 },
  {
    title: '已招募 / 资源收录',
    key: 'owned',
    width: 140,
    render: (row) => `${format(row.owned)} / ${format(row.available)}`
  },
  numberColumn('精二', 'elite2', (row) => row.max_phase < 2),
  numberColumn('满练', 'max_level'),
  numberColumn('模组等级', 'module_level', (row) => row.supports_modules === false),
  {
    title: '专精技能',
    key: 'skills',
    children: [1, 2, 3].map((level) => ({
      title: `专${['', '一', '二', '三'][level]}`,
      key: `skills.${level}`,
      align: 'right',
      render: (row) => (row.supports_mastery === false ? '—' : format(row.skills?.[level]))
    }))
  },
  {
    title: '模组数量',
    key: 'modules',
    children: [1, 2, 3].map((level) => ({
      title: `${level} 级`,
      key: `modules.${level}`,
      align: 'right',
      render: (row) => (row.supports_modules === false ? '—' : format(row.modules?.[level]))
    }))
  }
]
const materialColumns = [
  { title: '资源', key: 'name', minWidth: 140 },
  numberColumn('累计消耗', 'count'),
  {
    title: '单件等效理智',
    key: 'value',
    align: 'right',
    render: (row) => (row.value === null ? '未计价' : format(row.value, 4))
  },
  {
    title: '总等效理智',
    key: 'sanity',
    align: 'right',
    render: (row) => (row.sanity === null ? '未计价' : format(row.sanity, 1))
  }
]
const rankingColumns = [
  { title: '排名', key: 'position', width: 65 },
  { title: '干员', key: 'name', minWidth: 130 },
  { title: '星级', key: 'rarity', width: 65 },
  { title: '等效理智', key: 'sanity', align: 'right', render: (row) => `≈ ${format(row.sanity)}` },
  {
    title: '覆盖情况',
    key: 'coverage',
    render: (row) =>
      row.incomplete ? '部分养成数据缺失' : row.unpriced.length ? '含未计价材料' : '已计价'
  }
]
const historyChart = computed(() => ({
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
  margin: 0;
  color: inherit;
}
.section-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
  margin-bottom: 14px;
}
h2 {
  margin: 0 0 4px;
  font-size: 20px;
  font-weight: 650;
}
.section-heading :deep(.n-text) {
  font-size: 12px;
}
.roster-summary {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 20px;
  padding: 14px 4px 22px;
}
.roster-summary > div {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.roster-summary span,
.sanity-total > span {
  color: var(--muted);
  font-size: 12px;
}
.roster-summary strong {
  font-size: 28px;
  font-variant-numeric: tabular-nums;
}
.roster-summary small {
  font-size: 13px;
  font-weight: 400;
  color: var(--muted);
}
.explanation {
  color: var(--muted);
  font-size: 12px;
  line-height: 1.8;
}
.resource-summary {
  display: grid;
  grid-template-columns: 1fr 1.5fr;
  padding: 20px;
  border-radius: 12px;
  background: var(--panel);
  gap: 24px;
  margin: 10px 0 18px;
}
.sanity-total {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.sanity-total strong {
  font-size: 30px;
  font-variant-numeric: tabular-nums;
}
dl {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 18px 24px;
  margin: 0;
}
dt {
  color: var(--muted);
  font-size: 12px;
}
dd {
  margin: 5px 0 0;
  font-size: 18px;
  font-variant-numeric: tabular-nums;
}
.valuation-notes {
  margin-bottom: 16px;
  font-size: 12px;
}
.valuation-notes p {
  line-height: 1.8;
}
a {
  color: inherit;
  text-decoration: underline;
}
.coverage-note {
  margin-bottom: 14px;
}
.table-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  margin: 14px 0;
}
.search-input {
  width: 220px;
}
.rank-preview {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
  margin: 20px 0 26px;
}
.rank-preview > div {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 16px;
  background: var(--panel);
  border-radius: 10px;
}
.rank-preview strong,
.rank-preview :deep(.n-text) {
  display: block;
}
.rank-preview :deep(.n-text) {
  margin-top: 5px;
  font-size: 12px;
}
.rank-index {
  color: var(--muted);
  font-size: 30px;
  font-variant-numeric: tabular-nums;
}
@media (max-width: 720px) {
  .roster-summary {
    grid-template-columns: repeat(2, 1fr);
    gap: 14px;
  }
  .resource-summary {
    grid-template-columns: 1fr;
  }
  .rank-preview {
    grid-template-columns: 1fr;
    gap: 8px;
  }
  .search-input {
    width: 160px;
  }
}
</style>
