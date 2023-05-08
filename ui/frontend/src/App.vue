<template>
  <n-tabs type="segment" class="tabs">
    <n-tab-pane name="home" tab="主页">
      <home />
    </n-tab-pane>
    <n-tab-pane name="plan" tab="排班表">
      <div class="plan-container">
        <n-space justify="center">
          <table>
            <tr>
              <td></td>
              <td></td>
              <td></td>
              <td><n-button secondary class="w90">控制中枢</n-button></td>
              <td></td>
            </tr>
            <tr>
              <td><n-button secondary type="info">贸易站</n-button></td>
              <td><n-button secondary type="info">贸易站</n-button></td>
              <td><n-button secondary type="primary">发电站</n-button></td>
              <td><n-button secondary class="w90">宿舍</n-button></td>
              <td><n-button secondary>会客室</n-button></td>
            </tr>
            <tr>
              <td><n-button secondary type="warning">制造站</n-button></td>
              <td><n-button secondary type="warning">制造站</n-button></td>
              <td><n-button secondary type="primary">发电站</n-button></td>
              <td><n-button secondary class="w90">宿舍</n-button></td>
              <td><n-button secondary>加工室</n-button></td>
            </tr>
            <tr>
              <td><n-button secondary type="warning">制造站</n-button></td>
              <td><n-button secondary type="warning">制造站</n-button></td>
              <td><n-button secondary type="warning">制造站</n-button></td>
              <td><n-button secondary class="w90">宿舍</n-button></td>
              <td><n-button secondary>办公室</n-button></td>
            </tr>
            <tr>
              <td></td>
              <td></td>
              <td></td>
              <td><n-button secondary class="w90">宿舍</n-button></td>
              <td></td>
            </tr>
          </table>
        </n-space>
        <n-space justify="center">
          <table>
            <tr>
              <td>设施类别：</td>
              <td>
                <n-select
                  v-model:value="facility_type"
                  :options="facility_types"
                  class="type-select"
                />
              </td>
            </tr>
          </table>
        </n-space>
        <n-space justify="center">
          <table>
            <tr>
              <td>干员：</td>
              <td class="table-space">
                <n-select multiple filterable tag :options="operators" class="operator-select" />
              </td>
              <td>组：</td>
              <td class="table-space">
                <n-input></n-input>
              </td>
              <td>替换：</td>
              <td>
                <n-select multiple filterable tag :options="operators" class="replacement-select" />
              </td>
            </tr>
            <tr>
              <td>干员：</td>
              <td class="table-space">
                <n-select multiple filterable tag :options="operators" class="operator-select" />
              </td>
              <td>组：</td>
              <td class="table-space">
                <n-input></n-input>
              </td>
              <td>替换：</td>
              <td>
                <n-select multiple filterable tag :options="operators" class="replacement-select" />
              </td>
            </tr>
            <tr>
              <td>干员：</td>
              <td class="table-space">
                <n-select multiple filterable tag :options="operators" class="operator-select" />
              </td>
              <td>组：</td>
              <td class="table-space">
                <n-input></n-input>
              </td>
              <td>替换：</td>
              <td>
                <n-select multiple filterable tag :options="operators" class="replacement-select" />
              </td>
            </tr>
          </table>
        </n-space>
        <n-space justify="center">
          <n-button type="primary">保存</n-button>
          <n-button type="error">清空</n-button>
        </n-space>
      </div>
    </n-tab-pane>
    <n-tab-pane name="advanced" tab="高级设置">
      <div class="home-container">
        <n-space justify="center">
          <table>
            <tr>
              <td>运行模式：</td>
              <td colspan="3">
                <n-space>
                  <n-radio value="full" name="mode">换班模式</n-radio>
                  <n-radio value="orders_only" name="mode">仅跑单模式</n-radio>
                </n-space>
              </td>
              <td></td>
              <td></td>
            </tr>
            <tr>
              <td>令夕模式（令夕上班时起作用）：</td>
              <td colspan="3">
                <n-space>
                  <n-radio value="感知信息" name="令夕">感知信息</n-radio>
                  <n-radio value="人间烟火" name="令夕">人间烟火</n-radio>
                  <n-radio value="balanced" name="令夕">均衡模式</n-radio>
                </n-space>
              </td>
              <td></td>
              <td></td>
            </tr>
            <tr>
              <td>线索收集：</td>
              <td colspan="3">
                <n-space>
                  <n-radio value="enabled" name="clue">启用</n-radio>
                  <n-radio value="disabled" name="clue">禁用</n-radio>
                </n-space>
              </td>
              <td></td>
              <td></td>
            </tr>
            <tr>
              <td>最大组人数：</td>
              <td class="table-space">
                <n-input></n-input>
              </td>
              <td>跑单前置延时（分钟）：</td>
              <td>
                <n-input></n-input>
              </td>
            </tr>
            <tr>
              <td>无人机使用房间（room_X_X）：</td>
              <td class="table-space">
                <n-input></n-input>
              </td>
              <td>无人机使用阈值：</td>
              <td>
                <n-input></n-input>
              </td>
            </tr>
            <tr>
              <td>搓玉补货房间（逗号分隔房间名）：</td>
              <td colspan="3">
                <n-input></n-input>
              </td>
              <td></td>
              <td></td>
            </tr>
            <tr>
              <td>需要回满心情的干员：</td>
              <td colspan="3">
                <n-select multiple filterable tag :options="operators" />
              </td>
              <td></td>
              <td></td>
            </tr>
            <tr>
              <td>需要用尽心情的干员：</td>
              <td colspan="3">
                <n-select multiple filterable tag :options="operators" />
              </td>
              <td></td>
              <td></td>
            </tr>
            <tr>
              <td>宿舍低优先级干员：</td>
              <td colspan="3">
                <n-select multiple filterable tag :options="operators" />
              </td>
              <td></td>
              <td></td>
            </tr>
          </table>
        </n-space>
      </div>
    </n-tab-pane>
    <n-tab-pane name="external" tab="外部调用">
      <div class="home-container">
        <n-card>
          <template #header>
            <n-checkbox></n-checkbox>
            邮件提醒
          </template>
          <template #default>
            <table>
              <tr>
                <td class="table-space">QQ邮箱</td>
                <td class="table-space"><n-input></n-input></td>
                <td class="table-space">授权码</td>
                <td><n-input></n-input></td>
              </tr>
            </table>
          </template>
        </n-card>
        <n-card>
          <template #header>
            <n-checkbox></n-checkbox>
            MAA
          </template>
          <template #default>
            <table>
              <tr>
                <td class="table-space">MAA地址</td>
                <td class="table-space"><n-input></n-input></td>
                <td class="table-space">adb地址</td>
                <td><n-input></n-input></td>
              </tr>
            </table>
            <n-h4>周计划</n-h4>
            <table>
              <tr>
                <td class="table-space">周一</td>
                <td>关卡：</td>
                <td class="table-space">
                  <n-input></n-input>
                </td>
                <td>理智药</td>
                <td>
                  <n-input-number clearable></n-input-number>
                </td>
              </tr>
              <tr>
                <td class="table-space">周二</td>
                <td>关卡：</td>
                <td class="table-space">
                  <n-input></n-input>
                </td>
                <td>理智药</td>
                <td>
                  <n-input-number clearable></n-input-number>
                </td>
              </tr>
              <tr>
                <td class="table-space">周三</td>
                <td>关卡：</td>
                <td class="table-space">
                  <n-input></n-input>
                </td>
                <td>理智药</td>
                <td>
                  <n-input-number clearable></n-input-number>
                </td>
              </tr>
              <tr>
                <td class="table-space">周四</td>
                <td>关卡：</td>
                <td class="table-space">
                  <n-input></n-input>
                </td>
                <td>理智药</td>
                <td>
                  <n-input-number clearable></n-input-number>
                </td>
              </tr>
              <tr>
                <td class="table-space">周五</td>
                <td>关卡：</td>
                <td class="table-space">
                  <n-input></n-input>
                </td>
                <td>理智药</td>
                <td>
                  <n-input-number clearable></n-input-number>
                </td>
              </tr>
              <tr>
                <td class="table-space">周六</td>
                <td>关卡：</td>
                <td class="table-space">
                  <n-input></n-input>
                </td>
                <td>理智药</td>
                <td>
                  <n-input-number clearable></n-input-number>
                </td>
              </tr>
              <tr>
                <td class="table-space">周日</td>
                <td>关卡：</td>
                <td class="table-space">
                  <n-input></n-input>
                </td>
                <td>理智药</td>
                <td>
                  <n-input-number clearable></n-input-number>
                </td>
              </tr>
            </table>
          </template>
        </n-card>
      </div>
    </n-tab-pane>
  </n-tabs>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import home from '@/components/Home.vue'
