<template>
  <div class="link-container">
    在线文档地址：
    <n-a href="https://arkmowers.github.io/arknights-mower/" target="_blank">
      https://arkmowers.github.io/arknights-mower/
    </n-a>
  </div>
  <div>
    本地帮助文档已知问题<help-text>
      <div>本地部分页面跳转可能失效，如果出现404找不到，请尝试重新切换</div>
      <div>本地搜索关键字功能好像失效</div>
    </help-text>
  </div>
  <iframe
    src="/docs/arknights-mower/index.html"
    sandbox="allow-popups allow-scripts allow-same-origin allow-forms"
    style="width: 100%; height: 100vh; border: none"
  />
</template>

<style scoped>
.link-container {
  width: 100%;
  padding: 6px 12px 0;
  box-sizing: border-box;
}
</style>
