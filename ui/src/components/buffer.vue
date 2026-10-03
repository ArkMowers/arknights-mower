<template>
  <n-tr>
    <n-td colspan="7"></n-td>
  </n-tr>
  <n-tr
    v-for="(item, index) in props.childSkill"
    :key="`${item.skill_key}:${item.skill_level}`"
    :class="{ 'skill-unavailable': item.status === 'locked' || item.status === 'unowned' }"
  >
    <n-td
      v-if="index === 0"
      :rowspan="props.span"
      style="width: 5%; text-align: center; vertical-align: middle"
    >
      <div @click="openInNewTab()">
        <n-avatar lazy :src="`avatar/${props.avatar}.webp`" :size="40" round />
        <br />
        <n-button text tag="a" target="_blank" type="primary">{{ props.avatar }}</n-button>
      </div>
      <n-tag
        v-if="ownershipLabels[props.ownership]"
        :type="props.ownership === 'owned' ? 'success' : 'default'"
        size="small"
      >
        {{ ownershipLabels[props.ownership] }}
      </n-tag>
      <div v-if="props.progression" class="skill-progression">{{ props.progression }}</div>
    </n-td>
    <n-td style="width: 7%; text-align: center; vertical-align: middle">
      第 {{ item.skill_key + 1 }} 个技能
    </n-td>
    <n-td style="width: 5%; text-align: center; vertical-align: middle">
      {{ item.phase_level }}
    </n-td>
    <n-td style="text-align: center; vertical-align: middle">
      <n-tag
        v-if="skillStatusLabels[item.status]"
        :type="item.status === 'active' ? 'success' : 'default'"
        size="small"
      >
        {{ skillStatusLabels[item.status] }}
      </n-tag>
    </n-td>
    <n-td style="width: 5%; text-align: center; vertical-align: middle">
      <n-tag :color="{ color: item.buffColor, textColor: item.textColor }">
        <template #avatar>
          <n-avatar
            :src="`building_skill/${item.skillIcon}.webp`"
            round
            style="background-color: transparent"
          />
        </template>
        {{ item.skillname }}
      </n-tag>
    </n-td>
    <n-td style="width: 5%; text-align: center; vertical-align: middle">
      <n-tag :color="{ color: item.buffColor, textColor: item.textColor }">
        {{ item.roomType }}
      </n-tag>
    </n-td>
    <n-td>
      <bufferinfo
        :des="richText2HTML(item.des)"
        :isbuffer="item.buffer"
        :buffer="extendedBufferDes(item.buffer_des, buffer)"
      ></bufferinfo>
    </n-td>
  </n-tr>
</template>

<script setup>
import { richText2HTML } from '@/stores/richText2HTML'
import { useBasementSkill } from '@/stores/basementSkill'
import { ownershipLabels, skillStatusLabels } from '@/utils/basementSkills'

const { buffer } = useBasementSkill()
defineOptions({ name: 'BasementSkillRows' })

const props = defineProps({
  avatar: String,
  span: Number,
  childSkill: Array,
  ownership: String,
  progression: String
})
const openInNewTab = () => {
  window.open(`https://prts.wiki/w/${props.avatar}`, '_blank')
}
const extendedBufferDes = (bufferDes, buffer) => {
  let result = [...bufferDes]
  let temp = []
  bufferDes.forEach((thing) => {
    temp = buffer[thing]['buffer']
  })

  return result.concat(temp)
}
</script>

<style>
.skill-unavailable {
  opacity: 0.65;
}

.skill-progression {
  margin-top: 4px;
  font-size: 12px;
}

.cc-vup {
  color: #0098dc;
}

.cc-vdown {
  color: #ff6237;
}

.cc-rem {
  color: #f49800;
}

.cc-kw {
  color: #00b0ff;
}
.riic-term {
  text-decoration: underline;
}
</style>
