<script setup>
import { ref, onMounted, watch } from 'vue'
import { SlickList, SlickItem } from 'vue-slicksort'
import event_json from './stage_data/event_data.json'
const event_list = ref([])
event_list.value = event_json

watch(
  () => event_list.value,
  (newValue, oldValue) => {
    event_list.value = event_json
  }
)

const weekly_result = ref({
  星期1: ref([]),
  星期2: ref([]),
  星期3: ref([]),
  星期4: ref([]),
  星期5: ref([]),
  星期6: ref([]),
  星期7: ref([])
})
const deleteResult = (key) => {
  weekly_result.value[key] = []
}
</script>
<template>
  <n-grid x-gap="150" class="unselectable">
    <n-gi style="width: 300px">
      <n-card class="card_out">
        关卡<n-button @click="deleteResult(day)">重选</n-button>
        <SlickList axis="y" v-model:list="event_list" group="123">
          <SlickItem v-for="(event, i) in event_list" :key="event" :index="i">
            <n-card class="card_in">
              {{ event['id'] }}
            </n-card>
          </SlickItem>
        </SlickList>
      </n-card>
    </n-gi>
    <n-gi style="width: 300px" v-for="(result, day) in weekly_result" :key="day">
      <n-card class="card_out">
        {{ day }}
        <n-button @click="deleteResult(day)">重选</n-button>
        <SlickList axis="y" v-model:list="weekly_result[day]" group="123">
          <SlickItem v-for="(event, i) in weekly_result[day]" :key="event" :index="i">
            <n-card class="card_in">
              {{ event['id'] }}
            </n-card>
          </SlickItem>
        </SlickList>
      </n-card>
    </n-gi>
  </n-grid>
</template>
<style>
.unselectable {
  user-select: none;
  /* Standard syntax */
}

.card_out {
  width: 150px;
}

.card_in {
  width: 100px;
}
</style>
