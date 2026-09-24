<script setup>
import { useConfigStore } from '@/stores/config'
import { usePlanStore } from '@/stores/plan'
import { storeToRefs } from 'pinia'
import { swap } from '@/utils/common'
import { apply_operator_replace, collect_plan_operators } from '@/utils/plan_edit'

const config_store = useConfigStore()
const { free_blacklist, theme, experimental_dorm_logic } = storeToRefs(config_store)

const plan_store = usePlanStore()
const {
  ling_xi,
  mood_limits,
  operator_mood_limits,
  resting_priority,
  resting_standby,
  exhaust_require,
  rest_in_full,
  workaholic,
  backup_plans,
  sub_plan,
  refresh_trading,
  refresh_drained,
  ope_resting_priority,
  dorm_order,
  operators,
  plan
} = storeToRefs(plan_store)
const { load_plan, fill_empty } = plan_store

import { computed, inject, onMounted, onUnmounted, provide, ref, watch, watchEffect } from 'vue'
import { usePlanEditLock } from '@/utils/plan_edit_lock'
const axios = inject('axios')

const facility = ref('')
provide('facility', facility)
const edit_lock = usePlanEditLock()
const edit_locked = edit_lock.locked
provide('planEditLocked', edit_locked)

const current_plan = computed(() => {
  if (sub_plan.value == 'main') {
    return plan.value
  } else {
    return backup_plans.value[sub_plan.value].plan
  }
})

import { useDialog, useMessage, NAlert } from 'naive-ui'

const plan_editor = ref(null)

const generating_image = ref(false)
const show_mood_limits_dialog = ref(false)
watch(experimental_dorm_logic, (enabled) => {
  if (!enabled) show_mood_limits_dialog.value = false
})

const message = useMessage()
const dialog = useDialog()

function requireEditing() {
  if (!edit_lock.isEditable()) {
    message.warning('排班已锁定，请先解锁编辑')
    return false
  }
  edit_lock.noteActivity()
  return true
}

function beforeImport() {
  return requireEditing()
}

// Select menus teleport to body; consider the toolbar controls and the popup "inside".
const sub_plan_dropdown_open = ref(false)

function onSubPlanShowUpdate(show) {
  // Naive UI closes single-select before emitting its value. Ignore that close.
  if (show) sub_plan_dropdown_open.value = true
}

function onSubPlanSelected() {
  sub_plan_dropdown_open.value = true
}

function onSubPlanOutsidePointer(event) {
  const target = event.target
  if (
    target instanceof Element &&
    target.closest('.mower-sub-plan-controls, .mower-sub-plan-menu')
  ) {
    return
  }
  sub_plan_dropdown_open.value = false
}

function onSubPlanKeydown(event) {
  if (event.key === 'Escape') sub_plan_dropdown_open.value = false
}

onMounted(() => {
  edit_lock.start()
  document.addEventListener('pointerdown', onSubPlanOutsidePointer, true)
  document.addEventListener('keydown', onSubPlanKeydown, true)
})
onUnmounted(() => {
  document.removeEventListener('pointerdown', onSubPlanOutsidePointer, true)
  document.removeEventListener('keydown', onSubPlanKeydown, true)
  edit_lock.dispose()
})

import { sleep } from '@/utils/sleep'
import { toBlob } from 'html-to-image'
import { useLoadingBar } from 'naive-ui'

const loading_bar = useLoadingBar()

import Bowser from 'bowser'

import { render_op_label } from '@/utils/op_select'
import { pinyin_match } from '@/utils/common'

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
  if (!requireEditing()) return
  backup_plans.value.push({
    conf: {
      exhaust_require: [],
      free_blacklist: [],
      ling_xi: ling_xi.value,
      mood_limits: null,
      operator_mood_limits: {},
      rest_in_full: [],
      resting_priority: [],
      resting_standby: [],
      workaholic: [],
      refresh_trading: [],
      refresh_drained: [],
      ope_resting_priority: [],
      dorm_order: [],
      dorm_order_override: false
    },
    plan: fill_empty({}),
    trigger: {
      left: '',
      operator: '',
      right: ''
    },
    trigger_timing: 'AFTER_PLANNING',
    exit_trigger_timing: null,
    task: {},
    name: `plan${backup_plans.value.length}`
  })
  sub_plan.value = backup_plans.value.length - 1
}

function delete_sub_plan() {
  if (!requireEditing()) return
  backup_plans.value.splice(sub_plan.value, 1)
  sub_plan.value = 'main'
}

