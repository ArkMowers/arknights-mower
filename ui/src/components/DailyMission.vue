<script setup>
import { storeToRefs } from 'pinia'
import { useConfigStore } from '@/stores/config'

const store = useConfigStore()
const {check_mail_enable, report_enable } = storeToRefs(store)
</script>
<template>
  <n-card>
    <template #header>
      <n-checkbox v-model:checked="check_mail_enable">
        <div class="card-title">邮件领取 {{ check_mail_enable ? '开启' : '关闭' }}</div>
      </n-checkbox>
    </template>
  </n-card>
  <n-card>
    <template #header>
      <n-checkbox v-model:checked="report_enable">
        <div class="card-title">读取基报 {{ report_enable ? '开启' : '关闭' }}</div>
      </n-checkbox>
    </template>
  </n-card>
</template>
