<script setup>
import { inject, ref, watch, computed, h } from 'vue'
const show = inject('show_task')
const isLogPage = inject('add_task') || ref(false)
import { storeToRefs } from 'pinia'
import { usePlanStore } from '@/stores/plan'
import axios from 'axios'

const plan_store = usePlanStore()
const { sub_plan, backup_plans, operators } = storeToRefs(plan_store)

const task_list = ref([])
const task_time = ref(new Date().getTime())
const task_type = ref('空任务')
const skill_level = ref(1)
const upgrade_support = ref([])
const msg = ref('')
const error = ref(false)

const taskTypeOptions = [
  { label: '专精任务', value: '技能专精' },
  { label: '空任务', value: '空任务' }
]

function update_tasks() {
  if (sub_plan.value != 'main' && !isLogPage) {
    const result = []
    Object.entries(backup_plans.value[sub_plan.value].task).forEach(([room, operators]) => {
      result.push({ room, operators })
    })
    task_list.value = result
  }
  if (isLogPage) {
    task_list.value = []
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
    name: '',
    skill_level: upgrade_support.value.length + 1,
    efficiency: 30,
    swap_name: '艾丽妮',
    match: false
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

async function saveTasks() {
  const plan = {}
  for (const i of task_list.value) {
    plan[i.room] = i.operators
  }
  const task = {
    time: new Date(task_time.value).toLocaleString(),
    plan,
    task_type: task_type.value,
    meta_data: ''
  }
  if (task_type.value == '技能专精') {
    task.meta_data = skill_level.value + ''
  }
  const req = { task, upgrade_support: upgrade_support.value }
  msg.value = (await axios.post(`${import.meta.env.VITE_HTTP_URL}/task`, req)).data
  if (msg.value != '添加任务成功！') {
    error.value = true
  } else error.value = false
}

watch(
  task_list,
  async () => {
    const result = {}
    for (const i of task_list.value) {
      result[i.room] = i.operators
    }
    if (!isLogPage) {
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

import { match } from 'pinyin-pro'
import { render_op_label } from '@/utils/op_select'
</script>

<template>
  <n-modal
    v-model:show="show"
    preset="card"
    title="任务"
    transform-origin="center"
    style="width: 900px"
  >
    <div v-if="isLogPage" class="task_row">
      <label v-if="task_type == '技能专精'">说明</label>
      <help-text v-if="task_type == '技能专精'">
        <div>工具人等级不可重复，效率得手动输入</div>
        <div>任务开启前，请手动把专精干员放入训练室（Mower暂时不支持训练室换人）</div>
        <div>排班表是要填写协助位和训练位的，最好写从来没用的工具人。</div>
        <div>训练室排班表纠错暂时关闭，有需要纠错的朋友，请绑大组</div>
        <div>自动计算时暂时默认2，3专精获得小鸟/狗剩增益效果</div>
        <div>如果开启专精时未获得减半增益，本次专精可手动计算时间以添加艾丽妮替换任务</div>
        <div>攻略：https://www.skland.com/article?id=1915250</div>
      </help-text>
      <label>任务触发时间</label>
      <n-date-picker
        v-model:value="task_time"
        type="datetime"
        placeholder="选择时间"
        style="width: 200px"
      />
      <label>任务类别</label>
      <n-select
        v-model:value="task_type"
        :options="taskTypeOptions"
        placeholder="任务类别"
        class="dropdown-select"
        style="width: 150px"
      >
      </n-select>
      <label v-if="task_type == '技能专精'">专精技能</label>
      <n-input-number
        v-if="task_type == '技能专精'"
        v-model:value="skill_level"
        :min="1"
        :max="3"
        style="width: 75px"
      />
    </div>
    <n-scrollbar
      v-if="(isLogPage && task_type != '技能专精') || !isLogPage"
      style="max-height: 80vh; margin-top: 8px"
    >
      <n-dynamic-input v-model:value="task_list" :on-create="new_task">
        <template #create-button-default>添加任务</template>
        <template #default="{ value }">
          <div class="task_row">
            <n-input v-model:value="value.room" />
            <n-dynamic-tags v-model:value="value.operators" :max="3" size="large">
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
                  :filter="(p, o) => match(o.label, p)"
                  :render-label="render_op_label"
                />
              </template>
            </n-dynamic-tags>
          </div>
        </template>
      </n-dynamic-input>
      <n-card style="margin-top: 8px" content-style="padding: 8px" embedded>
        <n-code
          v-if="!isLogPage"
          :code="JSON.stringify(backup_plans[sub_plan].task, null, 2)"
          language="json"
          word-wrap
        />
        <n-code
          v-if="isLogPage"
          :code="JSON.stringify(task_list, null, 2)"
          language="json"
          word-wrap
        />
      </n-card>
    </n-scrollbar>
    <n-scrollbar
      v-if="isLogPage && task_type == '技能专精'"
      style="max-height: 80vh; margin-top: 8px"
    >
      <n-dynamic-input v-model:value="upgrade_support" :on-create="new_support" :max="3">
        <template #create-button-default>添加专精工具人</template>
        <template #default="{ value }">
          <div class="task_row">
            <label>工具人</label>
            <n-select
              v-model:value="value.name"
              filterable
              :options="operators_with_free_current"
              :filter="(p, o) => match(o.label, p)"
              :render-label="render_op_label"
              style="width: 175px"
            />
            <label>等级</label>
            <n-input-number
              v-model:value="value.skill_level"
              :min="1"
              :max="3"
              style="width: 80px"
            />
            <label>效率</label>
            <n-input-number
              v-model:value="value.efficiency"
              :min="30"
              :max="100"
              style="width: 80px"
            />
            <label>替换</label>
            <help-text>
              <div>请选择小鸟/狗剩</div>
              <div>没有的话，请设定和工具人相同</div>
              <div>如果艾丽妮/狗剩能触发30%效率提升，则勾选</div>
              <div>非小鸟/狗剩请不要勾选(重要)</div>
            </help-text>
            <n-checkbox v-model:checked="value.match"></n-checkbox>
            <n-select
              v-model:value="value.swap_name"
              filterable
              :options="operators_with_free_current"
              :filter="(p, o) => match(o.label, p)"
              :render-label="render_op_label"
              style="width: 175px"
            />
          </div>
        </template>
      </n-dynamic-input>
    </n-scrollbar>
    <div v-if="isLogPage" class="task_row button_row">
      <div style="margin-right: auto">
        <label v-if="error" style="color: red">{{ msg }}</label>
        <label v-if="!error" style="color: green">{{ msg }}</label>
      </div>
      <div style="display: flex">
        <n-button type="primary" @click="saveTasks">添加至任务队列</n-button>
        <n-button type="error" @click="clear">清除输入</n-button>
      </div>
    </div>
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

.n-dynamic-tags {
  align-items: center;
}
</style>
