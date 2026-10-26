<template>
  <section v-if="statistics" class="operator-statistics">
    <div class="stat-toolbar">
      <div class="stat-toolbar__title">
        <h3>本地练度档案</h3>
        <p>已同步 {{ format(totals.owned) }} 位干员 · 统计口径按星级筛选</p>
      </div>
      <n-checkbox-group v-model:value="rarities">
        <n-space :size="12">
          <n-checkbox
            v-for="rarity in [6, 5, 4, 3, 2, 1]"
            :key="rarity"
            :value="rarity"
            :label="rarity + ' 星'"
          />
        </n-space>
      </n-checkbox-group>
    </div>

    <n-tabs type="line" animated class="stat-tabs">
      <n-tab-pane name="roster" tab="干员统计">
        <div class="stat-kpis">
          <div class="stat-kpi">
            <span>已招募</span>
            <strong class="gp-num"
              >{{ format(totals.owned) }}<small>/ {{ format(totals.available) }}</small></strong
            >
            <em>资源收录 {{ rarities.length }} 个星级合计</em>
          </div>
          <div class="stat-kpi">
            <span>精二干员</span>
            <strong class="gp-num"
              >{{ format(totals.elite2)
              }}<small>{{ percent(totals.elite2, totals.owned) }}</small></strong
            >
            <em>占已招募</em>
          </div>
          <div class="stat-kpi">
            <span>专三技能</span>
            <strong class="gp-num">{{ format(totals.skills[3]) }}</strong>
            <em>仅计已专三</em>
          </div>
          <div class="stat-kpi">
            <span>已开启模组</span>
            <strong class="gp-num">{{ format(openedModules) }}</strong>
            <em>按已开启数量</em>
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
          <summary>统计口径</summary>
          <p>
            招募分母为当前资源收录的所选星级干员，包含尚未获得的干员，并非历史抽取次数。阿米娅各形态共用等级，仅计一位干员；各形态独立技能和模组分别统计。
          </p>
          <p>
            技能和模组列按当前恰好达到的等级分别计数。满练为 6 / 5 / 4 星精二 90 / 80 / 70 级，3
            星精一 55 级，1 / 2 星精零 30 级；模组开启等级为精二 ≥60 / 50 / 40
            级，不支持的养成项显示“—”。
          </p>
        </details>

        <div v-if="historyChart.series.length" class="stat-history">
          <div class="stat-history__head">
            <h4>已缓存的养成趋势</h4>
            <p>沿用每次同步时保存的原始统计，历史干员形态独立计数；未记录的指标不会补零。</p>
          </div>
          <v-chart :option="historyChart" autoresize style="height: 260px" />
        </div>
        <p v-else-if="history.length > 1" class="stat-empty">
          所选星级尚无足够历史记录；积累新快照后显示趋势。
        </p>
      </n-tab-pane>

      <n-tab-pane name="materials" tab="材料消耗">
        <div class="stat-resource">
          <div class="stat-resource__hero">
            <span>总消耗等效理智</span>
            <strong class="gp-num">≈ {{ format(totals.sanity) }}</strong>
            <em>相当于自然恢复约 {{ format(totals.sanity / 240, 1) }} 天</em>
          </div>
          <dl class="stat-resource__grid">
            <div>
              <dt>龙门币</dt>
              <dd class="gp-mono">{{ format(totals.consumed_lmd) }}</dd>
            </div>
            <div>
              <dt>作战记录经验</dt>
              <dd class="gp-mono">{{ format(totals.consumed_exp) }}</dd>
            </div>
            <div>
              <dt>模组数据块</dt>
              <dd class="gp-mono">{{ format(totals.module_blocks) }}</dd>
            </div>
            <div>
              <dt>技巧概要·卷3等效</dt>
              <dd class="gp-mono">{{ format(totals.skill_book_equivalent, 2) }}</dd>
            </div>
          </dl>
        </div>

        <details class="stat-notes">
          <summary>估值口径与数据来源</summary>
          <p>
            由已完成的等级、精英化、基础技能、专精与模组升级重建材料消耗，不扣当前仓库，也不计未完成计划。龙门币仅含直接养成支出，不推测历史加工费；技巧概要等效
            = 卷1 ÷ 9 + 卷2 ÷ 3 + 卷3，不计加工副产品。
          </p>
          <p>
            物品价值使用全部设置中“账号与数据来源”的当前保存值（{{
              statistics.source?.source
            }}）；EXP 以中级作战记录每 1000 经验折算。自然恢复按每 6 分钟 1 理智、每天 240
            理智折算。无法识别直升券等历史优惠，集成战略专属养成不计普通仓库材料。
          </p>
          <p>
            <a :href="statistics.source?.algorithm_url" target="_blank" rel="noopener noreferrer"
              >物品价值算法</a
            >
            ·
            <a :href="statistics.source?.values_url" target="_blank" rel="noopener noreferrer"
              >一图流材料价值</a
            >
          </p>
        </details>

        <n-alert
          v-if="unpricedNames.length || totals.incomplete.length"
          type="info"
          :show-icon="false"
          class="stat-coverage"
        >
          <div v-if="unpricedNames.length">
            未计价：{{ unpricedNames.join('、') }}。等效理智仅包含已知价格部分。
          </div>
          <div v-if="totals.incomplete.length">
            部分养成材料数据缺失：{{ totals.incomplete.join('、') }}。
          </div>
        </n-alert>

        <div class="stat-table-toolbar">
          <span class="gp-muted">{{ filteredMaterials.length }} 种已消耗资源</span>
          <n-input
            v-model:value="materialQuery"
            clearable
            placeholder="查找材料"
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

      <n-tab-pane name="ranking" tab="理智排行">
        <p class="stat-lead">
          按已完成养成材料的等效理智排序，包含全部已升级技能与模组；阿米娅各形态合并，未计价材料不参与排名数值。
        </p>
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
              :alt="row.name"
              loading="lazy"
              @error="(event) => (event.target.style.display = 'none')"
            />
            <div>
              <strong>{{ row.name }}</strong>
              <span>{{ row.rarity }} 星 · ≈ {{ format(row.sanity) }} 理智</span>
            </div>
          </div>
          <n-empty v-if="!totals.ranking.length" description="没有所选星级的数据" />
        </div>
        <details class="stat-ranking">
          <summary>查看完整排行（{{ totals.ranking.length }} 位）</summary>
          <div class="stat-table-toolbar">
            <span class="gp-muted">以已同步练度为准</span>
            <n-input
              v-model:value="operatorQuery"
              clearable
              placeholder="查找干员"
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
  {
    ...numberColumn('达到模组开启等级', 'module_level', (row) => row.supports_modules === false),
    width: 160
  },
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
const materialColumns = [
  {
    title: '资源',
    key: 'name',
    minWidth: 170,
    render: (row) => assetRow(assetIcon(materialIcon(row), 'icon'), row.name)
  },
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
  {
    title: '干员',
    key: 'name',
    minWidth: 160,
    render: (row) =>
      assetRow(assetIcon('/avatar/' + encodeURIComponent(row.name) + '.webp', 'avatar'), row.name)
  },
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
