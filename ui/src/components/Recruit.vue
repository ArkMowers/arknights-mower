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
  recruit_auto_5
} = storeToRefs(store)
import { ref, inject } from 'vue'

const mobile = inject('mobile')

const recruit_4 = ref('900')
</script>

<template>
  <n-card>
    <template #header>
      <n-checkbox v-model:checked="recruit_enable">
        <div class="card-title">公开招募</div>
      </n-checkbox>
    </template>
    <n-form :label-placement="mobile ? 'top' : 'left'" :show-feedback="false">
      <div class="misc-container">
        <div>启动间隔</div>
        <n-input-number class="hour-input" v-model:value="recruit_gap" />
        <div>小时（可填小数）</div>
      </div>
      <n-form-item>
        <template #label>
          <span>三星招募阈值</span>
          <help-text>
            <div>公招券数量大于此阈值时招募三星</div>
            <div>公招券的数量会维持在阈值附近</div>
            <div>如果不想招三星，就填一个很大的数</div>
          </help-text>
        </template>
        <n-input-number v-model:value="recruitment_permit" />
      </n-form-item>
    </n-form>
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
            <n-radio-group v-model:value="recruitment_time" name="recruitment_time">
              <n-space justify="start">
                <n-radio :value="true">7:40</n-radio>
                <n-radio :value="false">9:00</n-radio>
              </n-space>
            </n-radio-group>
          </td>
        </tr>
        <tr>
          <td>五星</td>
          <td>
            <n-radio-group name="recruit_auto_5" v-model:value="recruit_auto_5">
              <n-space justify="start">
                <n-radio :value="1"> 手动 </n-radio>
                <n-radio :value="2"> 自动 </n-radio>
                <n-radio :value="3"> 仅标签唯一时自动选择 </n-radio>
              </n-space>
            </n-radio-group>
          </td>
        </tr>
        <tr>
          <td>支援机械</td>
          <td>
            <n-checkbox v-model:checked="recruit_robot"> 保留标签 </n-checkbox>
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
