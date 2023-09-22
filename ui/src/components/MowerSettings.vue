<script setup>
import { useConfigStore } from '@/stores/config'

import { storeToRefs } from 'pinia'

const config_store = useConfigStore()

const {
  run_mode,

  start_automatically,

  adb,
  package_type,
  simulator,
  theme,

  tap_to_launch_game,
  exit_game_when_idle,
  screenshot
} = storeToRefs(config_store)

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

</template>

<style scoped lang="scss">
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
