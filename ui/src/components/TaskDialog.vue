<script setup>
import { computed, inject, ref, watch } from 'vue'
const show = inject('show_task')
const isLogPage = inject('add_task') || ref(false)
const edit_locked = inject('planEditLocked', ref(false))
watch(edit_locked, (locked) => {
  if (locked && !isLogPage.value) show.value = false
})
import { storeToRefs } from 'pinia'
import { usePlanStore } from '@/stores/plan'
import { useConfigStore } from '@/stores/config'
import axios from 'axios'
import { useMessage } from 'naive-ui'
import { masteryScheduleContext, masteryTraineeWarning } from '@/utils/masterySupport'
const message = useMessage()
const config_store = useConfigStore()
const plan_store = inject('planStore', null) || usePlanStore()
const { sub_plan, backup_plans, operators } = storeToRefs(plan_store)
const masterySchedule = computed(() => masteryScheduleContext(plan_store.plan, backup_plans.value))

import { useMowerStore } from '@/stores/mower'
const mower_store = useMowerStore()
const { get_tasks } = mower_store
const { workshop_settings } = storeToRefs(config_store)
const task_list = ref([])
const task_time = ref(new Date().getTime())
const task_type = ref('空任务')
const duration_minutes = ref(10)
const maintenance_mode = ref('prepare')
const isMaintenance = computed(() => ['闪断更新', '停服更新'].includes(task_type.value))
const daily_task = ref('日常任务')
const saving = ref(false)
const mastery_target_level = ref(1)
const mastery_operator = ref('')
const mastery_skill = ref(1)
const mastery_support_mode = ref('auto')
const workshop_operator = ref('')
const msg = ref('')
const error = ref(false)
const taskTypeOptions = [
  { label: '闪断更新', value: '闪断更新' },
  { label: '停服更新', value: '停服更新' },
  { label: '日常任务', value: '日常任务' },
  { label: '作战计划', value: '作战计划' },
  { label: '集成战略 (MAA)', value: '集成战略 (MAA)' },
  { label: '保全派驻 (MAA)', value: '保全派驻 (MAA)' },
  { label: '生息演算 (MAA)', value: '生息演算 (MAA)' },
  { label: '生息演算', value: '生息演算' },
  { label: '隐秘战线', value: '隐秘战线' },
  { label: '专精任务', value: '技能专精' },
  { label: '加工任务', value: '加工材料' },
  { label: '【实验性功能】分解所有重复家具', value: '分解所有重复家具' },
  { label: '仓库扫描', value: '仓库扫描' },
  { label: '线索任务', value: '线索任务' },
  { label: '空任务', value: '空任务' }
]
const dailyTaskOptions = [
  { label: '全部（按当前配置）', value: '日常任务' },
  { label: '公招', value: '公招' },
  { label: '森空岛签到', value: '森空岛签到' },
  { label: '信用购物', value: '信用购物' },
  { label: '领取邮件', value: '领取邮件' },
  { label: '读取基报', value: '读取基报' },
  { label: '访问好友', value: '访问好友' },
  { label: '领取任务奖励', value: '领取任务奖励' }
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
  { label: '回收站', value: 'recycle' },
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
  duration_minutes.value = 10
  maintenance_mode.value = 'prepare'
  daily_task.value = '日常任务'
  mastery_target_level.value = 1
  mastery_operator.value = ''
  mastery_skill.value = 1
  mastery_support_mode.value = 'auto'
  msg.value = ''
}

