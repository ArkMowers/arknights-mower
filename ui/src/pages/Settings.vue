<script setup lang="jsx">
import { useConfigStore } from '@/stores/config'
import { usePlanStore } from '@/stores/plan'
import { storeToRefs } from 'pinia'
import { computed, inject } from 'vue'

import { pinyin_match } from '@/utils/common'

import { folder_dialog } from '@/utils/dialog'

const config_store = useConfigStore()
const plan_store = usePlanStore()

const mobile = inject('mobile')

const {
  run_order_delay,
  drone_room,
  drone_count_limit,
  drone_interval,
  reload_room,
  start_automatically,
  adb,
  package_type,
  simulator,
  theme,
  resting_threshold,
  fia_threshold,
  rescue_threshold,
  tap_to_launch_game,
  exit_game_when_idle,
  close_simulator_when_idle,
  screenshot,
  screenshot_interval,
  run_order_grandet_mode,
  webview,
  fix_mumu12_adb_disconnect,
  touch_method,
  free_room,
  merge_interval,
  fia_fool,
  droidcast,
  maa_adb_path,
  maa_gap,
  custom_screenshot,
  check_for_updates,
  waiting_scene
} = storeToRefs(config_store)

const { operators } = storeToRefs(plan_store)

const { left_side_facility } = plan_store

const facility_with_empty = computed(() => {
  return [{ label: '（加速任意贸易站）', value: '' }].concat(left_side_facility)
})

