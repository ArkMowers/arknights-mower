<script setup>
import { i18n } from '@/i18n'
const { t } = i18n.global

defineOptions({ name: 'DepotSourceSettings' })
defineProps({ showEnable: { type: Boolean, default: true } })
const emit = defineEmits(['configure-accounts'])

import { useConfigStore } from '@/stores/config'
import { storeToRefs } from 'pinia'
const store = useConfigStore()
const { maa_depot_enable, skland_info } = storeToRefs(store)
</script>
<template>
  <n-card>
    <template #header>
      <span v-if="showEnable">{{ t('tasks.depotMixedReading') }}</span>
      <span v-else>{{ t('tasks.materialSource') }}</span>
      <help-text
        >{{ t('tasks.depotAccountHelpBefore') }}<b>{{ t('tasks.firstAccount') }}</b
        >{{ t('tasks.accountFragment') }}<b>{{ t('tasks.specifiedServer') }}</b
        >{{ t('tasks.materialsFragment') }}</help-text
      >
    </template>
    <n-form label-placement="left" :show-feedback="false" label-width="140" label-align="left">
      <n-form-item v-if="showEnable" :label="t('tasks.enableMixedReading')">
        <n-switch v-model:value="maa_depot_enable" :aria-label="t('tasks.enableMixedReading')" />
      </n-form-item>
      <div v-if="!showEnable && !skland_info?.length" class="depot-accounts-empty">
        <span>{{ t('tasks.addSklandFirst') }}</span>
        <n-button size="small" type="primary" secondary @click="emit('configure-accounts')">{{
          t('tasks.addSklandAccount')
        }}</n-button>
      </div>
      <div
        v-for="account_info in skland_info"
        :key="account_info.account"
        class="depot-account-row"
      >
        <div class="depot-account-name">
          {{ t('tasks.sklandAccountPrefix') }}{{ account_info.account }}
        </div>
        <n-radio-group v-model:value="account_info.cultivate_select">
          <n-flex>
            <n-radio :value="true">{{ t('tasks.officialServer') }}</n-radio>
            <n-radio :value="false">{{ t('tasks.bilibiliServer') }}</n-radio>
          </n-flex>
        </n-radio-group>
      </div>
    </n-form>
  </n-card>
</template>

<style scoped>
.depot-accounts-empty,
.depot-account-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px 24px;
}

.depot-account-row + .depot-account-row {
  margin-top: 12px;
}

.depot-account-name {
  min-width: 0;
  overflow-wrap: anywhere;
}

.depot-account-row :deep(.n-radio-group) {
  flex-shrink: 0;
}
</style>
