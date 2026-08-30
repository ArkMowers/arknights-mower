<script setup>
import { computed, inject, ref, watch } from 'vue'
const show = inject('show_task')
const isLogPage = inject('add_task') || ref(false)
import { storeToRefs } from 'pinia'
import { usePlanStore } from '@/stores/plan'
import { useConfigStore } from '@/stores/config'
import axios from 'axios'
const config_store = useConfigStore()
const plan_store = usePlanStore()
const { sub_plan, backup_plans, operators } = storeToRefs(plan_store)

import { useMowerStore } from '@/stores/mower'
const mower_store = useMowerStore()
const { get_task_id } = storeToRefs(mower_store)
const { get_tasks } = mower_store
const { workshop_settings } = storeToRefs(config_store)
const task_list = ref([])
const task_time = ref(new Date().getTime())
const task_type = ref('空任务')
const mastery_target_level = ref(1)
const mastery_operator = ref('')
const mastery_skill = ref(1)
const workshop_operator = ref('')
const msg = ref('')
const error = ref(false)
const taskTypeOptions = [
  { label: '专精任务', value: '技能专精' },
  { label: '加工任务', value: '加工材料' },
  { label: '空任务', value: '空任务' }
]
const workshopOperatorOptions = computed(() => {
  return workshop_settings.value.map((s) => ({
    label: s.operator,
    value: s.operator
  }))
})

const roomOptions = [
  { label: '会客室', value: 'meeting' },
  { label: '办公室', value: 'contact' },
  { label: '加工站', value: 'factory' },
  { label: '训练室', value: 'train' },
  { label: '控制中枢', value: 'central' },
  { label: '第一层1号房间', value: 'room_1_1' },
  { label: '第一层2号房间', value: 'room_1_2' },
  { label: '第一层3号房间', value: 'room_1_3' },
  { label: '第二层1号房间', value: 'room_2_1' },
  { label: '第二层2号房间', value: 'room_2_2' },
  { label: '第二层3号房间', value: 'room_2_3' },
  { label: '第三层1号房间', value: 'room_3_1' },
  { label: '第三层2号房间', value: 'room_3_2' },
  { label: '第三层3号房间', value: 'room_3_3' },
  { label: '宿舍1', value: 'dormitory_1' },
  { label: '宿舍2', value: 'dormitory_2' },
  { label: '宿舍3', value: 'dormitory_3' },
  { label: '宿舍4', value: 'dormitory_4' }
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
    room: '',
    operators: []
  }
}
function clear() {
  task_list.value = []
  task_time.value = new Date().getTime()
  task_type.value = '空任务'
  mastery_target_level.value = 1
  mastery_operator.value = ''
  mastery_skill.value = 1
  msg.value = ''
}

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
    // #71：手动对话框改走 DB 计划创建 API（POST /mastery-plan），保留用户选的目标等级。
    // 原「技能专精」/task（带 upgrade_support 载荷）是死流——server 只认 DB 计划。
    if (!mastery_operator.value) {
      msg.value = '请先选择要专精的干员！'
      error.value = true
      return
    }
    const body = {
      items: [
        {
          name: mastery_operator.value,
          skill_index: mastery_skill.value - 1,
          target_level: mastery_target_level.value
        }
      ]
    }
    const r = await axios.post(`${import.meta.env.VITE_HTTP_URL}/mastery-plan`, body)
    const results = r.data?.results || []
    if (results[0]?.status === 'added') {
      msg.value = `已添加 ${mastery_operator.value} 技能${mastery_skill.value} 专${mastery_target_level.value} 计划`
      error.value = false
    } else {
      msg.value = results[0]?.reason || '添加失败'
      error.value = true
    }
    return
  } else if (task_type.value == '加工材料') {
    if (!workshop_operator.value) {
      msg.value = '请先选择加工站工具人！'
      error.value = true
      return
    }
    task.meta_data = workshop_operator.value
    task.plan = {}
  }
  msg.value = (await axios.post(`${import.meta.env.VITE_HTTP_URL}/task`, { task })).data
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
          v-model:value="mastery_operator"
          filterable
          placeholder="选择干员"
          :options="operators"
          :filter="(p, o) => pinyin_match(o.label, p)"
          :render-label="render_op_label"
          style="width: 150px"
        />
        <n-select
          v-if="task_type == '技能专精'"
          v-model:value="mastery_skill"
          :options="skill_list"
          style="width: 100px"
        />
        <n-select
          v-if="task_type == '技能专精'"
          v-model:value="mastery_target_level"
          :options="level_list"
          style="width: 100px"
        />
        <n-date-picker
          v-if="task_type != '技能专精'"
          v-model:value="task_time"
          type="datetime"
          placeholder="选择时间"
          style="width: 200px"
        />
        <help-text v-if="task_type == '技能专精'">
          <div>选择要专精的干员、技能与目标等级，将加入专精计划，由系统自动调度训练</div>
          <div>协助位与中途换人由专精路线配置驱动（在专精计划页的路线设置中配置）</div>
          <div>不支持阿斯卡纶</div>
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
      v-if="!isLogPage || task_type == '空任务'"
      style="max-height: 80vh; margin-top: 8px"
    >
      <n-dynamic-input v-model:value="task_list" :on-create="new_task">
        <template #create-button-default>添加任务</template>
        <template #default="{ value }">
          <div class="task_row">
            <n-select
              v-model:value="value.room"
              :options="roomOptions"
              placeholder="选择房间"
              class="dropdown-select"
              style="width: 160px"
            />
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
            <n-text
              v-if="value.room == 'train'"
              depth="3"
              style="font-size: 12px; margin-left: 8px"
            >
              左边协助位，右边训练位
            </n-text>
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
      <div class="task_row" v-if="task_type == '加工材料'">
        <label>选择干员：</label>
        <n-select
          v-model:value="workshop_operator"
          filterable
          :options="workshopOperatorOptions"
          :filter="(p, o) => pinyin_match(o.label, p)"
          :render-label="render_op_label"
          style="width: 178px"
        />
        <help-text>
          <div>
            自身上限检查和子材料下限检查会有延迟，因为数据是从森空岛接口拿的，不是读取游戏内的
          </div>
        </help-text>
      </div>
      <div class="task_row button_row">
        <div style="margin-right: auto">
          <label v-if="error" style="color: red">{{ msg }}</label>
          <label v-if="!error" style="color: green">{{ msg }}</label>
        </div>
        <div style="display: flex; gap: 12px; margin-top: 16px">
          <n-button type="primary" @click="saveTasks">
            {{ task_type == '技能专精' ? '添加到专精计划' : '添加至任务队列' }}
          </n-button>
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

.n-dynamic-tags {
  align-items: center;
}
</style>
