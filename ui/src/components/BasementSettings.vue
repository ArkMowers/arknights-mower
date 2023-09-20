<script setup>
import { useConfigStore } from '@/stores/config'
import { usePlanStore } from '@/stores/plan'
import { storeToRefs } from 'pinia'
import { computed } from 'vue'

const config_store = useConfigStore()
const plan_store = usePlanStore()

const {
  run_order_delay,
  drone_room,
  drone_count_limit,
  reload_room,
  free_blacklist,
  resting_threshold
} = storeToRefs(config_store)

const { ling_xi } = storeToRefs(plan_store)

const { operators } = storeToRefs(plan_store)

const { left_side_facility } = plan_store

const facility_with_empty = computed(() => {
  return [{ label: '（加速贸易站）', value: '' }].concat(left_side_facility)
})
</script>

<template>
  <div class="home-container">
    <n-card title="基建设置">
      <table class="riic-conf">
        <tr>
          <td>
            宿舍黑名单<help-text>
              <div>不希望进行填充宿舍的干员</div>
            </help-text>
          </td>
          <td colspan="2">
            <n-select multiple filterable tag :options="operators" v-model:value="free_blacklist" />
          </td>
        </tr>
        <tr>
          <td>
            跑单前置延时<help-text>
              <div>推荐范围5-10</div>
            </help-text>
          </td>
          <td>
            <n-input-number v-model:value="run_order_delay" />
          </td>
          <td>分钟（可填小数）</td>
        </tr>
        <tr>
          <td>无人机使用房间：<help-text>
              <div>加速制造站就选对应的制造站</div>
              <div>加速龙门币贸易站，选择 (加速贸易站)</div>
              <div>卖玉的贸易站,不会被加速,放心选 (加速贸易站)</div>
            </help-text></td>
          <td colspan="2">
            <n-select :options="facility_with_empty" v-model:value="drone_room" />
          </td>
        </tr>
        <tr>
          <td>
            无人机使用阈值<help-text>
              <div>如加速贸易，推荐大于 贸易站数 x 10 + 92</div>
              <div>如加速制造，推荐大于 贸易站数 x 10</div>
            </help-text>
          </td>
          <td colspan="2">
            <n-input-number v-model:value="drone_count_limit" />
          </td>
        </tr>
        <tr>
          <td>搓玉补货房间：</td>
          <td colspan="2">
            <n-select
              multiple
              filterable
              tag
              :options="left_side_facility"
              v-model:value="reload_room"
            />
          </td>
        </tr>
        <tr>
          <td>
            心情阈值：<help-text>
              <div>2电站推荐不低于0.75</div>
              <div>3电站推荐不低于0.5</div>
              <div>即将大更新推荐设置成0.8</div>
            </help-text>
          </td>
          <td colspan="2">
            <div class="threshold">
              <n-slider v-model:value="resting_threshold" :step="0.05" :min="0.5" :max="0.8" />
              <n-input-number v-model:value="resting_threshold" :step="0.05" :min="0.5" :max="1" />
            </div>
          </td>
        </tr>
      </table>
    </n-card>
  </div>
</template>

<style scoped lang="scss">
.threshold {
  display: flex;
  align-items: center;
  gap: 14px;
}

.riic-conf {
  width: 100%;

  td {
    &:nth-child(1) {
      width: 130px;
    }

    &:nth-child(3) {
      padding-left: 12px;
      width: 120px;
    }
  }
}

.coord {
  td {
    width: 120px;

    &:nth-child(1),
    &:nth-child(3) {
      width: 30px;
    }

    &:nth-child(2) {
      padding-right: 30px;
    }
  }
}
</style>
