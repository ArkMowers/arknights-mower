<script setup lang="jsx">
import { useConfigStore } from '@/stores/config'
import { usePlanStore } from '@/stores/plan'
import { storeToRefs } from 'pinia'
import { computed, inject } from 'vue'

import pinyinMatch from 'pinyin-match/es/traditional'

import { folder_dialog } from '@/utils/dialog'

const config_store = useConfigStore()
const plan_store = usePlanStore()

const mobile = inject('mobile')

const {
  run_mode,
  run_order_delay,
  drone_room,
  drone_count_limit,
  drone_interval,
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
  screenshot,
  run_order_grandet_mode
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

async function select_simulator_folder() {
  const folder_path = await folder_dialog()
  if (folder_path) {
    simulator.value.simulator_folder = folder_path
  }
}

function render_label(option) {
  return (
    <div style="display: flex; gap: 6px; align-items: center">
      <n-avatar src={`/avatar/${option.value}.png`} size="small" round />
      <div>{option.value}</div>
    </div>
  )
}
</script>

<template>
  <div class="home-container">
    <div class="grid-two">
      <div class="grid-left">
        <div>
          <n-card title="Mower设置">
            <n-form
              :label-placement="mobile ? 'top' : 'left'"
              :show-feedback="false"
              label-width="120"
              label-align="left"
            >
              <n-form-item label="服务器：">
                <n-radio-group v-model:value="package_type">
                  <n-space>
                    <n-radio value="official">官服</n-radio>
                    <n-radio value="bilibili">BiliBili服</n-radio>
                  </n-space>
                </n-radio-group>
              </n-form-item>
              <n-form-item>
                <template #label>
                  <span>ADB连接地址</span>
                  <help-text>
                    <div>不同模拟器adb地址不同。如不填，系统会自动去寻找adb device中的第一个。</div>
                    <div>夜神：<code>127.0.0.1:62001</code></div>
                  </help-text>
                </template>
                <n-input v-model:value="adb"></n-input>
              </n-form-item>
              <n-form-item label="模拟器">
                <n-select v-model:value="simulator.name" :options="simulator_types" />
              </n-form-item>
              <n-form-item v-if="simulator.name">
                <template #label>
                  <span>多开编号</span>
                  <help-text>
                    <div>除夜神单开选择-1以外，其他的按照改模拟器多开器中的序号。</div>
                  </help-text>
                </template>
                <n-input-number v-model:value="simulator.index"></n-input-number>
              </n-form-item>
              <n-form-item v-if="simulator.name">
                <template #label>
                  <span>模拟器文件夹</span>
                  <help-text>
                    <div>夜神：写到bin文件夹</div>
                    <div>MuMu12: 写到shell文件夹</div>
                  </help-text>
                </template>
                <n-input v-model:value="simulator.simulator_folder"></n-input>
                <n-button @click="select_simulator_folder" class="dialog-btn">...</n-button>
              </n-form-item>
              <n-form-item label="启动游戏：">
                <n-select v-model:value="tap_to_launch_game.enable" :options="launch_options" />
              </n-form-item>
              <n-form-item v-if="tap_to_launch_game.enable == 'tap'" label="点击坐标：">
                <span class="coord-label">X:</span>
                <n-input-number v-model:value="tap_to_launch_game.x" />
                <span class="coord-label">Y:</span>
                <n-input-number v-model:value="tap_to_launch_game.y" />
              </n-form-item>
              <n-form-item :show-label="false">
                <n-checkbox v-model:checked="exit_game_when_idle">
                  任务结束后退出游戏以降低功耗
                </n-checkbox>
              </n-form-item>
              <n-form-item>
                <template #label>
                  <span>运行模式</span>
                  <help-text>“仅跑单”模式年久失修，推荐使用Mower0</help-text>
                </template>
                <n-radio-group v-model:value="run_mode">
                  <n-space>
                    <n-radio value="full">换班+跑单</n-radio>
                    <n-radio value="orders_only">仅跑单</n-radio>
                  </n-space>
                </n-radio-group>
              </n-form-item>
              <n-form-item :show-label="false">
                <n-checkbox v-model:checked="start_automatically">启动后自动开始任务</n-checkbox>
              </n-form-item>
              <n-form-item label="截图数量：">
                <n-input-number v-model:value="screenshot" />
              </n-form-item>
              <n-form-item label="显示主题：">
                <n-radio-group v-model:value="theme">
                  <n-space>
                    <n-radio value="light">亮色</n-radio>
                    <n-radio value="dark">暗色</n-radio>
                  </n-space>
                </n-radio-group>
              </n-form-item>
            </n-form>
          </n-card>
        </div>
        <div>
          <n-card title="基建设置">
            <n-form
              :label-placement="mobile ? 'top' : 'left'"
              :show-feedback="false"
              label-width="140"
              label-align="left"
            >
              <n-form-item>
                <template #label>
                  <span>宿舍黑名单</span>
                  <help-text>
                    <div>不希望进行填充宿舍的干员</div>
                  </help-text>
                </template>
                <n-transfer
                  v-if="mobile"
                  virtual-scroll
                  source-filterable
                  target-filterable
                  :options="operators"
                  v-model:value="free_blacklist"
                  :render-source-label="(o) => render_label(o.option)"
                  :render-target-label="(o) => render_label(o.option)"
                  :filter="(p, o) => (p ? pinyinMatch.match(o.label, p) : true)"
                />
                <n-select
                  v-else
                  multiple
                  filterable
                  tag
                  :options="operators"
                  :render-label="render_label"
                  v-model:value="free_blacklist"
                />
              </n-form-item>
              <n-form-item>
                <template #label>
                  <span>跑单前置延时</span>
                  <help-text>
                    <div>推荐范围5-10</div>
                    <div>可填小数</div>
                    <div>单位：分钟</div>
                  </help-text>
                </template>
                <n-input-number v-model:value="run_order_delay" />
              </n-form-item>
              <n-form-item :show-label="false">
                <n-checkbox v-model:checked="run_order_grandet_mode.enable">葛朗台跑单</n-checkbox>
              </n-form-item>
              <n-form-item v-if="run_order_grandet_mode.enable">
                <template #label>
                  <span>葛朗台缓冲时间</span>
                  <help-text>
                    <div>推荐范围：15-30</div>
                    <div>单位：秒</div>
                  </help-text>
                </template>
                <n-input-number v-model:value="run_order_grandet_mode.buffer_time" />
              </n-form-item>
              <n-form-item>
                <template #label>
                  <span>无人机使用房间</span>
                  <help-text>
                    <div>加速制造站为指定制造站加速</div>
                    <div>加速贸易站请选“（加速贸易站）”</div>
                    <div>（加速贸易站）只会加速有跑单人员作备班的站</div>
                    <div>例：没填龙舌兰但书的卖玉站 （加速贸易站） 不会被加速</div>
                  </help-text>
                </template>
                <n-select :options="facility_with_empty" v-model:value="drone_room" />
              </n-form-item>
              <n-form-item>
                <template #label>
                  <span>无人机使用阈值</span>
                  <help-text>
                    <div>如加速贸易，推荐大于 贸易站数 x 10 + 92</div>
                    <div>如加速制造，推荐大于 贸易站数 x 10</div>
                  </help-text>
                </template>
                <n-input-number v-model:value="drone_count_limit" />
              </n-form-item>
              <n-form-item>
                <template #label>
                  <span>无人机加速间隔</span>
                  <help-text>
                    <div>单位：小时</div>
                    <div>可填小数</div>
                  </help-text>
                </template>
                <n-input-number v-model:value="drone_interval" />
              </n-form-item>
              <n-form-item label="搓玉补货房间：">
                <n-select
                  multiple
                  filterable
                  tag
                  :options="left_side_facility"
                  v-model:value="reload_room"
                />
              </n-form-item>
              <n-form-item>
                <template #label>
                  <span>心情阈值：</span>
                  <help-text>
                    <div>2电站推荐不低于0.75</div>
                    <div>3电站推荐不低于0.5</div>
                    <div>即将大更新推荐设置成0.8</div>
                  </help-text>
                </template>
                <div class="threshold">
                  <n-slider v-model:value="resting_threshold" :step="0.05" :min="0.5" :max="0.8" />
                  <n-input-number
                    v-model:value="resting_threshold"
                    :step="0.05"
                    :min="0.5"
                    :max="0.8"
                  />
                </div>
              </n-form-item>
            </n-form>
          </n-card>
        </div>
        <div><maa-basic /></div>
        <div><SKLand /></div>
        <div><email /></div>
      </div>

      <div class="grid-right">
        <div><clue /></div>

        <div><Recruit /></div>
        <div><maa-weekly /></div>
        <!--div><maa-weekly-new /></div-->
        <div><maa-long-tasks /></div>
      </div>
    </div>
  </div>
</template>

<style scoped lang="scss">
.threshold {
  display: flex;
  align-items: center;
  gap: 14px;
  width: 100%;
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

.coord-label {
  width: 40px;
  padding-left: 8px;
}

p {
  margin: 0 0 8px 0;
}

h4 {
  margin: 12px 0 10px 0;
}

ul {
  padding-left: 24px;
  margin: 0 0 10px 0;
}

.time-table {
  width: 100%;
  margin-bottom: 12px;

  td:nth-child(1) {
    width: 40px;
  }
}
</style>

<style>
/*小于1400的内容！*/
@media (max-width: 1399px) {
  .grid-two {
    margin: 0 0 -10px 0;
  }
  .grid-left {
    display: grid;
    row-gap: 10px;
    grid-template-columns: 100%;
    max-width: 600px;
  }
  .grid-right {
    display: grid;
    row-gap: 10px;
    grid-template-columns: 100%;
    max-width: 600px;
  }
}
/*双栏 大于1400的内容 */
@media (min-width: 1400px) {
  .grid-two {
    display: grid;
    grid-template-columns: minmax(0px, 1fr) minmax(0px, 1fr);
    align-items: flex-start;
  }
  .grid-left {
    display: grid;
    gap: 5px;
    grid-template-columns: 100%;
    max-width: 600px;
  }
  .grid-right {
    display: grid;
    gap: 5px;
    grid-template-columns: 100%;
    max-width: 600px;
  }
}

.n-divider:not(.n-divider--vertical) {
  margin: 14px 0 8px;
}
</style>
