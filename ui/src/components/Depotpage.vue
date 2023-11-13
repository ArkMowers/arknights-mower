<script setup>
import { storeToRefs } from 'pinia'
import { useConfigStore } from '@/stores/config'

const store = useConfigStore()
const { maa_depot_enable } = storeToRefs(store)
</script>
<template>
  <n-card>
    <template #header>
      <n-checkbox v-model:checked="maa_depot_enable">
        <div class="card-title">MAA仓库扫描 {{ maa_depot_enable ? '开启' : '关闭' }}</div>
      </n-checkbox>
    </template>
  </n-card>
</template>
