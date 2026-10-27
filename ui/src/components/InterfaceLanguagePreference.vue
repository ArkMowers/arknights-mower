<script setup>
import { computed, onMounted } from 'vue'
import { storeToRefs } from 'pinia'
import { i18n, getInterfaceLanguageOptions } from '@/i18n'
import { useGuiStore } from '@/stores/gui'

const { t } = i18n.global
const gui = useGuiStore()
const languageOptions = computed(getInterfaceLanguageOptions)
const {
  interfaceLanguage,
  interfaceLanguageDisabled,
  interfaceLanguageSaving,
  interfaceLanguageError,
  appearanceBusy
} = storeToRefs(gui)

onMounted(() => void gui.load())
</script>

<template>
  <n-form-item
    :label="t('settings.gui.interfaceLanguage')"
    class="settings-appearance-row interface-language-preference"
    data-settings-keywords="界面语言 語言 言語 language locale 简体 繁體 日本語 English"
  >
    <div class="interface-language-content">
      <n-select
        :value="interfaceLanguage"
        :options="languageOptions"
        :disabled="interfaceLanguageDisabled"
        :loading="interfaceLanguageSaving"
        :aria-label="t('settings.gui.interfaceLanguage')"
        aria-describedby="interface-language-description"
        @update:value="gui.setInterfaceLanguage"
      />
      <span id="interface-language-description" class="settings-row-description">
        {{ t('settings.gui.interfaceLanguageDescription') }}
        {{ t('appearance.followSystemDescription') }}
      </span>
      <n-alert v-if="interfaceLanguageError" type="error" :show-icon="false" role="alert">
        {{ interfaceLanguageError }}
        <n-button size="small" text :disabled="appearanceBusy" @click="gui.retryInterfaceLanguage">
          {{ t('appearance.retry') }}
        </n-button>
      </n-alert>
    </div>
  </n-form-item>
</template>

<style scoped>
.interface-language-content {
  display: grid;
  width: 100%;
  min-width: 0;
  gap: 8px;
}
</style>
