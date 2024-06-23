<script setup>
import { useConfigStore } from '@/stores/config'
import { storeToRefs } from 'pinia'
const store = useConfigStore()
const { maa_depot_enable, skland_info } = storeToRefs(store)
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
  </n-card>
</template>
