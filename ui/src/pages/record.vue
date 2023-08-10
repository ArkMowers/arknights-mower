<template>
    <div>
        <h1 class="page-title">一周内干员心情变化曲线报表</h1>
    </div>
    <div class="report-container">
        <div v-for="(groupData, index) in reportData" :key="index" class="report-card">
            <h2>{{ groupData.groupName }}</h2>
            <Line :data="groupData.moodData" :options="chartOptions" />
        </div>
    </div>
</template>

<script setup>
import {ref,onMounted   } from 'vue';
import {Line} from 'vue-chartjs'
import 'chartjs-adapter-luxon';
import {useRecordStore} from '@/stores/record'
import {CategoryScale,TimeScale,TimeSeriesScale, Chart as ChartJS, Legend, LinearScale,Colors, LineElement, PointElement, Title, Tooltip} from 'chart.js'
const recordStore = useRecordStore()
const {
    getMoodRatios
} = recordStore

ChartJS.register(
    CategoryScale,
    LinearScale,
    TimeScale,
    TimeSeriesScale,
    PointElement,
    LineElement,
    Title,
    Tooltip,
    Legend,
    Colors
)
// Mock report data
const reportData = ref([])
onMounted(async () => {
    reportData.value = await getMoodRatios();
});

// Chart.js options
const chartOptions = ref({
    responsive: true,
    maintainAspectRatio: false,
    scales: {
        x: {
            autoSkip:true,
            type:'time',
            time: {
                unit: 'day'
            }

        },
        y: {
            beginAtZero: true,
            ticks: {
                min: 0,
                max: 24,
                stepSize:4
            }
        },
    },
});

</script>

<style scoped>
.report-container {
    display: flex;
    flex-wrap: wrap;
    gap: 20px;
}

.report-card {
    width: 300px;
    height: 200px;
    padding: 20px 20px 100px 20px;
    border: 1px solid #ccc;
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
}

h2 {
    margin-bottom: 10px;
    font-size: 1.2rem;
    text-align: center;
}

.page-title {
    text-align: center;
    font-size: 24px;
    margin-bottom: 20px;
}
</style>
