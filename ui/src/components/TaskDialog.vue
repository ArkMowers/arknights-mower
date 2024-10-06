<script setup>
import { inject, ref, watch, computed, h } from 'vue'
const show = inject('show_task')
const isLogPage = inject('add_task') || ref(false)
import { storeToRefs } from 'pinia'
import { usePlanStore } from '@/stores/plan'
import axios from 'axios'

const plan_store = usePlanStore()
const { sub_plan, backup_plans, operators } = storeToRefs(plan_store)

import { useMowerStore } from '@/stores/mower'
const mower_store = useMowerStore()
const { get_task_id } = storeToRefs(mower_store)
const { get_tasks } = mower_store

const task_list = ref([])
const task_time = ref(new Date().getTime())
const task_type = ref('空任务')
const skill_level = ref(1)
const upgrade_support = ref([])
const msg = ref('')
const error = ref(false)
const half_off = ref(true)
const taskTypeOptions = [
  { label: '空任务', value: '空任务' },
  { label: '专精任务', value: '技能专精' }
]

function update_tasks() {
  if (sub_plan.value != 'main' && !isLogPage.value) {
    const result = []
    Object.entries(backup_plans.value[sub_plan.value].task).forEach(([room, operators]) => {
      result.push({ room, operators })
    })
    task_list.value = result
  }
}

function new_task() {
  return {
    room: 'room_',
    operators: []
  }
}
function new_support() {
  return {
    name: '假日威龙陈',
    skill_level: upgrade_support.value.length + 1,
    efficiency: 30,
    swap: true,
    swap_name: '艾丽妮',
    match: true,
    half_off: true
  }
}
function clear() {
  task_list.value = []
  task_time.value = new Date().getTime()
  task_type.value = '空任务'
  skill_level.value = 1
  upgrade_support.value = []
  msg.value = ''
}

import { deepcopy } from '@/utils/deepcopy'

async function saveTasks() {
  const plan = {}
  for (const i of task_list.value) {
    plan[i.room] = i.operators
  }
  const task = {
    time: new Date(task_time.value),
    plan,
    task_type: task_type.value,
    meta_data: ''
  }
  if (task_type.value == '技能专精') {
    task.meta_data = skill_level.value + ''
    task.plan = {}
    upgrade_support.value.sort((a, b) => a.skill_level - b.skill_level)
    if (upgrade_support.value[0].skill_level != 1) {
      upgrade_support.value[0].half_off = half_off.value
      // 如果第一个不是1技能，则更新 是否减半
    } else upgrade_support.value[0].half_off = false
    const data = deepcopy(upgrade_support.value)
    for (const value of data) {
      if (!value.swap) {
        value.swap_name = value.name
        value.match = false
      }
      delete value.swap
    }
  } else {
    var data = []
  }

  const req = { task, upgrade_support: data }
  msg.value = (await axios.post(`${import.meta.env.VITE_HTTP_URL}/task`, req)).data
  if (msg.value != '添加任务成功！') {
    error.value = true
  } else {
    error.value = false
    clearTimeout(get_task_id.value)
    get_tasks()
  }
}

watch(
  task_list,
  () => {
    const result = {}
    for (const i of task_list.value) {
      result[i.room] = i.operators
    }
    if (!isLogPage.value) {
      backup_plans.value[sub_plan.value].task = result
    }
  },
  { deep: true }
)

watch(show, (new_value) => {
  if (new_value) {
    update_tasks()
  }
})

const operators_with_free_current = computed(() => {
  return [
    { value: 'Current', label: 'Current' },
    { value: 'Free', label: 'Free' }
  ].concat(operators.value)
})

import { pinyin_match } from '@/utils/common'
import { render_op_label } from '@/utils/op_select'

const skill_list = [
  { value: 1, label: '一技能' },
  { value: 2, label: '二技能' },
  { value: 3, label: '三技能' }
]

const level_list = [
  { value: 1, label: '专一' },
  { value: 2, label: '专二' },
  { value: 3, label: '专三' }
]

const swap_list = [
  { value: '艾丽妮', label: '艾丽妮' },
  { value: '逻各斯', label: '逻各斯' }
]

const swap_30 = [
  { value: true, label: '有30%速度加成' },
  { value: false, label: '无训练速度加成' }
]
</script>

