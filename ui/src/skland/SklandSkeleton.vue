<template>
  <div class="skland-panel skeleton" aria-hidden="true">
    <span class="skeleton__heading"></span>
    <div class="skeleton__layout">
      <div class="skeleton__days">
        <span v-for="day in 35" :key="day"></span>
      </div>
      <span class="skeleton__detail"></span>
    </div>
  </div>
</template>

<style scoped>
.skeleton__heading,
.skeleton__days span,
.skeleton__detail {
  display: block;
  background: var(--mower-control-surface);
  border-radius: 8px;
}
.skeleton__heading {
  width: 210px;
  height: 28px;
  margin-bottom: 34px;
}
.skeleton__layout {
  display: grid;
  grid-template-columns: minmax(0, 2.35fr) minmax(305px, 1fr);
  gap: 18px;
}
.skeleton__days {
  container-type: inline-size;
  display: grid;
  grid-template-columns: repeat(7, minmax(0, 1fr));
  gap: 6px;
}
.skeleton__days span {
  height: clamp(56px, 12cqi, 99px);
}
@container main-content (max-width: 740px) {
  .skeleton__layout {
    grid-template-columns: minmax(0, 1fr);
  }
  .skeleton__detail {
    min-height: 85px;
  }
}
@container main-content (max-width: 480px) {
  .skeleton__days {
    gap: 3px;
  }
}
</style>