function update_dorm_order_override(value) {
  if (!edit_lock.isEditable()) return
  if (sub_plan.value !== 'main') {
    current_conf.value.dorm_order_override = value.length > 0
  }
}

const current_conf = ref({
  ling_xi: ling_xi.value,
  mood_limits: mood_limits.value,
  operator_mood_limits: operator_mood_limits.value,
  rest_in_full: rest_in_full.value,
  resting_priority: resting_priority.value,
  resting_standby: resting_standby.value,
  workaholic: workaholic.value,
  exhaust_require: exhaust_require.value,
  refresh_trading: refresh_trading.value,
  dorm_order: dorm_order.value
})

watchEffect(() => {
  if (sub_plan.value == 'main') {
    current_conf.value = {
      ling_xi: ling_xi.value,
      mood_limits: mood_limits.value,
      operator_mood_limits: operator_mood_limits.value,
      rest_in_full: rest_in_full.value,
      resting_priority: resting_priority.value,
      resting_standby: resting_standby.value,
      workaholic: workaholic.value,
      exhaust_require: exhaust_require.value,
      refresh_trading: refresh_trading.value,
      free_blacklist: free_blacklist.value,
      refresh_drained: refresh_drained.value,
      ope_resting_priority: ope_resting_priority.value,
      dorm_order: dorm_order.value
    }
  } else {
    current_conf.value = backup_plans.value[sub_plan.value].conf
  }
})

watchEffect(() => {
  if (sub_plan.value == 'main') {
    ling_xi.value = current_conf.value.ling_xi
    mood_limits.value = current_conf.value.mood_limits
    operator_mood_limits.value = current_conf.value.operator_mood_limits
    rest_in_full.value = current_conf.value.rest_in_full
    exhaust_require.value = current_conf.value.exhaust_require
    resting_priority.value = current_conf.value.resting_priority
    resting_standby.value = current_conf.value.resting_standby
    workaholic.value = current_conf.value.workaholic
    refresh_trading.value = current_conf.value.refresh_trading
    free_blacklist.value = current_conf.value.free_blacklist
    refresh_drained.value = current_conf.value.refresh_drained
    ope_resting_priority.value = current_conf.value.ope_resting_priority
    dorm_order.value = current_conf.value.dorm_order
  } else {
    backup_plans.value[sub_plan.value].conf = current_conf.value
  }
})

const show_trigger_editor = ref(false)
provide('show_trigger_editor', show_trigger_editor)

const show_name_editor = ref(false)
provide('show_name_editor', show_name_editor)

const show_replace_dialog = ref(false)
provide('show_replace_dialog', show_replace_dialog)

const show_task = ref(false)
provide('show_task', show_task)

const add_task = ref(false)
provide('add_task', add_task)

watch(edit_locked, (locked) => {
  if (!locked) return
  show_trigger_editor.value = false
  show_name_editor.value = false
  show_replace_dialog.value = false
  show_task.value = false
})

const replace_source = ref('')
const replace_target = ref('')

// 弹窗关闭（应用或取消）时清空选择，避免重开时旧 target 已进排班 → 误报重复守卫
watch(show_replace_dialog, (open) => {
  if (!open) {
    replace_source.value = ''
    replace_target.value = ''
  }
})

async function validate_plan() {
  try {
    const { data } = await axios.post(
      `${import.meta.env.VITE_HTTP_URL}/validate-plan`,
      {},
      {
        headers: { token: token }
      }
    )
    if (data.success) {
      message.success(data.message)
    } else {
      message.error(data.message)
    }
  } catch (error) {
    message.error('验证失败: ' + error.message)
  }
}

function replace_main_conf() {
  return {
    rest_in_full: rest_in_full.value,
    exhaust_require: exhaust_require.value,
    workaholic: workaholic.value,
    resting_priority: resting_priority.value,
    resting_standby: resting_standby.value,
    refresh_trading: refresh_trading.value,
    refresh_drained: refresh_drained.value,
    free_blacklist: free_blacklist.value,
    ope_resting_priority: ope_resting_priority.value,
    operator_mood_limits: operator_mood_limits.value
  }
}

const replace_plan_state = () => ({
  main_plan: plan.value,
  main_conf: replace_main_conf(),
  backup_plans: backup_plans.value
})

