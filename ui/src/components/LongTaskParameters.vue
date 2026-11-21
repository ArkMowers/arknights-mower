<script setup>
import { computed, inject, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { useConfigStore } from '@/stores/config'

defineProps({ taskType: String })
const { maa_rcl_theme, garrison, rcl } = storeToRefs(useConfigStore())
const mobile = inject('mobile')

const garrisonGoal = computed({
  get: () => (garrison.value.mode === 'matches' ? 'matches' : garrison.value.target_wins),
  set: (value) => {
    garrison.value.mode = value === 'matches' ? 'matches' : 'medals'
    if (value !== 'matches') garrison.value.target_wins = value
  }
})
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
  <template v-if="taskType == 'rcl'">
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
  <maa-rogue v-else-if="taskType == 'rogue'" />
  <maa-copilot v-else-if="taskType == 'copilot'" :key="'copilot'" />
  <maa-copilot v-else-if="taskType == 'paradox'" :key="'paradox'" paradox />
  <maa-sss v-else-if="taskType == 'sss'" />
  <reclamation-algorithm v-else-if="taskType == 'ra'" />
  <secret-front v-else-if="taskType == 'sf'" />
  <template v-else-if="taskType == 'garrison'">
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
      >个人极速模拟使用预设编队，内置的对局脚本和棋盘布局取自 UnknownGlyph 的
      <a
        href="https://github.com/ALEXsun0/GarrisonFarm/tree/fd373c9b1ab1e8fbb52ad78b8da4c461ab325abb"
        target="_blank"
        rel="noopener noreferrer"
        >GarrisonFarm（个人 fork）</a
      >
      。开始时按需切换至「卫戍协议终端」，结束后保留该主题。新局需要至少 12 分钟空档。已保存的对局有
      9 分钟空档即可重连，基建任务到期时退出游戏。</n-p
    >
    <maa-task-status kind="garrison" :settings="garrison" />
    <n-button @click="garrison.run_id = String(Date.now())">{{
      garrison.mode === 'matches' ? '重新计数并继续' : '重新核对并继续'
    }}</n-button>
  </template>
</template>
