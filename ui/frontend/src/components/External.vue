<template>
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
        <n-h3>周计划</n-h3>
        <table>
          <tr>
            <td class="table-space"><n-h4>周一</n-h4></td>
            <td>关卡：</td>
            <td class="table-space">
              <n-input></n-input>
            </td>
            <td>理智药：</td>
            <td>
              <n-input-number clearable></n-input-number>
            </td>
          </tr>
          <tr>
            <td class="table-space"><n-h4>周二</n-h4></td>
            <td>关卡：</td>
            <td class="table-space">
              <n-input></n-input>
            </td>
            <td>理智药：</td>
            <td>
              <n-input-number clearable></n-input-number>
            </td>
          </tr>
          <tr>
            <td class="table-space"><n-h4>周三</n-h4></td>
            <td>关卡：</td>
            <td class="table-space">
              <n-input></n-input>
            </td>
            <td>理智药：</td>
            <td>
              <n-input-number clearable></n-input-number>
            </td>
          </tr>
          <tr>
            <td class="table-space"><n-h4>周四</n-h4></td>
            <td>关卡：</td>
            <td class="table-space">
              <n-input></n-input>
            </td>
            <td>理智药：</td>
            <td>
              <n-input-number clearable></n-input-number>
            </td>
          </tr>
          <tr>
            <td class="table-space"><n-h4>周五</n-h4></td>
            <td>关卡：</td>
            <td class="table-space">
              <n-input></n-input>
            </td>
            <td>理智药：</td>
            <td>
              <n-input-number clearable></n-input-number>
            </td>
          </tr>
          <tr>
            <td class="table-space"><n-h4>周六</n-h4></td>
            <td>关卡：</td>
            <td class="table-space">
              <n-input></n-input>
            </td>
            <td>理智药：</td>
            <td>
              <n-input-number clearable></n-input-number>
            </td>
          </tr>
          <tr>
            <td class="table-space"><n-h4>周日</n-h4></td>
            <td>关卡：</td>
            <td class="table-space">
              <n-input></n-input>
            </td>
            <td>理智药：</td>
            <td>
              <n-input-number clearable></n-input-number>
            </td>
          </tr>
        </table>
      </template>
    </n-card>
  </div>
</template>

<style scoped>
h4 {
  margin: 0;
}
</style>
