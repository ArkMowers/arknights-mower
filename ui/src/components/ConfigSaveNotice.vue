<script setup>
import { storeToRefs } from 'pinia'
import { useConfigStore } from '@/stores/config'
import StatusNotification from '@/components/StatusNotification.vue'
import { i18n } from '@/i18n'
const { t } = i18n.global

const config = useConfigStore()
const { config_save_error, config_saving } = storeToRefs(config)
</script>

<template>
  <StatusNotification
    :show="!!config_save_error"
    type="error"
    role="alert"
    :title="t('common.configSaveFailed')"
    :content="t('common.editsRetained', { message: config_save_error })"
  >
    <template #action>
      <n-button size="small" :loading="config_saving" @click="config.save_config().catch(() => {})">
        {{ t('common.retrySave') }}
      </n-button>
    </template>
  </StatusNotification>
</template>
