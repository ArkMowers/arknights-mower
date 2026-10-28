<script setup>
import { i18n } from '@/i18n'
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
const type_options = computed(() => [
  { label: 'DeepSeek', value: 'deepseek' },
  { label: i18n.global.t('settings.ai.localModelOpenaiCompatible'), value: 'custom-local' },
  {
    label: i18n.global.t('settings.ai.onlineProviderRelayOpenaiCompatible'),
    value: 'custom-online'
  }
])
const deepseekModels = [
  { label: 'DeepSeek Flash（deepseek-flash）', value: 'deepseek-flash' },
  { label: 'DeepSeek V4 Pro（deepseek-v4-pro）', value: 'deepseek-v4-pro' }
]
const selectMenuProps = { class: 'settings-select-menu' }
</script>
<template>
  <n-card
    :title="i18n.global.t('settings.ai.aiAssistantModelService')"
    class="ai-settings-card"
    data-settings-keywords="DeepSeek Flash Pro OpenAI 本地模型 在线模型 中转商 接口地址 模型名称 模型 ID API 密钥"
  >
    <div class="ai-settings-summary">
      <p>{{ i18n.global.t('settings.ai.configureTheModelServiceUsedByThe') }}</p>
      <span>{{ i18n.global.t('settings.ai.changesSaveAutomatically') }}</span>
    </div>
    <n-form label-placement="top" class="model-form settings-form-stacked" :show-feedback="false">
      <n-form-item :label="i18n.global.t('settings.ai.modelService')">
        <n-select
          v-model:value="ai_type"
          class="settings-select-wrap"
          :options="type_options"
          placement="bottom-end"
          :virtual-scroll="false"
          :menu-props="selectMenuProps"
          :consistent-menu-width="false"
          :aria-label="i18n.global.t('settings.ai.modelService')"
        />
        <p class="ai-field-description">
          {{
            ai_type === 'deepseek'
              ? i18n.global.t('settings.ai.selectAPresetOrEnterAModel')
              : ai_type === 'custom-local'
                ? i18n.global.t('settings.ai.connectToAnOpenaiCompatibleServiceOn')
                : i18n.global.t('settings.ai.useTheHttpsEndpointAndModelId')
          }}
        </p>
      </n-form-item>
      <n-form-item
        v-if="ai_type === 'deepseek'"
        :label="i18n.global.t('settings.ai.deepseekModel')"
      >
        <n-select
          v-model:value="ai_deepseek_model"
          class="settings-select-wrap"
          :consistent-menu-width="false"
          :options="deepseekModels"
          placement="bottom-end"
          :virtual-scroll="false"
          :menu-props="selectMenuProps"
          :aria-label="i18n.global.t('settings.ai.deepseekModel')"
          filterable
          tag
          :placeholder="i18n.global.t('settings.ai.selectAPresetOrEnterAModel2')"
        />
      </n-form-item>
      <template v-if="customModel">
        <n-form-item :label="i18n.global.t('settings.ai.apiEndpoint')">
          <n-input
            v-model:value="ai_base_url"
            :input-props="{
              'aria-label': i18n.global.t('settings.ai.apiEndpoint'),
              spellcheck: false
            }"
            :placeholder="
              ai_type === 'custom-local'
                ? 'http://127.0.0.1:11434/v1'
                : 'https://api.example.com/v1'
            "
          />
        </n-form-item>
        <n-form-item :label="i18n.global.t('settings.ai.modelName')">
          <n-input
            v-model:value="ai_model"
            :input-props="{
              'aria-label': i18n.global.t('settings.ai.modelName'),
              spellcheck: false
            }"
            :placeholder="i18n.global.t('settings.ai.enterTheModelIdSuppliedByYour')"
          />
        </n-form-item>
      </template>
      <n-form-item :label="i18n.global.t('settings.ai.apiKey')">
        <n-input
          type="password"
          v-model:value="modelKey"
          :placeholder="
            ai_type === 'custom-local'
              ? i18n.global.t('settings.ai.usuallyOptionalForALocalService')
              : i18n.global.t('settings.ai.enterYourApiKey')
          "
          show-password-on="click"
          autocomplete="off"
          :input-props="{ 'aria-label': i18n.global.t('settings.ai.apiKey') }"
        />
        <p v-if="ai_type === 'deepseek'" class="ai-field-description">
          {{ i18n.global.t('settings.ai.visit') }}
          <a href="https://platform.deepseek.com/api_keys" target="_blank">{{
            i18n.global.t('settings.ai.deepseekSWebsite')
          }}</a>
          {{ i18n.global.t('settings.ai.toObtainAnApiKey') }}
        </p>
      </n-form-item>
    </n-form>
    <div class="ai-service-note">
      <p>{{ i18n.global.t('settings.ai.aShortenedLogForTheSelectedError') }}</p>
      <p v-if="customModel">
        {{ i18n.global.t('settings.ai.localServicesMustSupportOpenaiChatCompletions') }}
      </p>
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
