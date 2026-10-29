<script setup>
import shamareFeast from '@/assets/halloween/shamare-feast.png'

defineProps({
  sidebarWidth: { type: Number, default: 210 },
  headerHeight: { type: Number, default: 36 },
  nativeHeader: { type: Boolean, default: false }
})
</script>

<template>
  <div
    class="halloween-backdrop"
    :class="{ 'halloween-backdrop--no-sidebar': sidebarWidth === 0 }"
    :style="{
      '--halloween-sidebar-width': `${sidebarWidth}px`,
      '--halloween-header-height': nativeHeader
        ? `calc(${headerHeight}px * var(--mower-zoom-inverse, 1))`
        : `${headerHeight}px`
    }"
    aria-hidden="true"
  >
    <div class="halloween-backdrop__wallpaper">
      <div
        class="halloween-backdrop__portrait"
        :style="{ backgroundImage: 'url(' + JSON.stringify(shamareFeast) + ')' }"
      />
      <div class="halloween-backdrop__engraving" />
    </div>
    <div v-if="headerHeight" class="halloween-backdrop__canopy" />
  </div>
</template>

<style scoped>
.halloween-backdrop {
  position: absolute;
  z-index: -1;
  inset: 0;
  overflow: hidden;
  pointer-events: none;
  user-select: none;
  background:
    radial-gradient(ellipse 420px 380px at 0 0, #e7c39554, transparent),
    radial-gradient(ellipse 680px 220px at 85% 0, #d5bda42b, transparent), #f7f2ea;
}
.halloween-backdrop__wallpaper {
  position: absolute;
  top: var(--halloween-header-height);
  bottom: 0;
  left: 0;
  width: calc(var(--halloween-sidebar-width) + 52px);
  mask-image: linear-gradient(
    90deg,
    #000 0,
    #000 calc(var(--halloween-sidebar-width) - 94px),
    transparent calc(var(--halloween-sidebar-width) + 32px)
  );
}
.halloween-backdrop--no-sidebar .halloween-backdrop__wallpaper {
  display: none;
}
.halloween-backdrop__portrait {
  position: absolute;
  bottom: 142px;
  left: calc(var(--halloween-sidebar-width) - 260px);
  width: 350px;
  height: 350px;
  object-fit: contain;
  background-size: contain;
  background-position: center;
  background-repeat: no-repeat;
  opacity: 0.12;
  mask-image: linear-gradient(180deg, transparent, #000 18%, #000 80%, transparent);
}
.halloween-backdrop__engraving {
  position: absolute;
  inset: 0;
  background: url('../assets/halloween/gothic-sidebar.svg') left top /
    var(--halloween-sidebar-width) 100% no-repeat;
  opacity: 0.76;
}
.halloween-backdrop__canopy {
  position: absolute;
  inset: 0 0 auto;
  height: calc(var(--halloween-header-height) + 32px);
  background: url('../assets/halloween/gothic-titlebar.svg') left top / 100% 62px no-repeat;
  mask-image: linear-gradient(180deg, #000 0, #000 12px, transparent 66px);
  opacity: 0.8;
}
:global(html[data-mower-theme='dark'] .halloween-backdrop) {
  background:
    radial-gradient(ellipse 440px 420px at 0 0, #73547844, transparent),
    radial-gradient(ellipse 680px 220px at 85% 0, #a4785324, transparent), #211f29;
}
:global(html[data-mower-theme='dark'] .halloween-backdrop__portrait) {
  opacity: 0.2;
}
@media (prefers-contrast: more) {
  .halloween-backdrop__wallpaper,
  .halloween-backdrop__canopy {
    display: none;
  }
}
</style>
