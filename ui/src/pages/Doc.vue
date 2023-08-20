<script setup>
const doc_url = 'https://arkmowers.github.io/arknights-mower/'
</script>

<template>
  <div class="intro">
    在线文档地址：<n-button text tag="a" :href="doc_url" target="_blank" type="primary">
      {{ doc_url }}
    </n-button>
  </div>
  <iframe :src="doc_url"></iframe>
</template>

<style scoped>
iframe {
  margin: 0 8px 8px;
  flex-grow: 1;
  border: none;
}

.intro {
  margin: 0 16px 12px;
}
</style>
