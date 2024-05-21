<script setup>
import { storeToRefs } from 'pinia'
import { useConfigStore } from '@/stores/config'

const store = useConfigStore()
const { check_mail_enable, report_enable, send_report, sign_in, visit_friend } = storeToRefs(store)
</script>

<template>
  <n-card title="每日任务">
    <n-flex vertical>
      <n-checkbox v-model:checked="sign_in.enable">
        <div class="item">签到活动</div>
      </n-checkbox>
      <n-divider />
      <n-checkbox v-model:checked="check_mail_enable">
        <div class="item">领取邮件</div>
      </n-checkbox>
      <n-divider />
      <n-checkbox v-model:checked="visit_friend">
        <div class="item">访问好友</div>
      </n-checkbox>
      <n-divider />
      <n-flex size="large">
        <n-checkbox v-model:checked="report_enable">
          <div class="item">读取基报</div>
        </n-checkbox>
        <n-checkbox v-model:checked="send_report" v-if="report_enable">发送邮件</n-checkbox>
      </n-flex>
    </n-flex>
  </n-card>
</template>

<style scoped>
.item {
  font-weight: 500;
  font-size: 16px;
}
.n-divider:not(.n-divider--vertical) {
  margin: 6px 0;
}
</style>