// 被替换侧只列排班里出现过的干员（防选了个不在排班里的干员变 no-op）
const replace_source_options = computed(() =>
  collect_plan_operators(replace_plan_state()).map((name) => ({ value: name, label: name }))
)

// 目标干员已在排班 → 提示（不硬禁：重复替换是合理需求，见 #168 修订）
const target_already_in_plan = computed(() => {
  const target = replace_target.value
  if (!target) return false
  return collect_plan_operators(replace_plan_state()).includes(target)
})

function do_replace() {
  if (!requireEditing()) return
  apply_operator_replace(replace_plan_state(), replace_source.value, replace_target.value)
  message.success('替换完成')
  show_replace_dialog.value = false
}

function apply_replace() {
  if (!requireEditing()) return
  if (!replace_source.value || !replace_target.value) {
    message.error('请选择源干员和目标干员')
    return
  }
  if (replace_source.value === replace_target.value) {
    message.error('源干员和目标干员不能相同')
    return
  }
  if (target_already_in_plan.value) {
    dialog.warning({
      title: '目标干员已在排班中',
      content:
        '目标干员已存在于排班（可能来自之前的替换，如主表换过、副表没换）。仍要执行的话会继续把排班里的源干员全部换成目标干员。',
      positiveText: '仍要替换',
      negativeText: '取消',
      onPositiveClick: do_replace
    })
    return
  }
  do_replace()
}

import DocumentExport from '@vicons/carbon/DocumentExport'
import DocumentImport from '@vicons/carbon/DocumentImport'
import IosArrowBack from '@vicons/ionicons4/IosArrowBack'
import IosArrowForward from '@vicons/ionicons4/IosArrowForward'
import CodeSlash from '@vicons/ionicons5/CodeSlash'
import Help from '@vicons/ionicons5/Help'
import TrashOutline from '@vicons/ionicons5/TrashOutline'
import AddTaskRound from '@vicons/material/AddTaskRound'
import RefreshRound from '@vicons/material/RefreshRound'
import PlusRound from '@vicons/material/PlusRound'
import Pencil from '@vicons/tabler/Pencil'
import LockClosedOutline from '@vicons/ionicons5/LockClosedOutline'
import LockOpenOutline from '@vicons/ionicons5/LockOpenOutline'

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
  if (!requireEditing()) return
  if (sub_plan.value !== 'main' && sub_plan.value > 0) {
    const currentIndex = sub_plan.value
    swap(currentIndex, currentIndex - 1, backup_plans.value)
    sub_plan.value = currentIndex - 1
  }
}

