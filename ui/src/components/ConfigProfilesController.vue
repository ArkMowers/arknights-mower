<script setup>
import { i18n } from '@/i18n'
import { computed, ref } from 'vue'
import { profileGroupText, profileSectionTitle } from '@/composables/configProfiles'

const props = defineProps({ controller: { type: Object, required: true } })
const {
  dialog,
  name,
  selected,
  file,
  sections,
  busy,
  loading,
  error,
  stale,
  pendingReload,
  writeDisabled,
  selectFile,
  toggleSection,
  submit,
  reloadPage,
  refresh
} = props.controller
const input = ref(null)
const title = computed(
  () =>
    ({
      create: i18n.global.t('settings.profileDialog.create'),
      copy: i18n.global.t('settings.profileDialog.copy'),
      rename: i18n.global.t('settings.profileDialog.rename'),
      import: i18n.global.t('settings.profileDialog.import'),
      activate: i18n.global.t('settings.profileDialog.activate')
    })[dialog.value?.action] || i18n.global.t('settings.profileDialog.profile')
)
const confirmLabel = computed(
  () =>
    ({
      create: i18n.global.t('settings.profileDialog.createAndSwitch'),
      copy: i18n.global.t('settings.profileDialog.copyAndSwitch'),
      rename: i18n.global.t('settings.profileDialog.saveName'),
      import: i18n.global.t('settings.profileDialog.importAndSwitch'),
      activate: i18n.global.t('settings.profileDialog.activate')
    })[dialog.value?.action]
)
const isReload = computed(() => stale.value || pendingReload.value)
function checked(section) {
  return section.children.every((group) => selected.value.includes(group.key))
}
function partial(section) {
  return !checked(section) && section.children.some((group) => selected.value.includes(group.key))
}
</script>

<template>
  <n-alert
    v-if="error && !dialog && !isReload"
    type="error"
    :title="i18n.global.t('settings.profileDialog.unavailable')"
    class="profiles-error"
  >
    {{ error }}
    <template #action
      ><n-button @click="reloadPage">{{
        i18n.global.t('settings.profileDialog.reloadPage')
      }}</n-button></template
    >
  </n-alert>
  <n-modal
    :show="Boolean(dialog) && !isReload"
    preset="card"
    :title="title"
    class="profiles-dialog"
    :style="{
      width: 'min(640px, calc(100vw - 32px))',
      display: 'flex',
      flexDirection: 'column'
    }"
    :content-style="{ overflowY: 'auto', minHeight: 0 }"
    :mask-closable="!busy"
    :closable="!busy"
    :close-on-esc="!busy"
    @update:show="
      (show) => {
        if (!show && !busy) dialog = null
      }
    "
  >
    <n-space vertical :size="18">
      <n-alert v-if="error" type="error" :show-icon="false">{{ error }}</n-alert>
      <n-form-item
        v-if="dialog?.action !== 'activate'"
        :label="i18n.global.t('settings.profileDialog.name')"
        :show-feedback="false"
      >
        <n-input
          v-model:value="name"
          :disabled="busy"
          :placeholder="i18n.global.t('settings.profileDialog.exampleNames')"
          :input-props="{ 'aria-label': i18n.global.t('settings.profileDialog.name') }"
          autofocus
        />
      </n-form-item>
      <template v-if="dialog?.action === 'import'">
        <n-space align="center">
          <n-button :disabled="busy" @click="input.click()">{{
            i18n.global.t('settings.profileDialog.selectBackup')
          }}</n-button>
          <n-text>{{ file?.name || i18n.global.t('settings.profileDialog.noFile') }}</n-text>
        </n-space>
        <input
          ref="input"
          type="file"
          hidden
          accept=".zip,application/zip"
          :aria-label="i18n.global.t('settings.profileDialog.selectProfileBackup')"
          @change="selectFile"
        />
      </template>
      <template v-if="dialog?.action !== 'rename'">
        <p class="profiles-copy">
          <template v-if="dialog?.action === 'activate'"
            >{{ i18n.global.t('settings.profileDialog.switchPrefix') }}{{ dialog.targetName
            }}{{ i18n.global.t('settings.profileDialog.switchSuffix') }}</template
          >
          <template v-else-if="dialog?.action === 'import'">{{
            i18n.global.t('settings.profileDialog.importDetails')
          }}</template>
          <template v-else>{{ i18n.global.t('settings.profileDialog.inheritDetails') }}</template>
        </p>
        <details
          v-for="section in sections"
          :key="section.key || section.label"
          class="profiles-section"
          open
        >
          <summary>
            <n-checkbox
              :checked="checked(section)"
              :indeterminate="partial(section)"
              :disabled="busy"
              @click.stop.prevent
              @update:checked="(value) => toggleSection(section, value)"
              ><strong>{{ profileSectionTitle(section) }}</strong></n-checkbox
            >
          </summary>
          <n-checkbox-group v-model:value="selected" :disabled="busy"
            ><div class="profiles-options">
              <n-checkbox
                v-for="group in section.children"
                :key="group.key"
                :value="group.key"
                :disabled="busy"
              >
                <span class="profiles-option"
                  ><span>{{ profileGroupText(group, 'label') }}</span
                  ><small>{{ profileGroupText(group, 'description') }}</small></span
                >
              </n-checkbox>
            </div></n-checkbox-group
          >
        </details>
        <n-text depth="3">{{ i18n.global.t('settings.profileDialog.pendingDrafts') }}</n-text>
      </template>
    </n-space>
    <template #footer
      ><n-space justify="end">
        <n-button :disabled="busy" @click="dialog = null">{{
          i18n.global.t('settings.profileDialog.cancel')
        }}</n-button>
        <n-button type="primary" :loading="busy" :disabled="writeDisabled" @click="submit">{{
          confirmLabel
        }}</n-button>
      </n-space></template
    >
  </n-modal>
  <n-modal
    :show="isReload"
    preset="card"
    :title="i18n.global.t('settings.profileDialog.reloadNeeded')"
    :style="{ width: 'min(480px, calc(100vw - 32px))' }"
    :closable="false"
    :mask-closable="false"
    :close-on-esc="false"
  >
    <n-space vertical :size="16">
      <n-text>{{ error || i18n.global.t('settings.profileDialog.switchedPaused') }}</n-text>
      <n-text v-if="stale && controller.state.value" depth="3"
        >{{ i18n.global.t('settings.profileDialog.currentProfile')
        }}{{
          controller.state.value.profiles.find(
            (item) => item.id === controller.state.value.active_id
          )?.name
        }}</n-text
      >
      <n-space justify="end">
        <n-button :loading="loading" @click="refresh()">{{
          i18n.global.t('settings.profileDialog.checkCurrent')
        }}</n-button>
        <n-button type="primary" @click="reloadPage">{{
          i18n.global.t('settings.profileDialog.reload')
        }}</n-button>
      </n-space>
    </n-space>
  </n-modal>
</template>

<style scoped>
.profiles-error {
  margin: 12px;
}
.profiles-copy {
  margin: 0;
  line-height: 1.7;
}
.profiles-section + .profiles-section {
  margin-top: 18px;
}
.profiles-options {
  display: grid;
  gap: 12px;
  padding: 12px 0 0 24px;
}
.profiles-option {
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.profiles-option small {
  opacity: 0.65;
  font-size: 12px;
  line-height: 1.5;
}
</style>
