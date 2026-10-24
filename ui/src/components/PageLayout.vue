<template>
  <div class="page">
    <div class="page__inner">
      <header v-if="$slots.header" class="page__header">
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
