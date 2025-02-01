<script setup>
import { useConfigStore } from '@/stores/config'
import { storeToRefs } from 'pinia'

const store = useConfigStore()

const { maa_mail, maa_recruit, maa_orundum, maa_mining, maa_specialaccess } = storeToRefs(store)
</script>

<template>
  <n-card title="领取奖励">
    <n-flex vertical>
      <n-checkbox v-model:checked="maa_mail">
        <div class="item">领取所有邮件奖励</div>
      </n-checkbox>
      <n-divider />
      <n-checkbox v-model:checked="maa_recruit">
        <div class="item">进行限定池赠送的每日免费单抽</div>
      </n-checkbox>
      <n-divider />
      <n-checkbox v-model:checked="maa_orundum">
        <div class="item">领取幸运墙的每日合成玉奖励</div>
      </n-checkbox>
      <n-divider />
      <n-checkbox v-model:checked="maa_mining">
        <div class="item">领取限时开采许可的每日合成玉奖励</div>
      </n-checkbox>
      <n-divider />
      <n-checkbox v-model:checked="maa_specialaccess">
        <div class="item">领取五周年赠送月卡奖励</div>
      </n-checkbox>
      <!-- <n-flex>
        <n-checkbox v-model:checked="sign_in.enable">
          <div class="item">签到活动</div>
        </n-checkbox>
        <help-text>游戏内签到、矿区、限定池每日单抽等</help-text>
      </n-flex> -->
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
