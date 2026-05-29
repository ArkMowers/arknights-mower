<script setup>
import { useConfigStore } from '@/stores/config'
import { storeToRefs } from 'pinia'
import { inject, ref, computed } from 'vue'
const axios = inject('axios')

const store = useConfigStore()

const { check_mail_enable, report_enable, sign_in, visit_friend, skland_info, skland_enable } =
  storeToRefs(store)

const sign_msg = ref('')

async function test_sign() {
  sign_msg.value = '正在测试签到……'
  const response = await axios.get(`${import.meta.env.VITE_HTTP_URL}/check-skland-sign`)
  sign_msg.value = response.data
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
  <n-card title="每日任务">
    <n-flex vertical>
      <n-checkbox v-model:checked="skland_enable">
        <div class="item">森空岛签到</div>
        <help-text>
          <div>签到失败时，请尝试：</div>
          <ol style="margin: 0">
            <li>检查森空岛连接是否正常；</li>
            <li>检查是否勾选了未绑定的区服/游戏</li>
          </ol>
          <div>Tips: 可以在根目录下的tmp/skland.csv中查看签到详情</div>
        </help-text>
      </n-checkbox>
      <n-tabs type="line" animated>
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
      <n-flex style="misc-container" align="center">
        <n-button :disabled="!enable_test" @click="test_sign">测试签到</n-button>
        <div>{{ sign_msg }}</div>
      </n-flex>
      <n-divider />
      <n-checkbox v-model:checked="check_mail_enable">
        <div class="item">领取邮件</div>
      </n-checkbox>
      <n-divider />
      <n-checkbox v-model:checked="visit_friend">
        <div class="item">访问好友</div>
      </n-checkbox>
      <n-divider />
      <n-flex>
        <n-checkbox v-model:checked="report_enable">
          <div class="item">读取基报</div>
        </n-checkbox>
      </n-flex>
      <n-divider />
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
