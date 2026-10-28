<script setup>
import { i18n } from '@/i18n'
import { operatorDisplayName } from '@/i18n/gameNames'
import { baseSkillText, baseSkillProgression } from '@/i18n/baseSkills'
import { localizedBaseSkill } from '@/i18n/baseSkillDetails'
import { computed } from 'vue'
const { t } = i18n.global

import { richText2HTML } from '@/stores/richText2HTML'
import { useBasementSkill } from '@/stores/basementSkill'
import { ownershipLabels, skillStatusLabels, basementSkillTerms } from '@/utils/basementSkills'
import BufferInfo from '@/components/bufferinfo.vue'

const { buffer } = useBasementSkill()
defineOptions({ name: 'BasementSkillRows' })
const props = defineProps({ item: { type: Object, required: true } })
const displayedSkills = computed(() =>
  props.item.childSkill.map((skill) => localizedBaseSkill(props.item.avatar, skill))
)
const resourceBase = import.meta.env.BASE_URL
</script>

<template>
  <table
    class="operator-skills"
    :aria-label="t('baseSkills.operatorSkills', { operator: operatorDisplayName(item.avatar) })"
  >
    <colgroup>
      <col style="width: 86px" />
      <col style="width: 66px" />
      <col style="width: 78px" />
      <col style="width: 80px" />
      <col style="width: 186px" />
      <col style="width: 78px" />
      <col />
    </colgroup>
    <thead class="accessible-heading">
      <tr>
        <th>{{ t('baseSkills.operator') }}</th>
        <th>{{ t('baseSkills.skillNumber') }}</th>
        <th>{{ t('baseSkills.unlockCondition') }}</th>
        <th>{{ t('baseSkills.status') }}</th>
        <th>{{ t('baseSkills.skillName') }}</th>
        <th>{{ t('baseSkills.facility') }}</th>
        <th>{{ t('baseSkills.description') }}</th>
      </tr>
    </thead>
    <tbody>
      <tr
        v-for="(skill, index) in displayedSkills"
        :key="`${skill.skill_key}:${skill.skill_level}`"
        class="skill-row"
      >
        <td v-if="index === 0" :rowspan="item.childSkill.length" class="operator-cell">
          <a
            :href="`https://prts.wiki/w/${encodeURIComponent(item.avatar)}`"
            target="_blank"
            rel="noopener noreferrer"
            class="operator-link"
          >
            <n-avatar
              :src="`${resourceBase}avatar/${encodeURIComponent(item.avatar)}.webp`"
              :size="40"
              round
              :img-props="{ alt: operatorDisplayName(item.avatar) }"
            >
              <template #fallback>{{ operatorDisplayName(item.avatar).slice(0, 1) }}</template>
            </n-avatar>
            <span>{{ operatorDisplayName(item.avatar) }}</span>
          </a>
          <n-tag
            v-if="ownershipLabels[item.ownership]"
            :type="item.ownership === 'owned' ? 'success' : 'default'"
            :bordered="false"
            size="small"
            >{{ baseSkillText(ownershipLabels[item.ownership]) }}</n-tag
          >
          <div v-if="item.progression" class="operator-growth">
            {{ baseSkillProgression(item.progression) }}
          </div>
        </td>
        <td
          class="skill-number"
          :class="{ 'skill-unavailable': ['locked', 'unowned'].includes(skill.status) }"
        >
          {{ t('baseSkills.skill') }} {{ skill.skill_key + 1 }}
        </td>
        <td class="skill-condition">{{ baseSkillProgression(skill.phase_level) }}</td>
        <td class="skill-status">
          <n-tag
            v-if="skillStatusLabels[skill.status]"
            :type="skill.status === 'active' ? 'success' : 'default'"
            :bordered="false"
            size="small"
            >{{ baseSkillText(skillStatusLabels[skill.status]) }}</n-tag
          >
        </td>
        <td
          class="skill-name"
          :class="{ 'skill-unavailable': ['locked', 'unowned'].includes(skill.status) }"
        >
          <n-tag :bordered="false" :color="{ color: skill.buffColor, textColor: skill.textColor }">
            <template #avatar>
              <n-avatar
                :src="`${resourceBase}building_skill/${encodeURIComponent(skill.skillIcon)}.webp`"
                :size="22"
                round
                style="background-color: transparent"
                aria-hidden="true"
              />
            </template>
            {{ skill.skillname }}
          </n-tag>
        </td>
        <td class="skill-facility">{{ baseSkillText(skill.roomType) }}</td>
        <td
          class="skill-description"
          :class="{ 'skill-unavailable': ['locked', 'unowned'].includes(skill.status) }"
        >
          <BufferInfo
            :des="richText2HTML(skill.des)"
            :isbuffer="skill.buffer"
            :buffer="basementSkillTerms(skill.buffer_des, buffer)"
          />
        </td>
      </tr>
    </tbody>
  </table>
