<script setup>
import { i18n } from '@/i18n'
const { t } = i18n.global

import { storeToRefs } from 'pinia'
import { useConfigStore } from '@/stores/config'

defineProps({
  showEnable: { type: Boolean, default: true },
  showInterval: { type: Boolean, default: true },
  compactHelp: { type: Boolean, default: false }
})
const descriptions = {
  get overview() {
    return t('tasks.trustOverview')
  },
  get threshold() {
    return t('tasks.trustThresholdHelp')
  },
  get completion() {
    return t('tasks.trustCompleteHelp')
  }
}
const {
  trust_rotation_enable,
  trust_rotation_prefer_low,
  trust_rotation_threshold,
  trust_rotation_interval
} = storeToRefs(useConfigStore())
</script>

<template>
  <n-card :title="t('tasks.trustRotation')">
    <n-space vertical :size="16">
      <n-checkbox v-if="showEnable" v-model:checked="trust_rotation_enable">{{
        t('tasks.trustRotation')
      }}</n-checkbox>
      <n-text v-if="!compactHelp" depth="3">{{ descriptions.overview }}</n-text>
      <n-space align="center">
        <n-checkbox
          v-model:checked="trust_rotation_prefer_low"
          :disabled="!trust_rotation_enable"
          >{{ t('tasks.preferTrustBelow') }}</n-checkbox
        >
        <n-input-number
          v-model:value="trust_rotation_threshold"
          :disabled="!trust_rotation_enable || !trust_rotation_prefer_low"
          :min="1"
          :max="200"
          :precision="0"
          style="width: 110px"
          :input-props="{ 'aria-label': t('tasks.trustPriorityThreshold') }"
          ><template #suffix>%</template></n-input-number
        >
        <n-text>{{ t('tasks.trustSuffix') }}</n-text>
        <help-text v-if="compactHelp" :label="t('tasks.trustRotationHelp')">
          <p>{{ descriptions.overview }}</p>
          <p v-if="trust_rotation_prefer_low">{{ descriptions.threshold }}</p>
          <p>{{ descriptions.completion }}</p>
        </help-text>
      </n-space>
      <n-text v-if="!compactHelp && trust_rotation_prefer_low" depth="3">{{
        descriptions.threshold
      }}</n-text>
      <n-space v-if="showInterval" align="center">
        <n-text>{{ t('tasks.inspectionInterval') }}</n-text>
        <n-input-number
          v-model:value="trust_rotation_interval"
          :disabled="!trust_rotation_enable"
          :min="1"
          :max="168"
          style="width: 130px"
          :input-props="{ 'aria-label': t('tasks.trustInspectionInterval') }"
          ><template #suffix>{{ t('tasks.hours') }}</template></n-input-number
        >
      </n-space>
      <n-text v-if="!compactHelp" depth="3">{{ descriptions.completion }}</n-text>
    </n-space>
  </n-card>
</template>
