<script setup>
defineProps({ showEnable: { type: Boolean, default: true } })
import { computed, inject, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { useConfigStore } from '@/stores/config'
const config_store = useConfigStore()
const {
  maa_rg_enable,
  maa_long_task_type,
  maa_rg_sleep_min,
  maa_rg_sleep_max,
  maa_rcl_theme,
  rcl
} = storeToRefs(config_store)
const longTaskEnabled = computed({
  get: () => maa_rg_enable.value === true || maa_rg_enable.value === 1,
  set: (value) => (maa_rg_enable.value = value)
})

const mobile = inject('mobile')

const maa_long_task_options = [
  { label: '集成战略 (MAA)', value: 'rogue' },
  { label: '保全派驻 (MAA)', value: 'sss' },
  { label: '生息演算 (MAA)', value: 'rcl' },
  { label: '生息演算', value: 'ra' },
  { label: '隐秘战线', value: 'sf' }
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
        <div class="long-task-times">
          <n-form-item label-placement="top">
            <template #label>
              开始时间
              <help-text label="大型任务时段说明">
                <div>开始与结束时间设置为相同值时全天开启。</div>
                <div>若结束时间早于开始时间，则表示开启至次日。例如：</div>
                <ul>
                  <li>23:00开始、8:00结束：表示从23:00至次日8:00执行大型任务；</li>
                  <li>10:00开始、14:00结束：表示从10:00至当日14:00执行大型任务。</li>
                </ul>
              </help-text>
            </template>
            <n-time-picker format="H:mm" v-model:formatted-value="maa_rg_sleep_max" />
          </n-form-item>
          <n-form-item label="停止时间" label-placement="top">
            <n-time-picker format="H:mm" v-model:formatted-value="maa_rg_sleep_min" />
          </n-form-item>
        </div>
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
          <n-form-item label="单次最大组装轮数">
            <mower-input-number v-model:value="rcl.num_craft_batches" :min="1" :max="2147483647" />
          </n-form-item>
        </template>
      </n-form>
    </template>
    <maa-rogue v-else-if="maa_long_task_type == 'rogue'" />
    <maa-sss v-else-if="maa_long_task_type == 'sss'" />
    <reclamation-algorithm v-else-if="maa_long_task_type == 'ra'" />
    <secret-front v-else-if="maa_long_task_type == 'sf'" />
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
