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

    <div class="history-block">
      <div class="block-title">仓库历史</div>
      <div class="depot-history-row">
        <div class="row-label">
          历史条数
          <help-text>
            <div>仓库页的趋势、环比与快照对比最多用这么多次扫描记录</div>
            <div>填得越大能往回看得越远，打开仓库页时加载也越慢</div>
            <div>默认 3000 次，按每 3 小时扫一次约一年</div>
          </help-text>
        </div>
        <mower-input-number
          v-model:value="depot_history_limit"
          :min="1"
          :max="20000"
          class="row-input"
        />
      </div>
      <div class="depot-history-row">
        <div class="row-label">
          保留条数
          <help-text>
            <div>扫描记录最多留多少条，超出的从最早的删起</div>
            <div>0 表示一直留着（默认）；改小后下一次扫仓库才生效</div>
          </help-text>
        </div>
        <mower-input-number v-model:value="depot_history_keep" :min="0" class="row-input" />
      </div>
    </div>
  </n-card>
</template>

<style scoped>
.history-block {
  margin-top: 16px;
  padding-top: 12px;
  border-top: 1px solid var(--mower-border, rgba(0, 0, 0, 0.08));
}

.block-title {
  font-size: 13px;
  font-weight: 600;
  margin-bottom: 4px;
}

.depot-history-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-top: 10px;
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
