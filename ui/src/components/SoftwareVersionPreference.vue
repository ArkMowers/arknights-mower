<script setup>
import { onMounted } from 'vue'
import { storeToRefs } from 'pinia'
import SoftwareVersionBadge from '@/components/SoftwareVersionBadge.vue'
import SettingsSegmented from '@/components/SettingsSegmented.vue'
import { useGuiStore } from '@/stores/gui'

const gui = useGuiStore()
const { softwareVersionDisplay, softwareVersionLanguage, displayDisabled, saving, error } =
  storeToRefs(gui)
const displayOptions = [
  { value: 'version', label: '版本号' },
  { value: 'channel', label: '版本类型' }
]
const languageOptions = [
  { value: 'zh', label: '中文' },
  { value: 'en', label: 'English' }
]
const buildExamples = [
  { kind: 'alpha', version: '4.1.6-alpha.12' },
  { kind: 'nightly', version: '4.1.6-alpha.12.g8c3f2a19' },
  { kind: 'stable', version: '4.1.6' }
]

onMounted(() => void gui.load())
</script>

<template>
  <n-form-item
    class="software-version-preference"
    data-settings-keywords="软件版本 类型 源码部署 source alpha 公测版 nightly 开发版 stable 正式版"
  >
    <template #label>
      <span>软件版本显示</span>
    </template>
    <SettingsSegmented
      class="version-display-switch"
      :value="softwareVersionDisplay"
      :options="displayOptions"
      :disabled="displayDisabled"
      :busy="saving"
      label="软件版本显示"
      @update:value="gui.setSoftwareVersionDisplay"
    />
  </n-form-item>
  <n-form-item class="settings-row-wide version-preview-row">
    <div class="version-preference-content">
      <div class="version-display-preview" aria-label="软件版本显示预览">
        <div class="version-preview-header">
          <span data-settings-label="软件版本显示预览">显示预览</span>
          <SettingsSegmented
            class="version-preview-language"
            data-settings-label="版本类型语言"
            data-settings-keywords="版本类型语言 中文 English"
            :value="softwareVersionLanguage"
            :options="languageOptions"
            :disabled="displayDisabled"
            :busy="saving"
            label="版本类型语言"
            @update:value="gui.setSoftwareVersionLanguage"
          />
        </div>
        <div class="version-build-workflow">
          <div class="version-workflow-source">
            <div
              class="version-workflow-job version-workflow-job--source"
              data-version-kind="source"
            >
              <SoftwareVersionBadge
                version="4.1.6-alpha.12+8c3f2a1"
                deployment="source"
                :display-mode="softwareVersionDisplay"
                read-only
              />
            </div>
          </div>
          <svg
            class="version-workflow-links"
            viewBox="0 0 48 192"
            preserveAspectRatio="none"
            aria-hidden="true"
          >
            <path
              d="M 0 32 H 48 M 0 32 C 16 32 24 40 24 56 V 136 C 24 152 32 160 48 160 M 24 96 H 48"
            />
          </svg>
          <div class="version-workflow-targets">
            <div
              v-for="example in buildExamples"
              :key="example.kind"
              class="version-workflow-target"
            >
              <div class="version-workflow-job" :data-version-kind="example.kind">
                <SoftwareVersionBadge
                  :version="example.version"
                  deployment="release"
                  :display-mode="softwareVersionDisplay"
                  read-only
                />
              </div>
            </div>
          </div>
        </div>
      </div>
      <span class="version-preference-status" role="status">{{ saving ? '正在保存…' : '' }}</span>
      <n-alert v-if="error" type="error" :show-icon="false" role="alert">
        {{ error }}
        <n-button size="small" text :disabled="displayDisabled && gui.loading" @click="gui.retry">
          重试
        </n-button>
      </n-alert>
    </div>
  </n-form-item>
</template>

<style scoped>
.version-preference-content {
  position: relative;
  display: grid;
  width: 100%;
  min-width: 0;
  gap: 12px;
}
.version-display-preview {
  width: 100%;
  min-width: 0;
  box-sizing: border-box;
  padding: 12px;
  border: 1px solid var(--mower-border);
  border-radius: 8px;
  background: var(--mower-control-surface);
}
.version-preview-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 8px 12px;
  margin-bottom: 8px;
  color: var(--mower-text-muted);
  font-size: 13px;
}
.version-preview-language {
  width: 144px;
  max-width: 100%;
  margin-left: auto;
}
.version-preview-language :deep(.settings-segmented-choice) {
  min-height: 28px;
  padding: 4px 8px;
  font-size: 12px;
  line-height: 20px;
}
.version-build-workflow {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 32px minmax(0, 1fr);
  min-width: 0;
  height: 192px;
}
.version-build-workflow :deep(.sidebar-brand-channel) {
  padding-inline: 4px;
  font-size: 10px;
  line-height: 15px;
  white-space: normal;
  overflow-wrap: anywhere;
}
.version-workflow-source,
.version-workflow-target {
  display: flex;
  align-items: center;
  min-width: 0;
  height: 64px;
}
.version-workflow-targets {
  min-width: 0;
}
.version-workflow-job {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  min-width: 0;
  min-height: 52px;
  padding: 4px 8px;
  box-sizing: border-box;
  border: 1px solid var(--mower-border);
  border-radius: 6px;
  background: var(--mower-surface);
}
.version-workflow-job::before,
.version-workflow-job--source::after {
  position: absolute;
  top: calc(50% - 5px);
  width: 10px;
  height: 10px;
  box-sizing: border-box;
  border: 2px solid var(--mower-surface);
  border-radius: 50%;
  background: var(--mower-text-muted);
  content: '';
}
.version-workflow-job::before {
  left: -6px;
}
.version-workflow-job--source::before {
  display: none;
}
.version-workflow-job--source::after {
  right: -6px;
}
.version-workflow-links {
  width: 32px;
  height: 192px;
  overflow: visible;
  fill: none;
  stroke: var(--mower-border);
  stroke-width: 2;
}
.version-preference-status {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
}
</style>
