<script setup>
import { i18n } from '@/i18n'
const { t } = i18n.global

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
  {
    get label() {
      return t('tasks.maaIntegratedStrategies')
    },
    value: 'rogue'
  },
  {
    get label() {
      return t('maaActivities.maaCopilot')
    },
    value: 'copilot'
  },
  {
    get label() {
      return t('maaActivities.maaParadox')
    },
    value: 'paradox'
  },
  {
    get label() {
      return t('tasks.maaSss')
    },
    value: 'sss'
  },
  {
    get label() {
      return t('tasks.maaReclamation')
    },
    value: 'rcl'
  },
  {
    get label() {
      return t('tasks.reclamationAlgorithm')
    },
    value: 'ra'
  },
  {
    get label() {
      return t('tasks.secretFront')
    },
    value: 'sf'
  }
]

const tool_options = [
  {
    get label() {
      return t('tasks.glowStick')
    },
    value: '荧光棒'
  },
  {
    get label() {
      return t('tasks.generator')
    },
    value: '发电机'
  }
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
    <template v-if="showEnable" #header>{{ t('tasks.longTasks') }}</template>
    <n-form
      class="long-task-setup"
      :label-placement="mobile ? 'top' : 'left'"
      :show-feedback="false"
    >
      <n-form-item v-if="showEnable" :label="t('tasks.enableLongTasks')">
        <n-switch v-model:value="longTaskEnabled" :aria-label="t('tasks.enableLongTasks')" />
      </n-form-item>
      <n-form-item :label="t('tasks.taskType')">
        <n-select
          v-model:value="maa_long_task_type"
          :options="maa_long_task_options"
          :consistent-menu-width="false"
          :aria-label="t('tasks.taskType')"
        />
      </n-form-item>
      <div class="long-task-time-container">
        <div class="long-task-times">
          <n-form-item label-placement="top">
            <template #label
              >{{ t('tasks.startTime')
              }}<help-text :label="t('tasks.longTaskWindowHelpTitle')">
                <div>{{ t('tasks.allDaySameTime') }}</div>
                <div>{{ t('tasks.overnightWindowHelp') }}</div>
                <ul>
                  <li>{{ t('tasks.overnightWindowExample') }}</li>
                  <li>{{ t('tasks.sameDayWindowExample') }}</li>
                </ul>
              </help-text>
            </template>
            <n-time-picker format="H:mm" v-model:formatted-value="maa_rg_sleep_max" />
          </n-form-item>
          <n-form-item :label="t('tasks.stopTime')" label-placement="top">
            <n-time-picker format="H:mm" v-model:formatted-value="maa_rg_sleep_min" />
          </n-form-item>
        </div>
      </div>
    </n-form>
    <template v-if="maa_long_task_type == 'rcl'">
      <n-form :label-placement="mobile ? 'top' : 'left'" :show-feedback="false">
        <n-form-item>
          <template #label
            >{{ t('tasks.theme')
            }}<help-text
              >{{ t('tasks.maaDocsAdvice')
              }}<n-button
                text
                tag="a"
                href="https://docs.maa.plus/zh-cn/manual/introduction/reclamation-algorithm.html"
                target="_blank"
                type="success"
                >{{ t('tasks.reclamationAlgorithm') }}</n-button
              >
            </help-text>
          </template>
          <n-select
            v-model:value="maa_rcl_theme"
            :consistent-menu-width="false"
            :options="[
              { label: t('tasks.reclamationTales'), value: 'Tales' },
              { label: t('tasks.reclamationAnchor'), value: 'RelaunchAnchor' }
            ]"
          />
        </n-form-item>
        <n-form-item :label="t('tasks.mode')">
          <n-select
            v-model:value="rcl.mode"
            :consistent-menu-width="false"
            :options="
              maa_rcl_theme == 'Tales'
                ? [
                    { label: t('tasks.defaultNoSave'), value: 0 },
                    { label: t('tasks.craftPointsSave'), value: 1 }
                  ]
                : [
                    { label: t('tasks.ra1NoOperator'), value: 16 },
                    { label: t('tasks.ra4Support'), value: 48 },
                    { label: t('tasks.ra15Support'), value: 32 }
                  ]
            "
          />
        </n-form-item>
        <template v-if="maa_rcl_theme == 'Tales'">
          <n-form-item v-if="rcl.mode === 0" :show-label="false">
            <n-checkbox v-model:checked="rcl.clear_store">{{
              t('maaActivities.clearStore')
            }}</n-checkbox>
          </n-form-item>
          <n-form-item :label="t('tasks.supportToolName')" v-if="rcl.mode == 1">
            <n-select
              v-model:value="rcl.tools_to_craft"
              :consistent-menu-width="false"
              multiple
              filterable
              tag
              :options="tool_options"
              :placeholder="t('tasks.supportToolInput')"
            />
          </n-form-item>
          <n-form-item :label="t('tasks.incrementMode')" v-if="rcl.mode == 1">
            <n-select
              v-model:value="rcl.increment_mode"
              :consistent-menu-width="false"
              :options="[
                { label: t('tasks.repeatedTaps'), value: 0 },
                { label: t('tasks.holdIncrease'), value: 1 }
              ]"
            />
          </n-form-item>
          <n-form-item v-if="rcl.mode === 1" :label="t('tasks.maxCraftRounds')">
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
