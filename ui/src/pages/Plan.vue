<script setup>
import { storeToRefs } from 'pinia'
import { useConfigStore } from '@/stores/config'
import { usePlanStore } from '@/stores/plan'
import { deepcopy } from '@/utils/deepcopy'

const config_store = useConfigStore()
const { plan_file, free_blacklist } = storeToRefs(config_store)
const { build_config } = config_store

const plan_store = usePlanStore()
const {
  ling_xi,
  max_resting_count,
  resting_priority,
  exhaust_require,
  rest_in_full,
  operators,
  workaholic,
  backup_plans,
  sub_plan
} = storeToRefs(plan_store)
const { load_plan, fill_empty } = plan_store

import { inject, ref, computed, provide } from 'vue'
const axios = inject('axios')

import { file_dialog } from '@/utils/dialog'

async function open_plan_file() {
  const file_path = await file_dialog()
  if (file_path) {
    plan_file.value = file_path
    await axios.post(`${import.meta.env.VITE_HTTP_URL}/conf`, build_config())
    await load_plan()
  }
}

import { toBlob } from 'html-to-image'
import { useMessage } from 'naive-ui'

const plan_editor = ref(null)

const generating_image = ref(false)

const message = useMessage()
const loading = ref(null)

async function save() {
  generating_image.value = true
  loading.value = message.loading('正在生成图片……', { duration: 0 })
  if (
    /webkit/i.test(navigator.userAgent) &&
    /gecko/i.test(navigator.userAgent) &&
    /safari/i.test(navigator.userAgent)
  ) {
    await toBlob(plan_editor.value.outer)
  }
  const blob = await toBlob(plan_editor.value.outer, { pixelRatio: 3, backgroundColor: 'white' })
  loading.value.destroy()
  generating_image.value = false
  const form_data = new FormData()
  form_data.append('img', blob)
  const resp = await axios.post(`${import.meta.env.VITE_HTTP_URL}/dialog/save/img`, form_data)
  message.info(resp.data)
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
      label: `副表${i + 1}`,
      value: i
    })
  }
  return result
})

function create_sub_plan() {
  backup_plans.value.push({
    conf: {
      exhaust_require: deepcopy(exhaust_require.value),
      free_blacklist: deepcopy(free_blacklist.value),
      ling_xi: ling_xi.value,
      max_resting_count: max_resting_count.value,
      rest_in_full: deepcopy(rest_in_full.value),
      resting_priority: deepcopy(resting_priority.value),
      workaholic: deepcopy(workaholic.value)
    },
    plan: fill_empty({}),
    trigger: {
      left: '',
      operator: '',
      right: ''
    },
    task: {}
  })
  sub_plan.value = backup_plans.value.length - 1
}

function delete_sub_plan() {
  backup_plans.value.splice(sub_plan.value, 1)
  sub_plan.value = 'main'
}

const current_conf = computed(() => {
  if (sub_plan.value == 'main') {
    return {}
  }
  return backup_plans.value[sub_plan.value].conf
})

const show_trigger_editor = ref(false)
provide('show_trigger_editor', show_trigger_editor)

const show_task = ref(false)
provide('show_task', show_task)
</script>

