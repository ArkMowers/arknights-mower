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
  <n-flex>
    <div>
      <n-thing>
        <n-button>关卡</n-button>
        <SlickList axis="y" v-model:list="event_list" group="123">
          <SlickItem v-for="(event, i) in event_list" :key="event" :index="i">
            <n-list bordered hoverable clickable>
              <n-list-item> {{ event['id'] }} {{ event['name'] }} </n-list-item>
            </n-list>
          </SlickItem>
        </SlickList>
      </n-thing>
    </div>

    <div v-for="(result, day) in weekly_result" :key="day">
      <n-thing class="card_out">
        <n-button @click="deleteResult(day)">{{ day }} 重选</n-button>
        <SlickList axis="y" v-model:list="weekly_result[day]" group="123">
          <SlickItem v-for="(event, i) in weekly_result[day]" :key="event" :index="i">
            <n-list bordered hoverable clickable>
              <n-list-item> {{ event['id'] }} {{ event['name'] }} </n-list-item>
            </n-list>
          </SlickItem>
        </SlickList>
        {{ weekly_result[day] }}
      </n-thing>
    </div>
  </n-flex>
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
