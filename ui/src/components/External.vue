<script setup>
import { useConfigStore } from '@/stores/config'
import { storeToRefs } from 'pinia'
import { inject, h } from 'vue'
import { NTag } from 'naive-ui'
import { ref } from 'vue'

const axios = inject('axios')

const store = useConfigStore()

const maa_add_task = ref('禁用')

const {
  mail_enable,
  account,
  pass_code,
  maa_enable,
  maa_path,
  maa_adb_path,
  maa_weekly_plan,
  maa_rg_enable,
  sleep_min,
  sleep_max,
  sss_type,
  copilot_file_location,
  copilot_loop_times,
  maa_mall_buy,
  maa_mall_blacklist,
  maa_gap,
  maa_recruitment_time,
  maa_recruit_only_4
} = storeToRefs(store)

const { shop_list } = store
const sss_option = ref([
  { label: '约翰老妈新建地块', value: 1 },
  { label: '雷神工业测试平台', value: 2 }
])

async function select_maa_dir() {
  const response = await axios.get(`${import.meta.env.VITE_HTTP_URL}/dialog/folder`)
  const folder_path = response.data
  if (folder_path) {
    maa_path.value = folder_path
  }
}

async function select_maa_adb_path() {
  const response = await axios.get(`${import.meta.env.VITE_HTTP_URL}/dialog/file`)
  const file_path = response.data
  if (file_path) {
    maa_adb_path.value = file_path
  }
}

function render_tag({ option, handleClose }) {
  return h(
    NTag,
    {
      type: option.type,
      closable: true,
      onMousedown: (e) => {
        e.preventDefault()
      },
      onClose: (e) => {
        e.stopPropagation()
        handleClose()
      }
    },
    { default: () => (option.label == '' ? '（上次作战）' : option.label) }
  )
}

function create_tag(label) {
  if (label == ' ') {
    return {
      label: '（上次作战）',
      value: ''
    }
  } else {
    return {
      label,
      value: label
    }
  }
}

function selectTab(tab) {
  maa_add_task.value = tab
}
</script>

