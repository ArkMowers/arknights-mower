<script setup>
import { useConfigStore } from '@/stores/config'
import { usePlanStore } from '@/stores/plan'
import { storeToRefs } from 'pinia'
import { swap } from '@/utils/common'

const config_store = useConfigStore()
const { free_blacklist, theme } = storeToRefs(config_store)

const plan_store = usePlanStore()
const {
  ling_xi,
  max_resting_count,
  resting_priority,
  exhaust_require,
  rest_in_full,
  workaholic,
  backup_plans,
  sub_plan,
  refresh_trading,
  refresh_drained
} = storeToRefs(plan_store)
const { load_plan, fill_empty } = plan_store

import { computed, inject, provide, ref, watchEffect } from 'vue'
const axios = inject('axios')

const facility = ref('')
provide('facility', facility)

import { useMessage } from 'naive-ui'

const plan_editor = ref(null)

const generating_image = ref(false)

const message = useMessage()

import { sleep } from '@/utils/sleep'
import { toBlob } from 'html-to-image'
import { useLoadingBar } from 'naive-ui'

const loading_bar = useLoadingBar()

import Bowser from 'bowser'

async function save() {
  generating_image.value = true
  loading_bar.start()
  if (facility.value != '') {
    facility.value = ''
    await sleep(500)
  }
  const browser = Bowser.getParser(window.navigator.userAgent)
  let blob
  if (browser.getEngine().name == 'WebKit') {
    blob = await toBlob(plan_editor.value.outer)
  }
  blob = await toBlob(plan_editor.value.outer, {
    pixelRatio: 3,
    backgroundColor: theme.value == 'light' ? '#ffffff' : '#000000',
    style: { margin: 0, padding: '8px 0' }
  })
  generating_image.value = false
  loading_bar.finish()
  const form_data = new FormData()
  form_data.append('img', blob)
  const { data } = await axios.post(`${import.meta.env.VITE_HTTP_URL}/dialog/save/img`, form_data, {
    responseType: 'blob'
  })
  const url = window.URL.createObjectURL(data)
  const link = document.createElement('a')
  link.href = url
  link.setAttribute('download', 'plan.jpg')
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  window.URL.revokeObjectURL(url)
}

const mobile = inject('mobile')

const sub_plan_options = computed(() => {
  const result = [
    {
      label: '主表',
      value: 'main'
    }
  ]
  for (let i = 0; i < backup_plans.value.length; i++) {
    result.push({
      label: backup_plans.value[i].name,
      value: i
    })
  }
  return result
})

function create_sub_plan() {
  backup_plans.value.push({
    conf: {
      exhaust_require: [],
      free_blacklist: [],
      ling_xi: ling_xi.value,
      max_resting_count: max_resting_count.value,
      rest_in_full: [],
      resting_priority: [],
      workaholic: [],
      refresh_trading: [],
      refresh_drained: []
    },
    plan: fill_empty({}),
    trigger: {
      left: '',
      operator: '',
      right: ''
    },
    trigger_timing: 'AFTER_PLANNING',
    task: {},
    name: `plan${backup_plans.value.length}`
  })
  sub_plan.value = backup_plans.value.length - 1
}

function delete_sub_plan() {
  backup_plans.value.splice(sub_plan.value, 1)
  sub_plan.value = 'main'
}

const current_conf = ref({
  ling_xi: ling_xi.value,
  max_resting_count: max_resting_count.value,
  rest_in_full: rest_in_full.value,
  resting_priority: resting_priority.value,
  workaholic: workaholic.value,
  exhaust_require: exhaust_require.value,
  refresh_trading: refresh_trading.value
})

watchEffect(() => {
  if (sub_plan.value == 'main') {
    current_conf.value = {
      ling_xi: ling_xi.value,
      max_resting_count: max_resting_count.value,
      rest_in_full: rest_in_full.value,
      resting_priority: resting_priority.value,
      workaholic: workaholic.value,
      exhaust_require: exhaust_require.value,
      refresh_trading: refresh_trading.value,
      free_blacklist: free_blacklist.value,
      refresh_drained: refresh_drained.value
    }
  } else {
    current_conf.value = backup_plans.value[sub_plan.value].conf
  }
})

watchEffect(() => {
  if (sub_plan.value == 'main') {
    ling_xi.value = current_conf.value.ling_xi
    max_resting_count.value = current_conf.value.max_resting_count
    rest_in_full.value = current_conf.value.rest_in_full
    exhaust_require.value = current_conf.value.exhaust_require
    resting_priority.value = current_conf.value.resting_priority
    workaholic.value = current_conf.value.workaholic
    refresh_trading.value = current_conf.value.refresh_trading
    free_blacklist.value = current_conf.value.free_blacklist
    refresh_drained.value = current_conf.value.refresh_drained
  } else {
    backup_plans.value[sub_plan.value].conf = current_conf.value
  }
})

