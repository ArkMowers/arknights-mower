<script setup>
import { i18n } from '@/i18n'
const { t } = i18n.global
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
const isMaintenance = computed(() => ['计划暂停', '计划停止'].includes(task_type.value))
const daily_task = ref('日常任务')
const saving = ref(false)
const mastery_target_level = ref(1)
const mastery_operator = ref('')
const mastery_skill = ref(1)
const mastery_support_mode = ref('auto')
const workshop_operator = ref('')
const rawMessage = ref('')
const translatedMessage = ref(null)
const msg = computed({
  get: () => {
    const message = translatedMessage.value
    if (!message) return rawMessage.value
    return t(message.key, {
      ...message.params,
      ...(message.statusKey ? { status: t(message.statusKey) } : {})
    })
  },
  set: (value) => {
    translatedMessage.value = null
    rawMessage.value = value
  }
})
function setMessage(key, params = {}, statusKey = null) {
  translatedMessage.value = { key, params, statusKey }
}
const error = ref(false)
const taskTypeOptions = computed(() => [
  { label: t('plans.taskPause'), value: '计划暂停' },
  { label: t('plans.taskStop'), value: '计划停止' },
  { label: t('plans.taskDaily'), value: '日常任务' },
  { label: t('plans.taskFight'), value: '作战计划' },
  { label: t('plans.taskRogue'), value: '集成战略 (MAA)' },
  { label: t('plans.taskSss'), value: '保全派驻 (MAA)' },
  { label: t('plans.taskReclamationMaa'), value: '生息演算 (MAA)' },
  { label: t('plans.taskReclamation'), value: '生息演算' },
  { label: t('plans.taskSecretFront'), value: '隐秘战线' },
  { label: t('plans.taskMastery'), value: '技能专精' },
  { label: t('plans.taskWorkshop'), value: '加工材料' },
  { label: t('plans.taskFurniture'), value: '分解所有重复家具' },
  { label: t('plans.taskDepot'), value: '仓库扫描' },
  { label: t('plans.taskClues'), value: '线索任务' },
  { label: t('plans.taskEmpty'), value: '空任务' }
])
const dailyTaskOptions = computed(() => [
  { label: t('plans.taskAllDaily'), value: '日常任务' },
  { label: t('plans.taskRecruit'), value: '公招' },
  { label: t('plans.taskSkland'), value: '森空岛签到' },
  { label: t('plans.taskCreditStore'), value: '信用购物' },
  { label: t('plans.taskMail'), value: '领取邮件' },
  { label: t('plans.taskBaseReport'), value: '读取基报' },
  { label: t('plans.taskFriends'), value: '访问好友' },
  { label: t('plans.taskMissionRewards'), value: '领取任务奖励' }
])
const workshopOperatorOptions = computed(() => {
  return workshop_settings.value.map((s) => ({
    label: s.operator,
    value: s.operator
  }))
})

const roomOptions = computed(() => [
  { label: t('plans.receptionRoom'), value: 'meeting' },
  { label: t('plans.office'), value: 'contact' },
  { label: t('plans.workshop'), value: 'factory' },
  { label: t('plans.trainingRoom'), value: 'train' },
  { label: t('plans.recycling'), value: 'recycle' },
  { label: t('plans.controlCenter'), value: 'central' },
  { label: t('plans.taskRoom11'), value: 'room_1_1' },
  { label: t('plans.taskRoom12'), value: 'room_1_2' },
  { label: t('plans.taskRoom13'), value: 'room_1_3' },
  { label: t('plans.taskRoom21'), value: 'room_2_1' },
  { label: t('plans.taskRoom22'), value: 'room_2_2' },
  { label: t('plans.taskRoom23'), value: 'room_2_3' },
  { label: t('plans.taskRoom31'), value: 'room_3_1' },
  { label: t('plans.taskRoom32'), value: 'room_3_2' },
  { label: t('plans.taskRoom33'), value: 'room_3_3' },
  { label: t('plans.dormitory1'), value: 'dormitory_1' },
  { label: t('plans.dormitory2'), value: 'dormitory_2' },
  { label: t('plans.dormitory3'), value: 'dormitory_3' },
  { label: t('plans.dormitory4'), value: 'dormitory_4' }
])
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
      duration_minutes.value < (task_type.value === '计划停止' ? 0 : 1) ||
      duration_minutes.value > 10080
    ) {
      setMessage(
        task_type.value === '计划停止' ? 'plans.taskStopDurationError' : 'plans.taskDurationError'
      )
      error.value = true
      return
    }
    task.duration_minutes = duration_minutes.value
    task.maintenance_mode = task_type.value === '计划停止' ? 'prepare' : maintenance_mode.value
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
      setMessage('plans.chooseWorkshopOperator')
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
    const result = (
      await axios.post(`${import.meta.env.VITE_HTTP_URL}/task`, { task }, { timeout: 30000 })
    ).data
    if (result != '添加任务成功！') {
      msg.value = result
      error.value = true
    } else {
      setMessage('plans.taskAdded')
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
    if (detail.message) msg.value = detail.message
    else setMessage('plans.taskConfigurationChanged')
  } else {
    setMessage('plans.taskSubmissionUnconfirmed', {
      detail: detail?.message || detail?.error || e.message
    })
  }
  error.value = true
}

