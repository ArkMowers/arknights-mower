<script setup>
import { computed } from 'vue'
import { NTag, NTooltip } from 'naive-ui'
import { getOperatorSkillDetails } from '@/utils/operatorSkillTooltip'
import { useBasementSkill } from '@/stores/basementSkill'
import { ownershipLabels, skillStatusLabels } from '@/utils/basementSkills'

const props = defineProps({ name: String })
const details = computed(() => getOperatorSkillDetails(props.name))
const { loadOwnedOperators } = useBasementSkill()

async function loadOwnership(show) {
  if (!show) return
  try {
    await loadOwnedOperators()
  } catch {
    // 读取失败时保留已有快照，仍可查看技能说明。
  }
}
</script>

<template>
  <NTooltip
    v-if="details.skills.length"
    trigger="hover"
    placement="right"
    :delay="350"
    :keep-alive-on-hover="true"
    @update:show="loadOwnership"
  >
    <template #trigger><slot /></template>
    <div class="operator-skill-tooltip">
      <div class="skill-heading">
        <strong>{{ name }} · 基建技能</strong>
        <NTag
          v-if="ownershipLabels[details.ownership]"
          :type="details.ownership === 'owned' ? 'success' : 'default'"
          :bordered="false"
          size="small"
          >{{ ownershipLabels[details.ownership] }}</NTag
        >
        <span v-if="details.progression" class="skill-unlock">{{ details.progression }}</span>
      </div>
      <section v-for="(skill, index) in details.skills" :key="index">
        <div class="skill-heading">
          <span>{{ skill.name }}</span>
          <NTag
            v-if="skillStatusLabels[skill.status]"
            :type="skill.status === 'active' ? 'success' : 'default'"
            :bordered="false"
            size="small"
            >{{ skillStatusLabels[skill.status] }}</NTag
          >
        </div>
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
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
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
