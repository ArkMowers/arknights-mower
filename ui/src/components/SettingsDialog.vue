<script setup>
import { i18n } from '@/i18n'
import { defineAsyncComponent } from 'vue'
import SettingsSidebar from './SettingsSidebar.vue'

defineProps({ show: Boolean })
const emit = defineEmits(['close'])
const MowerSettings = defineAsyncComponent(() => import('@/pages/Settings.vue'))
</script>

<template>
  <n-modal
    :show="show"
    preset="card"
    :title="i18n.global.t('settings.dialog.settings')"
    class="settings-dialog"
    data-modal-draggable="false"
    :bordered="false"
    :draggable="false"
    :mask-closable="false"
    @update:show="(visible) => !visible && emit('close')"
  >
    <div class="settings-dialog-body">
      <SettingsSidebar embedded />
      <div
        class="settings-dialog-content"
        role="region"
        :aria-label="i18n.global.t('settings.dialog.settingsContent')"
      >
        <MowerSettings />
      </div>
    </div>
  </n-modal>
</template>

<style>
.settings-dialog.n-modal {
  width: min(1000px, calc(100vw / var(--mower-zoom, 1) - 96px));
  height: min(720px, calc(84dvh / var(--mower-zoom, 1)));
  max-width: calc(100vw / var(--mower-zoom, 1) - 32px);
  max-height: calc(100dvh / var(--mower-zoom, 1) - 32px);
  box-sizing: border-box;
  border: 1px solid var(--mower-border);
  border-radius: 22px;
  container: settings-dialog / inline-size;
  background: var(--mower-surface);
  box-shadow: 0 20px 80px -24px rgb(0 0 0 / 28%);
}

.settings-dialog.n-card > .n-card-header {
  padding: 22px 28px 20px;
  cursor: default;
}

.settings-dialog > .n-card-header .n-card-header__main {
  font-size: 20px;
  font-weight: 500;
}

.settings-dialog.n-card > .n-card-content {
  display: flex;
  padding: 0;
  overflow: hidden;
}

.settings-dialog-body {
  display: grid;
  grid-template-columns: 216px minmax(0, 1fr);
  gap: 24px;
  width: 100%;
  min-height: 0;
  padding-left: 16px;
}

.settings-dialog-content {
  min-width: 0;
  min-height: 0;
  overflow-x: hidden;
  overflow-y: auto;
  overscroll-behavior: contain;
  container: settings-content / inline-size;
}

.settings-dialog .settings-page--shell {
  max-width: none;
  padding: 2px 28px 32px 0;
}

.settings-dialog .settings-page-header {
  margin-bottom: 20px;
}

.settings-dialog .settings-page-header h1 {
  font-size: 18px;
  font-weight: 500;
}

.settings-dialog .settings-card-grid {
  gap: 24px;
}

.settings-dialog .settings-page .settings-card-grid .n-card {
  border: 0;
  background: transparent;
  box-shadow: none;
}

.settings-dialog .settings-page .settings-card-grid .n-card > .n-card-content {
  padding: 16px;
  border: 1px solid var(--settings-card-border);
  border-radius: 14px;
  background: var(--mower-surface);
}

.settings-dialog .settings-page .n-form > .n-form-item {
  padding: 14px 0;
  align-items: center;
}

.settings-dialog .settings-page .n-form > .n-form-item:first-child {
  padding-top: 0;
}

.settings-dialog .settings-page .n-form > .n-form-item:last-child {
  padding-bottom: 0;
}

.settings-dialog .settings-page .n-form > .n-form-item:has(> .n-form-item-label) {
  grid-template-columns: minmax(0, 1fr) auto;
  grid-template-areas: 'label blank' 'feedback feedback';
  column-gap: 28px;
}

.settings-dialog .settings-page .n-form > .n-form-item > .n-form-item-blank {
  width: 260px;
  max-width: 100%;
  justify-content: flex-end;
}

