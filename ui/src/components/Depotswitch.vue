<script setup>
defineOptions({ name: 'DepotSourceSettings' })
defineProps({ showEnable: { type: Boolean, default: true } })
const emit = defineEmits(['configure-accounts'])

import { useConfigStore } from '@/stores/config'
import { storeToRefs } from 'pinia'
const store = useConfigStore()
const { maa_depot_enable, skland_info } = storeToRefs(store)
</script>
<template>
  <n-card>
    <template #header>
      <span v-if="showEnable">仓库物品混合读取</span>
      <span v-else>材料来源</span>
      <help-text>请调整森空岛账号顺序，仅读取<b>第一个</b>账户<b>指定服务器</b>的材料</help-text>
    </template>
    <n-form label-placement="left" :show-feedback="false" label-width="140" label-align="left">
      <n-form-item v-if="showEnable" label="启用混合读取">
        <n-switch v-model:value="maa_depot_enable" aria-label="启用混合读取" />
      </n-form-item>
      <div v-if="!showEnable && !skland_info?.length" class="depot-accounts-empty">
        <span>请先添加森空岛账号。</span>
        <n-button size="small" type="primary" secondary @click="emit('configure-accounts')">
          添加森空岛账号
        </n-button>
      </div>
      <div
        v-for="account_info in skland_info"
        :key="account_info.account"
        class="depot-account-row"
      >
        <div class="depot-account-name">森空岛账号：{{ account_info.account }}</div>
        <n-radio-group v-model:value="account_info.cultivate_select">
          <n-flex>
            <n-radio :value="true">官服</n-radio>
            <n-radio :value="false">B服</n-radio>
          </n-flex>
        </n-radio-group>
      </div>
    </n-form>
  </n-card>
</template>

<style scoped>
.depot-accounts-empty,
.depot-account-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px 24px;
}

.depot-account-row + .depot-account-row {
  margin-top: 12px;
}

.depot-account-name {
  min-width: 0;
  overflow-wrap: anywhere;
}

.depot-account-row :deep(.n-radio-group) {
  flex-shrink: 0;
}
</style>
