<script setup>
defineProps({ showEnable: { type: Boolean, default: true } })
import { computed, inject, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { useConfigStore } from '@/stores/config'
const config_store = useConfigStore()
const {
  maa_rg_enable,
  maa_long_task_type,
  maa_long_task_extra_windows,
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

const timeWindows = computed({
  get: () => [
    { start: maa_rg_sleep_max.value, end: maa_rg_sleep_min.value },
    ...maa_long_task_extra_windows.value
  ],
  set: ([first, ...extra]) => {
    maa_rg_sleep_max.value = first.start
    maa_rg_sleep_min.value = first.end
    maa_long_task_extra_windows.value = extra
  }
})

function addTimeWindow(index) {
  return { ...timeWindows.value[Math.max(0, index - 1)] }
}

function updateTimeWindow(index, field, value) {
  if (value !== null) {
    timeWindows.value = timeWindows.value.map((window, i) =>
      i === index ? { ...window, [field]: value } : window
    )
  }
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
      <div class="long-task-time-container">
        <n-dynamic-input v-model:value="timeWindows" :min="1" :on-create="addTimeWindow">
          <template #default="{ value, index }">
            <div class="long-task-times">
              <n-form-item label-placement="top">
                <template #label>
                  开始时间
                  <help-text v-if="index === 0" label="大型任务时段说明">
                    <div>
                      每天在任一执行时段内运行。开始与停止时间相同表示全天开启，停止时间早于开始时间表示跨午夜。
                    </div>
                  </help-text>
                </template>
                <n-time-picker
                  format="H:mm"
                  :formatted-value="value.start"
                  :aria-label="`第${index + 1}段开始时间`"
                  @update:formatted-value="updateTimeWindow(index, 'start', $event)"
                />
              </n-form-item>
              <n-form-item label="停止时间" label-placement="top">
                <n-time-picker
                  format="H:mm"
                  :formatted-value="value.end"
                  :aria-label="`第${index + 1}段停止时间`"
                  @update:formatted-value="updateTimeWindow(index, 'end', $event)"
                />
              </n-form-item>
            </div>
          </template>
        </n-dynamic-input>
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

.long-task-time-container {
  container: long-task-times / inline-size;
}

.long-task-times {
  width: 100%;
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.long-task-setup .long-task-times :deep(.n-form-item) {
  min-width: 0;
  margin: 0;
  padding: 0;
  grid-template-rows: 32px auto auto;
}

.long-task-times :deep(.n-form-item-label) {
  min-height: 24px;
  padding: 0 0 8px;
  align-items: center;
  gap: 6px;
}

.long-task-times :deep(.n-time-picker) {
  width: 100%;
  min-width: 0;
}

@container long-task-times (max-width: 440px) {
  .long-task-times {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
