<script setup>
import { useConfigStore } from '@/stores/config'
import { storeToRefs } from 'pinia'

const { depot_history_limit, depot_history_keep } = storeToRefs(useConfigStore())
</script>

<template>
  <n-card title="仓库历史">
    <n-form class="settings-row-form" label-placement="left" :show-feedback="false">
      <n-form-item>
        <template #label>
          <span class="settings-row-copy">
            <span>历史条数</span>
            <span id="depot-history-limit-description" class="settings-row-description">
              仓库趋势、环比与快照对比最多读取的扫描记录数，不影响本地记录的保留。
            </span>
          </span>
        </template>
        <mower-input-number
          v-model:value="depot_history_limit"
          :min="1"
          :max="20000"
          :input-props="{
            'aria-label': '历史条数',
            'aria-describedby': 'depot-history-limit-description'
          }"
        />
      </n-form-item>
      <n-form-item>
        <template #label>
          <span class="settings-row-copy">
            <span>保留条数</span>
            <span id="depot-history-keep-description" class="settings-row-description">
              本地最多保留的扫描记录数，超出后从最早的删除。0
              表示一直保留；改小后在下一次扫描仓库时生效。
            </span>
          </span>
        </template>
        <mower-input-number
          v-model:value="depot_history_keep"
          :min="0"
          :input-props="{
            'aria-label': '保留条数',
            'aria-describedby': 'depot-history-keep-description'
          }"
        />
      </n-form-item>
    </n-form>
    <p class="depot-history-note">
      历史条数默认 3000 次，每 3 小时扫描一次约可查看一年。条数越多，仓库页加载越慢。保留条数默认
      0。
    </p>
  </n-card>
</template>

<style scoped>
.depot-history-note {
  margin: 16px 0 0;
  padding-top: 14px;
  border-top: 1px solid var(--settings-card-border);
  color: var(--mower-text-muted);
  font-size: 12px;
  line-height: 1.65;
  text-wrap: pretty;
}
</style>
