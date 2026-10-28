<script setup>
import { i18n } from '@/i18n'
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
  test_result.value = i18n.global.t('settings.email.sending')
  try {
    const response = await axios.get(`${import.meta.env.VITE_HTTP_URL}/test-email`)
    test_result.value = response.data
    test_error.value = String(response.data).startsWith('邮件发送失败')
  } catch (error) {
    test_error.value = true
    test_result.value =
      error.response?.data?.message ||
      error.message ||
      i18n.global.t('settings.email.sendingFailedCheckYourEmailSettingsAnd')
  } finally {
    testing.value = false
  }
}

const levels = computed(() => [
  {
    label: i18n.global.t('settings.email.infoBaseTasksSanityFarmingRecruitmentSummaries'),
    value: 'INFO'
  },
  {
    label: i18n.global.t('settings.email.warningOutdatedVersionLargeMoraleDifferencesWithin'),
    value: 'WARNING'
  },
  {
    label: i18n.global.t('settings.email.errorSchedulingOrMasteryFailureMaaErrors'),
    value: 'ERROR'
  }
])
const selectMenuProps = { class: 'settings-select-menu' }

const mailboxTypes = computed(() => [
  { label: i18n.global.t('settings.email.qqMail'), value: 'qq' },
  { label: i18n.global.t('settings.email.customEmail'), value: 'custom' }
])
const mailboxType = computed({
  get: () => (custom_smtp_server.value.enable ? 'custom' : 'qq'),
  set: (value) => (custom_smtp_server.value.enable = value === 'custom')
})
</script>

