<script setup>
import { storeToRefs } from 'pinia'
import { useConfigStore } from '@/stores/config'
import StatusNotification from '@/components/StatusNotification.vue'

const config = useConfigStore()
const { config_save_error, config_saving } = storeToRefs(config)
</script>

<template>
  <StatusNotification
    :show="!!config_save_error"
    type="error"
    role="alert"
    title="配置保存失败"
    :content="`${config_save_error}。修改仍保留在当前页面。`"
  >
    <template #action>
      <n-button size="small" :loading="config_saving" @click="config.save_config().catch(() => {})">
        重试保存
      </n-button>
    </template>
  </StatusNotification>
</template>
