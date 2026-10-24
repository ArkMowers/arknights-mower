<template>
  <div class="page-header">
    <h1 class="page-header__title">
      <slot />
    </h1>
    <div v-if="$slots.actions" class="page-header__actions">
      <slot name="actions" />
    </div>
  </div>
</template>

<script setup>
defineOptions({ name: 'PageHeader' })
</script>

<style scoped>
.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
  width: 100%;
}

.page-header__title {
  flex: 1 1 auto;
  margin: 0;
  font-size: 24px;
  font-weight: 600;
  line-height: 1.3;
  color: inherit;
}

.page-header__actions {
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  gap: 8px;
}

@media (max-width: 640px) {
  .page-header__title {
    font-size: 20px;
  }

  .page-header__actions {
    width: 100%;
    justify-content: flex-start;
  }
}
</style>
