<script setup>
import { useConfigStore } from '@/stores/config'
import { storeToRefs } from 'pinia'
const store = useConfigStore()

import { ref } from 'vue'

const mode = ref('simple')

const { mail_enable, account, pass_code } = storeToRefs(store)
</script>

<template>
  <n-card>
    <template #header>
      <n-checkbox v-model:checked="mail_enable" class="email-title">
        <div class="card-title">邮件提醒</div>
        <div class="expand"></div>
        <n-radio-group class="email-mode" v-model:value="mode">
          <n-radio-button value="simple" label="简单模式" />
          <n-radio-button value="advanced" label="高级模式" />
        </n-radio-group>
      </n-checkbox>
    </template>
    <template #default>
      <template v-if="mode == 'simple'">
        <p>在任务完成后发送提醒邮件。</p>
        <p>
          在简单模式下，Mower使用您的QQ邮箱。
          <n-button
            text
            tag="a"
            href="https://service.mail.qq.com/detail/0/75"
            target="_blank"
            type="primary"
          >
            什么是授权码？
          </n-button>
        </p>
        <table class="email-table">
          <tr>
            <td class="email-label">QQ邮箱</td>
            <td><n-input v-model:value="account"></n-input></td>
          </tr>
          <tr>
            <td class="email-label">授权码</td>
            <td>
              <n-input v-model:value="pass_code" type="password" show-password-on="click"></n-input>
            </td>
          </tr>
        </table>
        <div class="email-test">
          <n-button>发送测试邮件</n-button>
          <div></div>
        </div>
        <n-divider />
        <table class="email-table">
          <tr>
            <td class="email-label">邮件主题</td>
            <td><n-input></n-input></td>
          </tr>
        </table>
        <div>邮件主题可用于区分多开的Mower。</div>
      </template>
    </template>
  </n-card>
</template>

<style scoped>
.email-title {
  width: 100%;
}

.expand {
  flex-grow: 1;
}

.email-table {
  width: 100%;
  margin-bottom: 12px;
}

.email-test {
  display: flex;
  align-items: center;
  gap: 16px;
}

.email-mode {
  margin-left: 20px;
}

.email-label {
  width: 68px;
}

p {
  margin: 0 0 10px 0;
}

.card-title {
  font-weight: 500;
  font-size: 18px;
}
</style>