function movePlanForward() {
  if (!requireEditing()) return
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
  <div class="plan-toolbar-viewport mx-auto mt-12" aria-label="排班操作栏">
    <div class="plan-bar">
      <n-button-group class="plan-lock-group">
        <n-tooltip trigger="hover" placement="top">
          <template #trigger>
            <n-button
              class="plan-lock-toggle"
              :type="edit_locked ? 'warning' : 'default'"
              :secondary="edit_locked"
              :aria-label="
                edit_locked ? '排班已锁定，点击解锁编辑' : '排班可编辑，点击锁定防止误触'
              "
              :aria-pressed="edit_locked"
              @click="edit_locked ? edit_lock.unlock() : edit_lock.lock()"
            >
              <template #icon>
                <n-icon>
                  <lock-closed-outline v-if="edit_locked" />
                  <lock-open-outline v-else />
                </n-icon>
              </template>
            </n-button>
          </template>
          {{ edit_locked ? '已锁定排班 · 点击解锁编辑' : '当前可编辑 · 点击锁定以防误触' }}
        </n-tooltip>
      </n-button-group>
      <n-button-group class="mower-sub-plan-controls plan-sort-controls">
        <n-button
          title="副表上移"
          aria-label="副表上移"
          :disabled="edit_locked || sub_plan == 'main' || sub_plan == 0"
          @click="movePlanBackward"
        >
          <template #icon>
            <n-icon><ios-arrow-back /></n-icon>
          </template>
        </n-button>
        <n-button
          title="副表下移"
          aria-label="副表下移"
          :disabled="edit_locked || sub_plan == 'main' || sub_plan == backup_plans.length - 1"
          @click="movePlanForward"
        >
          <template #icon>
            <n-icon><ios-arrow-forward /></n-icon>
          </template>
        </n-button>
      </n-button-group>
      <n-button-group class="mower-sub-plan-controls">
        <n-select
          v-model:value="sub_plan"
          :show="sub_plan_dropdown_open"
          style="width: 150px"
          :options="sub_plan_options"
          :menu-props="{ class: 'mower-sub-plan-menu' }"
          @update:show="onSubPlanShowUpdate"
          @update:value="onSubPlanSelected"
        />
        <n-button :disabled="edit_locked || sub_plan == 'main'" @click="show_name_editor = true">
          <template #icon>
            <n-icon>
              <Pencil />
            </n-icon>
          </template>
        </n-button>
      </n-button-group>
      <n-button-group>
        <n-button title="新建副表" :disabled="edit_locked" @click="create_sub_plan">
          <template #icon>
            <n-icon :size="22"><plus-round /></n-icon>
          </template>
          新建副表
        </n-button>
        <n-button v-if="sub_plan == 'main'" title="验证排班" @click="validate_plan">
          <template #icon>
            <n-icon><help /></n-icon>
          </template>
          验证排班
        </n-button>
        <n-button
          v-else
          title="编辑触发条件"
          :disabled="edit_locked"
          @click="show_trigger_editor = true"
        >
          <template #icon>
            <n-icon><code-slash /></n-icon>
          </template>
          编辑触发条件
        </n-button>
        <n-button
          v-if="sub_plan == 'main'"
          title="一键替换干员"
          :disabled="edit_locked"
          @click="show_replace_dialog = true"
        >
          <template #icon>
            <n-icon><refresh-round /></n-icon>
          </template>
          一键替换干员
        </n-button>
        <n-button v-else title="编辑任务" :disabled="edit_locked" @click="show_task = true">
          <template #icon>
            <n-icon><add-task-round /></n-icon>
          </template>
          编辑任务
        </n-button>
        <n-button
          title="删除此副表"
          :disabled="edit_locked || sub_plan == 'main'"
          @click="delete_sub_plan"
        >
          <template #icon>
            <n-icon><trash-outline /></n-icon>
          </template>
          删除此副表
        </n-button>
      </n-button-group>
      <n-upload
        :disabled="edit_locked"
        :on-before-upload="beforeImport"
        style="width: auto"
        :action="import_url"
        :headers="{ token: token }"
        :show-file-list="false"
        name="img"
        @finish="import_plan"
      >
        <n-button title="导入排班" :disabled="edit_locked">
          <template #icon>
            <n-icon><document-import /></n-icon>
          </template>
          导入排班
        </n-button>
      </n-upload>
      <drop-down :select="export_json" :options="export_options">
        <n-button
          title="导出图片"
          @click="save"
          :loading="generating_image"
          :disabled="generating_image"
        >
          <template #icon>
            <n-icon><document-export /></n-icon>
          </template>
          导出图片
        </n-button>
      </drop-down>
    </div>
  </div>
  <plan-editor ref="plan_editor" class="w-980 mx-auto mw-980 px-12" />
  <n-form
    class="w-980 mx-auto mb-12 px-12 mw-980"
    :label-placement="mobile ? 'top' : 'left'"
    :show-feedback="false"
    label-width="160"
    label-align="left"
  >
    <n-form-item v-if="experimental_dorm_logic" :show-label="false">
      <n-button @click="show_mood_limits_dialog = true">设置心情上下限</n-button>
    </n-form-item>
    <n-form-item v-else>
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
      <n-radio-group v-model:value="current_conf.ling_xi" :disabled="edit_locked">
        <n-space>
          <n-radio :value="1">感知信息</n-radio>
          <n-radio :value="2">人间烟火</n-radio>
          <n-radio :value="3">均衡模式</n-radio>
        </n-space>
      </n-radio-group>
    </n-form-item>
    <n-form-item>
      <template #label
        ><span>需要回满心情的干员</span><help-text>休息到当前心情上限后回班。</help-text></template
      >
      <slick-operator-select
        :disabled="edit_locked"
        v-model="current_conf.rest_in_full"
      ></slick-operator-select>
    </n-form-item>
    <n-form-item>
      <template #label>
        <span>需要用尽心情的干员</span
        ><help-text>用尽后下班，优先取得替班；被占用时先换替班，否则叫回占用组。</help-text>
      </template>
      <slick-operator-select
        :disabled="edit_locked"
        v-model="current_conf.exhaust_require"
      ></slick-operator-select>
    </n-form-item>
    <n-form-item>
      <template #label>
        <span>0心情工作的干员</span><help-text>心情涣散状态仍能触发技能的干员</help-text>
      </template>
      <slick-operator-select
        :disabled="edit_locked"
        v-model="current_conf.workaholic"
      ></slick-operator-select>
    </n-form-item>
    <n-form-item>
      <template #label>
        <span>宿舍低优先级干员</span>
        <help-text>
          <template v-if="experimental_dorm_logic">
            低于普通主班，高于候补；同级心情低者优先。需有床才能下班，不改变下班顺序。
          </template>
          <template v-else>降低宿舍分床优先级，不改变下班顺序。</template>
        </help-text>
      </template>
      <slick-operator-select
        :disabled="edit_locked"
        v-model="current_conf.resting_priority"
      ></slick-operator-select>
    </n-form-item>
    <n-form-item>
      <template #label>
        <span>宿舍休息候补干员</span>
        <help-text>
          <template v-if="experimental_dorm_logic">
            有床休息，无床待命；需有正常优先级主班在休息。绑组随组回班，未绑组随下一批回班。低于急救线须有床。
          </template>
          <template v-else>
            仅限绑组，须同组有高优休息。随组待命、回班，空位可补床，非急救时可给高优让床。
          </template>
          <p>待命不恢复心情；用尽、回满、固定宿舍和零心情工作干员不适用。</p>
        </help-text>
      </template>
      <slick-operator-select
        :disabled="edit_locked"
        v-model="current_conf.resting_standby"
      ></slick-operator-select>
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
        :disabled="edit_locked"
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
      <slick-operator-select
        :disabled="edit_locked"
        v-model="current_conf.refresh_drained"
      ></slick-operator-select>
    </n-form-item>
    <n-form-item>
      <template #label>
        <span>宿舍黑名单</span>
        <help-text>
          <template v-if="experimental_dorm_logic"
            >不参与动态分床和补床，固定宿舍岗位不受影响。</template
          >
          <template v-else>不参与空闲干员补床。</template>
        </help-text>
      </template>
      <slick-operator-select
        :disabled="edit_locked"
        v-model="current_conf.free_blacklist"
      ></slick-operator-select>
    </n-form-item>
    <n-form-item>
      <template #label>
        <span>干员休息优先级</span>
        <help-text>
          <template v-if="experimental_dorm_logic">
            <p>名单 → 普通主班 → 低优主班 → 候补 → 替班 → 空闲；同级心情低者优先。</p>
            <p>
              只影响分床和单回，不改变下班顺序。更高排名的新入住者可重分单回，已有普通床位保持不动。
            </p>
          </template>
          <template v-else>按名单顺序优先分床，不改变下班顺序。</template>
        </help-text>
      </template>
      <slick-operator-select
        :disabled="edit_locked"
        v-model="current_conf.ope_resting_priority"
      ></slick-operator-select>
    </n-form-item>
    <n-form-item v-if="experimental_dorm_logic">
      <template #label>
        <span>宿舍优先级排序</span>
        <help-text>
          按所选顺序分床，日常不搬动已入住者。主表默认 1→2→3→4；副表留空继承，调整后覆盖。
        </help-text>
      </template>
      <slick-dorm-select
        :disabled="edit_locked"
        v-model="current_conf.dorm_order"
        room-only
        @update:model-value="update_dorm_order_override"
      ></slick-dorm-select>
    </n-form-item>
  </n-form>
  <n-modal
    v-if="experimental_dorm_logic"
    v-model:show="show_mood_limits_dialog"
    :auto-focus="false"
    preset="card"
    title="设置心情上下限"
    :style="{ width: '680px', maxWidth: 'calc(100vw - 24px)' }"
    :content-style="{ maxHeight: '70vh', overflowY: 'auto' }"
  >
    <n-form label-placement="top" :show-feedback="false">
      <n-form-item>
        <template #label>
          <span>令夕模式</span>
          <help-text>
            <div>令夕上班时起作用</div>
            <div>启动Mower前需要手动对齐心情</div>
            <div>感知：夕心情-令心情=12</div>
            <div>烟火：令心情-夕心情=12</div>
            <div>均衡：夕令心情一样</div>
            <div>个人设置优先于令夕模式，令夕模式优先于全体设置。</div>
          </help-text>
        </template>
        <n-radio-group v-model:value="current_conf.ling_xi" :disabled="edit_locked">
          <n-space>
            <n-radio :value="1">感知信息</n-radio>
            <n-radio :value="2">人间烟火</n-radio>
            <n-radio :value="3">均衡模式</n-radio>
          </n-space>
        </n-radio-group>
      </n-form-item>
      <n-form-item label="自定义上下限">
        <mood-limits-editor
          v-model:defaults="current_conf.mood_limits"
          v-model:overrides="current_conf.operator_mood_limits"
          :disabled="edit_locked"
          :operators="operators"
          :is-backup="sub_plan !== 'main'"
        />
      </n-form-item>
    </n-form>
    <template #footer>
      <n-space justify="end">
        <n-button @click="show_mood_limits_dialog = false">完成</n-button>
      </n-space>
    </template>
  </n-modal>
  <n-modal
    v-model:show="show_replace_dialog"
    preset="card"
    title="一键替换干员"
    :style="{ width: '560px' }"
  >
    <n-alert title="警告" type="warning">
      该操作会一键替换主表+副表所有干员名字，不可逆，使用前最好复制现有排班表，以防出错
    </n-alert>
    <div class="replace-flow">
      <div class="replace-side">
        <div class="replace-side-label">被替换干员（排班中已有）</div>
        <n-select
          v-model:value="replace_source"
          :disabled="edit_locked"
          :options="replace_source_options"
          placeholder="选择排班中的干员"
          filterable
          :filter="(p, o) => pinyin_match(o.label, p)"
          :render-label="render_op_label"
        />
      </div>
      <svg
        class="replace-arrow"
        width="24"
        height="24"
        viewBox="0 0 24 24"
        fill="none"
        aria-hidden="true"
      >
        <path
          d="M5 12h13m-5-5 5 5-5 5"
          stroke="currentColor"
          stroke-width="2"
          stroke-linecap="round"
          stroke-linejoin="round"
        />
      </svg>
      <div class="replace-side">
        <div class="replace-side-label">替换为（全部干员池）</div>
        <n-select
          v-model:value="replace_target"
          :disabled="edit_locked"
          :options="operators"
          placeholder="选择目标干员"
          filterable
          :filter="(p, o) => pinyin_match(o.label, p)"
          :render-label="render_op_label"
        />
      </div>
    </div>
    <n-alert
      v-if="target_already_in_plan"
      title="目标干员已在排班中"
      type="warning"
      class="replace-duplicate"
    >
      目标干员已存在于排班（可能来自之前的替换，如主表换过、副表没换）。仍可替换：点「替换」后确认即可继续。
    </n-alert>
    <template #footer>
      <n-space justify="end">
        <n-button @click="show_replace_dialog = false">取消</n-button>
        <n-button type="primary" :disabled="edit_locked" @click="apply_replace">替换</n-button>
      </n-space>
    </template>
  </n-modal>
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

.plan-lock-toggle {
  min-width: 34px;
  padding: 0 6px;
}

.plan-lock-group {
  flex-shrink: 0;
}

.plan-toolbar-viewport {
  box-sizing: border-box;
  position: sticky;
  top: 0;
  z-index: 5;
  width: calc(100% - 16px);
  max-width: 1180px;
  min-height: 52px;
  overflow-x: auto;
  overflow-y: hidden;
  padding: 8px 0 12px;
  background-color: var(--n-color, #fff);
  scrollbar-width: thin;
  scrollbar-color: #a0a7a5 transparent;
  overscroll-behavior-x: contain;
}

.plan-bar {
  box-sizing: border-box;
  display: flex;
  flex-direction: row;
  flex-wrap: nowrap;
  width: max-content;
  min-width: 100%;
  min-height: 36px;
  gap: clamp(2px, 0.3vw, 5px);
  padding: 0 8px;
  align-items: center;
  justify-content: center;
  white-space: nowrap;
  overflow: visible;
}

.plan-bar > * {
  flex-shrink: 0;
}

.plan-bar :deep(.n-button) {
  padding-inline: clamp(5px, 0.45vw, 9px);
  min-width: 0;
}

.plan-sort-controls :deep(.n-button) {
  width: 32px;
  min-width: 32px;
  padding-inline: 5px;
}

.plan-bar :deep(.n-button__content) {
  gap: 4px;
}

.replace-flow {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 12px;
}

.replace-side {
  flex: 1;
  min-width: 0;
}

.replace-side-label {
  margin-bottom: 6px;
  font-size: 13px;
  color: rgb(153, 153, 153);
}

.replace-arrow {
  flex-shrink: 0;
  color: rgb(153, 153, 153);
}

.replace-duplicate {
  margin-top: 12px;
}
</style>
