<script setup>
import { i18n } from '@/i18n'
const { t } = i18n.global

defineOptions({ name: 'RecruitSettings' })
defineProps({
  showEnable: { type: Boolean, default: true },
  showInterval: { type: Boolean, default: true }
})

import { useConfigStore } from '@/stores/config'
const store = useConfigStore()
import { storeToRefs } from 'pinia'
const {
  recruit_enable,
  recruitment_permit,
  recruit_robot,
  recruit_gap,
  recruit_auto_5,
  recruit_auto_only5
} = storeToRefs(store)
import { inject } from 'vue'

const mobile = inject('mobile')
</script>

<template>
  <n-card>
    <template v-if="showEnable" #header>
      <n-checkbox v-model:checked="recruit_enable" :aria-label="t('tasks.enableRecruitment')">
        <div class="card-title">{{ t('tasks.recruitment') }}</div>
      </n-checkbox>
    </template>
    <n-form
      :label-placement="mobile ? 'top' : 'left'"
      :show-feedback="false"
      label-width="140"
      label-align="left"
    >
      <n-form-item v-if="showInterval">
        <template #label>
          <span>{{ t('tasks.startInterval') }}</span>
          <help-text>{{ t('tasks.decimalAllowed') }}</help-text>
        </template>
        <mower-input-number v-model:value="recruit_gap">
          <template #suffix>{{ t('tasks.hours') }}</template>
        </mower-input-number>
      </n-form-item>
      <n-form-item>
        <template #label>
          <span>{{ t('tasks.threeStarThreshold') }}</span>
          <help-text>{{ t('tasks.recruitmentPermitHelp') }}</help-text>
        </template>
        <mower-input-number v-model:value="recruitment_permit">
          <template #suffix>{{ t('tasks.permits') }}</template>
        </mower-input-number>
      </n-form-item>
      <n-form-item :label="t('tasks.fiveStarPolicy')">
        <n-radio-group v-model:value="recruit_auto_5">
          <n-space justify="start">
            <n-radio :value="1">{{ t('tasks.automaticSelection') }}</n-radio>
            <n-radio :value="2">{{ t('tasks.manualSelection') }}</n-radio>
          </n-space>
        </n-radio-group>
      </n-form-item>
      <n-form-item v-if="recruit_auto_5 === 2" :show-label="false">
        <n-checkbox v-model:checked="recruit_auto_only5">{{
          t('tasks.uniqueFiveStarTags')
        }}</n-checkbox>
      </n-form-item>
      <n-form-item :show-label="false">
        <n-checkbox v-model:checked="recruit_robot">{{ t('tasks.preserveRobotTags') }}</n-checkbox>
      </n-form-item>
    </n-form>
  </n-card>
</template>

<style scoped lang="scss">
p {
  margin: 0 0 8px 0;
}

h4 {
  margin: 12px 0 10px 0;
}

.big-table {
  margin-top: 10px;
  max-width: 320px;

  th {
    text-align: center;
  }

  tr {
    width: 70px;
  }

  td {
    height: 24px;

    &:nth-child(1) {
      width: 70px;
      text-align: center;
    }
    &:nth-child(2) {
      width: 420px;
    }
  }
}

.final {
  margin: 16px 0 0;
}
</style>