</template>

<style scoped>
.operator-skills {
  width: 100%;
  table-layout: fixed;
  border-collapse: collapse;
  font-size: 13px;
}
.accessible-heading {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
}
td {
  padding: 10px 6px;
  text-align: center;
  vertical-align: middle;
  border-bottom: 1px solid var(--mower-border);
}
.operator-link {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  padding: 4px 0;
  color: var(--mower-primary);
  text-decoration: none;
}
.operator-link:hover span {
  text-decoration: underline;
}
.operator-link :deep(.n-avatar) {
  outline: 1px solid rgb(0 0 0 / 10%);
  outline-offset: -1px;
}
:global(.provider--dark) .operator-link :deep(.n-avatar) {
  outline-color: rgb(255 255 255 / 10%);
}
.operator-growth {
  margin-top: 4px;
  font-size: 12px;
  color: var(--mower-text-muted);
}
.skill-name :deep(.n-tag) {
  max-width: 100%;
  height: auto;
  min-height: 28px;
  padding: 3px 7px;
  text-align: left;
  white-space: normal;
  line-height: 1.4;
}
.skill-name :deep(.n-tag__avatar) {
  margin-right: 5px;
  flex-shrink: 0;
}
.skill-name :deep(.n-tag__content) {
  min-width: 0;
  white-space: normal;
}
.skill-number,
.skill-condition,
.skill-facility {
  font-size: 12px;
  color: var(--mower-text-muted);
}
.skill-description {
  padding: 10px;
  text-align: left;
  line-height: 1.7;
  text-wrap: pretty;
}
.skill-unavailable {
  opacity: 0.65;
}
.skill-description :deep(.riic-term) {
  text-decoration: underline dotted;
  text-underline-offset: 3px;
  cursor: pointer;
}
@media (max-width: 900px) {
  .operator-skills,
  tbody {
    display: block;
  }
  colgroup {
    display: none;
  }
  .operator-skills {
    margin-bottom: 12px;
    border-bottom: 1px solid var(--mower-border);
  }
  .skill-row {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 6px 8px;
    padding: 10px 0;
    border-top: 1px solid var(--mower-border);
  }
  td {
    display: block;
    padding: 0;
    border: 0;
  }
  .operator-cell {
    display: flex;
    align-items: center;
    gap: 10px;
    width: 100%;
    padding-bottom: 6px;
  }
  .operator-link {
    flex-direction: row;
    gap: 8px;
    padding: 0;
  }
  .operator-growth {
    margin: 0;
  }
  .skill-name {
    order: 1;
  }
  .skill-facility {
    order: 2;
  }
  .skill-condition {
    order: 3;
  }
  .skill-number {
    order: 4;
  }
  .skill-status {
    order: 5;
  }
  .skill-description {
    order: 6;
    width: 100%;
    padding: 2px 0 0;
  }
}
</style>
