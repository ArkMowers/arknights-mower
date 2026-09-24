<script setup>
import { useConfigStore } from '@/stores/config'
import { storeToRefs } from 'pinia'
const store = useConfigStore()
const { maa_depot_enable, skland_info, depot_history_limit, depot_history_keep } =
  storeToRefs(store)
</script>
<template>
  <n-card>
    <template #header>
      <n-checkbox v-model:checked="maa_depot_enable">
        <div class="card-title">仓库物品混合读取</div>
      </n-checkbox>
      <help-text>请调整森空岛账号顺序，仅读取<b>第一个</b>账户<b>指定服务器</b>的材料</help-text>
    </template>
    <div v-for="account_info in skland_info" :key="account_info.account">
      <div style="display: flex; align-items: center; width: 100%">
        <div style="margin-right: 24px">森空岛账号：{{ account_info.account }}</div>
        <n-radio-group v-model:value="account_info.cultivate_select">
          <n-flex>
            <n-radio :value="true">官服</n-radio>
            <n-radio :value="false">B服</n-radio>
          </n-flex>
        </n-radio-group>
      </div>
    </div>

    <div class="depot-history-row">
      <div class="row-label">
        历史条数
        <help-text>
          <div>仓库页趋势与快照对比取用多少条快照</div>
          <div>完整库存快照约 2.4KB/条，条数越多响应越大</div>
        </help-text>
      </div>
      <mower-input-number v-model:value="depot_history_limit" :min="1" class="row-input" />
    </div>
    <div class="depot-history-row">
      <div class="row-label">
        文件保留
        <help-text>
          <div>每次扫描后把两份历史文件裁到最近这么多条</div>
          <div>0 表示不清理，文件只追加</div>
        </help-text>
      </div>
      <mower-input-number v-model:value="depot_history_keep" :min="0" class="row-input" />
    </div>
  </n-card>
</template>

<style scoped>
.depot-history-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-top: 12px;
}

.row-label {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 13px;
}

.row-input {
  width: 140px;
  flex-shrink: 0;
}
</style>
