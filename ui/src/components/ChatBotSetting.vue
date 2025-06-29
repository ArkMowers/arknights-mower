<script setup>
import { useConfigStore } from '@/stores/config'
import { storeToRefs } from 'pinia'
const store = useConfigStore()
const { ai_key, ai_type } = storeToRefs(store)
const type_options = [{ label: 'Deepseek', value: 'deepseek' }]
</script>
<template>
  <n-card>
    <template #header>
      <div class="card-title">本地 AI 助手</div>
      <help-text>目前仅支持Deepseek</help-text>
    </template>
    <n-form label-placement="left" label-width="auto">
      <n-form-item label="AI 类型">
        <n-select v-model:value="ai_type" :options="type_options" />
      </n-form-item>
      <n-form-item label="API 密钥">
        <n-input
          type="password"
          v-model:value="ai_key"
          placeholder="请输入API密钥"
          show-password-on="click"
        />
      </n-form-item>
    </n-form>
  </n-card>
</template>
