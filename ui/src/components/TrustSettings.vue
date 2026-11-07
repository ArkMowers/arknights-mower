<script setup>
import { storeToRefs } from 'pinia'
import { useConfigStore } from '@/stores/config'

defineProps({
  showEnable: { type: Boolean, default: true },
  showInterval: { type: Boolean, default: true },
  compactHelp: { type: Boolean, default: false }
})
const descriptions = {
  overview:
    '在日常任务期间一起检查基建副手和已建造活动室。默认信赖达到200%才更换；两类名单各自不重复，允许同一干员同时担任副手和活动室使用者，保留原工作状态。',
  threshold:
    '各位置达到阈值后，存在低于阈值的合格候选时才更换。最高位置副手优先安排最低信赖者。没有低于阈值的候选时，现任保留至200%，再选择信赖最低且未满200%的干员。',
  completion:
    '两类名单分别检查；本类名单以外的合格候选均满200%时，保留当前安排并跳过该类剩余位置。下次到达间隔后重新检查，新获得的干员仍可入选。'
}
const {
  trust_rotation_enable,
  trust_rotation_prefer_low,
  trust_rotation_threshold,
  trust_rotation_interval
} = storeToRefs(useConfigStore())
</script>

<template>
  <n-card title="自动切换信赖">
    <n-space vertical :size="16">
      <n-checkbox v-if="showEnable" v-model:checked="trust_rotation_enable"
        >自动切换信赖</n-checkbox
      >
      <n-text v-if="!compactHelp" depth="3">{{ descriptions.overview }}</n-text>
      <n-space align="center">
        <n-checkbox v-model:checked="trust_rotation_prefer_low" :disabled="!trust_rotation_enable"
          >优先选择信赖小于</n-checkbox
        >
        <n-input-number
          v-model:value="trust_rotation_threshold"
          :disabled="!trust_rotation_enable || !trust_rotation_prefer_low"
          :min="1"
          :max="200"
          :precision="0"
          style="width: 110px"
          :input-props="{ 'aria-label': '优先信赖阈值' }"
          ><template #suffix>%</template></n-input-number
        >
        <n-text>的干员</n-text>
        <help-text v-if="compactHelp" label="信赖轮换说明">
          <p>{{ descriptions.overview }}</p>
          <p v-if="trust_rotation_prefer_low">{{ descriptions.threshold }}</p>
          <p>{{ descriptions.completion }}</p>
        </help-text>
      </n-space>
      <n-text v-if="!compactHelp && trust_rotation_prefer_low" depth="3">{{
        descriptions.threshold
      }}</n-text>
      <n-space v-if="showInterval" align="center">
        <n-text>检查间隔</n-text>
        <n-input-number
          v-model:value="trust_rotation_interval"
          :disabled="!trust_rotation_enable"
          :min="1"
          :max="168"
          style="width: 130px"
          :input-props="{ 'aria-label': '信赖检查间隔' }"
          ><template #suffix>小时</template></n-input-number
        >
      </n-space>
      <n-text v-if="!compactHelp" depth="3">{{ descriptions.completion }}</n-text>
    </n-space>
  </n-card>
</template>
