<script setup>
import { inject, watch } from 'vue'
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

const mobile = inject('mobile')

const maa_long_task_options = [
  { label: '集成战略 (Maa)', value: 'rogue' },
  { label: '保全派驻 (Maa)', value: 'sss' },
  { label: '生息演算 (Maa)', value: 'rcl' },
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
    <template #header>
      <n-checkbox v-model:checked="maa_rg_enable">
        <div class="card-title">大型任务</div>
      </n-checkbox>
      <help-text>
        <div>开始与结束时间设置为相同值时全天开启。</div>
        <div>若结束时间早于开始时间，则表示开启至次日。例如：</div>
        <ul>
          <li>23:00开始、8:00结束：表示从23:00至次日8:00执行大型任务；</li>
          <li>10:00开始、14:00结束：表示从10:00至当日14:00执行大型任务。</li>
        </ul>
      </help-text>
      <n-select v-model:value="maa_long_task_type" :options="maa_long_task_options" />
    </template>
    <n-form
      :label-placement="mobile ? 'top' : 'left'"
      :show-feedback="false"
      style="margin-bottom: 12px"
    >
      <n-grid cols="2">
        <n-form-item-gi label="开始时间">
          <n-time-picker format="H:mm" v-model:formatted-value="maa_rg_sleep_max" />
        </n-form-item-gi>
        <n-form-item-gi label="停止时间">
          <n-time-picker format="H:mm" v-model:formatted-value="maa_rg_sleep_min" />
        </n-form-item-gi>
      </n-grid>
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
            :options="[
              { label: '沙洲遗闻', value: 'Tales' },
              { label: '重启锚点', value: 'RelaunchAnchor' }
            ]"
          />
        </n-form-item>
        <n-form-item label="模式">
          <n-select
            v-model:value="rcl.mode"
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
              :options="[
                { label: '连点', value: 0 },
                { label: '长按', value: 1 }
              ]"
            />
          </n-form-item>
          <n-form-item label="单次最大组装轮数">
            <n-input-number v-model:value="rcl.num_craft_batches" :min="1" :max="2147483647" />
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