<template>
  <div class="home-container external-container">
    <n-card>
      <template #header>
        <n-checkbox v-model:checked="mail_enable" class="email-title">
          <div class="card-title">邮件提醒</div>
          <div class="expand"></div>
          <n-radio-group class="email-mode">
            <n-radio-button value="simple" label="简单模式" />
            <n-radio-button value="advanced" label="高级模式" />
          </n-radio-group>
        </n-checkbox>
      </template>
      <template #default>
        <p>在任务完成后发送提醒邮件。</p>
        <p>
          在简单模式下，Mower使用您的QQ邮箱。
          <n-button text tag="a" href="https://service.mail.qq.com/detail/0/75" target="_blank" type="primary">
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
    </n-card>
    <n-card>
      <template #header>
        <n-checkbox v-model:checked="maa_enable">
          <div class="card-title">MAA</div>
        </n-checkbox>
      </template>
      <template #default>
        <table class="maa-table">
          <tr>
            <td class="table-space maa-table-label">MAA目录</td>
            <td class="input-td"><n-input v-model:value="maa_path"></n-input></td>
            <td class="table-space">
              <n-button @click="select_maa_dir">...</n-button>
            </td>
          </tr>
          <tr>
            <td class="table-space">adb地址</td>
            <td><n-input v-model:value="maa_adb_path"></n-input></td>
            <td>
              <n-button @click="select_maa_adb_path">...</n-button>
            </td>
          </tr>
          <tr>
            <td>MAA启动间隔(小时)：</td>
            <td>
              <n-input-number v-model:value="maa_gap"></n-input-number>
            </td>
            <td colspan="4">
              <n-checkbox v-model:checked="maa_recruitment_time"
                >公招三星设置7:40而非9:00</n-checkbox
              >
            </td>
            <td colspan="4">
              <n-checkbox v-model:checked="maa_recruit_only_4">仅公招四星</n-checkbox>
            </td>
          </tr>
          <tr>
            <td class="table-space">肉鸽：</td>
            <td colspan="3">
              <n-radio-group v-model:value="maa_rg_enable">
                <n-space>
                  <n-radio :value="1">启用</n-radio>
                  <n-radio :value="0">禁用</n-radio>
                </n-space>
              </n-radio-group>
            </td>
          </tr>
          <tr>
            <td class="table-space maa-mall">信用商店 优先购买</td>
            <td colspan="2">
              <n-select multiple filterable tag :options="shop_list" v-model:value="maa_mall_buy" />
            </td>
            <td class="table-space maa-mall">信用商店 黑名单</td>
            <td colspan="2">
              <n-select
                multiple
                filterable
                tag
                :options="shop_list"
                v-model:value="maa_mall_blacklist"
              />
            </td>
          </tr>
        </table>
        <div style="border: 1px solid black; width: 500px; padding: 10px">
          <div class="tab-buttons">
            <button @click="selectTab('禁用')" :class="{ active: maa_add_task === '禁用' }">
              禁用
            </button>
            <button @click="selectTab('肉鸽')" :class="{ active: maa_add_task === '肉鸽' }">
              肉鸽
            </button>
            <button @click="selectTab('保全')" :class="{ active: maa_add_task === '保全' }">
              保全
            </button>
            <button @click="selectTab('生息演算')" :class="{ active: maa_add_task === '生息演算' }">
              生息演算
            </button>
          </div>

          <div class="tab-content">
            <div v-if="maa_add_task === '禁用'"></div>
            <div v-if="maa_add_task === '肉鸽'">
              <table>
                <tr>
                  <td class="table-space">休息时间开始</td>
                  <td class="table-space">
                    <n-input v-model:value="sleep_min" placeholder="8:00"></n-input>
                  </td>
                  <td class="table-space">休息时间结束</td>
                  <td class="table-space">
                    <n-input v-model:value="sleep_max" placeholder="10:00"></n-input>
                  </td>
                </tr>
              </table>
            </div>
            <div v-if="maa_add_task === '保全'">
              <table>
                <tr>
                  <td class="select-label">保全派驻关卡：</td>
                  <td class="table-space">
                    <n-select
                      tag
                      :options="sss_option"
                      class="sss-select"
                      v-model:value="sss_type"
                    />
                  </td>
                  <td class="select-label">循环次数：</td>
                  <td style="width: 50px">
                    <n-input v-model:value="copilot_loop_times" placeholder="10">10</n-input>
                  </td>
                </tr>
                <tr>
                  <td class="select-label">作业地址：</td>
                  <td colspan="2" class="input-td">
                    <n-input v-model:value="copilot_file_location"></n-input>
                  </td>
                  <td class="table-space">
                    <n-button @click="select_maa_dir">...</n-button>
                  </td>
                </tr>
              </table>
            </div>
            <div v-if="maa_add_task === '生息演算'">
              <p>生息演算未开放</p>
            </div>
          </div>
        </div>
        <n-h3>周计划</n-h3>
        <span>关卡填写说明：</span>
        <ul>
          <li><b>基本操作</b>：输入关卡名，按回车键确认。文本变为标签，代表输入成功。</li>
          <li><b>上次作战</b>：输入空格后回车，生成（上次作战）标签。</li>
          <li>
            <b>多个关卡</b>
            ：填入多个关卡时，按顺序依次刷取所有关卡。关卡无法刷取或刷取结束后，继续尝试下一关卡。例：
            <ul>
              <li>HE-7、（上次作战）：刷活动关HE-7，若活动未开放，则刷上一关。</li>
              <li>AP-5、1-7：刷红票本AP-5，剩余体力刷1-7。</li>
            </ul>
          </li>
          <li><b>不刷理智</b>：留空表示不刷理智。</li>
        </ul>
        <table>
          <tr v-for="plan in maa_weekly_plan" :key="plan.weekday">
            <td class="table-space">
              <n-h4>{{ plan.weekday }}</n-h4>
            </td>
            <td>关卡：</td>
            <td class="table-space maa-stage">
              <n-select
                v-model:value="plan.stage"
                multiple
                filterable
                tag
                :show="false"
                :show-arrow="false"
                :render-tag="render_tag"
                :on-create="create_tag"
              />
            </td>
            <td>理智药：</td>
            <td>
              <n-input-number v-model:value="plan.medicine" :min="0"></n-input-number>
            </td>
          </tr>
        </table>
      </template>
    </n-card>
  </div>
</template>

<style scoped>
.external-container {
  max-width: 600px;
  margin: 0 auto;
}

h4 {
  margin: 0;
}

.tab-buttons {
  display: flex;
}

.sss-select {
  width: 175px;
}

.tab-buttons button {
  padding: 8px 16px;
  background-color: #f0f0f0;
  border: none;
  border-radius: 4px;
  margin-right: 8px;
  cursor: pointer;
}

.tab-buttons button.active {
  background-color: #ccc;
}

.tab-content {
  margin-top: 16px;
}

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

.card-title {
  font-weight: 500;
  font-size: 16px;
}

.maa-table {
  width: 100%;
}

.maa-table-label {
  width: 70px;
}

.maa-stage {
  min-width: 300px;
}

.maa-mall {
  width: 70px;
  word-wrap: break-word;
  word-break: break-all;
}

ul {
  padding-left: 24px;
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
</style>

<style>
.n-checkbox .n-checkbox__label {
  flex-grow: 1;
  display: flex;
  align-items: center;
  padding-right: 0;
}

.n-divider:not(.n-divider--vertical) {
  margin: 14px 0 8px;
}
</style>
