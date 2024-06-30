<template>
  <n-tr>
    <n-td colspan="6"><n-divider /></n-td>
  </n-tr>
  <n-tr v-for="(item, index) in props.childSkill" :key="index">
    <n-td
      v-if="index === 0"
      :rowspan="props.span"
      style="width: 5%; text-align: center; vertical-align: middle"
    >
      <div @click="openInNewTab()">
        <n-avatar lazy :src="`avatar/${props.avatar}.webp`" :size="100" round />
        <br />
        <n-button text tag="a" target="_blank" type="primary" v-text="props.avatar"> </n-button>
      </div>
    </n-td>
    <n-td style="width: 5%; text-align: center; vertical-align: middle">
      技能{{ item.skill_key }}
    </n-td>
    <n-td style="width: 5%; text-align: center; vertical-align: middle">
      {{ item.phase_level }}
    </n-td>
    <n-td style="width: 5%; text-align: center; vertical-align: middle">
      <n-tag :color="{ color: item.buffColor, textColor: item.textColor }">
        <template #avatar>
          <n-avatar
            :src="`building_skill/${item.skillIcon}.png`"
            round
            style="background-color: transparent"
          />
        </template>
        {{ item.skillname }}
      </n-tag>
    </n-td>
    <n-td style="width: 5%; text-align: center; vertical-align: middle">
      <n-tag :color="{ color: item.buffColor, textColor: item.textColor }" v-text="item.roomType"
    /></n-td>
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
import { ref, computed } from 'vue'
import { richText2HTML } from '@/stores/richText2HTML'
import buffer from '@/pages/buffer.json'

const props = defineProps({
  avatar: String,
  span: Number,
  childSkill: Array
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
