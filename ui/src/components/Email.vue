<script setup>
defineOptions({ name: 'EmailSettings' })

import { useConfigStore } from '@/stores/config'
import { storeToRefs } from 'pinia'
const store = useConfigStore()

import { computed, inject, ref } from 'vue'

const axios = inject('axios')

const test_result = ref('')
const testing = ref(false)
const test_error = ref(false)

const {
  mail_enable,
  account,
  pass_code,
  recipient,
  mail_subject,
  custom_smtp_server,
  notification_level,
  timezone_offset
} = storeToRefs(store)

async function test_email() {
  if (testing.value) return
  testing.value = true
  test_error.value = false
  test_result.value = '正在发送……'
  try {
    const response = await axios.get(`${import.meta.env.VITE_HTTP_URL}/test-email`)
    test_result.value = response.data
    test_error.value = String(response.data).startsWith('邮件发送失败')
  } catch (error) {
    test_error.value = true
    test_result.value =
      error.response?.data?.message || error.message || '发送失败，请检查邮箱设置后重试'
  } finally {
    testing.value = false
  }
}

const levels = [
  { label: 'INFO - 基建任务、刷理智、公招汇总、基报、活动签到等', value: 'INFO' },
  { label: 'WARNING - 版本过旧、组内心情差过大、漏单、公招稀有标签等', value: 'WARNING' },
  {
    label: 'ERROR - 无法排班、专精失败、MAA调用出错、森空岛签到失败、活动签到超时、OF-1失败等',
    value: 'ERROR'
  }
]
const selectMenuProps = { class: 'settings-select-menu' }

const mailboxTypes = [
  { label: 'QQ邮箱', value: 'qq' },
  { label: '自定义邮箱', value: 'custom' }
]
const mailboxType = computed({
  get: () => (custom_smtp_server.value.enable ? 'custom' : 'qq'),
  set: (value) => (custom_smtp_server.value.enable = value === 'custom')
})
</script>

<template>
  <n-card
    title="邮件提醒"
    class="email-settings"
    data-settings-keywords="发件邮箱 自定义邮箱 SMTP服务器 加密方式 SSL/TLS STARTTLS 端口号 账号 密码 授权码"
  >
    <template #default>
      <div class="email-enable-row" data-settings-label="启用邮件提醒">
        <div class="email-enable-copy">
          <span>启用邮件提醒</span>
          <p>通过邮件接收任务汇总和异常提醒。</p>
        </div>
        <n-switch v-model:value="mail_enable" aria-label="启用邮件提醒" />
      </div>
      <h3 class="email-group-title">发件邮箱</h3>
      <n-form
        class="settings-form-stacked email-fields-grid"
        label-placement="top"
        :show-feedback="false"
      >
        <n-form-item label="邮箱类型" class="email-field-wide">
          <n-select
            v-model:value="mailboxType"
            :options="mailboxTypes"
            :consistent-menu-width="false"
            aria-label="邮箱类型"
          />
        </n-form-item>
        <n-form-item label="SMTP服务器" v-if="custom_smtp_server.enable" class="email-field-wide">
          <n-input
            v-model:value="custom_smtp_server.server"
            :input-props="{ 'aria-label': 'SMTP服务器' }"
          />
        </n-form-item>
        <n-form-item label="加密方式" v-if="custom_smtp_server.enable">
          <n-radio-group v-model:value="custom_smtp_server.encryption" aria-label="加密方式">
            <n-flex>
              <n-radio value="tls" label="SSL/TLS" />
              <n-radio value="starttls" label="STARTTLS" />
            </n-flex>
          </n-radio-group>
        </n-form-item>
        <n-form-item label="端口号" v-if="custom_smtp_server.enable">
          <mower-input-number
            v-model:value="custom_smtp_server.ssl_port"
            :input-props="{ 'aria-label': '端口号' }"
          />
        </n-form-item>
        <n-form-item :label="custom_smtp_server.enable ? '账号' : 'QQ邮箱'">
          <n-input
            v-model:value="account"
            :input-props="{ 'aria-label': custom_smtp_server.enable ? '账号' : 'QQ邮箱' }"
          />
        </n-form-item>
        <n-form-item :label="custom_smtp_server.enable ? '密码' : '授权码'">
          <template #label>
            <span class="email-field-label">
              {{ custom_smtp_server.enable ? '密码' : '授权码' }}
              <help-text v-if="!custom_smtp_server.enable" label="查看 QQ邮箱授权码获取方法">
                <n-button
                  text
                  tag="a"
                  href="https://help.mail.qq.com/detail/106/985"
                  target="_blank"
                  type="primary"
                >
                  获取 QQ邮箱授权码
                </n-button>
              </help-text>
            </span>
          </template>
          <n-input
            v-model:value="pass_code"
            type="password"
            show-password-on="click"
            :input-props="{ 'aria-label': custom_smtp_server.enable ? '密码' : '授权码' }"
          />
        </n-form-item>
      </n-form>
      <div class="email-content-group">
        <h3 class="email-group-title">通知内容</h3>
        <n-form
          class="settings-form-stacked email-fields-grid"
          label-placement="top"
          :show-feedback="false"
        >
          <n-form-item label="通知等级" class="email-field-wide">
            <n-select
              v-model:value="notification_level"
              class="settings-select-wrap"
              :options="levels"
              placement="bottom-end"
              :virtual-scroll="false"
              :menu-props="selectMenuProps"
              :consistent-menu-width="false"
              aria-label="通知等级"
            />
          </n-form-item>
          <n-form-item label="标题前缀">
            <n-input
              v-model:value="mail_subject"
              :input-props="{
                'aria-describedby': 'email-subject-description',
                'aria-label': '标题前缀'
              }"
            />
            <p id="email-subject-description" class="email-field-description">
              用于区分多个 Mower 的邮件。
            </p>
          </n-form-item>
          <n-form-item label="时差修正">
            <template #label>
              <span class="email-field-label">
                时差修正
                <help-text label="查看邮件时差修正说明">
                  收件人时区与本地电脑的时差修正。比如你在中国帮美国的朋友代挂，发送邮件的任务时间会自动转化成当地时间。
                </help-text>
              </span>
            </template>
            <mower-input-number
              v-model:value="timezone_offset"
              :input-props="{
                'aria-describedby': 'email-timezone-description',
                'aria-label': '时差修正'
              }"
            />
            <p id="email-timezone-description" class="email-field-description">
              按收件人时区调整邮件中的任务时间。
            </p>
          </n-form-item>
          <n-form-item label="收件人" class="email-field-wide">
            <n-dynamic-input v-model:value="recipient" />
            <p class="email-field-description">不填时将邮件发给自己。</p>
          </n-form-item>
        </n-form>
      </div>
      <div class="email-test" data-settings-label="发送测试邮件">
        <div class="email-test-copy">
          <span>检查邮件配置</span>
          <p>发送一封测试邮件，确认邮箱能够收到提醒。</p>
        </div>
        <n-button :loading="testing" :disabled="testing" @click="test_email">发送测试邮件</n-button>
      </div>
      <p
        v-if="test_result"
        class="email-test-result"
        :class="{ 'is-error': test_error }"
        role="status"
      >
        {{ test_result }}
      </p>
    </template>
  </n-card>
