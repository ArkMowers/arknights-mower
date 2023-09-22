<script setup>
const doc_url = 'https://arkmowers.github.io/arknights-mower/'
</script>

<template>
  <iframe :src="doc_url" sandbox="allow-popups allow-scripts allow-same-origin"
    style="width: 100%; height: calc(var(--vh, 1vh) * 100);" />
</template>

<style scoped>
iframe {
  flex-grow: 1;
  border: none;
}
</style>