const simulator_types = [
  { label: '夜神', value: '夜神' },
  { label: 'MuMu模拟器12', value: 'MuMu12' },
  { label: 'Waydroid', value: 'Waydroid' },
  { label: '雷电模拟器9', value: '雷电9' },
  { label: 'ReDroid', value: 'ReDroid' },
  { label: 'MuMu模拟器Pro', value: 'MuMuPro' },
  { label: 'Genymotion', value: 'Genymotion' },
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

import { render_op_label } from '@/utils/op_select'

const scale_marks = {}
const display_marks = [0.5, 1.0, 1.5, 2.0, 3.0]
for (let i = 0.5; i <= 3.0; i += 0.25) {
  scale_marks[i] = display_marks.includes(i) ? `${i * 100}%` : ''
}

const new_scale = ref(webview.value.scale)

import { file_dialog } from '@/utils/dialog'

async function select_maa_adb_path() {
  const file_path = await file_dialog()
  if (file_path) {
    maa_adb_path.value = file_path
  }
}

const screenshot_method = computed({
  get() {
    let result = 'adb_gzip'
    if (droidcast.value.enable) {
      result = 'droidcast'
    } else if (custom_screenshot.value.enable) {
      result = 'custom'
    }
    return result
  },
  set(value) {
    droidcast.value.enable = false
    custom_screenshot.value.enable = false
    if (value == 'droidcast') {
      droidcast.value.enable = true
    } else if (value == 'custom') {
      custom_screenshot.value.enable = true
    }
  }
})

const tested = ref(false)
const image = ref('')
const elapsed = ref(0)
const loading = ref(false)
const axios = inject('axios')

async function test_screenshot() {
  loading.value = true
  tested.value = false
  try {
    const response = await axios.get(`${import.meta.env.VITE_HTTP_URL}/test-custom-screenshot`)
    image.value = response.data.screenshot
    elapsed.value = response.data.elapsed
  } finally {
    loading.value = false
    tested.value = true
  }
}

const scene_name = {
  CONNECTING: '正在提交反馈至神经',
  UNKNOWN: '未知',
  LOADING: '加载中',
  LOGIN_LOADING: '场景跳转时的等待界面',
  LOGIN_MAIN_NOENTRY: '登录页面（无按钮入口）',
  OPERATOR_ONGOING: '代理作战'
}

const onSelectionChange = (newValue) => {
  if (newValue === '夜神') {
    simulator.value.index = '-1'
  } else {
    simulator.value.index = '0'
  }
}
</script>

<template>
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
            <n-form-item label="服务器">
              <n-radio-group v-model:value="package_type">
                <n-space>
                  <n-radio value="official">官服</n-radio>
                  <n-radio value="bilibili">BiliBili服</n-radio>
                </n-space>
              </n-radio-group>
            </n-form-item>
            <n-form-item label="ADB路径">
              <n-input type="textarea" :autosize="true" v-model:value="maa_adb_path" />
              <n-button @click="select_maa_adb_path" class="dialog-btn">...</n-button>
            </n-form-item>
            <n-form-item>
              <template #label>
                <span>ADB连接地址</span>
                <help-text>
                  <div>不同模拟器adb地址不同。如不填，系统会自动去寻找adb device中的第一个。</div>
                  <div>夜神：<code>127.0.0.1:62001</code></div>
                </help-text>
              </template>
              <n-input v-model:value="adb" />
            </n-form-item>
            <n-form-item label="触控方案">
              <n-radio-group v-model:value="touch_method">
                <n-space>
                  <n-radio value="scrcpy">scrcpy-1.21-novideo</n-radio>
                  <n-radio value="maatouch">MaaTouch-1.1.0</n-radio>
                </n-space>
              </n-radio-group>
            </n-form-item>
            <n-form-item label="模拟器">
              <n-select
                v-model:value="simulator.name"
                :options="simulator_types"
                @update:value="onSelectionChange"
              />
            </n-form-item>
            <n-form-item v-if="simulator.name">
              <template #label>
                <span>模拟器文件夹</span>
                <help-text>
                  <div>夜神：写到bin文件夹</div>
                  <div>MuMu12: 写到shell文件夹</div>
                </help-text>
              </template>
              <n-input
                v-model:value="simulator.simulator_folder"
                type="textarea"
                :autosize="true"
              />
              <n-button @click="select_simulator_folder" class="dialog-btn">...</n-button>
            </n-form-item>
            <n-form-item v-if="simulator.name">
              <template #label>
                <span>多开编号</span>
                <help-text>
                  <div>除夜神单开选择-1以外，其他的按照改模拟器多开器中的序号。</div>
                </help-text>
              </template>
              <n-input v-model:value="simulator.index" />
            </n-form-item>
            <n-form-item label="模拟器启动时间" v-if="simulator.name">
              <n-input-number v-model:value="simulator.wait_time">
                <template #suffix>秒</template>
              </n-input-number>
            </n-form-item>
            <n-form-item v-if="simulator.name">
              <template #label>
                <span>模拟器老板键</span>
                <help-text>
                  <div>启动模拟器后按此快捷键</div>
                  <div>若不需要此功能，请留空</div>
                  <div>加号分隔按键，不要空格</div>
                  <div>
                    按键名参考
                    <n-button
                      text
                      tag="a"
                      href="https://pyautogui.readthedocs.io/en/latest/keyboard.html#keyboard-keys"
                      target="_blank"
                      type="primary"
                    >
                      KEYBOARD_KEYS
                    </n-button>
                  </div>
                </help-text>
              </template>
              <n-input
                v-model:value="simulator.hotkey"
                placeholder="输入模拟器的老板键，组合键用分号隔开，或留空以停用"
              />
            </n-form-item>
            <n-form-item label="启动游戏">
              <n-select v-model:value="tap_to_launch_game.enable" :options="launch_options" />
            </n-form-item>
            <n-form-item v-if="tap_to_launch_game.enable == 'tap'" label="点击坐标">
              <span class="coord-label">X:</span>
              <n-input-number v-model:value="tap_to_launch_game.x" />
              <span class="coord-label">Y:</span>
              <n-input-number v-model:value="tap_to_launch_game.y" />
            </n-form-item>
            <n-form-item :show-label="false">
              <n-checkbox
                v-model:checked="exit_game_when_idle"
                :disabled="simulator.name != '' && close_simulator_when_idle"
              >
                任务结束后退出游戏
                <help-text>降低功耗</help-text>
              </n-checkbox>
            </n-form-item>
            <n-form-item :show-label="false" v-if="simulator.name">
              <n-checkbox v-model:checked="close_simulator_when_idle">
                任务结束后关闭模拟器
                <help-text>减少空闲时的资源占用、避免模拟器长时间运行出现问题</help-text>
              </n-checkbox>
            </n-form-item>
            <n-form-item
              :show-label="false"
              v-if="simulator.name == 'MuMu12' && close_simulator_when_idle"
            >
              <n-checkbox v-model:checked="fix_mumu12_adb_disconnect">
                关闭MuMu模拟器12时结束adb进程
                <help-text>
                  <div>运行命令<code>taskkill /f /t /im adb.exe</code></div>
                  <div>使用MuMu模拟器12时，若遇到adb断连问题，可尝试开启此选项</div>
                </help-text>
              </n-checkbox>
            </n-form-item>
            <n-form-item :show-label="false">
              <n-checkbox v-model:checked="start_automatically">启动后自动开始任务</n-checkbox>
            </n-form-item>
            <n-form-item :show-label="false">
              <n-checkbox v-model:checked="check_for_updates">检查版本更新</n-checkbox>
            </n-form-item>
            <n-form-item label="截图方案">
              <n-radio-group v-model:value="screenshot_method">
                <n-flex>
                  <n-radio value="adb_gzip">
                    ADB+Gzip<help-text>无损压缩，兼容性好</help-text>
                  </n-radio>
                  <n-radio value="droidcast">
                    DroidCast<help-text>有损压缩，速度更快</help-text>
                  </n-radio>
                  <n-radio value="custom">
                    自定义命令<help-text>向<code>STDOUT</code>打印图像</help-text>
                  </n-radio>
                </n-flex>
              </n-radio-group>
            </n-form-item>
            <n-form-item label="旋转截图" v-if="droidcast.enable">
              <n-radio-group v-model:value="droidcast.rotate">
                <n-flex>
                  <n-radio :value="false">不旋转</n-radio>
                  <n-radio :value="true">旋转180度</n-radio>
                </n-flex>
              </n-radio-group>
            </n-form-item>
            <n-form-item label="截图命令" v-if="custom_screenshot.enable">
              <n-input v-model:value="custom_screenshot.command" type="textarea" :autosize="true" />
              <n-button class="dialog-btn" @click="test_screenshot" :loading="loading">
                测试
              </n-button>
            </n-form-item>
            <n-form-item v-if="custom_screenshot.enable && tested" :show-label="false">
              <n-flex vertical>
                <n-image :src="'data:image/jpeg;base64,' + image" width="100%" />
                <div>（截图用时{{ elapsed }}ms）</div>
              </n-flex>
            </n-form-item>
            <n-form-item label="截图最短间隔">
              <n-input-number v-model:value="screenshot_interval" :precision="0">
                <template #suffix>毫秒</template>
              </n-input-number>
            </n-form-item>
            <n-form-item>
              <template #label>
                <span>截图保存时间</span>
                <help-text>可填小数</help-text>
              </template>
              <n-input-number v-model:value="screenshot">
                <template #suffix>小时</template>
              </n-input-number>
            </n-form-item>
            <n-form-item label="等待时间">
              <n-table size="small" class="waiting-table">
                <thead>
                  <tr>
                    <th>场景</th>
                    <th>截图间隔</th>
                    <th>等待次数</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(value, key) in waiting_scene">
                    <td>{{ scene_name[key] }}</td>
                    <td>
                      <n-input-number v-model:value="value[0]" :show-button="false" :precision="0">
                        <template #suffix>秒</template>
                      </n-input-number>
                    </td>
                    <td>
                      <n-input-number v-model:value="value[1]" :show-button="false" :precision="0">
                        <template #suffix>次</template>
                      </n-input-number>
                    </td>
                  </tr>
                </tbody>
              </n-table>
              <!-- {{ waiting_scene }} -->
            </n-form-item>
            <n-form-item label="界面缩放">
              <n-slider
                v-model:value="new_scale"
                :step="0.25"
                :min="0.5"
                :max="3.0"
                :marks="scale_marks"
                :format-tooltip="(x) => `${x * 100}%`"
              />
              <n-button
                class="scale-apply"
                :disabled="new_scale == webview.scale"
                @click="webview.scale = new_scale"
              >
                应用
              </n-button>
            </n-form-item>
            <n-form-item :show-label="false">
              <n-checkbox v-model:checked="webview.tray">
                使用托盘图标
                <help-text>重启生效</help-text>
              </n-checkbox>
            </n-form-item>
            <n-form-item label="显示主题">
              <n-radio-group v-model:value="theme">
                <n-space>
                  <n-radio value="light">亮色</n-radio>
                  <n-radio value="dark">暗色</n-radio>
                </n-space>
              </n-radio-group>
            </n-form-item>
            <n-form-item>
              <template #label>
                <span>日常任务间隔</span>
                <help-text>
                  <div>可填小数</div>
                  <div>清理智、日常/周常任务领取、借助战打OF-1</div>
                </help-text>
              </template>
              <n-input-number v-model:value="maa_gap">
                <template #suffix>小时</template>
              </n-input-number>
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
                <span>跑单前置延时</span>
                <help-text>
                  <div>推荐范围5-10</div>
                  <div>可填小数</div>
                </help-text>
              </template>
              <n-input-number v-model:value="run_order_delay">
                <template #suffix>分钟</template>
              </n-input-number>
            </n-form-item>
            <n-form-item :show-label="false">
              <n-checkbox v-model:checked="run_order_grandet_mode.enable">葛朗台跑单</n-checkbox>
            </n-form-item>
            <n-form-item v-if="run_order_grandet_mode.enable">
              <template #label>
                <span>葛朗台缓冲时间</span>
                <help-text>推荐范围：15-30</help-text>
              </template>
              <n-input-number v-model:value="run_order_grandet_mode.buffer_time">
                <template #suffix>秒</template>
              </n-input-number>
            </n-form-item>
            <n-form-item v-if="run_order_grandet_mode.enable" :show-label="false">
              <n-checkbox v-model:checked="run_order_grandet_mode.back_to_index">
                跑单前返回主界面以保持登录状态
              </n-checkbox>
            </n-form-item>
            <n-form-item>
              <template #label>
                <span>无人机使用房间</span>
                <help-text>
                  <div>加速制造站为指定制造站加速</div>
                  <div>（加速任意贸易站）只会加速有跑单人员作备班的站</div>
                  <div>例：没填龙舌兰但书的卖玉站 （加速任意贸易站） 不会被加速</div>
                  <div>如需要加速特定某个贸易站请指定对应房间</div>
                </help-text>
              </template>
              <n-select :options="facility_with_empty" v-model:value="drone_room" />
            </n-form-item>
            <n-form-item>
              <template #label>
                <span>无人机使用阈值</span>
                <help-text>
                  <div>如加速贸易，推荐大于 贸易站数*10 + 92</div>
                  <div>如加速制造，推荐大于 贸易站数*10</div>
                </help-text>
              </template>
              <n-input-number v-model:value="drone_count_limit" />
            </n-form-item>
            <n-form-item>
              <template #label>
                <span>无人机加速间隔</span>
                <help-text>
                  <div>可填小数</div>
                </help-text>
              </template>
              <n-input-number v-model:value="drone_interval">
                <template #suffix>小时</template>
              </n-input-number>
            </n-form-item>
            <n-form-item label="搓玉补货房间">
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
                <span>心情阈值</span>
                <help-text>
                  <div>2电站推荐不低于65%</div>
                  <div>3电站推荐不低于50%</div>
                  <div>即将大更新推荐设置成80%</div>
                </help-text>
              </template>
              <div class="threshold">
                <n-slider
                  v-model:value="resting_threshold"
                  :step="5"
                  :min="50"
                  :max="80"
                  :format-tooltip="(v) => `${v}%`"
                />
                <n-input-number v-model:value="resting_threshold" :step="5" :min="50" :max="80">
                  <template #suffix>%</template>
                </n-input-number>
              </div>
            </n-form-item>
            <n-form-item :show-label="false">
              <n-checkbox v-model:checked="free_room">
                宿舍不养闲人
                <help-text>干员心情回满后，立即释放宿舍空位</help-text>
              </n-checkbox>
            </n-form-item>
            <n-form-item v-if="free_room">
              <template #label>
                <span>任务合并间隔</span>
                <help-text>
                  <div>可填小数</div>
                  <div>将不养闲人任务合并至下一个指定间隔内的任务</div>
                </help-text>
              </template>
              <n-input-number v-model:value="merge_interval">
                <template #suffix>分钟</template>
              </n-input-number>
            </n-form-item>
            <n-form-item :show-label="false">
              <n-checkbox v-model:checked="fia_fool">
                菲亚防呆
                <help-text>沿用默认逻辑，不确定菲亚替换心情消耗请启用本选项</help-text>
              </n-checkbox>
            </n-form-item>
            <n-form-item>
              <template #label>
                <span>菲亚阈值</span>
                <help-text>
                  <div>开启防呆设计时，菲亚只充心情在90%以下的干员，且此处设置无效</div>
                  <div>
                    不开启防呆设计时，菲亚优先充心情在该阈值以下的干员，若心情均高于该阈值则充心情最低者
                  </div>
                </help-text>
              </template>
              <div class="threshold">
                <n-slider
                  v-model:value="fia_threshold"
                  :step="5"
                  :min="50"
                  :max="90"
                  :format-tooltip="(v) => `${v}%`"
                />
                <n-input-number v-model:value="fia_threshold" :step="5" :min="50" :max="90">
                  <template #suffix>%</template>
                </n-input-number>
              </div>
            </n-form-item>
            <n-form-item>
              <template #label>
                <span>急救阈值</span>
                <help-text>
                  <div>整体心情低于换班阈值乘急救阈值后，将忽视高优人数安排休息任务。</div>
                </help-text>
              </template>
              <div class="threshold">
                <n-slider
                  v-model:value="rescue_threshold"
                  :step="5"
                  :min="0"
                  :max="90"
                  :format-tooltip="(v) => `${v}%`"
                />
                <n-input-number v-model:value="rescue_threshold" :step="5" :min="0" :max="90">
                  <template #suffix>%</template>
                </n-input-number>
              </div>
            </n-form-item>
          </n-form>
        </n-card>
      </div>
      <div>
        <SKLand />
      </div>
      <div>
        <Depotswitch />
      </div>
      <div>
        <DailyMission />
      </div>
      <div>
        <email />
      </div>
    </div>

    <div class="grid-right">
      <div>
        <clue />
      </div>
      <div>
        <Recruit />
      </div>
      <div><maa-weekly /></div>
      <div><maa-weekly-new /></div>
      <div><maa-basic /></div>
      <div><long-tasks /></div>
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

.time-table {
  width: 100%;
  margin-bottom: 12px;

  td:nth-child(1) {
    width: 40px;
  }
}

.scale {
  width: 60px;
  text-align: right;
}

.scale-apply {
  margin-left: 24px;
}

.waiting-table {
  th,
  td {
    padding: 4px;
    min-width: 70px;
    width: 100px;

    &:first-child {
      width: auto;
      padding: 4px 8px;
    }
  }
}
</style>

<style>
/*小于1400的内容！*/
@media (max-width: 1399px) {
  .grid-two {
    margin: 0 0 -10px 0;
    width: 100%;
    max-width: 600px;
  }

  .grid-left {
    display: grid;
    row-gap: 10px;
    grid-template-columns: 100%;
  }

  .grid-right {
    display: grid;
    row-gap: 10px;
    grid-template-columns: 100%;
    margin-top: 10px;
  }
}

/*双栏 大于1400的内容 */
@media (min-width: 1400px) {
  .grid-two {
    display: grid;
    grid-template-columns: minmax(0px, 1fr) minmax(0px, 1fr);
    align-items: flex-start;
    gap: 5px;
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

/* .results {
  display: grid;
  grid-template-rows: masonry;
  grid-template-columns: repeat(2, 600px);
  gap: 10px 10px ;
  justify-content: center;
} */
/* 实验性瀑布流（firefox nightly） */
</style>
