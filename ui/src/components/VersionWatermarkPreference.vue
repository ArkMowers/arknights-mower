<script setup>
import { i18n } from '@/i18n'
import { computed, onDeactivated, onMounted, ref } from 'vue'
import { storeToRefs } from 'pinia'
import { useGuiStore } from '@/stores/gui'

const gui = useGuiStore()
const { watermarkVisible, watermarkDisabled, watermarkSaving, watermarkError } = storeToRefs(gui)
const showConfirmation = ref(false)
const confirmationStep = ref(0)
const confirmationInput = ref('')
const confirmationText = '反馈问题时务必说明具体版本'
const reminderCount = 5
const reminderText = computed(() =>
  i18n.global.t('settings.watermark.whenReportingAProblemAfterHidingThe')
)
const finalStep = computed(() => confirmationStep.value === reminderCount - 1)
const confirmationDisabled = computed(
  () =>
    watermarkDisabled.value ||
    (finalStep.value && confirmationInput.value.trim() !== confirmationText)
)

function cancelConfirmation() {
  showConfirmation.value = false
  confirmationStep.value = 0
  confirmationInput.value = ''
}

function changeVisibility(value) {
  if (watermarkDisabled.value || showConfirmation.value) return
  if (value) {
    void gui.setWatermarkVisible(true)
    return
  }
  confirmationStep.value = 0
  confirmationInput.value = ''
  showConfirmation.value = true
}

function advanceConfirmation() {
  if (!showConfirmation.value || confirmationDisabled.value) return
  if (!finalStep.value) {
    confirmationStep.value += 1
    return
  }
  const confirmation = confirmationInput.value.trim()
  cancelConfirmation()
  void gui.setWatermarkVisible(false, confirmation)
}

onMounted(() => void gui.load())
onDeactivated(cancelConfirmation)
</script>

<template>
  <n-form-item
    :label="i18n.global.t('settings.watermark.versionWatermark')"
    class="settings-appearance-row version-watermark-preference"
    data-settings-keywords="版本水印 显示 隐藏 关闭 反馈 版本号"
  >
    <div class="watermark-preference-content">
      <div class="watermark-preference-control">
        <n-switch
          :value="watermarkVisible"
          :disabled="watermarkDisabled || showConfirmation"
          :loading="watermarkSaving"
          :aria-label="i18n.global.t('settings.watermark.showVersionWatermark')"
          aria-describedby="watermark-description"
          @update:value="changeVisibility"
        />
        <span>{{
          watermarkVisible
            ? i18n.global.t('settings.watermark.shown')
            : i18n.global.t('settings.watermark.hidden')
        }}</span>
      </div>
      <span id="watermark-description" class="watermark-preference-description">
        {{ reminderText }}
      </span>
      <n-alert v-if="watermarkError" type="error" :show-icon="false" role="alert">
        {{ watermarkError }}
        <n-button
          size="small"
          text
          :disabled="gui.loading || gui.saving || gui.layoutSaving || watermarkSaving"
          @click="gui.retryWatermarkVisible"
          >{{ i18n.global.t('settings.watermark.retry') }}</n-button
        >
      </n-alert>
    </div>
  </n-form-item>
  <n-modal
    :show="showConfirmation"
    preset="card"
    :title="
      i18n.global.t('settings.watermark.hideVersionWatermark', {
        value0: confirmationStep + 1,
        value1: reminderCount
      })
    "
    class="watermark-confirmation"
    style="width: min(480px, calc(100vw - 32px))"
    @update:show="cancelConfirmation"
  >
    <div aria-live="polite" aria-atomic="true">
      <p class="watermark-reminder">{{ reminderText }}</p>
    </div>
    <div class="watermark-confirmation-input">
      <template v-if="finalStep">
        <label for="watermark-confirmation-text"
          >{{ i18n.global.t('settings.watermark.typeTheFollowingChinesePhraseExactly')
          }}{{ confirmationText }}</label
        >
        <n-input
          v-model:value="confirmationInput"
          :placeholder="confirmationText"
          autocomplete="off"
          autofocus
          :input-props="{ id: 'watermark-confirmation-text', spellcheck: false }"
        />
      </template>
    </div>
    <div class="watermark-button-playground">
      <n-button
        type="primary"
        class="watermark-confirm-button"
        :class="`watermark-confirm-position-${confirmationStep}`"
        :disabled="confirmationDisabled"
        @click="advanceConfirmation"
        >{{
          finalStep
            ? i18n.global.t('settings.watermark.confirmHide')
            : i18n.global.t('settings.watermark.continue')
        }}</n-button
      >
    </div>
    <template #footer>
      <n-button block @click="cancelConfirmation">{{
        i18n.global.t('settings.watermark.keepWatermark')
      }}</n-button>
    </template>
  </n-modal>
</template>

<style scoped>
.watermark-preference-content {
  display: grid;
  gap: 8px;
  width: 100%;
  min-width: 0;
}
.watermark-preference-control {
  display: flex;
  align-items: center;
  gap: 10px;
}
.watermark-preference-description {
  color: var(--mower-text-muted);
  font-size: 12px;
  line-height: 20px;
}
.watermark-reminder {
  min-height: 48px;
  margin: 0 0 16px;
}
.watermark-confirmation-input {
  display: grid;
  align-content: start;
  gap: 8px;
  min-height: 84px;
}
.watermark-button-playground {
  position: relative;
  height: 152px;
  margin-top: 12px;
}
.watermark-confirm-button {
  position: absolute;
  height: auto;
  min-height: 34px;
  max-width: 100%;
  padding-block: 6px;
  text-align: center;
  white-space: normal;
}
.watermark-confirm-button :deep(.n-button__content) {
  white-space: normal;
  overflow-wrap: anywhere;
}
.watermark-confirm-position-0 {
  right: 0;
  bottom: 0;
}
.watermark-confirm-position-1 {
  top: 0;
  left: 0;
}
.watermark-confirm-position-2 {
  bottom: 0;
  left: 0;
}
.watermark-confirm-position-3 {
  top: 0;
  right: 0;
}
.watermark-confirm-position-4 {
  top: 50%;
  left: 50%;
  width: max-content;
  transform: translate(-50%, -50%);
}
</style>
