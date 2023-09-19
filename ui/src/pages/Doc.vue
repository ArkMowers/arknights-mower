<script setup>
const doc_url = 'https://arkmowers.github.io/arknights-mower/'
</script>

<template>
  <iframe :src="doc_url" sandbox="allow-popups allow-scripts"></iframe>
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