<template>
  <n-modal v-model:show="show" preset="card" transform-origin="center" style="width: auto">
    <template #header>
      <div v-if="isLogPage" class="task_row" style="width: auto">
        <n-select
          v-model:value="task_type"
          :options="taskTypeOptions"
          placeholder="任务类别"
          class="dropdown-select"
          style="width: 120px"
        />
        <n-select
          v-if="task_type == '技能专精'"
          v-model:value="skill_level"
          :options="skill_list"
          style="width: 100px"
        />
        <n-date-picker
          v-model:value="task_time"
          type="datetime"
          placeholder="选择时间"
          style="width: 200px"
        />
        <help-text v-if="task_type == '技能专精'">
          <div>不支持阿斯卡纶</div>
          <div>
            训练速度需手动输入，可使用<n-button
              text
              tag="a"
              href="https://arkntools.app/#/riic"
              target="_blank"
              type="primary"
            >
              明日方舟工具箱 </n-button
            >查询
          </div>
          <div>任务开启前，请手动把专精干员放入训练室（Mower暂时不支持训练室换人）</div>
          <div>排班表是要填写协助位和训练位的，最好写从来没用的工具人。</div>
          <div>训练室排班表纠错暂时关闭，有需要纠错的朋友，请绑大组</div>
          <div>自动计算时暂时默认2，3专精获得小鸟/狗剩增益效果</div>
          <div>如果开启专精时未获得减半增益（非专1-3），取消勾选【有减半加成】</div>
          <div>
            参考攻略：
            <n-button
              text
              tag="a"
              href="https://www.skland.com/article?id=1915250"
              target="_blank"
              type="primary"
            >
              通用最速专精方案
            </n-button>
          </div>
        </help-text>
      </div>
      <template v-else>任务</template>
    </template>
    <n-scrollbar
      v-if="!isLogPage || task_type != '技能专精'"
      style="max-height: 80vh; margin-top: 8px"
    >
      <n-dynamic-input v-model:value="task_list" :on-create="new_task">
        <template #create-button-default>添加任务</template>
        <template #default="{ value }">
          <div class="task_row">
            <n-input v-model:value="value.room" />
            <help-text>
              <div>会客室：meeting</div>
              <div>办公室：contact</div>
              <div>加工站：factory</div>
              <div>训练室：train</div>
              <div>控制中枢：central</div>
            </help-text>
            <n-dynamic-tags v-model:value="value.operators" :max="5" size="large">
              <template #input="{ submit, deactivate }">
                <n-select
                  v-model:value="value.operators"
                  filterable
                  :options="operators_with_free_current"
                  :on-update:value="
                    (v) => {
                      submit(v)
                    }
                  "
                  :on-blur="deactivate"
                  :filter="(p, o) => pinyin_match(o.label, p)"
                  :render-label="render_op_label"
                />
              </template>
            </n-dynamic-tags>
          </div>
        </template>
      </n-dynamic-input>
      <n-card style="margin-top: 8px" content-style="padding: 8px" embedded>
        <n-code
          :code="JSON.stringify(isLogPage ? task_list : backup_plans[sub_plan].task, null, 2)"
          language="json"
          word-wrap
        />
      </n-card>
    </n-scrollbar>
    <template v-if="isLogPage">
      <n-scrollbar v-if="task_type == '技能专精'" style="max-height: 80vh; margin-top: 8px">
        <n-dynamic-input v-model:value="upgrade_support" :on-create="new_support" :max="3">
          <template #create-button-default>添加专精工具人</template>
          <template #default="{ value }">
            <div class="outer">
              <n-select
                v-model:value="value.skill_level"
                :options="level_list"
                style="width: 80px"
              />
              <div class="inner">
                <div class="task-col">
                  <label>协助位</label>
                  <n-select
                    v-model:value="value.name"
                    filterable
                    :options="operators"
                    :filter="(p, o) => pinyin_match(o.label, p)"
                    :render-label="render_op_label"
                    style="width: 178px"
                  />
                  <label class="ml">训练速度</label>
                  <n-input-number
                    v-model:value="value.efficiency"
                    :min="30"
                    :max="100"
                    style="width: 80px"
                    :show-button="false"
                    placeholder=""
                  >
                    <template #suffix>%</template>
                  </n-input-number>
                </div>
                <div class="task-col">
                  <n-checkbox v-model:checked="value.swap">中途换人</n-checkbox>
                  <n-select
                    :disabled="!value.swap"
                    v-model:value="value.swap_name"
                    :options="swap_list"
                    :render-label="render_op_label"
                    style="width: 140px"
                  />
                  <n-select
                    :disabled="!value.swap"
                    v-model:value="value.match"
                    :options="swap_30"
                    style="width: 160px"
                  />
                </div>
              </div>
            </div>
          </template>
        </n-dynamic-input>
      </n-scrollbar>
      <div class="task_row button_row">
        <div style="margin-right: auto">
          <label v-if="error" style="color: red">{{ msg }}</label>
          <label v-if="!error" style="color: green">{{ msg }}</label>
        </div>
        <div style="display: flex; gap: 12px; margin-top: 16px">
          <n-checkbox
            v-if="task_type == '技能专精'"
            v-model:checked="half_off"
            :default-checked="true"
            >有减半加成</n-checkbox
          >
          <n-button type="primary" @click="saveTasks">添加至任务队列</n-button>
          <n-button type="error" @click="clear">清除输入</n-button>
        </div>
      </div>
    </template>
  </n-modal>
</template>

<style scoped lang="scss">
.button_row {
  margin-top: 8px;
}

.task_row {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;

  .n-input {
    width: 140px;
  }
}

.outer {
  display: flex;
  flex-direction: row;
  align-items: center;
  gap: 18px;
}

.inner {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.task-col {
  display: flex;
  flex-direction: row;
  gap: 8px;
  align-items: center;
}

.n-dynamic-tags {
  align-items: center;
}

.ml {
  margin-left: 16px;
}
</style>
