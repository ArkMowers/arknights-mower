<script setup>
import { useConfigStore } from '@/stores/config'
import { storeToRefs } from 'pinia'
import { inject, ref, computed } from 'vue'
const props = defineProps({
  task: { type: String, default: 'all' },
  showEnable: { type: Boolean, default: true }
})
const emit = defineEmits(['configure-accounts'])
const title = computed(
  () => ({ report: '读取基报', skland: '森空岛签到', mail: '领取邮件' })[props.task] || '每日任务'
)
const axios = inject('axios')

const store = useConfigStore()

const { check_mail_enable, mail_skip_clear_read, report_enable, skland_info, skland_enable } =
  storeToRefs(store)

const sign_msg = ref('')
const testing = ref(false)
const sign_error = ref(false)

async function test_sign() {
  if (testing.value || !enable_test.value) return
  testing.value = true
  sign_error.value = false
  sign_msg.value = '正在测试签到……'
  try {
    const response = await axios.get(`${import.meta.env.VITE_HTTP_URL}/check-skland-sign`)
    sign_msg.value = Array.isArray(response.data)
      ? response.data.join('\n')
      : String(response.data ?? '')
  } catch {
    sign_error.value = true
    sign_msg.value = '测试签到失败，请检查连接后重试'
  } finally {
    testing.value = false
  }
}

const enable_test = computed(() => {
  return skland_info.value.some((item) => {
    return item.account?.trim() && item.password?.trim()
  })
})

// 复选框逻辑
// 账号勾选时相当于全选
const AllCheck = (item, status, game) => {
  if (game == 'arknights') {
    item.arknights_isCheck = status
    item.sign_in_official = status
    item.sign_in_bilibili = status
  } else if (game == 'endfield') {
    item.endfield_isCheck = status
    item.sign_in_endfield_official = status
    item.sign_in_endfield_bilibili = status
  }
}
// 区服为空时同步账号为空
const SyncStatus = (item, game) => {
  if (game == 'arknights') {
    item.arknights_isCheck = item.sign_in_official || item.sign_in_bilibili
  } else if (game == 'endfield') {
    item.endfield_isCheck = item.sign_in_endfield_official || item.sign_in_endfield_bilibili
  }
}
</script>

<template>
  <n-card :title="title">
    <n-flex vertical>
      <n-flex
        v-show="task === 'all' || task === 'skland'"
        vertical
        data-daily-task="skland"
        data-task-editor="skland"
      >
        <n-checkbox v-if="showEnable" v-model:checked="skland_enable">
          <div class="item">森空岛签到</div>
        </n-checkbox>
        <div v-if="!skland_info.length" class="skland-empty">
          <p>尚未添加森空岛账号</p>
          <n-button
            v-if="!showEnable && task === 'skland'"
            type="primary"
            secondary
            @click="emit('configure-accounts')"
          >
            添加森空岛账号
          </n-button>
        </div>
        <n-tabs v-else type="line" animated>
          <n-tab-pane name="arknights" tab="明日方舟">
            <div v-for="account_info in skland_info" :key="account_info.account">
              <n-flex>
                <n-checkbox
                  v-model:checked="account_info.arknights_isCheck"
                  @update:checked="(status) => AllCheck(account_info, status, 'arknights')"
                  style="margin-right: 12px"
                >
                  森空岛账号：{{ account_info.account }}
                </n-checkbox>
                <div style="margin-left: auto">
                  <n-checkbox
                    v-model:checked="account_info.sign_in_official"
                    @update:checked="() => SyncStatus(account_info, 'arknights')"
                    style="margin-right: 12px"
                  >
                    官服签到
                  </n-checkbox>
                  <n-checkbox
                    v-model:checked="account_info.sign_in_bilibili"
                    @update:checked="() => SyncStatus(account_info, 'arknights')"
                    style="margin-right: 12px"
                  >
                    B服签到
                  </n-checkbox>
                </div>
              </n-flex>
            </div>
          </n-tab-pane>
          <n-tab-pane name="endfield" tab="明日方舟终末地">
            <div v-for="account_info in skland_info" :key="account_info.account">
              <n-flex>
                <n-checkbox
                  v-model:checked="account_info.endfield_isCheck"
                  @update:checked="(status) => AllCheck(account_info, status, 'endfield')"
                  style="margin-right: 12px"
                >
                  森空岛账号：{{ account_info.account }}
                </n-checkbox>
                <div style="margin-left: auto">
                  <n-checkbox
                    v-model:checked="account_info.sign_in_endfield_official"
                    @update:checked="() => SyncStatus(account_info, 'endfield')"
                    style="margin-right: 12px"
                  >
                    官服签到
                  </n-checkbox>
                  <n-checkbox
                    v-model:checked="account_info.sign_in_endfield_bilibili"
                    @update:checked="() => SyncStatus(account_info, 'endfield')"
                    style="margin-right: 12px"
                  >
                    B服签到
                  </n-checkbox>
                </div>
              </n-flex>
            </div>
          </n-tab-pane>
        </n-tabs>
        <n-flex v-if="skland_info.length" class="sign-test" align="center">
          <n-button :disabled="!enable_test || testing" :loading="testing" @click="test_sign">
            测试签到
          </n-button>
          <help-text label="森空岛签到说明">
            <div>签到失败时，请尝试：</div>
            <ol style="margin: 0">
              <li>检查森空岛连接是否正常；</li>
              <li>检查是否勾选了未绑定的区服/游戏</li>
            </ol>
            <div>Tips: 可以在根目录下的tmp/skland.csv中查看签到详情</div>
          </help-text>
          <div class="sign-result" :class="{ 'sign-result-error': sign_error }" aria-live="polite">
            {{ sign_msg }}
          </div>
        </n-flex>
      </n-flex>
      <n-divider v-show="task === 'all'" />
      <n-flex
        v-show="task === 'all' || task === 'mail'"
        align="center"
        data-daily-task="mail"
        data-task-editor="mail"
      >
        <n-checkbox v-if="showEnable" v-model:checked="check_mail_enable">
          <div class="item">领取邮件</div>
        </n-checkbox>
        <n-checkbox v-model:checked="mail_skip_clear_read" :disabled="!check_mail_enable">
          <div>跳过清除已读</div>
        </n-checkbox>
      </n-flex>
      <n-divider v-show="task === 'all'" />
      <n-flex
        v-show="task === 'all' || task === 'report'"
        data-daily-task="report"
        data-task-editor="report"
      >
        <n-checkbox v-if="showEnable" v-model:checked="report_enable">
          <div class="item">读取基报</div>
        </n-checkbox>
      </n-flex>
      <p v-if="!showEnable && task === 'report'">无需额外设置</p>
      <n-divider v-show="task === 'all'" />
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

.skland-empty {
  padding: 16px 0;
}

.skland-empty p {
  margin: 0 0 12px;
}

.sign-test {
  margin-top: 12px;
}

.sign-result {
  flex: 1 1 220px;
  min-width: 0;
  max-height: 200px;
  overflow-y: auto;
  overflow-wrap: anywhere;
  white-space: pre-line;
}

.sign-result-error {
  color: var(--mower-error);
}
</style>
