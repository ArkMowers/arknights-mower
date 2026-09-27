<script setup>
import { computed } from 'vue'
import { useConfigStore } from '@/stores/config'
import { storeToRefs } from 'pinia'
const store = useConfigStore()
const { ai_key, ai_custom_key, ai_type, ai_base_url, ai_model } = storeToRefs(store)
const customModel = computed(() => ['custom-local', 'custom-online'].includes(ai_type.value))
const modelKey = computed({
  get: () => (customModel.value ? ai_custom_key.value : ai_key.value),
  set: (value) => {
    if (customModel.value) ai_custom_key.value = value
    else ai_key.value = value
  }
})
const type_options = [
  { label: 'Deepseek V4 Flash', value: 'deepseek-v4-flash' },
  { label: 'Deepseek V4 Pro', value: 'deepseek-v4-pro' },
  { label: '本地模型（OpenAI 兼容）', value: 'custom-local' },
  { label: '在线模型 / 中转商（OpenAI 兼容）', value: 'custom-online' }
]
</script>
<template>
  <n-card>
    <template #header>
      <div class="card-title">AI 助手与模型服务</div>
      <help-text
        ><div>支持 Deepseek、本地 OpenAI 兼容接口及在线模型服务。</div>
        <div>
          Deepseek 密钥请前往
          <a href="https://platform.deepseek.com/api_keys" target="_blank">Deepseek 官网</a> 获取，
          或填写自己的模型接口。
        </div>
      </help-text>
    </template>
    <n-form label-placement="left" label-width="auto">
      <n-form-item label="AI 类型">
        <n-select v-model:value="ai_type" :options="type_options" />
      </n-form-item>
      <template v-if="customModel">
        <n-form-item label="接口地址">
          <n-input
            v-model:value="ai_base_url"
            :placeholder="
              ai_type === 'custom-local'
                ? 'http://127.0.0.1:11434/v1'
                : 'https://api.example.com/v1'
            "
          />
        </n-form-item>
        <n-form-item label="模型名称">
          <n-input v-model:value="ai_model" placeholder="填写服务商提供的模型 ID" />
        </n-form-item>
      </template>
      <n-form-item label="API 密钥">
        <n-input
          type="password"
          v-model:value="modelKey"
          :placeholder="ai_type === 'custom-local' ? '本地接口通常可留空' : '请输入 API 密钥'"
          show-password-on="click"
        />
      </n-form-item>
      <n-text depth="3">
        本地模型请使用兼容 OpenAI Chat Completions 的接口；在线接口必须使用 HTTPS。使用 AI
        分析时，所选报错的精简日志会发送到这里配置的服务。
      </n-text>
    </n-form>
  </n-card>
</template>
