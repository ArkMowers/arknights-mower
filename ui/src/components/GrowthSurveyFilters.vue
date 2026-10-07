<template>
  <n-card size="small" title="大数据养成推荐 / 干员筛选" class="survey-filters">
    <template #header-extra>
      <n-button size="small" :loading="loading" @click="$emit('refresh')">读取统计</n-button>
    </template>
    <n-alert v-if="survey.error" type="warning" :bordered="false" style="margin-bottom: 12px">
      {{ survey.error }}
    </n-alert>
    <div class="threshold-rows">
      <div v-for="dimension in surveyDimensions" :key="dimension.key" class="threshold-row">
        <n-tooltip>
          <template #trigger
            ><n-text strong>{{ dimension.label }}</n-text></template
          >
          {{ dimension.detail }}；分母为样本中拥有该干员的人数。
        </n-tooltip>
        <div class="threshold-controls">
          <n-scrollbar x-scrollable class="threshold-scroll">
            <div
              class="threshold-segments"
              :class="`tone-${dimension.key}`"
              role="group"
              :aria-label="`${dimension.label}阈值`"
              :style="{ '--foreground': theme.textColor1 }"
            >
              <button
                v-for="rate in surveyThresholds"
                :key="rate"
                type="button"
                :disabled="!hasSamples"
                :aria-pressed="modelValue[dimension.key] === rate"
                :aria-label="`${dimension.label}至少${rate}%`"
                :class="{ selected: modelValue[dimension.key] === rate }"
                @click="updateRate(dimension.key, rate)"
              >
                {{ rate }}%
              </button>
            </div>
          </n-scrollbar>
          <n-button
            size="small"
            :type="modelValue[dimension.key] === null ? 'primary' : 'default'"
            :secondary="modelValue[dimension.key] === null"
            @click="update(dimension.key, null)"
            >不限</n-button
          >
        </div>
      </div>
    </div>
    <n-space align="center" :size="12" style="margin-top: 14px">
      <n-checkbox
        :checked="modelValue.hideCompleted"
        :disabled="!hasSamples"
        @update:checked="update('hideCompleted', $event)"
        >隐藏已满足推荐条件的干员</n-checkbox
      >
      <n-select
        :value="modelValue.sort"
        :options="sortOptions"
        size="small"
        style="width: 150px"
        @update:value="update('sort', $event)"
      />
    </n-space>
    <n-divider style="margin: 14px 0" />
    <slot />
    <n-text depth="3" class="survey-source">
      统计最多每 24
      小时重新获取。比例用于发现养成方向，不代表强度排名。模组按已开启统计，精一率包含精二干员。
      <template v-if="survey.fetched_at"
        >统计获取于 {{ new Date(survey.fetched_at * 1000).toLocaleString() }}。</template
      >
      数据来自<a
        href="https://ark.yituliu.cn/survey/operators"
        target="_blank"
        rel="noopener noreferrer"
        >明日方舟一图流</a
      >， 依<a
        href="https://creativecommons.org/licenses/by-nc/4.0/deed.zh"
        target="_blank"
        rel="noopener noreferrer"
        >CC BY-NC 4.0</a
      >署名非商业使用，数据按原样提供。本功能为 Mower
      独立实现，属于非官方样本统计；推荐统计仅拉取公开数据，不上传个人练度。
    </n-text>
  </n-card>
</template>
<script setup>
import { computed } from 'vue'
import { useThemeVars } from 'naive-ui'
const theme = useThemeVars()
import { surveyDimensions, surveyThresholds } from '@/utils/growthSurvey'
const props = defineProps({
  modelValue: { type: Object, required: true },
  survey: { type: Object, required: true },
  loading: Boolean
})
const emit = defineEmits(['update:modelValue', 'refresh'])
const hasSamples = computed(() => props.survey.operators?.some((row) => row.own > 0))
function updateRate(key, rate) {
  update(key, props.modelValue[key] === rate ? null : rate)
}
const sortOptions = [
  { label: '默认排序', value: 'default' },
  { label: '推荐比例优先', value: 'recommendation' },
  { label: '等级从高到低', value: 'level' }
]
function update(key, value) {
  emit('update:modelValue', { ...props.modelValue, [key]: value })
}
</script>
<style scoped>
.survey-filters {
  margin-top: 16px;
}
.threshold-rows {
  display: grid;
  gap: 12px;
}
.threshold-row {
  display: grid;
  grid-template-columns: 100px minmax(0, 1fr);
  align-items: center;
  gap: 8px;
}
.threshold-controls {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  padding: 2px 0;
  align-items: center;
  gap: 14px;
}
.threshold-scroll {
  min-width: 0;
  border-radius: 999px;
}
.threshold-segments {
  --tone: #b98312;
  display: grid;
  grid-template-columns: repeat(10, minmax(54px, 1fr));
  min-width: 570px;
  padding: 4px;
  gap: 3px;
  border-radius: 999px;
  background: color-mix(in srgb, var(--tone) 10%, transparent);
  color: color-mix(in srgb, var(--tone) 78%, var(--foreground));
}
.tone-mastery {
  --tone: #2784d9;
}
.tone-module {
  --tone: #ee8a20;
}
.threshold-segments button {
  color: inherit;
  background: transparent;
  border: none;
  border-radius: 999px;
  padding: 9px 3px;
  font: inherit;
  font-size: 12px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  cursor: pointer;
}
.threshold-segments button:hover:not(:disabled),
.threshold-segments button.selected {
  background: color-mix(in srgb, var(--tone) 15%, transparent);
}
.threshold-segments button.selected {
  box-shadow: inset 0 0 0 1.5px currentColor;
}
.threshold-segments button:focus-visible {
  outline: 2px solid currentColor;
  outline-offset: -2px;
}
.threshold-segments button:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}
.survey-source {
  display: block;
  margin-top: 12px;
  font-size: 11px;
  line-height: 1.8;
}
.survey-source a {
  color: inherit;
  text-decoration: underline;
}
@media (max-width: 600px) {
  .threshold-row {
    grid-template-columns: 1fr;
  }
}
</style>