async function saveMasteryTask() {
  if (!mastery_operator.value) {
    setMessage('plans.chooseMasteryOperator')
    error.value = true
    return
  }
  const warning = masteryTraineeWarning(mastery_operator.value, masterySchedule.value.blocked)
  if (warning)
    message.warning(t('plans.taskMasteryScheduleWarning', { name: mastery_operator.value }))
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
      if (result?.reason) msg.value = result.reason
      else setMessage('plans.masteryPlanFailed')
      error.value = true
      return
    }
    if (result.warning) message.warning(result.warning)
    const planStatus =
      result.status === 'added' ? 'plans.masteryPlanAdded' : 'plans.masteryPlanExists'
    const task = result.task
    if (['inserted', 'queued'].includes(task?.status)) {
      setMessage('plans.masteryTaskQueued', { reason: task.reason }, planStatus)
      error.value = false
      get_tasks()
    } else if (task?.status === 'active') {
      setMessage('plans.masteryTaskActive', { reason: task.reason }, planStatus)
      error.value = false
    } else {
      setMessage(
        task?.reason ? 'plans.masteryTaskNotQueued' : 'plans.masteryTaskUnconfirmed',
        { reason: task?.reason },
        planStatus
      )
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

const skill_list = computed(() => [
  { value: 1, label: t('plans.skill1') },
  { value: 2, label: t('plans.skill2') },
  { value: 3, label: t('plans.skill3') }
])

const level_list = computed(() => [
  { value: 1, label: t('plans.mastery1') },
  { value: 2, label: t('plans.mastery2') },
  { value: 3, label: t('plans.mastery3') }
])
</script>

<template>
  <n-modal
    v-model:show="show"
    preset="card"
    transform-origin="center"
    :style="{ width: isLogPage ? 'auto' : 'max-content', maxWidth: '90vw' }"
    :content-style="
      !isLogPage || task_type === '空任务'
        ? 'display: flex; flex-direction: column; overflow: hidden'
        : undefined
    "
  >
    <template #header>
      <div v-if="isLogPage" class="task_row task_header" style="width: auto">
        <n-select
          v-model:value="task_type"
          :options="taskTypeOptions"
          filterable
          :filter="(p, o) => pinyin_match(o.label, p)"
          :consistent-menu-width="false"
          :placeholder="t('plans.taskType')"
          class="dropdown-select"
          :style="{ width: task_type === '分解所有重复家具' ? '290px' : '190px' }"
        />
        <n-select
          v-if="task_type === '日常任务'"
          v-model:value="daily_task"
          :options="dailyTaskOptions"
          :consistent-menu-width="false"
          :placeholder="t('plans.chooseDailyTask')"
          style="width: 210px"
        />
        <n-select
          v-if="task_type == '技能专精'"
          v-model:value="mastery_operator"
          filterable
          :placeholder="t('plans.chooseOperator')"
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
          :placeholder="t('plans.chooseTime')"
          style="width: 200px"
        />
        <help-text v-if="task_type == '技能专精'">
          <div>{{ t('plans.taskMasterySelectionHelp') }}</div>
          <div>{{ t('plans.taskMasteryRequirementsHelp') }}</div>
          <div>{{ t('plans.taskMasteryAutoHelp') }}</div>
          <div>{{ t('plans.taskMasteryRouteHelp') }}</div>
          <div>
            {{ t('plans.referenceGuide')
            }}<n-button
              text
              tag="a"
              href="https://www.skland.com/article?id=1915250"
              target="_blank"
              type="primary"
              >{{ t('plans.masteryGuide') }}</n-button
            >
          </div>
        </help-text>
      </div>
      <template v-else>{{ t('plans.tasks') }}</template>
    </template>
    <div v-if="!isLogPage || task_type == '空任务'" class="task-list-scroll">
      <n-dynamic-input
        v-model:value="task_list"
        :on-create="new_task"
        :disabled="!isLogPage && edit_locked"
      >
        <template #create-button-default>{{ t('plans.addTask') }}</template>
        <template #default="{ value }">
          <div class="task_row">
            <n-select
              v-model:value="value.room"
              :disabled="!isLogPage && edit_locked"
              :options="roomOptions"
              :placeholder="t('plans.chooseRoom')"
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
              >{{ t('plans.trainingPositionsHelp') }}</n-text
            >
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
    </div>
    <template v-if="isLogPage">
      <template v-if="isMaintenance">
        <div class="task_row">
          <label>{{ t('plans.taskDuration') }}</label>
          <n-input-number
            v-model:value="duration_minutes"
            :min="task_type === '计划停止' ? 0 : 1"
            :max="10080"
            :precision="0"
          />
        </div>
        <div v-if="task_type === '计划暂停'" class="task_row">
          <label>{{ t('plans.taskHandling') }}</label>
          <n-select
            v-model:value="maintenance_mode"
            :options="[
              { label: t('plans.pausePrepare'), value: 'prepare' },
              { label: t('plans.pauseDirect'), value: 'pause' }
            ]"
            style="width: 240px"
          />
        </div>
        <n-text depth="3">
          <template v-if="task_type === '计划停止'"
            >{{ t('plans.taskStopPreparationHelp')
            }}<template v-if="duration_minutes > 0">{{ t('plans.taskStopRestartHelp') }}</template>
            <template v-else>{{ t('plans.taskStopNoRestartHelp') }}</template>
          </template>
          <template v-else
            >{{ t('plans.taskPauseHelp')
            }}<template v-if="maintenance_mode === 'prepare'">{{
              t('plans.taskPausePrepareHelp')
            }}</template>
            <template v-else>{{ t('plans.taskPauseDirectHelp') }}</template>
          </template>
        </n-text>
      </template>
      <n-text v-if="task_type === '日常任务' && daily_task === '日常任务'" depth="3">{{
        t('plans.taskDailyHelp')
      }}</n-text>
      <n-text
        v-else-if="
          !isMaintenance &&
          !['空任务', '技能专精', '加工材料', '仓库扫描', '线索任务', '分解所有重复家具'].includes(
            task_type
          )
        "
        depth="3"
        >{{ t('plans.taskStandaloneHelp') }}</n-text
      >
      <n-text v-if="task_type == '分解所有重复家具'" depth="3">{{
        t('plans.taskFurnitureHelp')
      }}</n-text>
      <div class="task_row" v-if="task_type == '技能专精'">
        <label>{{ t('plans.taskSupportMode') }}</label>
        <n-select
          v-model:value="mastery_support_mode"
          style="width: 240px"
          :options="[
            { label: t('plans.supportAuto'), value: 'auto' },
            { label: t('plans.supportRoute'), value: 'route' }
          ]"
        />
      </div>
      <div class="task_row" v-if="task_type == '加工材料'">
        <label>{{ t('plans.taskOperator') }}</label>
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
          <div>{{ t('plans.taskWorkshopCacheHelp') }}</div>
        </help-text>
      </div>
      <div class="task_row button_row">
        <div style="margin-right: auto">
          <label v-if="error" style="color: red">{{ msg }}</label>
          <label v-if="!error" style="color: green">{{ msg }}</label>
        </div>
        <div style="display: flex; gap: 12px; margin-top: 16px">
          <n-button type="primary" :loading="saving" @click="saveTasks">
            {{ t(task_type == '技能专精' ? 'plans.addMasteryAndTask' : 'plans.addToQueue') }}
          </n-button>
          <n-button type="error" :disabled="saving" @click="clear">{{
            t('plans.clearInput')
          }}</n-button>
        </div>
      </div>
    </template>
  </n-modal>
</template>

<style scoped lang="scss">
.task-list-scroll {
  flex: 1 1 auto;
  min-height: 0;
  max-height: 80vh;
  margin-top: 8px;
  overflow-y: auto;
}

.button_row {
  flex: none;
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
