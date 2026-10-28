<script setup>
import { i18n } from '@/i18n'
import { computed, inject } from 'vue'
import { configProfilesKey } from '@/composables/configProfiles'

const controller = inject(configProfilesKey, null)
const currentProfileName = computed(() => {
  const state = controller?.state.value
  return (
    state?.profiles.find((profile) => profile.id === state.active_id)?.name ||
    i18n.global.t('settings.profiles.notLoaded')
  )
})
const importDisabled = computed(() => !controller || controller.writeDisabled.value)
const exportDisabled = computed(() => !controller || controller.readDisabled.value)

function openProfile(action) {
  if (action === 'import' ? importDisabled.value : exportDisabled.value) return
  return controller.open(action)
}
</script>

<template>
  <n-card
    :title="i18n.global.t('settings.profiles.importExportProfiles')"
    class="config-profiles-settings"
  >
    <p class="current-profile">
      {{ i18n.global.t('settings.profiles.currentProfile') }}{{ currentProfileName }}
    </p>
    <p class="profile-description">
      {{ i18n.global.t('settings.profiles.whenImportingChooseWhichPartsOfThe') }}
    </p>
    <p v-if="!controller" class="profile-description" role="status">
      {{ i18n.global.t('settings.profiles.profileManagementHasNotLoadedReloadThe') }}
    </p>
    <div class="profile-actions">
      <n-button :disabled="importDisabled" @click="openProfile('import')">{{
        i18n.global.t('settings.profiles.importProfile')
      }}</n-button>
      <n-button :disabled="exportDisabled" @click="openProfile('export')">{{
        i18n.global.t('settings.profiles.exportCurrentProfile')
      }}</n-button>
    </div>
  </n-card>
</template>

<style scoped>
.current-profile {
  margin: 0;
}

.profile-description {
  margin: 8px 0 0;
  color: var(--mower-text-muted);
  font-size: 12px;
  line-height: 1.65;
}

.profile-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 16px;
}
</style>