import { useConfigStore } from '@/stores/config'

const store = useConfigStore()
const { load_config } = store

const facility_types = [
  { label: '贸易站', value: 'trading_post' },
  { label: '制造站', value: 'factory' },
  { label: '发电站', value: 'power_plant' }
]

const operators = [
  { label: '孑', value: 'Jaye' },
  { label: '拉普兰德', value: 'Lappland' },
  { label: '德克萨斯', value: 'Texas' },
  { label: '泰拉大陆调查团', value: 'TerraResearchCommission' },
  { label: '但书', value: 'Proviso' },
  { label: '龙舌兰', value: 'Tequila' }
]

const facility_type = ref('trading_post')

onMounted(() => {
  load_config()
})
</script>

<style scoped>
.home-container {
  padding: 0 12px 12px;
  flex-grow: 1;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.tabs {
  height: 100%;
}

.w90 {
  width: 90px;
}

.type-select {
  width: 100px;
}

.operator-select {
  width: 380px;
}

.replacement-select {
  width: 200px;
}

.plan-container {
  min-width: 980px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.table-space {
  padding-right: 20px;
}

td {
  height: 34px;
}
</style>

<style>
#app {
  height: 100vh;
}

.n-tab-pane {
  flex-grow: 1;
  display: flex;
  flex-direction: column;
  overflow: scroll;
}

.n-card-header__main {
  display: flex;
  align-items: center;
  gap: 6px;
}
</style>
