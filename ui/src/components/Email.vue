<script setup>
import { useConfigStore } from '@/stores/config'
import { storeToRefs } from 'pinia'
const store = useConfigStore()

import { ref, inject } from 'vue'

const axios = inject('axios')

const mobile = inject('mobile')

const mode = ref('simple')
const test_result = ref('')

const { mail_enable, account, pass_code, mail_subject } = storeToRefs(store)

async function test_email() {
  test_result.value = '正在发送……'
  const response = await axios.get(`${import.meta.env.VITE_HTTP_URL}/test-email`)
  test_result.value = response.data
}
</script>

<template>
  <n-card>
    <template #header>
      <n-checkbox v-model:checked="mail_enable" class="email-title">
        <div class="card-title">邮件提醒</div>
        <div class="expand"></div>
        <n-radio-group class="email-mode" v-model:value="mode" disabled>
          <n-radio-button value="simple" label="简单模式" />
          <n-radio-button value="advanced" label="高级模式" />
        </n-radio-group>
      </n-checkbox>
    </template>
    <template #default>
      <template v-if="mode == 'simple'">
        <n-form
          :label-placement="mobile ? 'top' : 'left'"
          :show-feedback="false"
          label-width="96"
          label-align="left"
        >
          <n-form-item label="QQ邮箱">
            <n-input v-model:value="account" />
          </n-form-item>
          <n-form-item label="授权码">
            <template #label>
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
            <n-input v-model:value="pass_code" type="password" show-password-on="click" />
          </n-form-item>
          <n-form-item>
            <template #label>
              <span>标题前缀</span>
              <help-text>可用于区分来自多个Mower的邮件</help-text>
            </template>
            <n-input v-model:value="mail_subject" />
          </n-form-item>
        </n-form>
        <n-divider />
        <div class="email-test mt-16">
          <n-button @click="test_email">发送测试邮件</n-button>
          <div>{{ test_result }}</div>
        </div>
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

.mt-16 {
  margin-top: 16px;
}
</style>