const show_trigger_editor = ref(false)
provide('show_trigger_editor', show_trigger_editor)

const show_name_editor = ref(false)
provide('show_name_editor', show_name_editor)

const show_task = ref(false)
const add_task = ref(false)
provide('show_task', show_task)
provide('add_task', add_task)

import DocumentExport from '@vicons/carbon/DocumentExport'
import DocumentImport from '@vicons/carbon/DocumentImport'
import IosArrowBack from '@vicons/ionicons4/IosArrowBack'
import IosArrowForward from '@vicons/ionicons4/IosArrowForward'
import CodeSlash from '@vicons/ionicons5/CodeSlash'
import TrashOutline from '@vicons/ionicons5/TrashOutline'
import AddTaskRound from '@vicons/material/AddTaskRound'
import PlusRound from '@vicons/material/PlusRound'
import Pencil from '@vicons/tabler/Pencil'

function import_plan({ event }) {
  const msg = event.target.response
  if (msg == '排班已加载') {
    sub_plan.value = 'main'
    load_plan()
    message.success('成功导入排班表！')
  } else {
    message.error(msg)
  }
}

const import_url = `${import.meta.env.VITE_HTTP_URL}/import`

const token = inject('token')

const export_options = [
  {
    label: '导出JSON文件',
    key: 'json'
  }
]

async function export_json() {
  const { data } = await axios.get(`${import.meta.env.VITE_HTTP_URL}/export-json`, {
    responseType: 'blob'
  })
  console.log(data)
  const url = window.URL.createObjectURL(data)
  const link = document.createElement('a')
  link.href = url
  link.setAttribute('download', 'plan.json')
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  window.URL.revokeObjectURL(url)
}

function movePlanBackward() {
  if (sub_plan.value !== 'main' && sub_plan.value > 0) {
    const currentIndex = sub_plan.value
    swap(currentIndex, currentIndex - 1, backup_plans.value)
    sub_plan.value = currentIndex - 1
  }
}

function movePlanForward() {
  if (sub_plan.value !== 'main' && sub_plan.value < backup_plans.value.length - 1) {
    const currentIndex = sub_plan.value
    swap(currentIndex, currentIndex + 1, backup_plans.value)
    sub_plan.value = currentIndex + 1
  }
}
</script>

