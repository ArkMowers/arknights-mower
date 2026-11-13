<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { resourceActivityBadges, resourceActivityHint } from '@/utils/versionBadges'

const props = defineProps({ metadata: Object })
const now = ref(Date.now())
const activities = computed(() => resourceActivityBadges(props.metadata, now.value))
let clock
let stopWatch

function stopClock() {
  clearInterval(clock)
  clock = undefined
}

onMounted(() => {
  stopWatch = watch(
    () => props.metadata,
    () => {
      stopClock()
      now.value = Date.now()
      if (activities.value.length) {
        clock = setInterval(() => {
          now.value = Date.now()
          if (!activities.value.length) stopClock()
        }, 60000)
      }
    },
    { immediate: true, deep: true }
  )
})
onUnmounted(() => {
  stopWatch?.()
  stopClock()
})
</script>

<template>
  <section v-if="activities.length" aria-label="活动时限">
    <div class="update-caption">未结束活动（作战时间）</div>
    <p v-for="activity in activities" :key="activity.name" class="activity-time">
      {{ resourceActivityHint(activity) }}
    </p>
  </section>
</template>

<style scoped>
.activity-time {
  margin: 8px 0;
  white-space: pre-line;
}
</style>
