<script setup>
import { computed } from 'vue'
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
const selectMenuProps = { class: 'settings-select-menu' }
</script>
<template>
  <n-card
    title="AI 助手与模型服务"
    class="ai-settings-card"
    data-settings-keywords="DeepSeek Flash Pro OpenAI 本地模型 在线模型 中转商 接口地址 模型名称 模型 ID API 密钥"
  >
    <div class="ai-settings-summary">
      <p>配置 AI 助手和报错分析使用的模型服务。</p>
      <span>修改后自动保存</span>
    </div>
    <n-form label-placement="top" class="model-form settings-form-stacked" :show-feedback="false">
      <n-form-item label="模型服务">
        <n-select
          v-model:value="ai_type"
          class="settings-select-wrap"
          :options="type_options"
          placement="bottom-end"
          :virtual-scroll="false"
          :menu-props="selectMenuProps"
          :consistent-menu-width="false"
          aria-label="模型服务"
        />
        <p class="ai-field-description">
          {{
            ai_type === 'deepseek'
              ? '选择预设或填写模型 ID，使用 DeepSeek 官方服务。'
              : ai_type === 'custom-local'
                ? '连接本机或局域网中的 OpenAI 兼容服务。'
                : '使用服务商提供的 HTTPS 接口和模型 ID。'
          }}
        </p>
      </n-form-item>
      <n-form-item v-if="ai_type === 'deepseek'" label="DeepSeek 模型">
        <n-select
          v-model:value="ai_deepseek_model"
          class="settings-select-wrap"
          :consistent-menu-width="false"
          :options="deepseekModels"
          placement="bottom-end"
          :virtual-scroll="false"
          :menu-props="selectMenuProps"
          aria-label="DeepSeek 模型"
          filterable
          tag
          placeholder="选择预设，或输入模型 ID 后回车"
        />
      </n-form-item>
      <template v-if="customModel">
        <n-form-item label="接口地址">
          <n-input
            v-model:value="ai_base_url"
            :input-props="{ 'aria-label': '接口地址', spellcheck: false }"
            :placeholder="
              ai_type === 'custom-local'
                ? 'http://127.0.0.1:11434/v1'
                : 'https://api.example.com/v1'
            "
          />
        </n-form-item>
        <n-form-item label="模型名称">
          <n-input
            v-model:value="ai_model"
            :input-props="{ 'aria-label': '模型名称', spellcheck: false }"
            placeholder="填写服务商提供的模型 ID"
          />
        </n-form-item>
      </template>
      <n-form-item label="API 密钥">
        <n-input
          type="password"
          v-model:value="modelKey"
          :placeholder="ai_type === 'custom-local' ? '本地接口通常可留空' : '请输入 API 密钥'"
          show-password-on="click"
          autocomplete="off"
          :input-props="{ 'aria-label': 'API 密钥' }"
        />
        <p v-if="ai_type === 'deepseek'" class="ai-field-description">
          前往
          <a href="https://platform.deepseek.com/api_keys" target="_blank">DeepSeek 官网</a> 获取
          API 密钥。
        </p>
      </n-form-item>
    </n-form>
    <div class="ai-service-note">
      <p>所选报错的精简日志会发送到这里配置的模型服务。</p>
      <p v-if="customModel">本地接口需兼容 OpenAI Chat Completions，在线接口必须使用 HTTPS。</p>
    </div>
  </n-card>
</template>

<style scoped>
.ai-settings-summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 6px 16px;
  margin-bottom: 20px;
  color: var(--mower-text-muted);
  font-size: 12px;
  line-height: 1.65;
}

.ai-settings-summary p,
.ai-field-description,
.ai-service-note p {
  margin: 0;
  overflow-wrap: anywhere;
}

.ai-field-description,
.ai-service-note {
  color: var(--mower-text-muted);
  font-size: 12px;
  line-height: 1.65;
}

.ai-service-note {
  margin-top: 20px;
  padding: 12px 14px;
  border-radius: 8px;
  background: var(--mower-control-surface);
}

.ai-service-note p + p {
  margin-top: 4px;
}

.ai-settings-card .model-form {
  display: grid;
  gap: 18px;
}

.model-form :deep(.n-form-item) {
  min-width: 0;
}
</style>