</template>

<style scoped>
.email-settings {
  container: email-settings / inline-size;
}

.email-enable-row,
.email-test {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.email-enable-row {
  padding-bottom: 20px;
  margin-bottom: 20px;
  border-bottom: 1px solid var(--settings-card-border, var(--mower-border));
}

.email-enable-copy,
.email-test-copy {
  flex: 1 1 220px;
  min-width: 0;
}

.email-enable-copy > span,
.email-test-copy > span {
  font-size: 14px;
}

.email-enable-copy p,
.email-test-copy p,
.email-field-description {
  margin: 4px 0 0;
  color: var(--mower-text-muted);
  font-size: 12px;
  line-height: 1.65;
  overflow-wrap: anywhere;
}

.email-group-title {
  margin: 0 0 16px;
  font-size: 13px;
  font-weight: 500;
  color: var(--mower-text-muted);
}

.email-settings .email-fields-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: 16px 20px;
}

.email-settings .email-fields-grid > .n-form-item {
  min-width: 0;
  padding: 0;
  border: 0;
}

.email-field-wide {
  grid-column: 1 / -1;
}

.email-field-label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.email-content-group,
.email-test {
  margin-top: 24px;
  padding-top: 24px;
  border-top: 1px solid var(--settings-card-border, var(--mower-border));
}

.email-test-result {
  margin: 16px 0 0;
  padding: 12px 14px;
  border-radius: 8px;
  background: var(--mower-control-surface);
  font-size: 13px;
  line-height: 1.65;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.email-test-result.is-error {
  color: var(--mower-error);
}

@container email-settings (max-width: 540px) {
  .email-settings .email-fields-grid {
    grid-template-columns: minmax(0, 1fr);
  }

  .email-settings :deep(.n-dynamic-input-item) {
    flex-direction: column;
    gap: 8px;
  }

  .email-settings :deep(.n-dynamic-input-item__action) {
    align-self: flex-end;
    margin: 0;
  }
}
</style>
