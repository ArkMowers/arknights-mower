<template>
  <div class="page" :class="{ 'page--fill': fill }">
    <div class="page__inner">
      <header v-if="$slots.header && !fill" class="page__header">
        <slot name="header" />
      </header>
      <div class="page__content">
        <slot />
      </div>
    </div>
  </div>
</template>

<script setup>
defineOptions({ name: 'PageLayout' })

defineProps({
  maxWidth: {
    type: String,
    default: '1200px'
  },
  // 填满内容区：去掉页头与外层留白，由页面自己管理内部滚动（股票模式等沉浸式页面）。
  fill: {
    type: Boolean,
    default: false
  }
})
</script>

<style scoped>
.page {
  display: flex;
  flex-direction: column;
  width: 100%;
  height: 100%;
  overflow-y: auto;
  overflow-x: hidden;
}

/* 填满模式：页面铺满内容区且自身不滚动，滚动交给页面内部的面板。 */
.page--fill {
  overflow: hidden;
}

.page--fill .page__inner {
  display: flex;
  flex-direction: column;
  max-width: none;
  height: 100%;
  padding: 0;
}

.page--fill .page__content {
  flex: 1 1 auto;
  gap: 0;
  min-height: 0;
}

.page__inner {
  flex: 1 1 auto;
  width: 100%;
  max-width: v-bind(maxWidth);
  margin: 0 auto;
  padding: 12px;
  box-sizing: border-box;
}

.page__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}

.page__content {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-height: 0;
}

@media (max-width: 640px) {
  .page__inner {
    padding: 8px;
  }

  .page__header {
    margin-bottom: 12px;
    gap: 12px;
  }

  .page__content {
    gap: 8px;
  }
}
</style>