<template>
  <trigger-dialog />
  <task-dialog />
  <div class="home-container plan-bar w-980 mx-auto mt-12">
    <n-input v-model:value="plan_file" />
    <n-button @click="open_plan_file">...</n-button>
    <n-button v-if="generating_image" disabled>正在生成</n-button>
    <n-button @click="save" v-else>导出图片</n-button>
  </div>
  <div class="home-container plan-bar w-980 mx-auto">
    <n-select v-model:value="sub_plan" :options="sub_plan_options" />
    <n-button @click="create_sub_plan">新建副表</n-button>
    <n-button :disabled="sub_plan == 'main'" @click="delete_sub_plan">删除此副表</n-button>
    <n-button :disabled="sub_plan == 'main'" @click="show_trigger_editor = true"
      >编辑触发条件</n-button
    >
    <n-button :disabled="sub_plan == 'main'" @click="show_task = true">编辑任务</n-button>
  </div>
  <plan-editor ref="plan_editor" class="w-980 mx-auto" />
  <n-form
    class="w-980 mx-auto mb-12"
    :label-placement="mobile ? 'top' : 'left'"
    :show-feedback="false"
    label-width="160"
    label-align="left"
    v-if="sub_plan == 'main'"
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
      <n-radio-group v-model:value="ling_xi">
        <n-space>
          <n-radio :value="1">感知信息</n-radio>
          <n-radio :value="2">人间烟火</n-radio>
          <n-radio :value="3">均衡模式</n-radio>
        </n-space>
      </n-radio-group>
    </n-form-item>
    <n-form-item>
      <template #label>
        <span>最大组人数</span><help-text><div>请查阅文档</div></help-text>
      </template>
      <n-input-number v-model:value="max_resting_count" />
    </n-form-item>
    <n-form-item>
      <template #label>
        <span>需要回满心情的干员</span><help-text><div>请查阅文档</div></help-text>
      </template>
      <n-select multiple filterable tag :options="operators" v-model:value="rest_in_full" />
    </n-form-item>
    <n-form-item>
      <template #label>
        <span>需要用尽心情的干员</span
        ><help-text><div>仅推荐写入具有暖机技能的干员</div></help-text>
      </template>
      <n-select multiple filterable tag :options="operators" v-model:value="exhaust_require" />
    </n-form-item>
    <n-form-item>
      <template #label>
        <span>0心情工作的干员</span><help-text><div>心情涣散状态仍能触发技能的干员</div></help-text>
      </template>
      <n-select multiple filterable tag :options="operators" v-model:value="workaholic" />
    </n-form-item>
    <n-form-item>
      <template #label>
        <span>宿舍低优先级干员</span><help-text><div>请查阅文档</div></help-text>
      </template>
      <n-select multiple filterable tag :options="operators" v-model:value="resting_priority" />
    </n-form-item>
  </n-form>
  <n-form
    class="w-980 mx-auto mb-12"
    :label-placement="mobile ? 'top' : 'left'"
    :show-feedback="false"
    label-width="160"
    label-align="left"
    v-else
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
      <template #label>
        <span>最大组人数</span><help-text><div>请查阅文档</div></help-text>
      </template>
      <n-input-number v-model:value="current_conf.max_resting_count" />
    </n-form-item>
    <n-form-item>
      <template #label>
        <span>需要回满心情的干员</span><help-text><div>请查阅文档</div></help-text>
      </template>
      <n-select
        multiple
        filterable
        tag
        :options="operators"
        v-model:value="current_conf.rest_in_full"
      />
    </n-form-item>
    <n-form-item>
      <template #label>
        <span>需要用尽心情的干员</span
        ><help-text><div>仅推荐写入具有暖机技能的干员</div></help-text>
      </template>
      <n-select
        multiple
        filterable
        tag
        :options="operators"
        v-model:value="current_conf.exhaust_require"
      />
    </n-form-item>
    <n-form-item>
      <template #label>
        <span>0心情工作的干员</span><help-text><div>心情涣散状态仍能触发技能的干员</div></help-text>
      </template>
      <n-select
        multiple
        filterable
        tag
        :options="operators"
        v-model:value="current_conf.workaholic"
      />
    </n-form-item>
    <n-form-item>
      <template #label>
        <span>宿舍低优先级干员</span><help-text><div>请查阅文档</div></help-text>
      </template>
      <n-select
        multiple
        filterable
        tag
        :options="operators"
        v-model:value="current_conf.resting_priority"
      />
    </n-form-item>
    <n-form-item v-if="sub_plan != 'main'">
      <template #label>
        <span>宿舍黑名单</span>
        <help-text>
          <div>不希望进行填充宿舍的干员</div>
        </help-text>
      </template>
      <n-select
        multiple
        filterable
        tag
        :options="operators"
        v-model:value="current_conf.free_blacklist"
      />
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

.plan-bar {
  flex-direction: row;
  flex-grow: 0;
  gap: 6px;
  padding: 0;
}
</style>
