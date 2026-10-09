<script setup>
import { ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { useConfigStore } from '@/stores/config'

const { theme } = storeToRefs(useConfigStore())
const guideFrame = ref(null)
const docSrc = `/docs/Mower入门指北.html?theme=${theme.value === 'dark' ? 'dark' : 'light'}`

function syncTheme() {
  guideFrame.value?.contentWindow?.postMessage(
    { type: 'mower-doc-theme', theme: theme.value === 'dark' ? 'dark' : 'light' },
    window.location.origin
  )
}

watch(theme, syncTheme)
</script>

<template>
  <div class="link-container">
    <strong>本地一条龙入门说明</strong>
    <n-a
      href="https://docs.qq.com/sheet/DUEJ6UWN5VFVRU0dG?tab=BB08J2"
      target="_blank"
      rel="noopener noreferrer"
    >
      Mower 反馈表
    </n-a>
    在线文档地址：
    <n-a href="https://arkmowers.github.io/arknights-mower/" target="_blank">
      https://arkmowers.github.io/arknights-mower/
    </n-a>
  </div>
  <iframe
    ref="guideFrame"
    title="Mower 一条龙入门说明"
    :src="docSrc"
    @load="syncTheme"
    sandbox="allow-popups allow-popups-to-escape-sandbox allow-scripts allow-same-origin allow-forms"
    style="width: 100%; height: 100vh; border: none"
  />
</template>

<style scoped>
.link-container {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 16px;
  width: 100%;
  padding: 6px 12px 0;
  box-sizing: border-box;
}
</style>
