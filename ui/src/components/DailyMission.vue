<script setup>
import { useConfigStore } from '@/stores/config'
import { storeToRefs } from 'pinia'

const store = useConfigStore()

const {
  check_mail_enable,
  report_enable,
  send_report,
  sign_in,
  visit_friend,
  skland_info,
  skland_enable
} = storeToRefs(store)
</script>

<template>
  <n-card title="每日任务">
    <n-flex vertical>
      <n-checkbox v-model:checked="skland_enable">
        <div class="item">森空岛签到</div>
      </n-checkbox>
      <div v-for="account_info in skland_info" :key="account_info.account">
        <n-flex>
          <n-checkbox v-model:checked="account_info.isCheck" style="margin-right: 12px">
            森空岛账号：{{ account_info.account }}
          </n-checkbox>
          <n-checkbox v-model:checked="account_info.sign_in_official" style="margin-right: 12px">
            官服签到
          </n-checkbox>
          <n-checkbox v-model:checked="account_info.sign_in_bilibili" style="margin-right: 12px">
            B服签到
          </n-checkbox>
        </n-flex>
      </div>
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
      <n-divider />
      <n-flex>
        <n-checkbox v-model:checked="sign_in.enable">
          <div class="item">签到活动</div>
        </n-checkbox>
        <help-text>游戏内签到、矿区、限定池每日单抽等</help-text>
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
