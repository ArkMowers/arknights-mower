<script setup>
import { useConfigStore } from '@/stores/config'
const store = useConfigStore()
import { storeToRefs } from 'pinia'
const { recruit_enable, recruit_only_4, recruitment_time, recruit_robot } = storeToRefs(store)
import { ref, computed } from 'vue'

const recruit_3 = computed({
  get() {
    if (recruit_only_4.value) {
      return 'skip'
    }
    return recruitment_time.value ? '740' : '900'
  },
  set(v) {
    recruit_only_4.value = v == 'skip'
    recruitment_time.value = v == '740'
  }
})

const recruit_4 = ref('900')
</script>

<template>
  <n-card>
    <template #header>
      <n-checkbox v-model:checked="recruit_enable">
        <div class="card-title">公开招募</div>
      </n-checkbox>
    </template>
    <n-table :single-line="false" size="small" class="big-table">
      <thead>
        <tr>
          <th>可保底</th>
          <th>招募选项</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td>三星</td>
          <td>
            <n-radio-group v-model:value="recruit_3" name="recruit_3">
              <n-space justify="start">
                <n-radio value="skip">不招</n-radio>
                <n-radio value="740">7:40</n-radio>
                <n-radio value="900">9:00</n-radio>
              </n-space>
            </n-radio-group>
          </td>
        </tr>
        <tr>
          <td>四星</td>
          <td>
            <n-radio-group name="recruit_4" v-model:value="recruit_4">
              <n-space justify="start">
                <n-radio value="900">9:00</n-radio>
              </n-space>
            </n-radio-group>
          </td>
        </tr>
        <tr>
          <td>支援机械</td>
          <td>
            <n-radio-group name="recruit_robot" v-model:value="recruit_robot">
              <n-space justify="start">
                <n-radio :value="true">
                  邮件通知
                  <help-text>
                    <div>发送邮件通知，不自动选择</div>
                  </help-text>
                </n-radio>
                <n-radio :value="false">
                  忽略标签
                  <help-text>
                    <div>忽略支援机械标签，按策略自动刷新或选择标签</div>
                  </help-text>
                </n-radio>
              </n-space>
            </n-radio-group>
          </td>
        </tr>
      </tbody>
    </n-table>
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

.recruit-3 td {
  &:nth-child(1) {
    width: 64px;
  }

  &:nth-child(2) {
    width: 200px;
  }
}

.big-table {
  margin-top: 10px;
  width: 400px;

  th {
    text-align: center;
  }

  td {
    height: 24px;

    &:nth-child(1) {
      width: 70px;
      text-align: center;
    }
    &:nth-child(2) {
      padding-left: 18px;
    }
  }
}

.final {
  margin: 16px 0 0;
}
</style>