async function saveTasks() {
  if (saving.value || (!isLogPage.value && edit_locked.value)) return
  const plan = {}
  for (const i of task_list.value) {
    plan[i.room] = i.operators
  }
  const task = {
    time: new Date(task_time.value),
    plan,
    task_type: task_type.value === '日常任务' ? daily_task.value : task_type.value,
    meta_data: ''
  }
  if (isMaintenance.value) {
    if (
      !Number.isInteger(duration_minutes.value) ||
      duration_minutes.value < 1 ||
      duration_minutes.value > 10080
    ) {
      msg.value = '更新时长须为 1 至 10080 分钟的整数'
      error.value = true
      return
    }
    task.duration_minutes = duration_minutes.value
    task.maintenance_mode = task_type.value === '停服更新' ? 'prepare' : maintenance_mode.value
    task.plan = {}
  } else if (task_type.value == '技能专精') {
    saving.value = true
    try {
      await saveMasteryTask()
    } finally {
      saving.value = false
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
  } else if (task_type.value !== '空任务') {
    // 独立任务不携带房间排班。
    task.plan = {}
  }
  saving.value = true
  try {
    msg.value = (
      await axios.post(`${import.meta.env.VITE_HTTP_URL}/task`, { task }, { timeout: 30000 })
    ).data
    if (msg.value != '添加任务成功！') {
      error.value = true
    } else {
      error.value = false
      get_tasks()
    }
  } catch (e) {
    showSubmissionError(e)
  } finally {
    saving.value = false
  }
}

function showSubmissionError(e) {
  const detail = e.response?.data
  if ((detail?.code || detail?.error) === 'configuration_changed') {
    msg.value = detail.message || '当前配置已切换，请刷新页面后再操作'
  } else {
    msg.value = `未确认提交结果：${detail?.message || detail?.error || e.message}，请刷新计划和任务队列后重试`
  }
  error.value = true
}

async function saveMasteryTask() {
  if (!mastery_operator.value) {
    msg.value = '请先选择要专精的干员！'
    error.value = true
    return
  }
  const warning = masteryTraineeWarning(mastery_operator.value, masterySchedule.value.blocked)
  if (warning) message.warning(warning)
  try {
    const { data } = await axios.post(
      `${import.meta.env.VITE_HTTP_URL}/mastery-plan`,
      {
        create_task: true,
        items: [
          {
            name: mastery_operator.value,
            skill_index: mastery_skill.value - 1,
            target_level: mastery_target_level.value,
            support_mode: mastery_support_mode.value
          }
        ]
      },
      { timeout: 30000 }
    )
    const result = data?.results?.[0]
    if (!['added', 'existing'].includes(result?.status)) {
      msg.value = result?.reason || '添加专精计划失败'
      error.value = true
      return
    }
    if (result.warning) message.warning(result.warning)
    const planStatus = result.status === 'added' ? '已加入专精计划' : '已在专精计划中'
    const task = result.task
    if (['inserted', 'queued'].includes(task?.status)) {
      msg.value = `${planStatus}；${task.reason}`
      error.value = false
      get_tasks()
    } else if (task?.status === 'active') {
      msg.value = `${planStatus}；${task.reason}，未重复生成任务`
      error.value = false
    } else {
      msg.value = `${planStatus}；尚未生成任务：${task?.reason || '未确认入队结果，请刷新后重试'}`
      error.value = true
    }
  } catch (e) {
    showSubmissionError(e)
  }
}

watch(
  task_list,
  () => {
    const result = {}
    for (const i of task_list.value) {
      result[i.room] = i.operators
    }
    if (!isLogPage.value && !edit_locked.value && sub_plan.value !== 'main') {
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
import { render_op_option, render_op_label } from '@/utils/op_select'

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
  <n-modal
    v-model:show="show"
    preset="card"
    transform-origin="center"
    :style="{ width: isLogPage ? 'auto' : 'max-content', maxWidth: '90vw' }"
  >
    <template #header>
      <div v-if="isLogPage" class="task_row task_header" style="width: auto">
        <n-select
          v-model:value="task_type"
          :options="taskTypeOptions"
          filterable
          :filter="(p, o) => pinyin_match(o.label, p)"
          :consistent-menu-width="false"
          placeholder="任务类别"
          class="dropdown-select"
          :style="{ width: task_type === '分解所有重复家具' ? '290px' : '190px' }"
        />
        <n-select
          v-if="task_type === '日常任务'"
          v-model:value="daily_task"
          :options="dailyTaskOptions"
          :consistent-menu-width="false"
          placeholder="选择日常项目"
          style="width: 210px"
        />
        <n-select
          v-if="task_type == '技能专精'"
          v-model:value="mastery_operator"
          filterable
          placeholder="选择干员"
          :options="operators"
          :filter="(p, o) => pinyin_match(o.label, p)"
          :render-label="render_op_label"
          :render-option="render_op_option"
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
          <div>选择干员、技能与目标等级，加入专精计划并生成关联的专精任务。</div>
          <div>
            需开启专精自动化并运行 Mower；材料不足或训练室占用时，保留计划并显示未入队原因。
          </div>
          <div>自动协助按已同步 BOX 生成方案；未同步 BOX 时使用职业路线。</div>
          <div>使用职业路线时，可在通用专精路线预览中设置协助者。</div>
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
      <n-dynamic-input
        v-model:value="task_list"
        :on-create="new_task"
        :disabled="!isLogPage && edit_locked"
      >
        <template #create-button-default>添加任务</template>
        <template #default="{ value }">
          <div class="task_row">
            <n-select
              v-model:value="value.room"
              :disabled="!isLogPage && edit_locked"
              :options="roomOptions"
              placeholder="选择房间"
              class="dropdown-select task-room-select"
            />
            <n-dynamic-tags
              v-model:value="value.operators"
              :disabled="!isLogPage && edit_locked"
              :max="5"
              size="large"
              style="justify-content: flex-end"
            >
              <template #input="{ submit, deactivate }">
                <n-select
                  :value="null"
                  :disabled="!isLogPage && edit_locked"
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
                  :render-option="render_op_option"
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
      <template v-if="isMaintenance">
        <div class="task_row">
          <label>更新时长（分钟）：</label>
          <n-input-number v-model:value="duration_minutes" :min="1" :max="10080" :precision="0" />
        </div>
        <div v-if="task_type === '闪断更新'" class="task_row">
          <label>处理方式：</label>
          <n-select
            v-model:value="maintenance_mode"
            :options="[
              { label: '提前准备后暂停', value: 'prepare' },
              { label: '直接暂停', value: 'pause' }
            ]"
            style="width: 240px"
          />
        </div>
        <n-text depth="3">
          从所选时间开始暂停，满设定时长后继续；期间不会提前尝试登录。
          <template v-if="task_type === '停服更新'">
            会按已有提前量触发停服更新副表，并复用停服更新前的跑单和换人安排。
          </template>
          <template v-else-if="maintenance_mode === 'prepare'">
            更新前会按现有闪断更新规则提前跑单、更换专精协助干员。
          </template>
          <template v-else>不为本次更新提前跑单或换人。</template>
        </n-text>
      </template>
      <n-text v-if="task_type === '日常任务' && daily_task === '日常任务'" depth="3">
        按当前配置执行已启用的日常项目和作战计划，不包含长任务。
      </n-text>
      <n-text
        v-else-if="
          !isMaintenance &&
          !['空任务', '技能专精', '加工材料', '仓库扫描', '线索任务', '分解所有重复家具'].includes(
            task_type
          )
        "
        depth="3"
      >
        按当前设置执行一次所选任务，无需开启自动执行；作战和长任务会为其他排队任务预留时间。
      </n-text>
      <n-text v-if="task_type == '分解所有重复家具'" depth="3">
        进入加工站家具页，只分解超出一整套所需数量的家具；无法确认套装数量时跳过。无需选择干员，不消耗心情。
      </n-text>
      <div class="task_row" v-if="task_type == '技能专精'">
        <label>协助方式：</label>
        <n-select
          v-model:value="mastery_support_mode"
          style="width: 240px"
          :options="[
            { label: '自动协助（无 BOX 时使用职业路线）', value: 'auto' },
            { label: '使用职业路线', value: 'route' }
          ]"
        />
      </div>
      <div class="task_row" v-if="task_type == '加工材料'">
        <label>选择干员：</label>
        <n-select
          v-model:value="workshop_operator"
          filterable
          :options="workshopOperatorOptions"
          :filter="(p, o) => pinyin_match(o.label, p)"
          :render-label="render_op_label"
          :render-option="render_op_option"
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
          <n-button type="primary" :loading="saving" @click="saveTasks">
            {{ task_type == '技能专精' ? '加入专精计划并生成任务' : '添加至任务队列' }}
          </n-button>
          <n-button type="error" :disabled="saving" @click="clear">清除输入</n-button>
        </div>
      </div>
    </template>
  </n-modal>
</template>

<style scoped lang="scss">
.button_row {
  margin-top: 8px;
  flex-wrap: wrap;
}

.task_header {
  flex-wrap: wrap;
}

.task_row {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 2px;

  .n-input {
    width: 140px;
  }
}

.n-dynamic-tags {
  align-items: center;
  flex: 1;
  min-width: 0;
}
.task-room-select {
  width: 160px;
  min-width: 160px;
  flex: 0 0 160px;
}
</style>
