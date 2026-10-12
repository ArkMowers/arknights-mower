<script setup>
import { computed } from 'vue'
import { NTooltip } from 'naive-ui'
import { getOperatorSkillDetails } from '@/utils/operatorSkillTooltip'

const props = defineProps({ name: String })
const skills = computed(() => getOperatorSkillDetails(props.name))
</script>

<template>
  <NTooltip
    v-if="skills.length"
    trigger="hover"
    placement="right"
    :delay="350"
    :keep-alive-on-hover="true"
  >
    <template #trigger><slot /></template>
    <div class="operator-skill-tooltip">
      <strong>{{ name }} · 基建技能</strong>
      <section v-for="(skill, index) in skills" :key="index">
        <div class="skill-heading">{{ skill.name }}</div>
        <div class="skill-unlock">{{ skill.facility }} · {{ skill.unlock }}</div>
        <p>{{ skill.description }}</p>
      </section>
    </div>
  </NTooltip>
  <slot v-else />
</template>

<style scoped>
.operator-skill-tooltip {
  width: 380px;
  max-width: calc(100vw - 40px);
  max-height: min(60vh, 480px);
  overflow-y: auto;
  line-height: 1.6;
}
section {
  margin-top: 12px;
}
.skill-heading {
  font-weight: 600;
}
.skill-unlock {
  opacity: 0.7;
  font-size: 12px;
}
p {
  margin: 4px 0 0;
}
</style>