.settings-dialog .settings-page .n-form > .n-form-item > .n-form-item-blank:has(> .n-switch),
.settings-dialog
  .settings-page
  .n-form
  > .n-form-item
  > .n-form-item-blank:has(> .n-button:only-child) {
  width: auto;
}

.settings-dialog .settings-page .n-form-item-blank > .n-select {
  width: 180px;
}

.settings-dialog
  .settings-page
  .n-form
  > .n-form-item
  > .n-form-item-blank:has(> .settings-select-wrap) {
  width: 300px;
}

.settings-dialog .settings-page .n-form-item-blank > .settings-select-wrap {
  width: 100%;
}

.settings-dialog .n-select .n-base-selection {
  --n-border: 1px solid transparent !important;
  --n-color: var(--mower-control-surface) !important;
  --n-padding-single: 6px 32px 6px 12px !important;
}

.settings-dialog .settings-page .n-form-item-blank > .n-input-number,
.settings-dialog .settings-page .settings-field:has(> .n-input-number) {
  width: 128px;
}

.settings-dialog .settings-page .settings-field {
  max-width: 260px;
}

.settings-dialog
  .settings-page
  .n-form
  > .n-form-item
  > .n-form-item-blank:has(> .desktop-scale-settings) {
  width: 320px;
}

.settings-dialog .settings-page .desktop-scale-settings {
  max-width: 320px;
}

.settings-dialog .settings-page .n-form-item-label {
  min-width: 0;
  font-size: 14px;
  font-weight: 400;
}

.settings-dialog .settings-row-copy {
  min-width: 0;
  text-wrap: pretty;
}

.settings-dialog .settings-row-description {
  display: block;
  margin-top: 6px;
  font-size: 12px;
  line-height: 1.65;
}

.settings-dialog .settings-page .n-form > .n-form-item.settings-row-wide {
  grid-template-columns: minmax(0, 1fr);
  grid-template-areas: 'label' 'blank' 'feedback';
  row-gap: 14px;
}

.settings-dialog .settings-page .n-form > .settings-row-wide > .n-form-item-blank {
  width: 100%;
  max-width: none;
}

@container settings-content (max-width: 480px) {
  .settings-dialog .settings-page .n-form > .n-form-item:has(> .n-form-item-label) {
    grid-template-columns: minmax(0, 1fr);
    grid-template-areas: 'label' 'blank' 'feedback';
    row-gap: 8px;
  }

  .settings-dialog .settings-page .n-form > .n-form-item > .n-form-item-label {
    min-height: 0;
    padding: 0;
  }

  .settings-dialog .settings-page .n-form > .n-form-item > .n-form-item-blank {
    justify-self: start;
    justify-content: flex-start;
  }

  .settings-dialog .settings-page .n-form > .n-form-item > .n-form-item-blank:has(> .n-select) {
    justify-self: stretch;
    width: 100%;
  }

  .settings-dialog .settings-page .n-form-item-blank > .n-select {
    width: 100%;
  }

  .settings-dialog .settings-page .n-form > .n-form-item:has(> .n-form-item-blank > .n-switch) {
    grid-template-columns: minmax(0, 1fr) auto;
    grid-template-areas: 'label blank' 'feedback feedback';
  }
}

@media (max-width: 680px) {
  .settings-dialog.n-modal {
    width: calc(100vw / var(--mower-zoom, 1) - 24px);
    height: calc(100dvh / var(--mower-zoom, 1) - 24px);
    max-width: none;
    max-height: none;
    border-radius: 20px;
  }
}

@container settings-dialog (max-width: 680px) {
  .settings-dialog.n-card > .n-card-header {
    padding: 20px 20px 16px;
  }

  .settings-dialog-body {
    grid-template-columns: minmax(0, 1fr);
    grid-template-rows: auto minmax(0, 1fr);
    gap: 12px;
    padding-left: 0;
  }

  .settings-dialog .settings-page--shell {
    padding: 4px 12px 20px;
  }

  .settings-dialog .settings-page .settings-card-grid .n-card > .n-card-content {
    padding: 12px;
  }
}
</style>
