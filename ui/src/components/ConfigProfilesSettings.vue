<script setup>
import { computed, inject } from 'vue'
import { configProfilesKey } from '@/composables/configProfiles'

const controller = inject(configProfilesKey, null)
const currentProfileName = computed(() => {
  const state = controller?.state.value
  return state?.profiles.find((profile) => profile.id === state.active_id)?.name || '尚未载入'
})
const importDisabled = computed(() => !controller || controller.writeDisabled.value)
const exportDisabled = computed(() => !controller || controller.readDisabled.value)

function openProfile(action) {
  if (action === 'import' ? importDisabled.value : exportDisabled.value) return
  return controller.open(action)
}
</script>

<template>
  <n-card title="档案导入与导出" class="config-profiles-settings">
    <p class="current-profile">当前档案：{{ currentProfileName }}</p>
    <p class="profile-description">
      导入时可选择保留当前档案的哪些内容，其余内容来自 ZIP，并创建、切换到新档案。
      导出包含当前档案的设置、排班和本地数据。
    </p>
    <p v-if="!controller" class="profile-description" role="status">
      档案管理尚未载入，请重新加载页面后再试。
    </p>
    <div class="profile-actions">
      <n-button :disabled="importDisabled" @click="openProfile('import')">导入档案</n-button>
      <n-button :disabled="exportDisabled" @click="openProfile('export')">导出当前档案</n-button>
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
