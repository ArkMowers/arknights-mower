<script setup>
import { storeToRefs } from 'pinia'
import { useConfigStore } from '@/stores/config'
const store = useConfigStore()
const { maa_depot_enable, skland_enable, skland_info } = storeToRefs(store)
</script>
<template>
  <n-card>
    <template #header>
      <n-checkbox v-model:checked="maa_depot_enable">
        <div class="card-title">混和读取仓库物品</div>
      </n-checkbox>
    </template>
    <div v-if="skland_enable">
      <div v-for="account_info in skland_info">
        <div style="display: flex; align-items: center; width: 100%">
          <div style="margin-right: 12px">森空岛账号：{{ account_info.account }}</div>
          <div>
            <n-switch v-model:value="account_info.cultivate_select" />
            {{ account_info.cultivate_select ? '官服' : 'Bilibili服务器' }}
          </div>
        </div>
      </div>
    </div>
    <template #footer>
      请调整森空岛账号顺序，仅读取<b>第一个</b>账户<b>指定服务器</b>的材料
    </template>
  </n-card>
</template>