<template>
  <n-card
    :title="i18n.global.t('settings.email.emailNotifications')"
    class="email-settings"
    data-settings-keywords="发件邮箱 自定义邮箱 SMTP服务器 加密方式 SSL/TLS STARTTLS 端口号 账号 密码 授权码"
  >
    <template #default>
      <div
        class="email-enable-row"
        :data-settings-label="i18n.global.t('settings.email.enableEmailNotifications')"
      >
        <div class="email-enable-copy">
          <span>{{ i18n.global.t('settings.email.enableEmailNotifications') }}</span>
          <p>{{ i18n.global.t('settings.email.receiveTaskSummariesAndErrorNotificationsBy') }}</p>
        </div>
        <n-switch
          v-model:value="mail_enable"
          :aria-label="i18n.global.t('settings.email.enableEmailNotifications')"
        />
      </div>
      <h3 class="email-group-title">{{ i18n.global.t('settings.email.sender') }}</h3>
      <n-form
        class="settings-form-stacked email-fields-grid"
        label-placement="top"
        :show-feedback="false"
      >
        <n-form-item
          :label="i18n.global.t('settings.email.emailProvider')"
          class="email-field-wide"
        >
          <n-select
            v-model:value="mailboxType"
            :options="mailboxTypes"
            :consistent-menu-width="false"
            :aria-label="i18n.global.t('settings.email.emailProvider')"
          />
        </n-form-item>
        <n-form-item
          :label="i18n.global.t('settings.email.smtpServer')"
          v-if="custom_smtp_server.enable"
          class="email-field-wide"
        >
          <n-input
            v-model:value="custom_smtp_server.server"
            :input-props="{ 'aria-label': i18n.global.t('settings.email.smtpServer') }"
          />
        </n-form-item>
        <n-form-item
          :label="i18n.global.t('settings.email.encryption')"
          v-if="custom_smtp_server.enable"
        >
          <n-radio-group
            v-model:value="custom_smtp_server.encryption"
            :aria-label="i18n.global.t('settings.email.encryption')"
          >
            <n-flex>
              <n-radio value="tls" label="SSL/TLS" />
              <n-radio value="starttls" label="STARTTLS" />
            </n-flex>
          </n-radio-group>
        </n-form-item>
        <n-form-item :label="i18n.global.t('settings.email.port')" v-if="custom_smtp_server.enable">
          <mower-input-number
            v-model:value="custom_smtp_server.ssl_port"
            :input-props="{ 'aria-label': i18n.global.t('settings.email.port') }"
          />
        </n-form-item>
        <n-form-item
          :label="
            custom_smtp_server.enable
              ? i18n.global.t('settings.email.account')
              : i18n.global.t('settings.email.qqMail')
          "
        >
          <n-input
            v-model:value="account"
            :input-props="{
              'aria-label': custom_smtp_server.enable
                ? i18n.global.t('settings.email.account')
                : i18n.global.t('settings.email.qqMail')
            }"
          />
        </n-form-item>
        <n-form-item
          :label="
            custom_smtp_server.enable
              ? i18n.global.t('settings.email.password')
              : i18n.global.t('settings.email.authorizationCode')
          "
        >
          <template #label>
            <span class="email-field-label">
              {{
                custom_smtp_server.enable
                  ? i18n.global.t('settings.email.password')
                  : i18n.global.t('settings.email.authorizationCode')
              }}
              <help-text
                v-if="!custom_smtp_server.enable"
                :label="i18n.global.t('settings.email.howToGetAQqMailAuthorization')"
              >
                <n-button
                  text
                  tag="a"
                  href="https://help.mail.qq.com/detail/106/985"
                  target="_blank"
                  type="primary"
                >
                  {{ i18n.global.t('settings.email.getAQqMailAuthorizationCode') }}
                </n-button>
              </help-text>
            </span>
          </template>
          <n-input
            v-model:value="pass_code"
            type="password"
            show-password-on="click"
            :input-props="{
              'aria-label': custom_smtp_server.enable
                ? i18n.global.t('settings.email.password')
                : i18n.global.t('settings.email.authorizationCode')
            }"
          />
        </n-form-item>
      </n-form>
      <div class="email-content-group">
        <h3 class="email-group-title">{{ i18n.global.t('settings.email.notificationContent') }}</h3>
        <n-form
          class="settings-form-stacked email-fields-grid"
          label-placement="top"
          :show-feedback="false"
        >
          <n-form-item
            :label="i18n.global.t('settings.email.notificationLevel')"
            class="email-field-wide"
          >
            <n-select
              v-model:value="notification_level"
              class="settings-select-wrap"
              :options="levels"
              placement="bottom-end"
              :virtual-scroll="false"
              :menu-props="selectMenuProps"
              :consistent-menu-width="false"
              :aria-label="i18n.global.t('settings.email.notificationLevel')"
            />
          </n-form-item>
          <n-form-item :label="i18n.global.t('settings.email.subjectPrefix')">
            <n-input
              v-model:value="mail_subject"
              :input-props="{
                'aria-describedby': 'email-subject-description',
                'aria-label': i18n.global.t('settings.email.subjectPrefix')
              }"
            />
            <p id="email-subject-description" class="email-field-description">
              {{ i18n.global.t('settings.email.distinguishEmailsFromDifferentMowerInstances') }}
            </p>
          </n-form-item>
          <n-form-item :label="i18n.global.t('settings.email.timeZoneOffset')">
            <template #label>
              <span class="email-field-label">
                {{ i18n.global.t('settings.email.timeZoneOffset') }}
                <help-text :label="i18n.global.t('settings.email.aboutTheEmailTimeZoneOffset')">
                  {{ i18n.global.t('settings.email.adjustTaskTimesForTheDifferenceBetween') }}
                </help-text>
              </span>
            </template>
            <mower-input-number
              v-model:value="timezone_offset"
              :input-props="{
                'aria-describedby': 'email-timezone-description',
                'aria-label': i18n.global.t('settings.email.timeZoneOffset')
              }"
            />
            <p id="email-timezone-description" class="email-field-description">
              {{ i18n.global.t('settings.email.adjustTaskTimesInEmailsForThe') }}
            </p>
          </n-form-item>
          <n-form-item :label="i18n.global.t('settings.email.recipients')" class="email-field-wide">
            <n-dynamic-input v-model:value="recipient" />
            <p class="email-field-description">
              {{ i18n.global.t('settings.email.leaveBlankToSendEmailsToYourself') }}
            </p>
          </n-form-item>
        </n-form>
      </div>
      <div class="email-test" :data-settings-label="i18n.global.t('settings.email.sendTestEmail')">
        <div class="email-test-copy">
          <span>{{ i18n.global.t('settings.email.checkEmailSettings') }}</span>
          <p>{{ i18n.global.t('settings.email.sendATestEmailToCheckThat') }}</p>
        </div>
        <n-button :loading="testing" :disabled="testing" @click="test_email">{{
          i18n.global.t('settings.email.sendTestEmail')
        }}</n-button>
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
