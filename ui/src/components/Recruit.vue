<script setup>
import { useConfigStore } from '@/stores/config'
const store = useConfigStore()
import { storeToRefs } from 'pinia'
const {
  recruit_enable,
  recruitment_permit,
  recruitment_time,
  recruit_robot,
  recruit_gap,
  recruit_auto_5,
  recruit_auto_only5,
  recruit_email_enable
} = storeToRefs(store)
import { inject } from 'vue'

const mobile = inject('mobile')
</script>

<template>
  <n-card>
    <template #header>
      <n-checkbox v-model:checked="recruit_enable">
        <div class="card-title">公开招募</div>
      </n-checkbox>
    </template>
    <n-form
      :label-placement="mobile ? 'top' : 'left'"
      :show-feedback="false"
      label-width="140"
      label-align="left"
    >
      <n-form-item>
        <template #label>
          <span>启动间隔</span>
          <help-text>
            <div>单位：小时</div>
            <div>可填小数</div>
          </help-text>
        </template>
        <n-input-number v-model:value="recruit_gap" />
      </n-form-item>
      <n-form-item label="三星招募阈值">
        <n-input-number v-model:value="recruitment_permit" />
      </n-form-item>
      <n-form-item label="三星招募时长">
        <n-radio-group v-model:value="recruitment_time" name="recruitment_time">
          <n-space justify="start">
            <n-radio :value="true">7:40</n-radio>
            <n-radio :value="false">9:00</n-radio>
          </n-space>
        </n-radio-group>
      </n-form-item>
      <n-form-item label="五星招募策略">
        <n-radio-group v-model:value="recruit_auto_5" name="recruitment_time">
          <n-space justify="start">
            <n-radio :value="1">自动选择</n-radio>
            <n-radio :value="2">手动选择</n-radio>
          </n-space>
        </n-radio-group>
      </n-form-item>
      <n-form-item v-if="recruit_auto_5 === 2" :show-label="false">
        <n-checkbox v-model:checked="recruit_auto_only5">五星词条组合唯一时自动选择</n-checkbox>
      </n-form-item>
      <n-form-item :show-label="false">
        <n-checkbox v-model:checked="recruit_email_enable">邮件通知</n-checkbox>
      </n-form-item>
      <n-form-item :show-label="false">
        <n-checkbox v-model:checked="recruit_robot">保留支援机械标签</n-checkbox>
      </n-form-item>
    </n-form>
  </n-card>
</template>

<style scoped lang="scss">
.card-title {
  font-weight: 500;
  font-size: 18px;
}

p {
  margin: 0 0 8px 0;
}

h4 {
  margin: 12px 0 10px 0;
}

.big-table {
  margin-top: 10px;
  max-width: 320px;

  th {
    text-align: center;
  }

  tr {
    width: 70px;
  }

  td {
    height: 24px;

    &:nth-child(1) {
      width: 70px;
      text-align: center;
    }
    &:nth-child(2) {
      width: 420px;
    }
  }
}

.final {
  margin: 16px 0 0;
}
</style>
