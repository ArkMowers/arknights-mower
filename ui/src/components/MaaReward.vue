<script setup>
import { i18n } from '@/i18n'
const { t } = i18n.global

import { useConfigStore } from '@/stores/config'
import { storeToRefs } from 'pinia'
import { computed } from 'vue'
import { getMaaRewardSelection, setTaskEnabled } from '@/task-workflow/model'

const store = useConfigStore()

const { maa_mail, maa_recruit, maa_orundum, maa_mining, maa_specialaccess, maa_signinevent } =
  storeToRefs(store)
const selection = computed(() => getMaaRewardSelection(store))
function setRewardsEnabled(value) {
  setTaskEnabled(store, 'rewards', value)
}
</script>

<template>
  <n-card>
    <template #header>
      <n-flex align="center" :size="8">
        <n-checkbox
          :checked="selection.checked"
          :indeterminate="selection.indeterminate"
          :aria-label="t('tasks.enableMaaRewards')"
          @update:checked="setRewardsEnabled"
        />
        <span>{{ t('tasks.maaRewards') }}</span>
      </n-flex>
    </template>
    <n-flex vertical>
      <n-checkbox v-model:checked="maa_mail">
        <div class="item">{{ t('tasks.allMailRewards') }}</div>
      </n-checkbox>
      <n-divider />
      <n-checkbox v-model:checked="maa_recruit">
        <div class="item">{{ t('tasks.dailyFreePull') }}</div>
      </n-checkbox>
      <n-divider />
      <n-checkbox v-model:checked="maa_orundum">
        <div class="item">{{ t('tasks.luckyWallOrundum') }}</div>
      </n-checkbox>
      <n-divider />
      <n-checkbox v-model:checked="maa_mining">
        <div class="item">{{ t('tasks.miningOrundum') }}</div>
      </n-checkbox>
      <n-divider />
      <n-checkbox v-model:checked="maa_specialaccess">
        <div class="item">{{ t('tasks.giftMonthlyCard') }}</div>
      </n-checkbox>
      <n-divider />
      <n-flex align="center">
        <n-checkbox v-model:checked="maa_signinevent">
          <div class="item">{{ t('maaActivities.signinReward') }}</div>
        </n-checkbox>
        <help-text>{{ t('maaActivities.signinHelp') }}</help-text>
      </n-flex>
    </n-flex>
  </n-card>
</template>

<style scoped>
.item {
  font-weight: 500;
  font-size: 16px;
}

.n-divider:not(.n-divider--vertical) {
  margin: 6px 0;
}
</style>