<template>
  <trigger-dialog />
  <task-dialog />
  <rename-dialog />
  <div class="plan-bar w-980 mx-auto mt-12 mw-980">
    <n-button-group>
      <n-button :disabled="sub_plan == 'main' || sub_plan == 0" @click="movePlanBackward">
        <template #icon>
          <n-icon><ios-arrow-back /></n-icon>
        </template>
      </n-button>
      <n-button
        :disabled="sub_plan == 'main' || sub_plan == backup_plans.length - 1"
        @click="movePlanForward"
      >
        <template #icon>
          <n-icon><ios-arrow-forward /></n-icon>
        </template>
      </n-button>
    </n-button-group>
    <n-button-group>
      <n-select v-model:value="sub_plan" :style="{ width: '150px' }" :options="sub_plan_options" />
      <n-button :disabled="sub_plan == 'main'" @click="show_name_editor = true">
        <template #icon>
          <n-icon><Pencil /></n-icon>
        </template>
      </n-button>
    </n-button-group>
    <n-button-group>
      <n-button @click="create_sub_plan">
        <template #icon>
          <n-icon :size="22"><plus-round /></n-icon>
        </template>
        新建副表
      </n-button>
      <n-button :disabled="sub_plan == 'main'" @click="show_trigger_editor = true">
        <template #icon>
          <n-icon><code-slash /></n-icon>
        </template>
        编辑触发条件
      </n-button>
      <n-button :disabled="sub_plan == 'main'" @click="show_task = true">
        <template #icon>
          <n-icon><add-task-round /></n-icon>
        </template>
        编辑任务
      </n-button>
      <n-button :disabled="sub_plan == 'main'" @click="delete_sub_plan">
        <template #icon>
          <n-icon><trash-outline /></n-icon>
        </template>
        删除此副表
      </n-button>
    </n-button-group>
    <n-upload
      style="width: auto; margin-left: 8px"
      :action="import_url"
      :headers="{ token: token }"
      :show-file-list="false"
      name="img"
      @finish="import_plan"
    >
      <n-button>
        <template #icon>
          <n-icon><document-import /></n-icon>
        </template>
        导入排班
      </n-button>
    </n-upload>
    <drop-down :select="export_json" :options="export_options">
      <n-button @click="save" :loading="generating_image" :disabled="generating_image">
        <template #icon>
          <n-icon><document-export /></n-icon>
        </template>
        导出图片
      </n-button>
    </drop-down>
  </div>
  <plan-editor ref="plan_editor" class="w-980 mx-auto mw-980 px-12" />
  <n-form
    class="w-980 mx-auto mb-12 px-12 mw-980"
    :label-placement="mobile ? 'top' : 'left'"
    :show-feedback="false"
    label-width="160"
    label-align="left"
  >
    <n-form-item>
      <template #label>
        <span>令夕模式</span>
        <help-text>
          <div>令夕上班时起作用</div>
          <div>启动Mower前需要手动对齐心情</div>
          <div>感知：夕心情-令心情=12</div>
          <div>烟火：令心情-夕心情=12</div>
          <div>均衡：夕令心情一样</div>
        </help-text>
      </template>
      <n-radio-group v-model:value="current_conf.ling_xi">
        <n-space>
          <n-radio :value="1">感知信息</n-radio>
          <n-radio :value="2">人间烟火</n-radio>
          <n-radio :value="3">均衡模式</n-radio>
        </n-space>
      </n-radio-group>
    </n-form-item>
    <n-form-item>
      <template #label><span>最大组人数</span><help-text>请查阅文档</help-text></template>
      <n-input-number v-model:value="current_conf.max_resting_count">
        <template #suffix>人</template>
      </n-input-number>
    </n-form-item>
    <n-form-item>
      <template #label><span>需要回满心情的干员</span><help-text>请查阅文档</help-text></template>
      <slick-operator-select v-model="current_conf.rest_in_full"></slick-operator-select>
    </n-form-item>
    <n-form-item>
      <template #label>
        <span>需要用尽心情的干员</span><help-text>仅推荐写入具有暖机技能的干员</help-text>
      </template>
      <slick-operator-select v-model="current_conf.exhaust_require"></slick-operator-select>
    </n-form-item>
    <n-form-item>
      <template #label>
        <span>0心情工作的干员</span><help-text>心情涣散状态仍能触发技能的干员</help-text>
      </template>
      <slick-operator-select v-model="current_conf.workaholic"></slick-operator-select>
    </n-form-item>
    <n-form-item>
      <template #label><span>宿舍低优先级干员</span><help-text>请查阅文档</help-text></template>
      <slick-operator-select v-model="current_conf.resting_priority"></slick-operator-select>
    </n-form-item>
    <n-form-item>
      <template #label>
        <span>跑单时间刷新干员</span>
        <help-text>
          <p>贸易站外影响贸易效率的干员</p>
          <p>
            默认情况下，mower 只在贸易站内干员换班后重读所有贸易站的订单剩余时间。<br />
            若有贸易站外的干员影响贸易效率，且与贸易站内的干员不在一组，则需写入此选项中。
          </p>
        </help-text>
      </template>
      <slick-operator-select
        v-model="current_conf.refresh_trading"
        select_placeholder="填入在贸易站外影响贸易效率的干员"
      ></slick-operator-select>
    </n-form-item>
    <n-form-item>
      <template #label>
        <span>用尽刷新</span>
        <help-text>
          <p>会影响用尽干员心情消耗速率的干员</p>
          <p>在填入该选项的干员上下班后，会重新读取用尽干员的下班时间</p>
        </help-text>
      </template>
      <slick-operator-select v-model="current_conf.refresh_drained"></slick-operator-select>
    </n-form-item>
    <n-form-item>
      <template #label>
        <span>宿舍黑名单</span>
        <help-text>不希望进行填充宿舍的干员</help-text>
      </template>
      <slick-operator-select v-model="current_conf.free_blacklist"></slick-operator-select>
    </n-form-item>
  </n-form>
</template>

<style scoped lang="scss">
.w-980 {
  width: 100%;
  max-width: 980px;
}

.mx-auto {
  margin: 0 auto;
}

.mt-12 {
  margin-top: 12px;
}

.mb-12 {
  margin-bottom: 12px;
}

.px-12 {
  padding: 0 12px;
}

.mw-980 {
  min-width: 980px;
}

.plan-bar {
  display: flex;
  flex-direction: row;
  flex-grow: 0;
  gap: 6px;
  padding: 0 12px;
}
</style>
