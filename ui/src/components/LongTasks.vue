<script setup>
defineProps({ showEnable: { type: Boolean, default: true } })
import { computed, inject, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { useConfigStore } from '@/stores/config'
import { WEEKDAYS } from '@/utils/maa_weekly_plan'
import WeeklyPlanDayCell from './WeeklyPlanDayCell.vue'
const config_store = useConfigStore()
const {
  maa_rg_enable,
  maa_long_task_type,
  maa_long_task_extra_windows,
  maa_long_task_weekly_windows,
  maa_rg_sleep_min,
  maa_rg_sleep_max,
  maa_rcl_theme,
  garrison,
  rcl
} = storeToRefs(config_store)
const longTaskEnabled = computed({
  get: () => maa_rg_enable.value === true || maa_rg_enable.value === 1,
  set: (value) => (maa_rg_enable.value = value)
})

const everyDay = WEEKDAYS.map((_, day) => day)
const weekColumns = [6, 0, 1, 2, 3, 4, 5]
const validTime = (value) => /^(?:[01]?[0-9]|2[0-3]):[0-5][0-9]$/.test(value)
const timeWindows = computed(() => {
  if (maa_long_task_weekly_windows.value !== null) return maa_long_task_weekly_windows.value
  const daily = [
    { start: maa_rg_sleep_max.value, end: maa_rg_sleep_min.value },
    ...maa_long_task_extra_windows.value
  ].filter(({ start, end }) => validTime(start) && validTime(end))
  if (!daily.length) daily.push({ start: '0:00', end: '0:00' })
  return daily.map((window) => ({ ...window, weekdays: everyDay.slice() }))
})

function addTimeWindow() {
  maa_long_task_weekly_windows.value = [
    ...timeWindows.value,
    { start: '8:00', end: '12:00', weekdays: [] }
  ]
}

function removeTimeWindow(index) {
  maa_long_task_weekly_windows.value = timeWindows.value.filter((_, i) => i !== index)
}

function updateWindow(index, update) {
  maa_long_task_weekly_windows.value = timeWindows.value.map((window, i) =>
    i === index ? { ...window, ...update } : window
  )
}

function updateTimeWindow(index, field, value) {
  if (validTime(value)) updateWindow(index, { [field]: value })
}

function toggleWeekday(index, day) {
  const days = timeWindows.value[index].weekdays
  const checked = !days.includes(day)
  updateWindow(index, {
    weekdays: everyDay.filter((weekday) => (weekday === day ? checked : days.includes(weekday)))
  })
}

function allDaysSelected(window) {
  return everyDay.every((day) => window.weekdays.includes(day))
}

function clockMinute(time) {
  const [hour, minute] = time.split(':').map(Number)
  return hour * 60 + minute
}

const garrisonGoal = computed({
  get: () => (garrison.value.mode === 'matches' ? 'matches' : garrison.value.target_wins),
  set: (value) => {
    garrison.value.mode = value === 'matches' ? 'matches' : 'medals'
    if (value !== 'matches') garrison.value.target_wins = value
  }
})
const mobile = inject('mobile')

const maa_long_task_options = [
  { label: '集成战略 (MAA)', value: 'rogue' },
  { label: '自动战斗／作业 (MAA)', value: 'copilot' },
  { label: '悖论模拟 (MAA)', value: 'paradox' },
  { label: '保全派驻 (MAA)', value: 'sss' },
  { label: '生息演算 (MAA)', value: 'rcl' },
  { label: '生息演算', value: 'ra' },
  { label: '隐秘战线', value: 'sf' },
  { label: '卫戍协议 · 个人极速模拟', value: 'garrison' }
]

const tool_options = [
  { label: '荧光棒', value: '荧光棒' },
  { label: '发电机', value: '发电机' }
]

watch(maa_rcl_theme, (theme) => {
  if (theme == 'RelaunchAnchor' && (rcl.value?.mode ?? 0) <= 1) {
    rcl.value = { ...rcl.value, mode: 16, tools_to_craft: ['荧光棒'], increment_mode: 0 }
  }
  if (theme == 'Tales' && (rcl.value?.mode ?? 0) >= 16) {
    rcl.value = { ...rcl.value, mode: 0, tools_to_craft: ['荧光棒'], increment_mode: 0 }
  }
})

watch(
  () => rcl.value?.mode,
  (val) => {
    if (val === 0) {
      rcl.value = { ...rcl.value, tools_to_craft: ['荧光棒'], increment_mode: 0 }
    }
  }
)
</script>

<template>
  <n-card>
    <template v-if="showEnable" #header>大型任务</template>
    <n-form
      class="long-task-setup"
      :label-placement="mobile ? 'top' : 'left'"
      :show-feedback="false"
    >
      <n-form-item v-if="showEnable" label="启用大型任务">
        <n-switch v-model:value="longTaskEnabled" aria-label="启用大型任务" />
      </n-form-item>
      <n-form-item label="任务类型">
        <n-select
          v-model:value="maa_long_task_type"
          :options="maa_long_task_options"
          :consistent-menu-width="false"
          aria-label="任务类型"
        />
      </n-form-item>
      <div class="long-task-weekly">
        <div class="long-task-weekly-toolbar">
          <span>
            执行时段
            <help-text label="大型任务时段说明">
              按 Mower
              运行机器的时间，午夜换日。重叠或相接的时段合并执行。起止时间相同表示当天全天，停止时间早于开始时间表示运行到次日。
            </help-text>
          </span>
          <n-button size="small" aria-label="添加执行时段" @click="addTimeWindow">
            添加执行时段
          </n-button>
        </div>
        <div class="long-task-table-wrap">
          <table class="long-task-table" aria-label="大型任务周计划">
            <thead>
              <tr>
                <th scope="col" class="select-all-column">全选</th>
                <th scope="col" class="time-column">时间段</th>
                <th v-for="day in weekColumns" :key="day" scope="col">{{ WEEKDAYS[day] }}</th>
                <th scope="col" class="window-action">操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(window, index) in timeWindows" :key="index">
                <td class="select-all-column">
                  <n-checkbox
                    :checked="allDaysSelected(window)"
                    :indeterminate="window.weekdays.length > 0 && !allDaysSelected(window)"
                    :aria-label="`第${index + 1}段全选`"
                    @update:checked="
                      updateWindow(index, { weekdays: $event ? everyDay.slice() : [] })
                    "
                  />
                </td>
                <td class="time-column">
                  <div class="time-inputs">
                    <n-time-picker
                      size="small"
                      format="H:mm"
                      :formatted-value="window.start"
                      :aria-label="`第${index + 1}段开始时间`"
                      @update:formatted-value="updateTimeWindow(index, 'start', $event)"
                    />
                    <span>至</span>
                    <n-time-picker
                      size="small"
                      format="H:mm"
                      :formatted-value="window.end"
                      :aria-label="`第${index + 1}段停止时间`"
                      @update:formatted-value="updateTimeWindow(index, 'end', $event)"
                    />
                    <small v-if="clockMinute(window.end) === clockMinute(window.start)">全天</small>
                    <small v-else-if="clockMinute(window.end) < clockMinute(window.start)"
                      >次日</small
                    >
                  </div>
                </td>
                <WeeklyPlanDayCell
                  v-for="day in weekColumns"
                  :key="day"
                  :selected="window.weekdays.includes(day)"
                  :label="`第${index + 1}段${WEEKDAYS[day]}`"
                  @toggle="toggleWeekday(index, day)"
                >
                  ✓
                </WeeklyPlanDayCell>
                <td class="window-action">
                  <n-button
                    type="error"
                    size="small"
                    :aria-label="`删除第${index + 1}段`"
                    @click="removeTimeWindow(index)"
                  >
                    删除
                  </n-button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <n-text v-if="!timeWindows.some((window) => window.weekdays.length)" depth="3">
          未选执行时段，大型任务暂停自动执行。
        </n-text>
      </div>
    </n-form>
    <template v-if="maa_long_task_type == 'rcl'">
      <n-form :label-placement="mobile ? 'top' : 'left'" :show-feedback="false">
        <n-form-item>
          <template #label>
            主题
            <help-text>
              使用前建议阅读 MAA 文档：
              <n-button
                text
                tag="a"
                href="https://docs.maa.plus/zh-cn/manual/introduction/reclamation-algorithm.html"
                target="_blank"
                type="success"
                >生息演算</n-button
              >
            </help-text>
          </template>
          <n-select
            v-model:value="maa_rcl_theme"
            :consistent-menu-width="false"
            :options="[
              { label: '沙洲遗闻', value: 'Tales' },
              { label: '重启锚点', value: 'RelaunchAnchor' }
            ]"
          />
        </n-form-item>
        <n-form-item label="模式">
          <n-select
            v-model:value="rcl.mode"
            :consistent-menu-width="false"
            :options="
              maa_rcl_theme == 'Tales'
                ? [
                    { label: '默认模式（无存档）', value: 0 },
                    { label: '制造刷点数（有存档）', value: 1 }
                  ]
                : [
                    { label: 'RA-1（无干员要求）', value: 16 },
                    { label: 'RA-4（维什戴尔 可借助战）', value: 48 },
                    { label: 'RA-15（圣聆初雪 可借助战）', value: 32 }
                  ]
            "
          />
        </n-form-item>
        <template v-if="maa_rcl_theme == 'Tales'">
          <n-form-item v-if="rcl.mode === 0" :show-label="false">
            <n-checkbox v-model:checked="rcl.clear_store">刷满后清空商店</n-checkbox>
          </n-form-item>
          <n-form-item label="支援道具名称" v-if="rcl.mode == 1">
            <n-select
              v-model:value="rcl.tools_to_craft"
              :consistent-menu-width="false"
              multiple
              filterable
              tag
              :options="tool_options"
              placeholder="输入或选择道具名"
            />
          </n-form-item>
          <n-form-item label="增加方式" v-if="rcl.mode == 1">
            <n-select
              v-model:value="rcl.increment_mode"
              :consistent-menu-width="false"
              :options="[
                { label: '连点', value: 0 },
                { label: '长按', value: 1 }
              ]"
            />
          </n-form-item>
          <n-form-item v-if="rcl.mode === 1" label="单次最大组装轮数">
            <mower-input-number v-model:value="rcl.num_craft_batches" :min="1" :max="2147483647" />
          </n-form-item>
        </template>
      </n-form>
    </template>
    <maa-rogue v-else-if="maa_long_task_type == 'rogue'" />
    <maa-copilot v-else-if="maa_long_task_type == 'copilot'" :key="'copilot'" />
    <maa-copilot v-else-if="maa_long_task_type == 'paradox'" :key="'paradox'" paradox />
    <maa-sss v-else-if="maa_long_task_type == 'sss'" />
    <reclamation-algorithm v-else-if="maa_long_task_type == 'ra'" />
    <secret-front v-else-if="maa_long_task_type == 'sf'" />
    <template v-else-if="maa_long_task_type == 'garrison'">
      <n-form-item label="刷取目标">
        <n-select
          v-model:value="garrisonGoal"
          :options="[
            { label: '三胜 · 金章', value: 3 },
            { label: '六胜 · 彩章', value: 6 },
            { label: '刷等级', value: 'matches' }
          ]"
          aria-label="刷取目标"
        />
      </n-form-item>
      <n-form-item v-if="garrison.mode === 'matches'" label="刷取局数（0 为不限）">
        <n-input-number
          :value="garrison.match_limit"
          :min="0"
          :precision="0"
          aria-label="刷取局数"
          @update:value="
            (value) => {
              if (value !== null) garrison.match_limit = value
            }
          "
        />
      </n-form-item>
      <n-p>
        开局前可在游戏的「选配助战」里借用自己缺少的干员。商店优先购买的前六名依次为塔露拉、史尔特尔、耀骑士临光、逻各斯、克莱门莎、锏。
      </n-p>
      <details>
        <summary>查看其余助战推荐（按购买优先级）</summary>
        <n-p>
          帕拉斯、真言、蕾缪安、烛煌、艾丽妮、薇薇安娜、维娜·维多利亚、乌尔比安、棘刺、怒潮凛冬、圣聆初雪、迷迭香、鸿雪、贝洛内、佩佩、隐德来希、冻河、酒神。
        </n-p>
      </details>
      <n-p
        >个人极速模拟使用预设编队。首次运行从
        <a
          href="https://github.com/UnknownGlyph/GarrisonFarm"
          target="_blank"
          rel="noopener noreferrer"
          >GarrisonFarm</a
        >
        下载对局脚本和布局。新局需要至少 12 分钟空档。已保存的对局有 9
        分钟空档即可重连，基建任务到期时退出游戏。</n-p
      >
      <maa-task-status kind="garrison" :settings="garrison" />
      <n-button @click="garrison.run_id = String(Date.now())">{{
        garrison.mode === 'matches' ? '重新计数并继续' : '重新核对并继续'
      }}</n-button>
    </template>
  </n-card>
</template>

<style scoped>
.long-task-setup {
  margin-bottom: 16px;
}

.long-task-weekly {
  width: 100%;
  min-width: 0;
}

.long-task-weekly-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 10px;
}

.long-task-table-wrap {
  overflow-x: auto;
  border-radius: 10px;
  box-shadow:
    0 0 0 1px rgba(0, 0, 0, 0.06),
    0 4px 12px rgba(0, 0, 0, 0.04);
}

.long-task-table {
  width: 100%;
  min-width: 700px;
  table-layout: fixed;
  border-collapse: separate;
  border-spacing: 0;
  text-align: center;
}

.long-task-table :is(th, td) {
  padding: 0;
  box-shadow: inset -1px -1px 0 rgba(0, 0, 0, 0.06);
}

.long-task-table th {
  height: 40px;
  font-weight: 600;
}

.select-all-column {
  width: 44px;
}

.time-column {
  width: 260px;
  text-align: left;
}

.long-task-table .time-column {
  padding: 0 8px;
}

.window-action {
  width: 64px;
}

.time-inputs {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr) 28px;
  align-items: center;
  gap: 6px;
}

.time-inputs small {
  white-space: nowrap;
}
</style>
