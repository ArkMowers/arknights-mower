<script setup>
import { useConfigStore } from '@/stores/config'
import { usePlanStore } from '@/stores/plan'
import { storeToRefs } from 'pinia'
import { computed } from 'vue'

const config_store = useConfigStore()
const plan_store = usePlanStore()

const {
  run_mode,
  run_order_delay,
  drone_room,
  drone_count_limit,
  reload_room,
  start_automatically,
  free_blacklist,
  adb,
  package_type,
  simulator,
  theme,
  resting_threshold,
  tap_to_launch_game,
  exit_game_when_idle,
  screenshot
} = storeToRefs(config_store)

const { operators } = storeToRefs(plan_store)

const { left_side_facility } = plan_store

const facility_with_empty = computed(() => {
  return [{ label: '（加速贸易站）', value: '' }].concat(left_side_facility)
})

const simulator_types = [
  { label: '夜神', value: '夜神' },
  { label: 'MuMu模拟器12', value: 'MuMu12' },
  { label: '其它', value: '' }
]

const launch_options = [
  { label: '使用adb命令启动', value: 'adb' },
  { label: '点击屏幕启动', value: 'tap' }
]

import { folder_dialog } from '@/utils/dialog'

async function select_simulator_folder() {
  const folder_path = await folder_dialog()
  if (folder_path) {
    simulator.value.simulator_folder = folder_path
  }
}
</script>

<template>
  <div class="home-container external-container">
    <n-card title="Mower设置">
      <table class="mower-basic">
        <tr>
          <td class="config-label">服务器：</td>
          <td colspan="2">
            <n-radio-group v-model:value="package_type">
              <n-space>
                <n-radio value="official">官服</n-radio>
                <n-radio value="bilibili">BiliBili服</n-radio>
              </n-space>
            </n-radio-group>
          </td>
        </tr>
        <tr>
          <td>
            adb连接地址
            <help-text>
              <div>不同模拟器adb地址不同。如不填，系统会自动去寻找adb device中的第一个。</div>
              <div>夜神：<code>127.0.0.1:62001</code></div>
            </help-text>
          </td>
          <td colspan="2">
            <n-input v-model:value="adb"></n-input>
          </td>
        </tr>
        <tr>
          <td>模拟器</td>
          <td colspan="2">
            <n-select v-model:value="simulator.name" :options="simulator_types" />
          </td>
        </tr>
        <tr v-if="simulator.name">
          <td>
            多开编号
            <help-text>
              <div>除夜神单开选择-1以外，其他的按照改模拟器多开器中的序号。</div>
            </help-text>
          </td>
          <td colspan="2">
            <n-input-number v-model:value="simulator.index"></n-input-number>
          </td>
        </tr>
        <tr v-if="simulator.name">
          <td>
            模拟器文件夹<help-text>
              <div>夜神：写到bin文件夹</div>
              <div>MuMu12: 写到shell文件夹</div>
            </help-text>
          </td>
          <td>
            <n-input v-model:value="simulator.simulator_folder"></n-input>
          </td>
          <td>
            <n-button @click="select_simulator_folder">...</n-button>
          </td>
        </tr>
        <tr>
          <td>启动游戏：</td>
          <td colspan="2">
            <n-select v-model:value="tap_to_launch_game.enable" :options="launch_options" />
          </td>
        </tr>
        <tr v-if="tap_to_launch_game.enable == 'tap'">
          <td>点击坐标：</td>
          <td colspan="2">
            <table class="coord">
              <tr>
                <td>X:</td>
                <td>
                  <n-input-number v-model:value="tap_to_launch_game.x"></n-input-number>
                </td>
                <td>Y:</td>
                <td>
                  <n-input-number v-model:value="tap_to_launch_game.y"></n-input-number>
                </td>
              </tr>
            </table>
          </td>
        </tr>
        <tr>
          <td colspan="3">
            <n-checkbox v-model:checked="exit_game_when_idle"
              >任务结束后退出游戏以降低功耗</n-checkbox
            >
          </td>
        </tr>
        <tr>
          <td>运行模式：</td>
          <td colspan="2">
            <n-radio-group v-model:value="run_mode">
              <n-space>
                <n-radio value="full">换班+跑单</n-radio>
                <n-radio value="orders_only">仅跑单</n-radio>
              </n-space>
            </n-radio-group>
          </td>
        </tr>
        <tr>
          <td colspan="3">
            <n-checkbox v-model:checked="start_automatically">启动后自动开始任务</n-checkbox>
          </td>
        </tr>
        <tr>
          <td>截图数量：</td>
          <td colspan="2">
            <n-input-number v-model:value="screenshot" />
          </td>
        </tr>
        <tr>
          <td>显示主题：</td>
          <td colspan="2">
            <n-radio-group v-model:value="theme">
              <n-space>
                <n-radio value="light">亮色</n-radio>
                <n-radio value="dark">暗色</n-radio>
              </n-space>
            </n-radio-group>
          </td>
        </tr>
      </table>
    </n-card>
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
          <td>无人机使用房间：</td>
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
              <n-input-number
                v-model:value="resting_threshold"
                :step="0.05"
                :min="0.5"
                :max="0.8"
              />
            </div>
          </td>
        </tr>
      </table>
    </n-card>
    <maa-basic />
    <email />
    <!--    <SKLand/>-->
  </div>
</template>

<style scoped lang="scss">
.threshold {
  display: flex;
  align-items: center;
  gap: 14px;
}

.mower-basic {
  width: 100%;

  td:nth-child(1) {
    width: 120px;
  }

  td:nth-child(3) {
    padding-left: 6px;
    width: 40px;
  }
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
