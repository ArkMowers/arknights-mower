<template>
  <n-tabs type="segment" class="tabs">
    <n-tab-pane name="home" tab="主页">
      <div class="home-container">
        <table>
          <tr>
            <td>服务器：</td>
            <td>
              <n-radio value="official" name="server">官服</n-radio>
              <n-radio value="bilibili" name="server">BiliBili服</n-radio>
            </td>
            <td></td>
          </tr>
          <tr>
            <td>adb连接地址：</td>
            <td>
              <n-input></n-input>
            </td>
            <td></td>
          </tr>
          <tr>
            <td>宿舍黑名单：</td>
            <td>
              <n-input></n-input>
            </td>
            <td></td>
          </tr>
          <tr>
            <td>排班表：</td>
            <td>
              <n-input></n-input>
            </td>
            <td>
              <n-button>...</n-button>
            </td>
          </tr>
        </table>
        <n-log class="log" :log="'114514'" />
        <div>
          <n-button type="primary">开始执行</n-button>
        </div>
      </div>
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
    <n-tab-pane name="advanced" tab="高级设置"></n-tab-pane>
    <n-tab-pane name="external" tab="外部调用"></n-tab-pane>
  </n-tabs>
</template>

<script setup>
import { ref } from 'vue'

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
</script>

<style scoped>
.home-container {
  padding: 0 12px 12px;
  flex-grow: 1;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.log {
  flex-grow: 1;
  border: 1px solid rgb(224, 224, 230);
  border-radius: 3px;
  padding: 4px;
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
</style>
