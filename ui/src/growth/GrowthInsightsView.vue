<script setup>
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
  if (!stamp) return '尚未获取'
  return new Date(stamp * 1000).toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  })
})
const surveyNote = computed(() => {
  if (props.survey?.error) return '公开样本暂时不可用：' + props.survey.error
  if (!surveyCoverage.value) return '还没有可用的公开样本；干员卡会显示“暂无样本”。'
  return (
    '覆盖 ' + formatCompactNumber(surveyCoverage.value) + ' 位干员 · 样本获取于 ' + fetchedAt.value
  )
})
</script>

<template>
  <div class="growth-insights">
    <section class="gp-panel growth-insights__stats">
      <header class="gp-section-head">
        <div>
          <span class="gp-kicker">Local archive</span>
          <h2 class="gp-section-head__title">养成统计</h2>
        </div>
      </header>
      <OperatorStatistics v-if="statistics" :statistics="statistics" :history="history" />
      <div v-else class="gp-empty">
        <p class="gp-empty__title">还没有可统计的练度</p>
        <p class="gp-muted">从森空岛同步一次干员数据后，这里会显示招募、精英化、专精与材料消耗。</p>
      </div>
    </section>

    <section class="gp-panel growth-insights__survey">
      <header class="gp-section-head">
        <div>
          <span class="gp-kicker">Public sample</span>
          <h2 class="gp-section-head__title">大数据样本</h2>
        </div>
        <n-button size="small" quaternary :loading="surveyLoading" @click="emit('refresh-survey')">
          <template #icon><n-icon :component="RefreshOutline" /></template>
          重新读取
        </n-button>
      </header>
      <div class="growth-insights__survey-body">
        <div class="growth-insights__survey-metric">
          <strong class="gp-num">{{ surveyCoverage }}</strong>
          <span>位干员的公开样本</span>
        </div>
        <p class="growth-insights__survey-note">{{ surveyNote }}</p>
        <p class="growth-insights__survey-legal">
          比例用于发现养成方向，不代表强度排名；缺失样本显示“暂无样本”。模组按已开启统计，精一率包含精二干员。
          数据来自
          <a
            href="https://ark.yituliu.cn/survey/operators"
            target="_blank"
            rel="noopener noreferrer"
            >明日方舟一图流<sup>↗</sup></a
          >，依
          <a
            href="https://creativecommons.org/licenses/by-nc/4.0/deed.zh"
            target="_blank"
            rel="noopener noreferrer"
            >CC BY-NC 4.0<sup>↗</sup></a
          >署名非商业使用。统计展示由 Mower 独立实现，公开样本仅供参考；读取公开样本不上传个人练度。
        </p>
        <a
          class="gp-link growth-insights__survey-link"
          href="https://ark.yituliu.cn/survey/operators"
          target="_blank"
          rel="noopener noreferrer"
        >
          查看数据来源
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
