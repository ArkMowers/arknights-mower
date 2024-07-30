<script setup>
import { useConfigStore } from '@/stores/config'
import { storeToRefs } from 'pinia'
const store = useConfigStore()

import { inject, ref } from 'vue'

const axios = inject('axios')

const mobile = inject('mobile')

const test_result = ref('')

const {
  mail_enable,
  account,
  pass_code,
  recipient,
  mail_subject,
  custom_smtp_server,
  notification_level
} = storeToRefs(store)

async function test_email() {
  test_result.value = '正在发送……'
  const response = await axios.get(`${import.meta.env.VITE_HTTP_URL}/test-email`)
  test_result.value = response.data
}

const levels = [
  { label: 'INFO - 基建任务、刷理智、公招、基报、活动签到等', value: 'INFO' },
  { label: 'WARNING - 版本过旧、组内心情差过大、漏单等', value: 'WARNING' },
  {
    label: 'ERROR - 无法排班、专精失败、Maa调用出错、森空岛签到失败、活动签到超时、OF-1失败等',
    value: 'ERROR'
  }
]
</script>

<template>
  <n-card>
    <template #header>
      <n-checkbox v-model:checked="mail_enable" class="email-title">
        <div class="card-title">邮件提醒</div>
        <div class="expand"></div>
      </n-checkbox>
      <n-button
        v-if="mobile"
        @click="custom_smtp_server.enable = !custom_smtp_server.enable"
        type="primary"
        ghost
        >{{ custom_smtp_server.enable ? '自定义邮箱' : 'QQ邮箱' }}</n-button
      >
      <n-radio-group v-else class="email-mode" v-model:value="custom_smtp_server.enable">
        <n-radio-button :value="false" label="QQ邮箱" />
        <n-radio-button :value="true" label="自定义邮箱" />
      </n-radio-group>
    </template>
    <template #default>
      <n-form
        :label-placement="mobile ? 'top' : 'left'"
        :show-feedback="false"
        label-width="96"
        label-align="left"
      >
        <n-form-item label="SMTP服务器" v-if="custom_smtp_server.enable">
          <n-input v-model:value="custom_smtp_server.server" />
        </n-form-item>
        <n-form-item label="加密方式" v-if="custom_smtp_server.enable">
          <n-radio-group v-model:value="custom_smtp_server.encryption">
            <n-flex>
              <n-radio value="tls" label="SSL/TLS" />
              <n-radio value="starttls" label="STARTTLS" />
            </n-flex>
          </n-radio-group>
        </n-form-item>
        <n-form-item label="端口号" v-if="custom_smtp_server.enable">
          <n-input-number v-model:value="custom_smtp_server.ssl_port" />
        </n-form-item>
        <n-form-item>
          <template #label>
            <span v-if="custom_smtp_server.enable">账号</span>
            <span v-else>QQ邮箱</span>
          </template>
          <n-input v-model:value="account" />
        </n-form-item>
        <n-form-item>
          <template #label>
            <span v-if="custom_smtp_server.enable">密码</span>
            <template v-else>
              <span>授权码</span>
              <help-text>
                <n-button
                  text
                  tag="a"
                  href="https://service.mail.qq.com/detail/0/75"
                  target="_blank"
                  type="primary"
                >
                  https://service.mail.qq.com/detail/0/75
                </n-button>
              </help-text>
            </template>
          </template>
          <n-input v-model:value="pass_code" type="password" show-password-on="click" />
        </n-form-item>
        <n-form-item label="通知等级">
          <n-select v-model:value="notification_level" :options="levels" />
        </n-form-item>
        <n-form-item>
          <template #label>
            <span>标题前缀</span>
            <help-text>可用于区分来自多个Mower的邮件</help-text>
          </template>
          <n-input v-model:value="mail_subject" />
        </n-form-item>
        <n-form-item>
          <template #label>
            <span>收件人</span>
            <help-text>不填时将邮件发给自己</help-text>
          </template>
          <n-dynamic-input v-model:value="recipient" />
        </n-form-item>
      </n-form>
      <n-divider />
      <div class="email-test mt-16">
        <n-button @click="test_email">发送测试邮件</n-button>
        <div>{{ test_result }}</div>
      </div>
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

.mt-16 {
  margin-top: 16px;
}
</style>
