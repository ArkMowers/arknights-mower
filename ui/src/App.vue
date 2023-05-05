<template>
  <n-tabs type="segment" class="tabs">
    <n-tab-pane name="home" tab="主页">
      <div class="container">
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
    <n-tab-pane name="plan" tab="排班表"></n-tab-pane>
    <n-tab-pane name="advanced" tab="高级设置"></n-tab-pane>
    <n-tab-pane name="external" tab="外部调用"></n-tab-pane>
  </n-tabs>
</template>

<script setup></script>

<style scoped>
.container {
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
</style>

<style>
#app {
  height: 100vh;
}

.n-tab-pane {
  flex-grow: 1;
  display: flex;
  flex-direction: column;
}
</style>
