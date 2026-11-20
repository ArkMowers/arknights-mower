<script setup>
import sanityLines from '@/assets/sanity-lines.png'

// The mask keeps the linework from arknights_mower/resources/sanity.png.
const mask = `url("${sanityLines}") center / 96% auto no-repeat`
</script>

<template>
  <svg
    xmlns="http://www.w3.org/2000/svg"
    viewBox="0 0 24 24"
    :style="{ WebkitMask: mask, mask }"
    aria-hidden="true"
    focusable="false"
  >
    <rect width="24" height="24" fill="currentColor" />
  </svg>
</template>
