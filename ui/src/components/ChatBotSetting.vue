<script setup>
import { computed } from 'vue'
import MowerAIIcon from './MowerAIIcon.vue'
import { useConfigStore } from '@/stores/config'
import { storeToRefs } from 'pinia'
const store = useConfigStore()
const { ai_key, ai_custom_key, ai_type, ai_base_url, ai_model, ai_deepseek_model } =
  storeToRefs(store)
const customModel = computed(() => ['custom-local', 'custom-online'].includes(ai_type.value))
const modelKey = computed({
  get: () => (customModel.value ? ai_custom_key.value : ai_key.value),
  set: (value) => {
    if (customModel.value) ai_custom_key.value = value
    else ai_key.value = value
  }
})
const type_options = [
  { label: 'DeepSeek', value: 'deepseek' },
  { label: '本地模型（OpenAI 兼容）', value: 'custom-local' },
  { label: '在线模型 / 中转商（OpenAI 兼容）', value: 'custom-online' }
]
const deepseekModels = [
  { label: 'DeepSeek Flash（deepseek-flash）', value: 'deepseek-flash' },
  { label: 'DeepSeek V4 Pro（deepseek-v4-pro）', value: 'deepseek-v4-pro' }
]
</script>
<template>
  <n-card class="ai-settings-card">
    <template #header>
      <div class="ai-settings-header">
        <div class="card-title">AI 助手与模型服务</div>
        <help-text
          ><div>支持 DeepSeek、本地 OpenAI 兼容接口及在线模型服务。</div>
          <div>
            DeepSeek 密钥请前往
            <a href="https://platform.deepseek.com/api_keys" target="_blank">DeepSeek 官网</a>
            获取， 或填写自己的模型接口。
          </div>
        </help-text>
      </div>
    </template>
    <div class="service-overview">
      <n-icon :component="MowerAIIcon" aria-hidden="true" />
      <div>
        <strong>{{
          type_options.find((option) => option.value === ai_type)?.label || '选择模型服务'
        }}</strong>
        <p>
          {{
            ai_type === 'deepseek'
              ? '选择预设或填写模型 ID，使用 DeepSeek 官方服务。'
              : ai_type === 'custom-local'
                ? '连接本机或局域网中的 OpenAI 兼容服务。'
                : '使用服务商提供的 HTTPS 接口和模型 ID。'
          }}
        </p>
      </div>
    </div>
    <n-form label-placement="top" class="model-form">
      <n-form-item label="模型服务" class="service-field">
        <n-select v-model:value="ai_type" :options="type_options" />
      </n-form-item>
      <n-form-item v-if="ai_type === 'deepseek'" label="DeepSeek 模型" class="deepseek-field">
        <n-select
          v-model:value="ai_deepseek_model"
          :options="deepseekModels"
          filterable
          tag
          placeholder="选择预设，或输入模型 ID 后回车"
        />
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
      <n-form-item label="API 密钥" class="model-key">
        <n-input
          type="password"
          v-model:value="modelKey"
          :placeholder="ai_type === 'custom-local' ? '本地接口通常可留空' : '请输入 API 密钥'"
          show-password-on="click"
          autocomplete="off"
        />
      </n-form-item>
      <div class="model-service-note">
        <span>修改后自动保存</span>
        <p>
          所选报错的精简日志会发送到这里配置的模型服务。本地接口需兼容 OpenAI Chat
          Completions，在线接口必须使用 HTTPS。
        </p>
      </div>
    </n-form>
  </n-card>
</template>

<style scoped>
.ai-settings-header {
  display: flex;
  align-items: center;
  gap: 8px;
}
.service-overview {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 20px;
  padding: 14px 16px;
  border-radius: 12px;
  background: var(--mower-control-surface);
}
.service-overview > .n-icon {
  margin-top: 2px;
  font-size: 26px;
  color: var(--mower-primary-text);
}
.service-overview strong {
  font-size: 14px;
  font-weight: 550;
}
.service-overview p {
  margin: 5px 0 0;
  font-size: 12px;
  line-height: 1.7;
  color: var(--mower-text-muted);
}
.model-form {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0 16px;
}
.model-form :deep(.n-form-item) {
  min-width: 0;
}
.service-field,
.deepseek-field,
.model-key,
.model-service-note {
  grid-column: 1 / -1;
}
.model-service-note {
  padding-top: 4px;
  font-size: 12px;
  color: var(--mower-text-muted);
}
.model-service-note > span {
  color: var(--mower-success-text);
}
.model-service-note p {
  margin: 6px 0 0;
  line-height: 1.7;
  text-wrap: pretty;
}
@media (max-width: 640px) {
  .model-form {
    grid-template-columns: 1fr;
  }
}
</style>
